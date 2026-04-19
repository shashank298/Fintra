import re
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

BANK_PATTERNS = {
    "hdfcbank.net": {
        "amount": r"Rs\.?\s*([\d,]+\.?\d*)\s*(?:debited|spent|withdrawn)",
        "merchant": r"(?:at|to)\s+([A-Z0-9][A-Za-z0-9\s\-&'.]+?)(?:\s+on|\s+via|\s+Ref|\.|\s*$)",
        "date": r"on\s+(\d{2}-\d{2}-\d{4})",
    },
    "axisbank.com": {
        "amount": r"(?:INR|Rs\.?)\s*([\d,]+\.?\d*)\s*(?:debited|spent|paid)",
        "merchant": r"(?:at|to)\s+([A-Za-z0-9\s\-&'.]+?)(?:\s+on|\s+via|\.|$)",
        "date": r"(\d{2}-\d{2}-\d{4})",
    },
    "icicibank.com": {
        "amount": r"(?:INR|Rs\.?)\s*([\d,]+\.?\d*)\s*(?:debited|spent)",
        "merchant": r"(?:at|to)\s+([A-Za-z0-9\s\-&'.]+?)(?:\s+on|\s+via|\s+on\s+a/c|\.|$)",
        "date": r"(\d{2}-\d{2}-\d{4})",
    },
    "google.com": {
        "amount": r"(?:Rs\.?|INR)\s*([\d,]+\.?\d*)",
        "merchant": r"paid\s+(?:to\s+)?([A-Za-z0-9\s\-&'.]+?)(?:\s+via|\s+using|\s+with|\.|$)",
        "date": r"(\d{2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})",
    },
    "phonepe.com": {
        "amount": r"(?:Rs\.?|INR)\s*([\d,]+\.?\d*)",
        "merchant": r"(?:paid|sent)\s+(?:to\s+)?([A-Za-z0-9\s\-&'.]+?)(?:\s+via|\s+using|\.|$)",
        "date": r"(\d{2}\s+\w+\s+\d{4}|\d{2}-\d{2}-\d{4})",
    },
    "paytm.com": {
        "amount": r"(?:Rs\.?|INR)\s*([\d,]+\.?\d*)",
        "merchant": r"(?:paid|transferred)\s+(?:to\s+)?([A-Za-z0-9\s\-&'.]+?)(?:\s+via|\s+on|\.|$)",
        "date": r"(\d{2}\s+\w+\s+\d{4}|\d{2}-\d{2}-\d{4})",
    },
    "kotak.com": {
        "amount": r"(?:INR|Rs\.?)\s*([\d,]+\.?\d*)\s*(?:debited|spent)",
        "merchant": r"(?:at|to)\s+([A-Za-z0-9\s\-&'.]+?)(?:\s+on|\s+via|\.|$)",
        "date": r"(\d{2}-\d{2}-\d{4})",
    },
    "indusind.com": {
        "amount": r"(?:INR|Rs\.?)\s*([\d,]+\.?\d*)",
        "merchant": r"(?:at|to)\s+([A-Za-z0-9\s\-&'.]+?)(?:\s+on|\s+via|\.|$)",
        "date": r"(\d{2}-\d{2}-\d{4})",
    },
}

TRANSACTION_KEYWORDS = ["debited", "spent", "paid", "transferred", "withdrawn", "purchase", "transaction"]


def _find_pattern_key(sender: str) -> Optional[str]:
    for key in BANK_PATTERNS:
        if key in sender.lower():
            return key
    return None


def _parse_amount(text: str) -> Optional[float]:
    for pattern_key, patterns in BANK_PATTERNS.items():
        m = re.search(patterns["amount"], text, re.IGNORECASE)
        if m:
            return float(m.group(1).replace(",", ""))
    return None


