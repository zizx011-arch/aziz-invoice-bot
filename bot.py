
import os
import re
import logging
import hashlib
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TZ = ZoneInfo("Africa/Lusaka")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Tall, mobile-readable portrait invoice
W = 1400
M = 70
NAVY = "#14243A"
GOLD = "#E2BD69"
CREAM = "#FAF7EF"
WHITE = "#FFFFFF"
INK = "#1D2C40"
GREY = "#657286"
PALE = "#F3E9D2"


def font(size, bold=False):
    names = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for name in names:
        if os.path.exists(name):
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def clean_amount(value):
    return value.strip().replace("٬", "").replace(",", "").replace(" ", "")


def show_amount(value):
    try:
        n = float(clean_amount(value))
        return f"{int(n):,}" if n.is_integer() else f"{n:,.2f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return value.strip()


def parse_statement(text):
    lines = [x.strip() for x in text.splitlines() if x.strip()]

    def amount_for(labels):
        for line in lines:
            for label in labels:
                match = re.search(
                    re.escape(label) + r"\s*[:=]?\s*(-?[\d,٬ ]+(?:\.\d+)?)",
                    line, re.I
                )
                if match:
                    return show_amount(match.group(1))
        return "0"

    total = amount_for(["Total Amount", "Grand Total", "Total"])
    paid = amount_for(["Total Payments", "Total Payment", "Total Paid"])
    remaining = amount_for([
        "Remaining Balance", "Outstanding Balance",
        "Balance Remaining", "Remaining"
    ])

    invoice_no = None
    for line in lines:
        match = re.search(
            r"(?:Invoice\s*(?:No\.?|Number|#)|Reference\s*(?:No\.?|#))"
            r"\s*[:#-]?\s*([A-Za-z0-9/_-]+)", line, re.I
        )
        if match:
            invoice_no = match.group(1)
            break

    payments = []
    for line in lines:
        match = re.search(
            r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*(?:=|:|-)?\s*"
            r"(-?[\d,٬ ]+(?:\.\d+)?)", line
        )
        if match:
            payments.append((
                match.group(1).replace("-", "/"),
                show_amount(match.group(2))
            ))

    return total, paid, remaining, payments, invoice_no


def centered(draw, text, y, f, color, width=W):
    b = draw.textbbox((0, 0), text, font=f)
    x = (width - (b[2] - b[0])) // 2
    draw.text((x, y), text, font=f, fill=color)


def fitted_font(draw, text, max_width, size, bold=True):
    while size > 22:
        f = font(size, bold)
        b = draw.textbbox((0, 0), text, font=f)
        if b[2] - b[0] <= max_width:
            return f
        size -= 2
    return font(size, bold)


