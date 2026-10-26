
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

# A4 portrait proportions, rendered at high resolution
WIDTH = 1240
MARGIN = 76

NAVY = "#14243A"
NAVY_LIGHT = "#203751"
GOLD = "#D6B46A"
GOLD_PALE = "#F7EED9"
PAPER = "#FAF8F2"
WHITE = "#FFFFFF"
TEXT = "#243247"
MUTED = "#667085"
LINE = "#E5DFD1"


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


def clean_number(value):
    value = value.strip().replace("٬", "").replace(",", "")
    value = value.replace(" ", "")
    return value


def format_number(value):
    """Format numeric amounts with thousands separators, without a currency."""
    value = clean_number(value)

    try:
        number = float(value)
        if number.is_integer():
            return f"{int(number):,}"
        return f"{number:,.2f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return value


def find_amount(lines, labels):
    for line in lines:
        for label in labels:
            if re.search(re.escape(label), line, re.IGNORECASE):
                # Prefer a number after the label, not digits in the label.
                tail = re.split(
                    re.escape(label), line, maxsplit=1,
                    flags=re.IGNORECASE
                )[-1]
                match = re.search(
                    r"-?\s*\d[\d,٬ ]*(?:\.\d+)?", tail
                )
                if match:
                    value = clean_number(match.group(0))
                    if value:
                        return format_number(value)

    return "0"


def parse_invoice(raw_text):
    lines = [
        line.strip()
        for line in raw_text.splitlines()
        if line.strip()
    ]

    total = find_amount(
        lines, ["Total Amount", "Total", "Grand Total"]
    )
    remaining = find_amount(
        lines, ["Remaining Balance", "Balance Remaining",
                "Outstanding Balance", "Remaining"]
    )
    paid = find_amount(
        lines, ["Total Payments", "Total Payment",
                "Payments Total", "Total Paid"]
    )

    invoice_number = None

    for line in lines:
        match = re.search(
            r"(?:Invoice\s*(?:No\.?|Number|#)|Reference\s*(?:No\.?|#))"
            r"\s*[:#-]?\s*([A-Za-z0-9/_-]+)",
            line,
            re.IGNORECASE,
        )
        if match:
            invoice_number = match.group(1)
            break

    # Accept dates followed by amounts, e.g. 2023/09/13 = 25,000
    payments = []
    date_pattern = re.compile(
        r"^\s*(\d{4}[/-]\d{1,2}[/-]\d{1,2})"
        r"\s*(?:=|:|-|\t|\s)+"
        r"(-?\s*\d[\d,٬ ]*(?:\.\d+)?)\s*$"
    )

    for line in lines:
        match = date_pattern.search(line)
        if match:
            date = match.group(1).replace("-", "/")
            amount = format_number(match.group(2))
            payments.append((date, amount))

    return total, remaining, paid, payments, invoice_number


def text_width(draw, text, font):
    box = draw.textbbox((0, 0), str(text), font=font)
    return box[2] - box[0]


def draw_centered(draw, text, y, font, fill, width=WIDTH):
    x = (width - text_width(draw, text, font)) // 2
    draw.text((x, y), text, font=font, fill=fill)


def fit_font(draw, text, max_width, start_size, bold=True):
    size = start_size
    while size > 16:
        font = get_font(size, bold)
        if text_width(draw, text, font) <= max_width:
            return font
        size -= 2
    return get_font(16, bold)


