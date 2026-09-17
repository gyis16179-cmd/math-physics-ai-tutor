import os
import time
import base64
import io
import threading
import traceback
import textwrap

import requests
from flask import Flask, jsonify
from PIL import Image, ImageDraw, ImageFont


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MODEL = "gpt-5.6-luna"

OPENAI_URL = "https://api.openai.com/v1/responses"

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)


# =========================================================
# AI INSTRUCTIONS
# =========================================================

SYSTEM_PROMPT = """
You are a Math and Physics AI Tutor for Myanmar students.

The student can send a Math or Physics question as text or as a photo.

Read the question carefully.

If the photo is unclear, do not guess.
Tell the student to send a clearer photo.

Solve the question correctly.

Explain in simple Burmese.

For Mathematics:
Show the calculation step by step.

For Physics use:

Given:
Required:
Formula:
Substitution:
Calculation:
Answer:

IMPORTANT:
Do not use Markdown.
Do not use LaTeX.
Do not use dollar signs.
Do not use code blocks.
Do not use \\[ or \\].

Keep the answer clear and easy to copy into a notebook.
"""


# =========================================================
# OPENAI RESPONSE TEXT
# =========================================================

def extract_answer(data):

    if not isinstance(data, dict):
        return ""

    direct = data.get("output_text")

    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    output = data.get("output", [])

    if not isinstance(output, list):
        return ""

    result = []

    for item in output:

        if not isinstance(item, dict):
            continue

        if item.get("type") != "message":
            continue

        content = item.get("content", [])

        if not isinstance(content, list):
            continue

        for part in content:

            if not isinstance(part, dict):
                continue

            if part.get("type") == "output_text":

                text = part.get("text", "")

                if isinstance(text, str):
                    result.append(text)

    return "\n".join(result).strip()


# =========================================================
# ASK OPENAI
# =========================================================

def ask_openai(question=None, image_bytes=None):

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    content = []

    if question:

        content.append({
            "type": "input_text",
            "text": question
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
            ),
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
        OPENAI_URL,
        headers=headers,
        json=payload,
        timeout=120
    )

    if not response.ok:

        print(
            "OPENAI ERROR:",
            response.status_code
        )

        print(
            response.text
        )

        raise Exception(
            "OpenAI API request failed"
        )

    data = response.json()

    answer = extract_answer(data)

    if not answer:

        print("EMPTY OPENAI RESPONSE")
        print(data)

        raise Exception(
            "OpenAI returned empty answer"
        )

    return answer


# =========================================================
# CLEAN ANSWER
# =========================================================

def clean_answer(text):

    if not text:
        return "အဖြေမရသေးပါ။"

    replacements = [
        ("\\[", ""),
        ("\\]", ""),
        ("\\(", ""),
        ("\\)", ""),
        ("$$", ""),
        ("$", ""),
        ("```", ""),
        ("### ", ""),
        ("## ", ""),
        ("# ", "")
    ]

    for old, new in replacements:
        text = text.replace(old, new)

    return text.strip()


# =========================================================
# FONT
# =========================================================

def get_font(size=40, bold=False):

    if bold:

        paths = [
            "/usr/share/fonts/truetype/noto/NotoSansMyanmar-Bold.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansMyanmar-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        ]

    else:

        paths = [
            "/usr/share/fonts/truetype/noto/NotoSansMyanmar-Regular.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansMyanmar-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ]

    for path in paths:

        if os.path.exists(path):

            return ImageFont.truetype(
                path,
                size
            )

    return ImageFont.load_default()


# =========================================================
# CREATE NOTEBOOK IMAGE
# =========================================================

def create_solution_image(solution):

    solution = clean_answer(solution)

    width = 1400
    left = 150
    top = 120
    bottom = 100
    line_height = 65

    font = get_font(40, False)
    bold_font = get_font(43, True)

    raw_lines = solution.splitlines()

    lines = []

    for line in raw_lines:

        if not line.strip():

            lines.append("")
            continue

        wrapped = textwrap.wrap(
            line,
            width=48,
            replace_whitespace=False
        )

        if wrapped:

            lines.extend(wrapped)

    height = max(
        1000,
        top + len(lines) * line_height + bottom
    )

    image = Image.new(
        "RGB",
        (