def _normalize_date(date_str: str) -> Optional[str]:
    import datetime
    formats = ["%d-%m-%Y", "%d %B %Y", "%d %b %Y", "%Y-%m-%d"]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def regex_parse(body: str, sender: str) -> Optional[dict]:
    pattern_key = _find_pattern_key(sender)
    if not pattern_key:
        return None

    if not any(kw in body.lower() for kw in TRANSACTION_KEYWORDS):
        return None

    patterns = BANK_PATTERNS[pattern_key]

    amount_match = re.search(patterns["amount"], body, re.IGNORECASE)
    if not amount_match:
        return None
    amount = float(amount_match.group(1).replace(",", ""))

    merchant = "Unknown"
    merchant_match = re.search(patterns["merchant"], body, re.IGNORECASE)
    if merchant_match:
        merchant = merchant_match.group(1).strip()

    date = None
    date_match = re.search(patterns["date"], body, re.IGNORECASE)
    if date_match:
        date = _normalize_date(date_match.group(1))

    return {"amount": amount, "merchant": merchant, "date": date, "currency": "INR"}


async def gemini_parse(body: str) -> Optional[dict]:
    try:
        import google.generativeai as genai
        from app.config import get_settings
        settings = get_settings()
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = (
            "Extract transaction details from this bank or UPI email. "
            "Return ONLY a JSON object with these exact fields: "
            "is_transaction (boolean), amount (float or null), merchant (string or null), "
            "date (YYYY-MM-DD string or null), currency (string default INR). "
            "If this is not a transaction email set is_transaction to false. "
            "No explanation, no markdown, JSON only.\n\n"
            f"Email:\n{body[:3000]}"
        )

        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"```(?:json)?\n?", "", text).replace("```", "").strip()

        data = json.loads(text)
        if not data.get("is_transaction"):
            return None

        return {
            "amount": float(data["amount"]),
            "merchant": data.get("merchant", "Unknown"),
            "date": data.get("date"),
            "currency": data.get("currency", "INR"),
        }
    except Exception as e:
        logger.warning(f"Gemini parse failed: {e}")
        return None


async def groq_parse(body: str) -> Optional[dict]:
    try:
        from groq import Groq
        from app.config import get_settings
        settings = get_settings()
        client = Groq(api_key=settings.GROQ_API_KEY)

        prompt = (
            "Extract transaction details from this bank or UPI email. "
            "Return ONLY a JSON object with these exact fields: "
            "is_transaction (boolean), amount (float or null), merchant (string or null), "
            "date (YYYY-MM-DD string or null), currency (string default INR). "
            "If this is not a transaction email set is_transaction to false. "
            "No explanation, no markdown, JSON only.\n\n"
            f"Email:\n{body[:3000]}"
        )

        completion = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        text = completion.choices[0].message.content
        data = json.loads(text)

        if not data.get("is_transaction"):
            return None

        return {
            "amount": float(data["amount"]),
            "merchant": data.get("merchant", "Unknown"),
            "date": data.get("date"),
            "currency": data.get("currency", "INR"),
        }
    except Exception as e:
        logger.warning(f"Groq parse failed: {e}")
        return None


async def run_parser_pipeline(body: str, sender: str) -> Optional[dict]:
    result = regex_parse(body, sender)
    if result:
        return result

    result = await gemini_parse(body)
    if result:
        return result

    result = await groq_parse(body)
    if result:
        return result

    logger.info(f"All parser stages failed for sender: {sender}")
    return None


async def ocr_receipt(image_base64: str, mime_type: str) -> Optional[dict]:
    try:
        import google.generativeai as genai
        from app.config import get_settings
        settings = get_settings()
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = (
            "Extract details from this receipt image. Return ONLY JSON: "
            '{"amount": float, "merchant": string, "date": "YYYY-MM-DD or null", '
            '"currency": string, "line_items": [{"name": string, "price": float}]}. '
            "No explanation. JSON only."
        )

        import base64 as b64
        image_data = b64.b64decode(image_base64)
        response = model.generate_content([
            prompt,
            {"mime_type": mime_type, "data": image_data},
        ])
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"```(?:json)?\n?", "", text).replace("```", "").strip()

        return json.loads(text)
    except Exception as e:
        logger.error(f"Receipt OCR failed: {e}")
        return None
