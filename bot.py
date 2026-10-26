
import os
import re
import io
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TIMEZONE = ZoneInfo("Africa/Lusaka")

NAVY = "#17365D"
BLUE = "#2463A6"
LIGHT = "#F2F6FC"
GOLD = "#D5A64A"
GREEN = "#21865B"
DARK = "#243247"
GRAY = "#64748B"
WHITE = "#FFFFFF"


def font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def money(value):
    return f"{value:,.0f}"


def parse_invoice(text):
    total = re.search(
        r"Total Amount\s*:\s*([\d,]+(?:\.\d+)?)", text, re.I
    )
    remaining = re.search(
        r"Remaining Balance\s*:\s*([\d,]+(?:\.\d+)?)", text, re.I
    )
    payments_total = re.search(
        r"Total Payments\s*:\s*([\d,]+(?:\.\d+)?)", text, re.I
    )

    if not (total and remaining and payments_total):
        raise ValueError(
            "Please include Total Amount, Remaining Balance, "
            "and Total Payments."
        )

    def number(match):
        return float(match.group(1).replace(",", ""))

    rows = []
    for line in text.splitlines():
        match = re.match(
            r"\s*\|?\s*(\d{4}/\d{2}/\d{2})\s*\|\s*"
            r"([\d,]+(?:\.\d+)?)\s*\|?\s*$",
            line,
        )
        if match:
            date = datetime.strptime(match.group(1), "%Y/%m/%d")
            amount = float(match.group(2).replace(",", ""))
            rows.append((date, amount))

    if not rows:
        raise ValueError("No payment rows found. Please check the table.")

    return number(total), number(remaining), number(payments_total), rows


def make_invoice(total, remaining, payments_total, rows):
    width = 1000
    margin = 55
    row_height = 48
    table_top = 440
    footer_height = 100
    height = table_top + 58 + len(rows) * row_height + footer_height

    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)

    # Header
    draw.rounded_rectangle(
        (margin, 35, width - margin, 175),
        radius=24,
        fill=NAVY,
    )
    draw.text(
        (width // 2, 78),
        "Aziz Egyptian commerce",
        font=font(37, True),
        fill=WHITE,
        anchor="mm",
    )
    draw.rounded_rectangle(
        (width // 2 - 100, 122, width // 2 + 100, 128),
        radius=3,
        fill=GOLD,
    )
    draw.text(
        (width // 2, 151),
        "CUSTOMER ACCOUNT STATEMENT",
        font=font(17, True),
        fill="#E7EDF7",
        anchor="mm",
    )

    now = datetime.now(TIMEZONE)
    draw.text(
        (width // 2, 208),
        "ISSUE DATE & TIME",
        font=font(17, True),
        fill=GRAY,
        anchor="mm",
    )
    draw.text(
        (width // 2, 240),
        now.strftime("%Y/%m/%d   %H:%M"),
        font=font(25, True),
        fill=DARK,
        anchor="mm",
    )

    # Summary cards
    card_top, card_bottom = 285, 405
    gap = 15
    card_width = (width - 2 * margin - 2 * gap) // 3
    cards = [
        ("TOTAL AMOUNT", total, NAVY),
        ("TOTAL PAYMENTS", payments_total, GREEN),
        ("REMAINING BALANCE", remaining, BLUE),
    ]

    for i, (label, amount, color) in enumerate(cards):
        x1 = margin + i * (card_width + gap)
        x2 = x1 + card_width
        draw.rounded_rectangle(
            (x1, card_top, x2, card_bottom),
            radius=16,
            fill=LIGHT,
            outline="#DCE5F0",
            width=2,
        )
        draw.rounded_rectangle(
            (x1, card_top, x2, card_top + 8),
            radius=4,
            fill=color,
        )
        draw.text(
            ((x1 + x2) // 2, card_top + 38),
            label,
            font=font(14, True),
            fill=GRAY,
            anchor="mm",
        )
        draw.text(
            ((x1 + x2) // 2, card_top + 78),
            money(amount),
            font=font(25, True),
            fill=color,
            anchor="mm",
        )

    # Payment history
    draw.rounded_rectangle(
        (margin, table_top, width - margin, table_top + 48),
        radius=10,
        fill=NAVY,
    )
    draw.text(
        (margin + 22, table_top + 24),
        "PAYMENT HISTORY",
        font=font(20, True),
        fill=WHITE,
        anchor="lm",
    )

    header_y = table_top + 58
    draw.rectangle(
        (margin, header_y, width - margin, header_y + 43),
        fill="#E5EDF7",
    )
    draw.text(
        (margin + 25, header_y + 21),
        "NO.",
        font=font(15, True),
        fill=NAVY,
        anchor="lm",
    )
    draw.text(
        (margin + 110, header_y + 21),
        "DATE",
        font=font(15, True),
        fill=NAVY,
        anchor="lm",
    )
    draw.text(
        (width - margin - 25, header_y + 21),
        "AMOUNT",
        font=font(15, True),
        fill=NAVY,
        anchor="rm",
    )

    y = header_y + 43
    for index, (date, amount) in enumerate(rows, 1):
        bg = WHITE if index % 2 == 0 else LIGHT
        draw.rectangle(
            (margin, y, width - margin, y + row_height),
            fill=bg,
        )
        draw.text(
            (margin + 25, y + row_height // 2),
            str(index),
            font=font(16),
            fill=GRAY,
            anchor="lm",
        )
        draw.text(
            (margin + 110, y + row_height // 2),
            date.strftime("%Y/%m/%d"),
            font=font(17),
            fill=DARK,
            anchor="lm",
        )
        draw.text(
            (width - margin - 25, y + row_height // 2),
            money(amount),
            font=font(17, True),
            fill=DARK,
            anchor="rm",
        )
        draw.line(
            (margin, y + row_height, width - margin, y + row_height),
            fill="#DFE6EF",
            width=1,
        )
        y += row_height

    # Footer
    footer_y = y + 25
    draw.rounded_rectangle(
        (margin, footer_y, width - margin, footer_y + 65),
        radius=12,
        fill="#F7F0E2",
    )
    draw.text(
        (width // 2, footer_y + 32),
        f"TOTAL PAYMENTS: {money(payments_total)}",
        font=font(20, True),
        fill=NAVY,
        anchor="mm",
    )

    output = io.BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return output


async def handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    message = update.effective_message
    if not message or not message.text:
        return

    try:
        total, remaining, paid, rows = parse_invoice(message.text)
        picture = make_invoice(total, remaining, paid, rows)

        await message.reply_photo(
            photo=picture,
            caption="Aziz Egyptian commerce | Invoice generated",
        )

        sum_rows = sum(amount for _, amount in rows)
        if abs(sum_rows - paid) > 0.01:
            await message.reply_text(
                f"Warning: Payment rows total {money(sum_rows)}, "
                f"but Total Payments says {money(paid)}."
            )

    except Exception as error:
        await message.reply_text(
            "I couldn't format this invoice.\n"
            f"Details: {error}"
        )


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    print("Invoice bot is running.")
    app.run_polling()


if __name__ == "__main__":
    main()
