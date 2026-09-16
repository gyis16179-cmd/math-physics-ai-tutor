import os
import time
import base64
import threading
import io
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

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
OPENAI_API = "https://api.openai.com/v1/responses"

app = Flask(__name__)


# =========================================================
# FONT
# =========================================================

def get_font(size=34, bold=False):

    possible_fonts = []

    if bold:
        possible_fonts = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        ]
    else:
        possible_fonts = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
        ]

    for path in possible_fonts:

        if os.path.exists(path):

            return ImageFont.truetype(
                path,
                size
            )

    return ImageFont.load_default()


# =========================================================
# AI PROMPT
# =========================================================

SYSTEM_PROMPT = """
You are a Math and Physics AI Tutor for a Myanmar high-school student.

The student may send a photo of a Math or Physics question.

IMPORTANT:
- Carefully read the image.
- Solve the actual question in the image.
- Never pretend the image is missing when it is readable.
- Never invent unreadable numbers.
- If genuinely unreadable, ask for a clearer photo.

LANGUAGE:
- Explain in simple Burmese.
- Keep the calculation clear and easy to copy into a notebook.

MATH:
- Solve step by step.
- Show every important calculation.
- Make fractions and algebra easy to follow.
- Do not skip important steps.
- Give the final answer.

PHYSICS:
Use:

Given:
Required:
Formula:
Substitution:
Calculation:
Answer:

VERY IMPORTANT OUTPUT FORMAT:

Return ONLY the solution.
Do NOT use Markdown.
Do NOT use LaTeX.
Do NOT use $ signs.
Do NOT use \[ \].
Do NOT use ```.

Use simple lines like:

မေးခွန်း
...

ဖြေရှင်းချက်

1)
...

2)
...

3)
...

အဖြေ = ...

For fractions, write them clearly using lines when possible.
Example:

    1
  ─────
   3+√3

For Physics:

Given:
v₀ = 10 m/s
a = 2 m/s²
t = 5 s

Required:
v = ?

Formula:
v = v₀ + at

Substitution:
v = 10 + (2)(5)

Calculation:
v = 20 m/s

Answer:
20 m/s

Do not add unnecessary explanations.

At the end write:
နားလည်သွားပြီလား? 😊
"""


# =========================================================
# OPENAI TEXT EXTRACTION
# =========================================================

def extract_answer(data):

    output = data.get(
        "output",
        []
    )

    for item in output:

        if item.get("type") != "message":
            continue

        content = item.get(
            "content",
            []
        )

        for part in content:

            if part.get("type") == "output_text":

                text = part.get(
                    "text",
                    ""
                )

                if text:

                    return text.strip()

    return None


# =========================================================
# ASK OPENAI
# =========================================================

def ask_openai(
    text=None,
    image_bytes=None
):

    if not OPENAI_API_KEY:

        raise Exception(
            "OPENAI_API_KEY is missing"
        )

    content = []

    # TEXT
    if text:

        content.append({

            "type": "input_text",

            "text": text

        })

    # IMAGE
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
            "No input"
        )

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

    print(
        "Sending request to OpenAI..."
    )

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

    answer = extract_answer(
        data
    )

    if not answer:

        print(
            "No answer in response:",
            data
        )

        raise Exception(
            "No text returned"
        )

    print(
        "AI answer received."
    )

    return answer


# =========================================================
# CREATE NOTEBOOK IMAGE
# =========================================================

