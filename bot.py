
import os
import re
from datetime import datetime
from io import BytesIO

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

# ألوان التصميم
NAVY = "#102F5E"
NAVY_LIGHT = "#194778"
GOLD = "#F4C45E"
WHITE = "#FFFFFF"
BG = "#FCFAF5"
BLUE_PALE = "#E7F2FC"
TEXT = "#102F5E"
GREEN = "#087B68"
BORDER = "#3D91D8"

# أبعاد الصورة: نسبة قريبة من A4 بالطول
W = 1400
MARGIN = 48


def load_font(size, bold=False):
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
    )

    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


def fit_font(draw, text, max_width, size, bold=True, min_size=18):
    while size > min_size:
        f = load_font(size, bold)
        if draw.textbbox((0, 0), text, font=f)[2] <= max_width:
            return f
        size -= 2
    return load_font(min_size, bold)


def centered(draw, xy, text, font, fill):
    x, y = xy
    draw.text((x, y), text, font=font, fill=fill, anchor="mm")


def parse_statement(text):
    """
    يقبل بيانات بالشكل التالي:

    Total Amount: 110000
    Remaining Balance: 30000
    Total Payments: 80000
    2023/09/13 = 25000
    2024/02/20 = 15000
    """

    total = None
    remaining = None
    stated_paid = None
    payments = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        normalized = line.lower().replace(",", "").strip()

        amount_match = re.search(r"-?\d+(?:\.\d+)?", normalized)

        if amount_match:
            value = float(amount_match.group())
            if value.is_integer():
                value = int(value)
        else:
            value = None

        if value is not None and any(
            key in normalized
            for key in ["total amount", "إجمالي المبلغ", "اجمالي المبلغ"]
        ):
            total = value
            continue

        if value is not None and any(
            key in normalized
            for key in [
                "remaining balance",
                "remaining",
                "المتبقي",
                "الباقي",
            ]
        ):
            remaining = value
            continue

        if value is not None and any(
            key in normalized
            for key in [
                "total payments",
                "total paid",
                "إجمالي المدفوع",
                "اجمالي المدفوع",
                "المدفوع",
            ]
        ):
            stated_paid = value
            continue

        # استخراج التاريخ والمبلغ من سطر الدفعة
        match = re.search(
            r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*(?:=|:|-|\s)\s*"
            r"([\d,]+(?:\.\d+)?)",
            line,
        )

        if match:
            date_text = match.group(1).replace("-", "/")
            try:
                date_obj = datetime.strptime(date_text, "%Y/%m/%d")
                date_text = date_obj.strftime("%Y/%m/%d")
            except ValueError:
                pass

            raw_amount = match.group(2).replace(",", "")
            amount = float(raw_amount)
            if amount.is_integer():
                amount = int(amount)

            payments.append((date_text, amount))

    if not payments and total is None and remaining is None:
        raise ValueError(
            "لم أجد بيانات فاتورة واضحة. أرسل إجمالي المبلغ "
            "والباقي وسطور الدفعات بالتواريخ."
        )

    calculated_paid = sum(amount for _, amount in payments)
    paid = stated_paid if stated_paid is not None else calculated_paid

    if total is None and remaining is not None:
        total = paid + remaining

    if remaining is None and total is not None:
        remaining = total - paid

    if total is None:
        total = paid + (remaining or 0)

    if remaining is None:
        remaining = 0

    return total, paid, remaining, payments


def money(value):
    try:
        return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"
    except (ValueError, TypeError):
        return str(value)


def draw_rounded(draw, box, radius, fill, outline=None, width=2):
    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width,
    )


