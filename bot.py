import os
import time
import base64
import threading
import traceback
import textwrap
import io

import requests

from flask import Flask, jsonify
from PIL import Image, ImageDraw, ImageFont


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OPENAI_API = "https://api.openai.com/v1/responses"
MODEL = "gpt-5.6-luna"

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)


# =========================================================
# AI SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
You are a Math and Physics AI Tutor for Myanmar students.

The student may send a Math or Physics question as text or as an image.

Read the question carefully.

IMPORTANT:
- Never guess if the image is unclear.
- If the question cannot be read, say that the image is unclear and ask the student to send a clearer photo.
- Solve the problem correctly.
- Explain in simple Burmese.
- Use step-by-step calculations.
- Do not use Markdown.
- Do not use LaTeX.
- Do not use $ symbols.
- Do not use \\ symbols.
- Do not use code blocks.

For Mathematics:
Show the calculation step by step.
Keep the explanation easy to understand.

For Physics use this format:

Given:
Required:
Formula:
Substitution:
Calculation:
Answer:

Do not make the answer unnecessarily long.

Return only the solution/explanation that should be shown to the student.
"""


# =========================================================
# BASIC CHECK
# =========================================================

if not BOT_TOKEN:
    print("WARNING: BOT_TOKEN is missing.")

if not OPENAI_API_KEY:
    print("WARNING: OPENAI_API_KEY is missing.")


# =========================================================
# OPENAI RESPONSE TEXT EXTRACTOR
# =========================================================

def extract_answer(data):

    if not isinstance(data, dict):
        return ""

    # Direct output_text
    output_text = data.get("output_text")

    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    # Nested output
    output = data.get("output", [])

    if not isinstance(output, list):
        return ""

    parts = []

    for item in output:

        if not isinstance(item, dict):
            continue

        if item.get("type") != "message":
            continue

        content = item.get("content", [])

        if not isinstance(content, list):
            continue

        for content_item in content:

            if not isinstance(content_item, dict):
                continue

            if content_item.get("type") == "output_text":

                text = content_item.get("text", "")

                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())

    return "\n".join(parts).strip()


# =========================================================
# ASK OPENAI
# =========================================================

def ask_openai(text=None, image_bytes=None):

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    content = []

    if text:
        content.append({
            "type": "input_text",
            "text": text
        })

    if image_bytes:

        encoded = base64.b64encode(image_bytes).decode("utf-8")

        image_url = (
            "data:image/jpeg;base64,"
            + encoded
        )

        content.append({
            "type": "input_image",
            "image_url": image_url,
            "detail": "high"
        })

    payload = {
        "model": MODEL,
        "instructions": SYSTEM_PROMPT,
        "input": [
            {
                "role": "user",
                "content": content
            }
        ],
        "max_output_tokens": 4000
    }

    response = requests.post(
        OPENAI_API,
        headers=headers,
        json=payload,
        timeout=120
    )

    if not response.ok:

        print("OPENAI ERROR STATUS:", response.status_code)
        print("OPENAI ERROR:", response.text)

        raise Exception(
            f"OpenAI API Error {response.status_code}"
        )

    data = response.json()

    answer = extract_answer(data)

    if not answer:
        print("OPENAI RESPONSE:")
        print(data)

        raise Exception(
            "OpenAI returned no answer."
       
