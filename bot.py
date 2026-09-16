import os
import time
import threading
import sqlite3
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify
from google import genai
from google.genai import types


# ============================================================
# SETTINGS
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not configured.")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not configured.")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
TELEGRAM_FILE_API = f"https://api.telegram.org/file/bot{BOT_TOKEN}"

MODEL = "gemini-2.5-flash-lite"
PORT = int(os.getenv("PORT", "10000"))

client = genai.Client(api_key=GEMINI_API_KEY)


# ============================================================
# WEB SERVER
# ============================================================

app = Flask(__name__)


@app.get("/")
def home():
    return "Math + Physics AI Tutor is running."


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/healthz")
def healthz():
    return jsonify({"status": "ok"})


# ============================================================
# DATABASE
# ============================================================

DB_FILE = "tutor.db"
db_lock = threading.Lock()

db = sqlite3.connect(
    DB_FILE,
    check_same_thread=False
)

db.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    context TEXT DEFAULT ''
)
""")

db.commit()


def get_context(user_id):
    with db_lock:
        row = db.execute(
            "SELECT context FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if row:
            return row[0] or ""

        db.execute(
            "INSERT INTO users (user_id, context) VALUES (?, ?)",
            (user_id, "")
        )

        db.commit()

        return ""


def save_context(user_id, context):
    # Prevent context from growing forever.
    context = context[-16000:]

    with db_lock:
        db.execute(
            """
            INSERT INTO users (user_id, context)
            VALUES (?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET context = excluded.context
            """,
            (user_id, context)
        )

        db.commit()


def clear_context(user_id):
    with db_lock:
        db.execute(
            "DELETE FROM users WHERE user_id = ?",
            (user_id,)
        )

        db.commit()


# ============================================================
# TELEGRAM API
# ============================================================

def telegram_request(method, data=None, timeout=60):
    response = requests.post(
        f"{TELEGRAM_API}/{method}",
        data=data or {},
        timeout=timeout
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(
            result.get("description", "Telegram API error")
        )

    return result.get("result")


def send_message(chat_id, text):
    # Telegram has a message length limit.
    max_length = 4000

    if not text:
        return

    for start in range(0, len(text), max_length):
        telegram_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text[start:start + max_length]
            },
            timeout=30
        )


def send_typing(chat_id):
    try:
        telegram_request(
            "sendChatAction",
            {
                "chat_id": chat_id,
                "action": "typing"
            },
            timeout=15
        )
    except Exception:
        pass


# ============================================================
# GEMINI INSTRUCTIONS
# ============================================================

SYSTEM_PROMPT = """
You are a Math and Physics AI Tutor for a Myanmar student.

Always answer in simple, natural Burmese.

Your main job is to:
- Read Math and Physics questions.
- Solve them accurately.
- Explain them step by step.
- Use easy methods suitable for a school student.
- Explain WHY important steps are performed.
- Check calculations before giving the final answer.

MATH:
Show the important algebra and calculation steps clearly.

PHYSICS:
Use this structure when appropriate:

Given:
Required:
Formula:
Substitution:
Calculation:
Answer:

IMAGE QUESTIONS:
Carefully read all visible numbers, symbols, units and words.
Never guess a number or symbol that cannot be read.
If the image is genuinely unclear, ask for a clearer/full image.

If multiple questions are visible and it is unclear which one the student wants,
ask which question they want.

FOLLOW-UP:
Remember the current problem and understand questions such as:
"ဒီအဆင့်ကို ဘာလို့လုပ်တာလဲ?"
"ဒီ 2 က ဘယ်ကရတာလဲ?"
"အဖြေက ဘယ်လောက်လဲ?"
"နောက်တစ်နည်းနဲ့တွက်ပြ"

If the student says they do not understand:
Explain the difficult part again using smaller steps and simple Burmese.

If the student asks for another method:
Solve the same problem using another valid method.

After solving a problem, normally ask:
"နားလည်သွားပြီလား? 😊"
"""


# ============================================================
# TEXT QUESTION
# ============================================================

def solve_text(user_id, text):
    previous_context = get_context(user_id)

    prompt = SYSTEM_PROMPT

    if previous_context:
        prompt += """

Previous conversation:
--------------------
""" + previous_context + """
--------------------
"""

    prompt += """

Student's new message:
""" + text

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt
    )

    answer = getattr(response, "text", None)

    if not answer:
        raise RuntimeError("Gemini returned an empty response.")

    updated_context = (
        previous_context
        + "\nStudent: "
        + text
        + "\nTutor: "
        + answer
    )

    save_context(user_id, updated_context)

    return answer


# ============================================================
# TELEGRAM PHOTO DOWNLOAD
# ============================================================

def download_photo(photo):
    file_info = telegram_request(
        "getFile",
        {
            "file_id": photo["file_id"]
        },
        timeout=30
    )

    file_path = file_info.get("file_path")

    if not file_path:
        raise RuntimeError("Telegram file path is missing.")

    response = requests.get(
        f"{TELEGRAM_FILE_API}/{file_path}",
        timeout=60
    )

    response.raise_for_status()

    if not response.content:
        raise RuntimeError("Image download returned empty data.")

    return response.content


def get_best_photo(photo_list):
    if not photo_list:
        return None

    # Telegram normally gives photo sizes from smallest to largest.
    return photo_list[-1]


# ============================================================
# IMAGE QUESTION
# ============================================================

def solve_image(user_id, image_bytes, caption=""):
    previous_context = get_context(user_id)

    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type="image/jpeg"
    )

    prompt = SYSTEM_PROMPT + """

The student has sent an image of a Math or Physics problem.

Read the image carefully.

First understand the exact question.
Then solve it.

Do not guess unclear mathematical symbols, numbers, units or words.
If something essential cannot be read, clearly tell the student what is unclear.

"""

    if caption:
        prompt += """

The student also wrote this caption:
""" + caption

    if previous_context:
        prompt += """

Previous conversation context:
--------------------
""" + previous_context + """
--------------------
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            image_part,
            prompt
        ]
    )

    answer = getattr(response, "text", None)

    if not answer:
        raise RuntimeError("Gemini returned an empty image response.")

    updated_context = (
        previous_context
        + "\nStudent sent a Math/Physics image."
        + ("\nCaption: " + caption if caption else "")
        + "\nTutor: "
        + answer
    )

    save_context(user_id, updated_context)

    return answer


