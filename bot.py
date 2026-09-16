import os
import time
import base64
import threading
import requests

from flask import Flask, jsonify


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MODEL = "gpt-5.6-luna"

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
OPENAI_API = "https://api.openai.com/v1/responses"

app = Flask(__name__)


# =========================================================
# AI INSTRUCTIONS
# =========================================================

SYSTEM_PROMPT = """
You are a Math and Physics AI Tutor for a Myanmar high-school student.

IMPORTANT:
- The user may send a photo containing a Math or Physics question.
- Carefully inspect and read the image.
- Do not say that the image is missing if an image was actually provided.
- Do not ask the user to resend the image unless the image is genuinely unreadable.
- Never guess a number or symbol that cannot be read clearly.

LANGUAGE:
- Always explain in simple Burmese.
- Use English only for necessary mathematical or physics terms.

MATH:
- Solve step by step.
- Show important calculations.
- Do not skip algebra steps.
- Explain why an important step is performed.
- Make the final answer clear.

PHYSICS:
Use this format when appropriate:

Given:
Required:
Formula:
Substitution:
Calculation:
Answer:

If the user asks:
"ဒီအဆင့်ကို ဘာလို့လုပ်တာလဲ?"
or
"ဒီ 2 က ဘယ်ကရတာလဲ?"
explain that exact step simply.

If the user asks for another method:
- Solve using another valid method.

If several questions are visible:
- If the user clearly says which question, solve that question.
- If it is genuinely unclear which question they want, ask for the question number.

If the image is genuinely too blurry to read:
- Say that the image is unclear.
- Ask for a clearer photo.

At the end of a normal solution:
"နားလည်သွားပြီလား? 😊"
"""


# =========================================================
# TELEGRAM FUNCTIONS
# =========================================================

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


def get_telegram_file(file_id):

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
            "Telegram getFile error: "
            + str(data)
        )

    return data["result"]["file_path"]


def download_telegram_file(file_path):

    url = (
        f"https://api.telegram.org/"
        f"file/bot{BOT_TOKEN}/{file_path}"
    )

    response = requests.get(
        url,
        timeout=60
    )

    response.raise_for_status()

    return response.content


# =========================================================
# OPENAI FUNCTIONS
# =========================================================

def extract_openai_answer(data):

    """
    Extract text from the raw Responses API JSON.
    """

    output = data.get("output", [])

    for item in output:

        if item.get("type") != "message":
            continue

        content = item.get("content", [])

        for content_item in content:

            if content_item.get("type") == "output_text":

                text = content_item.get("text")

                if text:
                    return text

    return None


def ask_openai(text=None, image_bytes=None):

    if not OPENAI_API_KEY:

        raise Exception(
            "OPENAI_API_KEY is missing"
        )

    content = []

    # -----------------------------------------------------
    # TEXT
    # -----------------------------------------------------

    if text:

        content.append({
            "type": "input_text",
            "text": text
        })

    # -----------------------------------------------------
    # IMAGE
    # -----------------------------------------------------

    if image_bytes:

        encoded = base64.b64encode(
            image_bytes
        ).decode("utf-8")

        content.append({

            "type": "input_image",

            "image_url":
                "data:image/jpeg;base64,"
                + encoded,

            "detail": "high"
        })

    if not content:

        raise Exception(
            "No text or image was provided"
        )

    # -----------------------------------------------------
    # REQUEST
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # API ERROR
    # -----------------------------------------------------

    if not response.ok:

        print(
            "OpenAI API error:",
            response.status_code
        )

        print(
            response.text
        )

        raise Exception(
            "OpenAI API request failed"
        )

    # -----------------------------------------------------
    # JSON
    # -----------------------------------------------------

    data = response.json()

    answer = extract_openai_answer(
        data
    )

    if answer:

        return answer

    # -----------------------------------------------------
    # NO TEXT FOUND
    # -----------------------------------------------------

    print(
        "OpenAI returned no output text."
    )

    print(
        "Response keys:",
        list(data.keys())
    )

    return (
        "AI က အဖြေစာသား ပြန်မရသေးပါ။ "
        "ခဏနေပြီး ထပ်စမ်းကြည့်ပါ။"
    )


# =========================================================
# MESSAGE HANDLER
# =========================================================

def handle_message(message):

    chat_id = message["chat"]["id"]

    # =====================================================
    # /start
    # =====================================================

    if message.get("