def make_invoice(text):
    total, paid, remaining, payments, invoice_no = parse_statement(text)
    now = datetime.now(TZ)

    if not invoice_no:
        seed = text + now.strftime("%Y%m%d%H%M")
        code = hashlib.sha1(seed.encode()).hexdigest()[:8].upper()
        invoice_no = "AZ-" + now.strftime("%Y%m%d") + "-" + code

    # Every payment gets a very tall row for readability.
    header_h = 340
    date_h = 155
    summary_h = 3 * 190 + 110
    table_title_h = 115
    table_head_h = 100
    row_h = 125
    footer_h = 175
    height = (
        header_h + date_h + summary_h + table_title_h
        + table_head_h + max(len(payments), 1) * row_h
        + footer_h
    )

    im = Image.new("RGB", (W, height), CREAM)
    d = ImageDraw.Draw(im)

    # Premium navy and gold header
    d.rectangle((0, 0, W, header_h), fill=NAVY)
    d.rectangle((0, header_h - 12, W, header_h), fill=GOLD)

    centered(d, "AZIZ EGYPTIAN COMMERCE", 48, font(53, True), GOLD)
    centered(d, "PAYMENT STATEMENT", 135, font(48, True), WHITE)
    centered(d, "INVOICE  " + invoice_no, 230, font(31, True), GOLD)

    # Issue date
    y = header_h + 25
    d.rounded_rectangle(
        (M, y, W - M, y + 115), radius=22,
        fill=WHITE, outline=GOLD, width=3
    )
    d.text((M + 30, y + 12), "ISSUE DATE", font=font(24, True), fill=GREY)
    d.text(
        (M + 30, y + 48),
        now.strftime("%d %B %Y   |   %I:%M %p"),
        font=font(34, True), fill=NAVY
    )

    # Summary cards, stacked vertically for large type
    y += 150
    centered(d, "ACCOUNT SUMMARY", y, font(43, True), NAVY)
    y += 80

    cards = [
        ("TOTAL AMOUNT", total),
        ("TOTAL PAYMENTS", paid),
        ("REMAINING BALANCE", remaining),
    ]

    for label, amount in cards:
        d.rounded_rectangle(
            (M, y, W - M, y + 170), radius=24,
            fill=WHITE, outline=GOLD, width=3
        )
        d.rounded_rectangle(
            (M, y, M + 15, y + 170), radius=6, fill=GOLD
        )
        d.text((M + 34, y + 17), label, font=font(29, True), fill=GREY)

        af = fitted_font(d, amount, W - 2 * M - 90, 58, True)
        d.text((M + 34, y + 66), amount, font=af, fill=NAVY)
        y += 190

    # Payment history
    y += 5
    centered(d, "PAYMENT HISTORY", y, font(43, True), NAVY)
    y += 75

    d.rounded_rectangle(
        (M, y, W - M, y + table_head_h), radius=16, fill=NAVY
    )
    d.text((M + 28, y + 24), "DATE", font=font(30, True), fill=GOLD)
    amount_head = "AMOUNT"
    hb = d.textbbox((0, 0), amount_head, font=font(30, True))
    d.text(
        (W - M - 28 - (hb[2] - hb[0]), y + 24),
        amount_head, font=font(30, True), fill=GOLD
    )
    y += table_head_h

    if not payments:
        d.rectangle((M, y, W - M, y + row_h), fill=WHITE)
        d.text((M + 28, y + 38), "No payment entries found",
               font=font(28), fill=GREY)
        y += row_h
    else:
        for i, (date, amount) in enumerate(payments):
            d.rectangle(
                (M, y, W - M, y + row_h),
                fill=WHITE if i % 2 == 0 else PALE
            )

            d.text((M + 28, y + 38), date, font=font(32, True), fill=INK)

            af = fitted_font(d, amount, 400, 35, True)
            ab = d.textbbox((0, 0), amount, font=af)
            d.text(
                (W - M - 28 - (ab[2] - ab[0]), y + 35),
                amount, font=af, fill=NAVY
            )

            d.line((M, y + row_h, W - M, y + row_h), fill=GOLD, width=2)
            y += row_h

    # Footer
    y += 35
    d.line((M, y, W - M, y), fill=GOLD, width=4)
    centered(d, "THANK YOU FOR YOUR BUSINESS", y + 30,
             font(28, True), NAVY)
    centered(d, "AZIZ EGYPTIAN COMMERCE", y + 80,
             font(22, True), GREY)

    out = BytesIO()
    im.save(out, format="PNG", dpi=(150, 150), optimize=True)
    out.seek(0)
    out.name = "aziz_invoice.png"
    return out


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to Aziz Egyptian Commerce!\n\n"
        "Send your statement in English.\n\n"
        "Example:\n"
        "Invoice No: 12345\n"
        "Total Amount: 110000\n"
        "Remaining Balance: 30000\n"
        "Total Payments: 80000\n"
        "2023/09/13 = 25000\n"
        "2024/02/20 = 15000\n"
        "2024/07/05 = 30000\n"
        "2024/08/14 = 10000"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    try:
        image = make_invoice(update.message.text)
        await update.message.reply_photo(
            photo=image,
            caption="Your invoice is ready."
        )
    except Exception:
        log.exception("Invoice creation failed")
        await update.message.reply_text(
            "Could not create the invoice. Please check the statement format."
        )


async def error_handler(update, context):
    log.error("Telegram error", exc_info=context.error)


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing.")

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