# ============================================================
# /START
# ============================================================

def handle_start(chat_id, user_id):
    clear_context(user_id)

    message = """မင်္ဂလာပါ 👋

ကျွန်တော်က Math နဲ့ Physics ပုစ္ဆာတွေကို ကူညီဖြေရှင်းပေးမယ့် AI Tutor ပါ။ 🧮📚

မသိတဲ့ပုစ္ဆာရှိရင် ပုံရိုက်ပြီး ပို့လိုက်ပါ။
ပုံထဲက ပုစ္ဆာကို ဖတ်ပြီး အဆင့်လိုက်၊ နားလည်လွယ်အောင် မြန်မာလို ရှင်းပြပြီး တွက်ပေးပါမယ်။ 😊

စာနဲ့ရိုက်ပြီး မေးလည်း ရပါတယ်။

📷 ပုံနဲ့ပုစ္ဆာ မေးနိုင်ပါတယ်။
📝 စာနဲ့လည်း မေးနိုင်ပါတယ်။"""

    send_message(chat_id, message)


# ============================================================
# TEXT HANDLER
# ============================================================

def handle_text(chat_id, user_id, text):
    send_typing(chat_id)

    try:
        answer = solve_text(
            user_id,
            text
        )

        send_message(
            chat_id,
            answer
        )

    except Exception as error:
        print(
            "Text solving error:",
            type(error).__name__,
            str(error)
        )

        send_message(
            chat_id,
            "AI Tutor ကို ခဏချိတ်ဆက်မရသေးပါဘူး။ ခဏနေရင် ပြန်မေးပေးပါနော်။ 🙏"
        )


# ============================================================
# PHOTO HANDLER
# ============================================================

def handle_photo(chat_id, user_id, message):
    photo = get_best_photo(
        message.get("photo", [])
    )

    if not photo:
        send_message(
            chat_id,
            "ပုံကို မရရှိသေးပါဘူး။ ပြန်ပို့ပေးပါနော်။ 🙏"
        )
        return

    send_typing(chat_id)

    try:
        image_bytes = download_photo(photo)

        caption = (
            message.get("caption", "").strip()
        )

        answer = solve_image(
            user_id,
            image_bytes,
            caption
        )

        send_message(
            chat_id,
            answer
        )

    except Exception as error:
        print(
            "Image solving error:",
            type(error).__name__,
            str(error)
        )

        send_message(
            chat_id,
            """ပုံကိုဖတ်ပြီး ဖြေရှင်းရာမှာ အခက်အခဲဖြစ်နေပါတယ်။ 🙏

ပုံက ရှင်းပြီး ပုစ္ဆာတစ်ခုလုံး ပါနေရင် ပြန်ပို့ပြီး စမ်းကြည့်ပေးပါနော်။"""
        )


# ============================================================
# TELEGRAM UPDATE
# ============================================================

def process_update(update):
    message = update.get("message")

    if not message:
        return

    chat = message.get("chat")
    sender = message.get("from")

    if not chat or not sender:
        return

    chat_id = chat.get("id")
    user_id = sender.get("id")

    if not chat_id or not user_id:
        return

    # TEXT
    if message.get("text"):
        text = message["text"].strip()

        if text == "/start":
            handle_start(
                chat_id,
                user_id
            )
        else:
            handle_text(
                chat_id,
                user_id,
                text
            )

    # PHOTO
    elif message.get("photo"):
        handle_photo(
            chat_id,
            user_id,
            message
        )


# ============================================================
# TELEGRAM LONG POLLING
# ============================================================

def telegram_polling():
    offset = None

    print("Telegram bot polling started.")

    while True:
        try:
            params = {
                "timeout": 30,
                "allowed_updates": '["message"]'
            }

            if offset is not None:
                params["offset"] = offset

            response = requests.get(
                f"{TELEGRAM_API}/getUpdates",
                params=params,
                timeout=45
            )

            response.raise_for_status()

            data = response.json()

            if not data.get("ok"):
                raise RuntimeError(
                    data.get(
                        "description",
                        "Telegram polling failed."
                    )
                )

            updates = data.get(
                "result",
                []
            )

            for update in updates:
                offset = update["update_id"] + 1

                try:
                    process_update(update)

                except Exception as error:
                    print(
                        "Update error:",
                        type(error).__name__,
                        str(error)
                    )

        except Exception as error:
            print(
                "Polling error:",
                type(error).__name__,
                str(error)
            )

            time.sleep(5)


# ============================================================
# START SERVER + BOT
# ============================================================

if __name__ == "__main__":

    polling_thread = threading.Thread(
        target=telegram_polling,
        daemon=True
    )

    polling_thread.start()

    print(
        "Starting web server on port",
        PORT
    )

    app.run(
        host="0.0.0.0",
        port=PORT
    )
