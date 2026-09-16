import os
import time
import base64
import sqlite3
import threading
import requests

from flask import Flask, jsonify


# =========================
# SETTINGS
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MODEL = "gpt-5.6-luna"

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
OPENAI_API = "https://api.openai.com/v1/responses"

app = Flask(__name__)


# =========================
# DATABASE
# =========================

DB_FILE = "tutor.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS context (
            user_id INTEGER PRIMARY KEY,
            messages TEXT
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================
# TELEGRAM
# =========================

def send_message(chat_id, text):
    try:
        response = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text
            },
            timeout=30
        )

        if not response.ok:
            print(
                "Telegram send error:",
                response.status_code,
                response.text
            )

    except Exception as e:
        print(
            "Telegram send exception:",
            type(e).__name__,
            str(e)
        )


def get_updates(offset=None):

    params = {
        "timeout": 30
    }

    if offset is not None:
        params["offset"] = offset

    response = requests.get(
        f"{TELEGRAM_API}/getUpdates",
        params=params,
        timeout=40
    )

    response.raise_for_status()

    return response.json()


def get_file(file_id):

    response = requests.get(
        f"{TELEGRAM_API}/getFile",
        params={
            "file_id": file_id
        },
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        raise Exception(
            "Telegram file error: "
            + str(data)
        )

    return data["result"]["file_path"]


def download_telegram_file(file_path):

    response = requests.get(
        f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}",
        timeout=60
    )

    response.raise_for_status()

    return response.content


# =========================
# OPENAI
# =========================

SYSTEM_PROMPT = """
You are a Math and Physics AI Tutor for a Myanmar student.

Always explain in simple Burmese.

For Math:
- Read the question carefully.
- Show the calculation step by step.
- Explain important steps clearly.
- Do not skip important algebra steps.
- Give the final answer clearly.

For Physics use exactly this structure when appropriate:

Given:
Required:
Formula:
Substitution:
Calculation:
Answer:

If the student asks:
"ဘာလို့ဒီအဆင့်လုပ်တာလဲ?"
or
"ဒီ 2 က ဘယ်ကရတာလဲ?"
explain that specific step simply.

If the student asks for another method:
- Solve using another valid method.

If the image is unclear:
- Do not guess.
- Ask the student to send a clearer photo.

If multiple questions are shown and it is unclear which one:
- Ask which question number they want.

Use simple Burmese suitable for a high-school student.

At the end of a normal solution, ask:

နားလည်သွားပြီလား? 😊
"""


def extract_openai_text(data):

    """
    Read text from the raw Responses API JSON.
    """

    output = data.get("output", [])

    for item in output:

        if item.get("type") != "message":
            continue

        content = item.get("content", [])

        for content_item in content:

            if content_item.get("type") == "output_text":

                text = content_item.get("text", "")

                if text:
                    return text

    return None


def ask_openai(text=None, image_bytes=None):

    if not OPENAI_API_KEY:
        raise Exception("OPENAI_API_KEY is missing")

    content = []

    if text:

        content.append({
            "type": "input_text",
            "text": text
        })

    if image_bytes:

        encoded = base64.b64encode(
            image_bytes
        ).decode("utf-8")

        content.append({
            "type": "input_image",
            "image_url": (
                "data:image/jpeg;base64,"
                + encoded
            )
        })

    payload = {

        "model": MODEL,

        "input": [

            {
                "role": "system",

                "content": [

                    {
                        "type": "input_text",
                        "text": SYSTEM_PROMPT
                    }

                ]
            },

            {
                "role": "user",

                "content": content
            }

        ]
    }

    headers = {

        "Authorization":
            f"Bearer {OPENAI_API_KEY}",

        "Content-Type":
            "application/json"
    }

    print("Sending request to OpenAI...")

    response = requests.post(

        OPENAI_API,

        headers=headers,

        json=payload,

        timeout=120
    )

    print(
        "OpenAI status:",
        response.status_code
    )

    if not response.ok:

        print(
            "OpenAI error:",
            response.text
        )

        raise Exception(
            "OpenAI API error"
        )

    data = response.json()

    answer = extract_openai_text(data)

    if answer:

        return answer

    print(
        "OpenAI response did not contain text:",
        data
    )

    return "အဖြေမရသေးပါ။"


# =========================
# MESSAGE HANDLER
# =========================

def handle_message(message):

    chat_id = message["chat"]["id"]

    # =====================
    # START
    # =====================

    if message.get("text") == "/start":

        send_message(

            chat_id,

            "မင်္ဂလာပါ 👋\n\n"
            "ကျွန်တော်က Math + Physics AI Tutor ပါ။\n\n"
            "📷 Math / Physics မေးခွန်းပုံ ပို့နိုင်ပါတယ်။\n"
            "✍️ မေးခွန်းကို စာနဲ့လည်း ရိုက်ပို့နိုင်ပါတယ်။\n\n"
            "အဆင့်လိုက် မြန်မာလို ရှင်းပြပေးပါမယ်။ 😊"

        )

        return

    try:

        # =====================
        # PHOTO
        # =====================

        if "photo" in message:

            photos = message["photo"]

            photo = photos[-1]

            file_id = photo["file_id"]

            file_path = get_file(
                file_id
            )

            image_bytes = download_telegram_file(
                file_path
            )

            send_message(
                chat_id,
                "မေးခွန်းကို ဖတ်ပြီး တွက်ပေးနေပါတယ်... ⏳"
            )

            answer = ask_openai(
                image_bytes=image_bytes
            )

            send_message(
                chat_id,
                answer
            )

            return

        # =====================
        # TEXT
        # =====================

        if "text" in message:

            text = message["text"].strip()

            if not text:
                return

            answer = ask_openai(
                text=text
            )

            send_message(
                chat_id,
                answer
            )

            return

    except Exception as e:

        print(
            "Handler error:",
            type(e).__name__,
            str(e)
        )

        send_message(

            chat_id,

            "တစ်ခုခုအမှားဖြစ်သွားပါတယ်။\n"
            "ခဏနေပြီး ပြန်စမ်းကြည့်ပါ။"

        )


# =========================
# BOT LOOP
# =========================

def bot_loop():

    print("Bot started.")

    offset = None

    while True:

        try:

            result = get_updates(
                offset
            )

            if not result.get("ok"):

                print(
                    "Telegram API error:",
                    result
                )

                time.sleep(5)

                continue

            updates = result.get(
                "result",
                []
            )

            for update in updates:

                offset = (
                    update["update_id"]
                    + 1
                )

                if "message" in update:

                    handle_message(
                        update["message"]
                    )

        except Exception as e:

            print(
                "Bot loop error:",
                type(e).__name__,
                str(e)
            )

            time.sleep(5)


# =========================
# RENDER HEALTH CHECK
# =========================

@app.route("/")
def home():

    return "Math Physics AI Tutor is running."


@app.route("/health")
def health():

    return "OK"


@app.route("/api/healthz")
def healthz():

    return jsonify({

        "status": "ok",

        "bot": "running"

    })


# =========================
# START
# =========================

if __name__ == "__main__":

    if not BOT_TOKEN:

        print(
            "ERROR: BOT_TOKEN is missing"
        )

    if not OPENAI_API_KEY:

        print(
            "ERROR: OPENAI_API_KEY is missing"
        )

    thread = threading.Thread(

        target=bot_loop,

        daemon=True
    )

    thread.start()

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    app.run(

        host="0.0.0.0",

        port=port
    )