def create_solution_image(
    solution
):

    # -----------------------------------------------------
    # Image settings
    # -----------------------------------------------------

    width = 1400
    padding = 70

    font = get_font(
        34,
        False
    )

    bold_font = get_font(
        42,
        True
    )

    small_font = get_font(
        28,
        False
    )

    # -----------------------------------------------------
    # Clean text
    # -----------------------------------------------------

    solution = solution.replace(
        "```",
        ""
    )

    lines = []

    for raw_line in solution.splitlines():

        line = raw_line.strip()

        if not line:

            lines.append("")

            continue

        # Wrap very long lines
        wrapped = textwrap.wrap(
            line,
            width=48,
            break_long_words=False,
            break_on_hyphens=False
        )

        if wrapped:

            lines.extend(
                wrapped
            )

    if not lines:

        lines = [
            "အဖြေ မရသေးပါ။"
        ]

    # -----------------------------------------------------
    # Calculate height
    # -----------------------------------------------------

    line_height = 55

    height = max(
        1000,
        padding * 2
        + len(lines) * line_height
    )

    # -----------------------------------------------------
    # Create white paper
    # -----------------------------------------------------

    image = Image.new(
        "RGB",
        (width, height),
        "white"
    )

    draw = ImageDraw.Draw(
        image
    )

    # -----------------------------------------------------
    # Notebook lines
    # -----------------------------------------------------

    notebook_start = 145

    for y in range(
        notebook_start,
        height,
        55
    ):

        draw.line(
            [
                (40, y),
                (width - 40, y)
            ],
            fill=(225, 232, 240),
            width=1
        )

    # Red margin
    draw.line(
        [
            (110, 0),
            (110, height)
        ],
        fill=(240, 180, 180),
        width=2
    )

    # -----------------------------------------------------
    # Header
    # -----------------------------------------------------

    draw.text(
        (150, 45),
        "Math + Physics AI Tutor",
        font=bold_font,
        fill=(30, 30, 30)
    )

    # -----------------------------------------------------
    # Solution text
    # -----------------------------------------------------

    y = 145

    for line in lines:

        # Make headings larger
        if (
            line.startswith("Given:")
            or line.startswith("Required:")
            or line.startswith("Formula:")
            or line.startswith("Substitution:")
            or line.startswith("Calculation:")
            or line.startswith("Answer:")
            or line.startswith("အဖြေ")
            or line.startswith("ဖြေရှင်းချက်")
        ):

            current_font = bold_font

        else:

            current_font = font

        draw.text(
            (150, y),
            line,
            font=current_font,
            fill=(25, 25, 25)
        )

        y += line_height

    # -----------------------------------------------------
    # Crop unnecessary bottom space
    # -----------------------------------------------------

    final_height = min(
        height,
        y + 100
    )

    image = image.crop(
        (
            0,
            0,
            width,
            final_height
        )
    )

    # -----------------------------------------------------
    # Convert to bytes
    # -----------------------------------------------------

    output = io.BytesIO()

    image.save(
        output,
        format="PNG"
    )

    output.seek(0)

    return output.getvalue()


# =========================================================
# TELEGRAM SEND TEXT
# =========================================================

def send_message(
    chat_id,
    text
):

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
                "Telegram error:",
                response.text
            )

    except Exception as e:

        print(
            "Telegram send error:",
            e
        )


# =========================================================
# TELEGRAM SEND PHOTO
# =========================================================

def send_photo(
    chat_id,
    image_bytes,
    caption=""
):

    try:

        files = {

            "photo": (
                "solution.png",
                image_bytes,
                "image/png"
            )

        }

        data = {

            "chat_id":
                str(chat_id),

            "caption":
                caption

        }

        response = requests.post(

            f"{TELEGRAM_API}/sendPhoto",

            files=files,

            data=data,

            timeout=60

        )

        if not response.ok:

            print(
                "Telegram photo error:",
                response.text
            )

    except Exception as e:

        print(
            "Telegram photo error:",
            e
        )


# =========================================================
# TELEGRAM GET UPDATES
# =========================================================

def get_updates(
    offset=None
):

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


# =========================================================
# TELEGRAM FILE
# =========================================================

def get_file(
    file_id
):

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
            "Telegram file error"
        )

    return data["result"]["file_path"]


def download_file(
    file_path
):

    response = requests.get(

        f"https://api.telegram.org/file/bot"
        f"{BOT_TOKEN}/{file_path}",

        timeout=60

    )

    response.raise_for_status()

    return response.content


# =========================================================
# MESSAGE HANDLER
# =========================================================

def handle_message(
    message
):

    chat_id = message[
        "chat"
    ][
        "id"
    ]

    # -----------------------------------------------------
    # START
    # -----------------------------------------------------

    if message.get(
        "text"
    ) == "/start":

        send_message(

            chat_id,

            "မင်္ဂလာပါ 👋\n\n"
            "📐 Math မေးခွန်းပုံ ပို့ပါ။\n"
            "⚡ Physics မေးခွန်းပုံ ပို့ပါ။\n\n"
            "AI ကတွက်ပြီး\n"
            "စာရွက်ပေါ်မှာတွက်ထားသလို "
            "ပုံအဖြစ် ပြန်ပို့ပေးပါမယ်။ ✍️📄"

        )

        return

    try:

        # =================================================
        # PHOTO
        # =================================================

        if "photo" in message:

            photos = message[
                "photo"
            ]

            photo = photos[
                -1
            ]

            file_id = photo[
                "file_id"
            ]

            print(
                "Photo received."
            )

            file_path = get_file(
                file_id
            )

            image_bytes = download_file(
                file_path
            )

            print(
                "Image downloaded:",
                len(image_bytes),
                "bytes"
            )

            send_message(

                chat_id,

                "မေးခွန်းကို ဖတ်ပြီး "
                "စာရွက်ပေါ်တွက်ထားသလို "
                "လုပ်ပေးနေပါတယ်... ✍️⏳"

            )

            # AI solve
            answer = ask_openai(

                image_bytes=image_bytes

            )

            print(
                "Creating solution image..."
            )

            # Convert answer to image
            solution_image = create_solution_image(
                answer
            )

            # Send image
            send_photo(

                chat_id,

                solution_image,

                "📐 Math / ⚡ Physics ဖြေရှင်းချက်
