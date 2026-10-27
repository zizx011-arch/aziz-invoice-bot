
import os
import re
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MAX_LENGTH = 3500


def money(value):
    try:
        number = float(str(value).replace(",", "").replace("٬", "").strip())
        return f"{number:,.2f}" if number % 1 else f"{int(number):,}"
    except (ValueError, TypeError):
        return "0"


def parse_money(value):
    cleaned = re.sub(r"[^\d.\-]", "", value.replace(",", "").replace("٬", ""))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_statement(text):
    total = None
    paid = None
    remaining = None
    updated = "Today"
    payments = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        low = line.lower()

        if "last updated" in low:
            if ":" in line:
                updated = line.split(":", 1)[1].strip() or "Today"
            continue

        if re.search(r"\b(total amount|totale)\b", low):
            value = re.split(r"[:=]", line, maxsplit=1)
            if len(value) > 1:
                total = parse_money(value[1])
            continue

        if re.search(r"\b(total payments|payments|paiements)\b", low):
            value = re.split(r"[:=]", line, maxsplit=1)
            if len(value) > 1:
                paid = parse_money(value[1])
            continue

        if re.search(r"\b(remaining balance|remaining|restant)\b", low):
            value = re.split(r"[:=]", line, maxsplit=1)
            if len(value) > 1:
                remaining = parse_money(value[1])
            continue

        if "date" in low and ("amount" in low or "montant" in low):
            continue

        match = re.match(
            r"^\s*(\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*[|=;\t]\s*(.+?)\s*$",
            line,
        )
        if match:
            date = match.group(1).replace("-", "/")
            amount = parse_money(match.group(2))
            payments.append((date, amount))

    calculated_paid = sum(amount for _, amount in payments)

    if paid is None:
        paid = calculated_paid
    if total is None and remaining is not None:
        total = paid + remaining
    if total is None:
        total = paid
    if remaining is None:
        remaining = total - paid

    return total, paid, remaining, updated, payments


def make_invoice(text):
    total, paid, remaining, updated, payments = parse_statement(text)

    lines = [
        "AZIZ EGYPTIAN COMMERCE",
        "CUSTOMER ACCOUNT STATEMENT",
        "=" * 32,
        "",
        "ACCOUNT SUMMARY",
        f"Total Amount:      {money(total)}",
        f"Total Payments:    {money(paid)}",
        f"Remaining Balance: {money(remaining)}",
        "",
        "PAYMENT HISTORY",
        "-" * 32,
        f"{'DATE':<14} {'AMOUNT':>16}",
        "-" * 32,
    ]

    if payments:
        for date, amount in payments:
            lines.append(f"{date:<14} {money(amount):>16}")
    else:
        lines.append("No payment records found.")

    lines.extend([
        "-" * 32,
        f"Number of Payments: {len(payments)}",
        f"Last Updated: {updated}",
        "",
        "Thank you for your business.",
    ])

    return "\n".join(lines), len(payments)


def split_text(text):
    chunks = []
    current = ""

    for line in text.splitlines():
        candidate = line if not current else current + "\n" + line

        if len(candidate) > MAX_LENGTH:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "AZIZ EGYPTIAN COMMERCE\n\n"
        "Send your customer statement as TEXT.\n"
        "I will return an English invoice as text, not an image.\n\n"
        "Payment format:\n"
        "2023/05/19 | 10,000"
    )


async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return

    original = message.text.strip()

    if not original:
        await message.reply_text("Please send the statement as text.")
        return

    invoice, payment_count = make_invoice(original)

    has_summary = any(
        word in original.lower()
        for word in (
            "total amount", "total payments", "remaining balance",
            "totale", "restant", "paiements"
        )
    )

    if payment_count == 0 and not has_summary:
        await message.reply_text(
            "I could not recognize this statement.\n\n"
            "Please send text containing:\n"
            "Total Amount: 360,000\n"
            "Remaining Balance: 0\n"
            "Total Payments: 360,000\n"
            "2023/05/19 | 10,000"
        )
        return

    # Send text only. No photo/document methods are used.
    for part in split_text(invoice):
        await message.reply_text(part)

    logger.info("Text invoice sent. Payments: %s", payment_count)


async def error_handler(update, context):
    logger.error("Bot error: %s", context.error)


def main():
    if not TOKEN:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN environment variable."
        )

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text)
    )
    app.add_error_handler(error_handler)

    logger.info("AZIZ TEXT INVOICE BOT STARTING")
    app.run_polling()


if __name__ == "__main__":
    main()