def make_invoice(text):
    total, paid, remaining, payments = parse_statement(text)

    # نحدد ارتفاع الصورة حسب عدد الدفعات حتى لا تتداخل الصفوف
    row_h = 54
    table_header_h = 88
    title_h = 100
    summary_h = 190
    meta_h = 100
    footer_h = 115
    gap = 26

    table_h = table_header_h + max(len(payments), 1) * row_h
    H = (
        180 + meta_h + gap + summary_h + gap
        + title_h + table_h + footer_h + 80
    )

    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    # رأس الفاتورة
    d.rectangle((0, 0, W, 170), fill=NAVY)
    d.rectangle((0, 158, W, 166), fill=GOLD)

    centered(
        d, (W // 2, 54),
        "AZIZ EGYPTIAN COMMERCE",
        load_font(54, True), GOLD
    )
    centered(
        d, (W // 2, 116),
        "PAYMENT STATEMENT",
        load_font(42, True), WHITE
    )

    y = 190

    # بيانات الفاتورة
    draw_rounded(
        d, (MARGIN, y, W - MARGIN, y + meta_h),
        22, "#F1F0EC", outline="#E2DCCF", width=2
    )
    d.text(
        (MARGIN + 28, y + 18), "DATE & TIME",
        font=load_font(23, True), fill=NAVY
    )
    d.text(
        (MARGIN + 28, y + 53),
        datetime.now().strftime("%d %B %Y  |  %I:%M %p"),
        font=fit_font(d, datetime.now().strftime("%d %B %Y  |  %I:%M %p"),
                      510, 25, True),
        fill=TEXT
    )

    divider_x = W // 2 + 20
    d.line(
        (divider_x, y + 16, divider_x, y + meta_h - 16),
        fill=GOLD, width=3
    )
    d.text(
        (divider_x + 28, y + 18), "INVOICE NO.",
        font=load_font(23, True), fill=NAVY
    )
    invoice_no = datetime.now().strftime("AZ-%Y%m%d-%H%M%S")
    d.text(
        (divider_x + 28, y + 53), invoice_no,
        font=fit_font(d, invoice_no, W // 2 - 100, 25, True),
        fill=TEXT
    )

    y += meta_h + gap

    # بطاقات الملخص
    card_gap = 16
    card_w = (W - 2 * MARGIN - 2 * card_gap) // 3
    cards = [
        ("TOTAL AMOUNT", total, NAVY),
        ("TOTAL PAYMENTS", paid, GREEN),
        ("REMAINING BALANCE", remaining, NAVY),
    ]

    for i, (label, value, color) in enumerate(cards):
        x1 = MARGIN + i * (card_w + card_gap)
        x2 = x1 + card_w

        draw_rounded(d, (x1, y, x2, y + summary_h), 24, color)
        centered(
            d, ((x1 + x2) // 2, y + 42),
            label,
            fit_font(d, label, card_w - 28, 25, True, 18),
            WHITE
        )

        d.rounded_rectangle(
            (x1 + 3, y + 76, x2 - 3, y + summary_h - 3),
            radius=20, fill=BG
        )
        centered(
            d, ((x1 + x2) // 2, y + 132),
            money(value),
            fit_font(d, money(value), card_w - 26, 46, True, 22),
            GREEN if i == 1 else NAVY
        )
        d.rounded_rectangle(
            (x1 + 2, y, x2 - 2, y + summary_h),
            radius=24, outline=color, width=3
        )

    y += summary_h + gap

    # عنوان جدول الدفعات
    d.rounded_rectangle(
        (MARGIN, y, W - MARGIN, y + title_h),
        radius=22, fill=NAVY
    )
    d.text(
        (MARGIN + 32, y + 22), "PAYMENT DETAILS",
        font=load_font(39, True), fill=WHITE
    )
    d.line(
        (MARGIN + 24, y + title_h - 4, W - MARGIN - 24, y + title_h - 4),
        fill=GOLD, width=4
    )

    y += title_h - 1
    table_top = y
    table_bottom = table_top + table_h

    # خلفية الجدول
    d.rectangle(
        (MARGIN, table_top, W - MARGIN, table_bottom),
        fill=WHITE
    )
    d.rectangle(
        (MARGIN, table_top, W - MARGIN, table_top + table_header_h),
        fill=NAVY_LIGHT
    )

    left_col = MARGIN + 30
    mid_col = W // 2
    right_col = W - MARGIN - 30

    centered(
        d, ((left_col + mid_col) // 2, table_top + table_header_h // 2),
        "DATE", load_font(32, True), WHITE
    )
    centered(
        d, ((mid_col + right_col) // 2, table_top + table_header_h // 2),
        "AMOUNT", load_font(32, True), WHITE
    )

    d.line(
        (mid_col, table_top, mid_col, table_bottom),
        fill="#B7D5F0", width=2
    )

    if not payments:
        centered(
            d, (W // 2, table_top + table_header_h + row_h // 2),
            "NO PAYMENT DETAILS",
            load_font(24, True), TEXT
        )
    else:
        for i, (date_text, amount) in enumerate(payments):
            row_y = table_top + table_header_h + i * row_h
            row_end = row_y + row_h

            if i % 2 == 0:
                d.rectangle(
                    (MARGIN, row_y, W - MARGIN, row_end),
                    fill="#F7FBFF"
                )
            else:
                d.rectangle(
                    (MARGIN, row_y, W - MARGIN, row_end),
                    fill=BLUE_PALE
                )

            d.text(
                (left_col + 12, row_y + row_h // 2),
                date_text,
                font=fit_font(d, date_text, mid_col - left_col - 28, 29, True),
                fill=TEXT,
                anchor="lm"
            )
            d.text(
                (right_col - 12, row_y + row_h // 2),
                money(amount),
                font=fit_font(d, money(amount), right_col - mid_col - 28, 30, True),
                fill=TEXT,
                anchor="rm"
            )

            d.line(
                (MARGIN, row_end, W - MARGIN, row_end),
                fill="#D9E8F5", width=1
            )

    # إطار الجدول
    d.rounded_rectangle(
        (MARGIN, table_top, W - MARGIN, table_bottom),
        radius=22, outline=BORDER, width=3
    )

    # التذييل
    footer_y = table_bottom + 35
    centered(
        d, (W // 2, footer_y + 15),
        "THANK YOU FOR YOUR BUSINESS",
        load_font(25, True), NAVY
    )
    d.line(
        (MARGIN + 30, footer_y + 15, W // 2 - 250, footer_y + 15),
        fill=GOLD, width=3
    )
    d.line(
        (W // 2 + 250, footer_y + 15, W - MARGIN - 30, footer_y + 15),
        fill=GOLD, width=3
    )
    centered(
        d, (W // 2, footer_y + 55),
        "AZIZ EGYPTIAN COMMERCE",
        load_font(20), NAVY
    )

    # شريط سفلي كحلي وذهبي
    d.rectangle((0, H - 20, W, H), fill=NAVY)
    d.rectangle((0, H - 20, W, H - 14), fill=GOLD)

    output = BytesIO()
    im.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً بك في AZIZ EGYPTIAN COMMERCE.\n\n"
        "أرسل بيانات الفاتورة في رسالة واحدة بهذا الشكل:\n\n"
        "Total Amount: 110000\n"
        "Remaining Balance: 30000\n"
        "Total Payments: 80000\n"
        "2023/09/13 = 25000\n"
        "2024/02/20 = 15000\n"
        "2024/07/05 = 30000\n"
        "2024/08/14 = 10000\n\n"
        "سأحوّل البيانات إلى صورة فاتورة."
    )


async def receive_statement(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if not update.message or not update.message.text:
        return

    try:
        image_file = make_invoice(update.message.text)
        await update.message.reply_photo(
            photo=image_file,
            caption="AZIZ EGYPTIAN COMMERCE — PAYMENT STATEMENT"
        )
    except Exception as exc:
        print("Invoice error:", repr(exc))
        await update.message.reply_text(
            "لم أستطع إنشاء الفاتورة من البيانات المرسلة.\n"
            "تأكد من وجود إجمالي المبلغ أو الباقي، "
            "وأن كل دفعة مكتوبة بالتاريخ والمبلغ."
        )


def main():
    if not TOKEN:
        raise RuntimeError(
            "متغير البيئة TELEGRAM_BOT_TOKEN غير موجود. "
            "أضف التوكن في إعدادات Environment Variables."
        )

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, receive_statement)
    )

    print("Invoice bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
