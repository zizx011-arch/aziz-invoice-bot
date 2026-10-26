
import os
import re
import logging
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TZ = ZoneInfo("Africa/Lusaka")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def get_font(size, bold=False):
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
    return value.replace(",", "").replace("٬", "").strip()


def parse_invoice(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    def find_amount(label):
        for line in lines:
            if label.lower() in line.lower():
                match = re.search(r"(-?[\d,٬]+(?:\.\d+)?)", line)
                if match:
                    return money(match.group(1))
        return "0"

    total = find_amount("Total Amount")
    remaining = find_amount("Remaining Balance")
    payments_total = find_amount("Total Payments")

    payments = []
    for line in lines:
        match = re.search(
            r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*(?:=|:|-)?\s*"
            r"(-?[\d,٬]+(?:\.\d+)?)",
            line,
        )
        if match:
            date = match.group(1).replace("-", "/")
            amount = money(match.group(2))
            if date not in ("0000/00/00",):
                payments.append((date, amount))

    return total, remaining, payments_total, payments


def create_invoice(text):
    total, remaining, payments_total, payments = parse_invoice(text)

    width = 1100
    margin = 65
    row_height = 48
    height = 440 + max(len(payments), 1) * row_height + 80

    image = Image.new("RGB", (width, height), "#F4F6FA")
    draw = ImageDraw.Draw(image)

    title_font = get_font(38, True)
    heading_font = get_font(25, True)
    body_font = get_font(22)
    small_font = get_font(17)

    # Header
    draw.rectangle((0, 0, width, 150), fill="#172B4D")
    draw.text((margin, 30), "AZIZ EGYPTIAN COMMERCE",
              font=title_font, fill="white")
    draw.text((margin, 92), "PAYMENT STATEMENT",
              font=body_font, fill="#DCE6F5")

    now = datetime.now(TZ).strftime("%d %b %Y  |  %I:%M %p")
    draw.text((margin, 175), f"Issue date: {now}",
              font=small_font, fill="#526078")

    # Summary cards
    cards = [
        ("TOTAL AMOUNT", total),
        ("TOTAL PAYMENTS", payments_total),
        ("REMAINING BALANCE", remaining),
    ]
    card_y = 220
    gap = 18
    card_w = (width - 2 * margin - 2 * gap) // 3

    for i, (label, value) in enumerate(cards):
        x = margin + i * (card_w + gap)
        draw.rounded_rectangle(
            (x, card_y, x + card_w, card_y + 115),
            radius=15, fill="white", outline="#E0E5ED", width=2
        )
        draw.text((x + 18, card_y + 18), label,
                  font=small_font, fill="#526078")
        draw.text((x + 18, card_y + 55), value,
                  font=heading_font, fill="#172B4D")

    # Payment history
    table_y = 375
    draw.text((margin, table_y), "PAYMENT HISTORY",
              font=heading_font, fill="#172B4D")

    table_y += 48
    draw.rounded_rectangle(
        (margin, table_y, width - margin, table_y + 46),
        radius=7, fill="#DCE6F5"
    )
    draw.text((margin + 18, table_y + 10), "DATE",
              font=body_font, fill="#172B4D")
    draw.text((width - margin - 250, table_y + 10), "AMOUNT",
              font=body_font, fill="#172B4D")

    table_y += 46

    if not payments:
        draw.text((margin + 18, table_y + 14),
                  "No payment entries found",
                  font=body_font, fill="#526078")
    else:
        for i, (date, amount) in enumerate(payments):
            y = table_y + i * row_height
            fill = "white" if i % 2 == 0 else "#EEF1F6"
            draw.rectangle(
                (margin, y, width - margin, y + row_height),
                fill=fill
            )
            draw.text((margin + 18, y + 10), date,
                      font=body_font, fill="#26364D")
            draw.text((width - margin - 250, y + 10), amount,
                      font=body_font, fill="#26364D")

    footer_y = height - 55
    draw.text((margin, footer_y),
              "Thank you for your business.",
              font=small_font, fill="#526078")

    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return output


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome!\n\n"
        "Send me your payment statement as text, and I will "
        "turn it into an English invoice image (PNG).\n\n"
        "Include these labels:\n"
        "Total Amount: 360000\n"
        "Remaining Balance: 0\n"
        "Total Payments: 360000\n\n"
        "Payment rows: 2023/05/19 = 10000"
    )


async def handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if not update.message or not update.message.text:
        return

    try:
        image = create_invoice(update.message.text)
        await update.message.reply_photo(
            photo=image,
            caption="Your payment statement is ready."
        )
    except Exception:
        log.exception("Invoice generation failed")
        await update.message.reply_text(
            "I couldn't create the invoice. Please check the text format."
        )


async def error_handler(update, context):
    log.exception("Telegram bot error", exc_info=context.error)


def main():
    if not TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN environment variable is missing."
        )

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    app.add_error_handler(error_handler)

    log.info("Telegram invoice bot is starting.")
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