def create_invoice(raw_text):
    total, remaining, paid, payments, invoice_number = parse_invoice(
        raw_text
    )

    now = datetime.now(TZ)
    if not invoice_number:
        digest = hashlib.sha1(
            (raw_text + now.strftime("%Y%m%d%H%M")).encode("utf-8")
        ).hexdigest()[:8].upper()
        invoice_number = f"AZ-{now.strftime('%Y%m%d')}-{digest}"

    # Tall portrait invoice; extra height is added for every payment row.
    header_h = 300
    info_h = 170
    summary_h = 430
    table_header_h = 88
    row_h = 86
    footer_h = 150

    row_count = max(len(payments), 1)
    height = (
        header_h + info_h + summary_h + table_header_h
        + row_count * row_h + footer_h + 80
    )

    image = Image.new("RGB", (WIDTH, height), PAPER)
    draw = ImageDraw.Draw(image)

    # Elegant navy header with gold accent
    draw.rectangle((0, 0, WIDTH, header_h), fill=NAVY)
    draw.rectangle((0, header_h - 9, WIDTH, header_h), fill=GOLD)

    draw_centered(
        draw, "AZIZ EGYPTIAN COMMERCE",
        55, get_font(43, True), GOLD
    )
    draw_centered(
        draw, "PAYMENT STATEMENT",
        125, get_font(34, True), WHITE
    )

    draw_centered(
        draw, f"INVOICE NO.  {invoice_number}",
        195, get_font(24, True), GOLD
    )

    # Date and time
    info_top = header_h + 35
    draw.rounded_rectangle(
        (MARGIN, info_top, WIDTH - MARGIN, info_top + 105),
        radius=18, fill=WHITE, outline=LINE, width=2
    )
    draw.text(
        (MARGIN + 28, info_top + 17),
        "ISSUE DATE",
        font=get_font(20, True), fill=MUTED
    )
    date_text = now.strftime("%d %B %Y")
    time_text = now.strftime("%I:%M %p")
    draw.text(
        (MARGIN + 28, info_top + 49),
        f"{date_text}   |   {time_text}",
        font=get_font(27, True), fill=NAVY
    )

    # Financial summary
    summary_top = info_top + 140
    draw.text(
        (MARGIN, summary_top),
        "ACCOUNT SUMMARY",
        font=get_font(31, True), fill=NAVY
    )

    summary_items = [
        ("TOTAL AMOUNT", total, NAVY),
        ("TOTAL PAYMENTS", paid, NAVY_LIGHT),
        ("REMAINING BALANCE", remaining, NAVY),
    ]

    box_top = summary_top + 58
    box_gap = 18
    box_h = 105
    for i, (label, amount, color) in enumerate(summary_items):
        y = box_top + i * (box_h + 17)

        draw.rounded_rectangle(
            (MARGIN, y, WIDTH - MARGIN, y + box_h),
            radius=18, fill=WHITE, outline=LINE, width=2
        )
        draw.rounded_rectangle(
            (MARGIN, y, MARGIN + 12, y + box_h),
            radius=5, fill=GOLD
        )

        draw.text(
            (MARGIN + 32, y + 17),
            label,
            font=get_font(23, True), fill=MUTED
        )

        amount_font = fit_font(
            draw, amount, WIDTH - 2 * MARGIN - 80, 38, True
        )
        amount_width = text_width(draw, amount, amount_font)
        draw.text(
            (WIDTH - MARGIN - 32 - amount_width, y + 48),
            amount,
            font=amount_font, fill=color
        )

    # Payment history table
    table_top = box_top + 3 * (box_h + 17) + 32

    draw.text(
        (MARGIN, table_top),
        "PAYMENT HISTORY",
        font=get_font(31, True), fill=NAVY
    )

    table_top += 58
    draw.rounded_rectangle(
        (MARGIN, table_top, WIDTH - MARGIN, table_top + table_header_h),
        radius=12, fill=NAVY
    )

    date_x = MARGIN + 26
    amount_right = WIDTH - MARGIN - 26
    draw.text(
        (date_x, table_top + 25),
        "DATE",
        font=get_font(25, True), fill=GOLD
    )

    amount_heading = "AMOUNT"
    draw.text(
        (
            amount_right - text_width(
                draw, amount_heading, get_font(25, True)
            ),
            table_top + 25
        ),
        amount_heading,
        font=get_font(25, True), fill=GOLD
    )

    table_y = table_top + table_header_h

    if not payments:
        draw.rounded_rectangle(
            (MARGIN, table_y, WIDTH - MARGIN, table_y + row_h),
            radius=8, fill=WHITE, outline=LINE, width=1
        )
        draw.text(
            (date_x, table_y + 25),
            "No payment entries found",
            font=get_font(23), fill=MUTED
        )
        table_y += row_h
    else:
        for index, (date, amount) in enumerate(payments, start=1):
            fill = WHITE if index % 2 else GOLD_PALE
            draw.rectangle(
                (MARGIN, table_y, WIDTH - MARGIN, table_y + row_h),
                fill=fill
            )

            draw.text(
                (date_x, table_y + 24),
                date,
                font=get_font(26, True), fill=TEXT
            )

            amount_font = fit_font(
                draw, amount, 340, 27, True
            )
            amount_width = text_width(draw, amount, amount_font)
            draw.text(
                (amount_right - amount_width, table_y + 24),
                amount,
                font=amount_font, fill=NAVY
            )

            draw.line(
                (MARGIN, table_y + row_h, WIDTH - MARGIN,
                 table_y + row_h),
                fill=LINE, width=2
            )
            table_y += row_h

    # Footer
    footer_y = table_y + 38
    draw.line(
        (MARGIN, footer_y, WIDTH - MARGIN, footer_y),
        fill=GOLD, width=3
    )
    draw_centered(
        draw, "THANK YOU FOR YOUR BUSINESS",
        footer_y + 28, get_font(23, True), NAVY
    )
    draw_centered(
        draw, "AZIZ EGYPTIAN COMMERCE",
        footer_y + 67, get_font(18, True), MUTED
    )

    output = BytesIO()
    image.save(output, format="PNG", dpi=(150, 150), optimize=True)
    output.seek(0)
    output.name = "aziz_invoice.png"
    return output


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to Aziz Egyptian Commerce!\n\n"
        "Send your payment statement in English and I will "
        "create a clear, portrait invoice image.\n\n"
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


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message or not update.message.text:
        return

    try:
        image = create_invoice(update.message.text)
        await update.message.reply_photo(
            photo=image,
            caption="Your invoice is ready."
        )
    except Exception:
        log.exception("Invoice generation failed")
        await update.message.reply_text(
            "Sorry, I couldn't create the invoice. "
            "Please check the English labels and payment dates."
        )


async def error_handler(update, context):
    log.error(
        "Telegram application error",
        exc_info=context.error
    )


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
