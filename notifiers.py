"""Notification dispatchers for DeadlineSnap via Email (SMTP), Telegram, and WhatsApp (Twilio).

Includes input validation, DRY_RUN fallbacks for testing without credentials, and graceful error handling.
"""

import json
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple
import requests
import streamlit as st

try:
    from twilio.rest import Client as TwilioClient
except ImportError:
    TwilioClient = None  # type: ignore

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PHONE_REGEX = re.compile(r"^\+?[1-9]\d{7,14}$")


def is_placeholder_or_empty(value: Optional[str]) -> bool:
    """Check if a secret configuration value is missing or still has placeholder text."""
    if not value or not isinstance(value, str):
        return True
    val = value.strip().lower()
    return not val or val.startswith("your-") or val.startswith("placeholder")


def validate_email(email_str: str) -> bool:
    """Validate email address format."""
    if not email_str:
        return False
    return bool(EMAIL_REGEX.match(email_str.strip()))


def validate_phone(phone_str: str) -> bool:
    """Validate E.164 phone number format (with optional + prefix)."""
    if not phone_str:
        return False
    cleaned = phone_str.strip().replace(" ", "").replace("-", "")
    if cleaned.startswith("whatsapp:"):
        cleaned = cleaned[9:]
    return bool(PHONE_REGEX.match(cleaned))


def sanitize_message_text(text: str, max_length: int = 1500) -> str:
    """Collapse excess whitespace and cap message length for messaging platforms."""
    if not text:
        return ""
    # Collapse multiple consecutive blank lines or spaces
    cleaned = re.sub(r"[ \t]+", " ", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if len(cleaned) > max_length:
        return cleaned[: max_length - 30] + "\n\n[Truncated for length limit]"
    return cleaned


@st.cache_resource
def get_twilio_client() -> Optional[Any]:
    """Cache and return a Twilio Client instance if valid credentials exist."""
    if TwilioClient is None:
        return None
    try:
        account_sid = st.secrets.get("TWILIO_ACCOUNT_SID", "")
        auth_token = st.secrets.get("TWILIO_AUTH_TOKEN", "")
    except Exception:
        return None

    if is_placeholder_or_empty(account_sid) or is_placeholder_or_empty(auth_token):
        return None
    try:
        return TwilioClient(account_sid, auth_token)
    except Exception:
        return None


def send_email(to_email: str, name: str, subject: str, body: str) -> Tuple[bool, str]:
    """Send deadline digest email via SMTP with both plain-text and HTML versions.

    Falls back to Dry-Run mode if SMTP credentials are not configured in secrets.

    Args:
        to_email: Target recipient email address.
        name: Recipient student's name.
        subject: Subject line for the email.
        body: Plain text body of the deadline digest.

    Returns:
        Tuple of (success: bool, info_message: str).
    """
    if not validate_email(to_email):
        return False, f"Invalid email address '{to_email}'. Please check the format."

    try:
        smtp_host = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(st.secrets.get("SMTP_PORT", 587))
        smtp_user = st.secrets.get("SMTP_USER", "")
        smtp_password = st.secrets.get("SMTP_PASSWORD", "")
    except Exception:
        smtp_host, smtp_port, smtp_user, smtp_password = "smtp.gmail.com", 587, "", ""

    # DRY RUN fallback
    if is_placeholder_or_empty(smtp_user) or is_placeholder_or_empty(smtp_password):
        log_msg = f"[DRY_RUN EMAIL] To: {to_email} | Name: {name} | Subject: {subject}\n{body}"
        print(log_msg)
        return (
            True,
            f"dry-run: email printed to console (SMTP credentials not configured in secrets.toml).",
        )

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"DeadlineSnap <{smtp_user}>"
        msg["To"] = to_email
        msg["Subject"] = subject

        # HTML formatted version
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
                .header {{ background: linear-gradient(135deg, #4f46e5, #06b6d4); color: #ffffff; padding: 24px; text-align: center; }}
                .content {{ padding: 24px; font-size: 15px; line-height: 1.6; white-space: pre-wrap; }}
                .footer {{ background: #f1f5f9; padding: 16px; text-align: center; font-size: 12px; color: #64748b; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 style="margin:0;">📅 DeadlineSnap Digest</h2>
                    <p style="margin:4px 0 0 0; opacity:0.9;">Academic Schedule & Alert Summary</p>
                </div>
                <div class="content">
Hi {name},

{body}
                </div>
                <div class="footer">
                    Sent automatically by DeadlineSnap • Never miss an assignment again.
                </div>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        return True, f"Digest email successfully sent to {to_email}!"

    except Exception as e:
        return False, f"Email delivery failed: {str(e)}"


def get_telegram_instructions() -> str:
    """Return friendly markdown instructions explaining how to set up Telegram Bot notifications."""
    return """
### 🤖 How to get your Telegram Chat ID:
1. Open Telegram and search for your bot username (or `@userinfobot`).
2. Click **Start** (or send `/start`) to initiate a conversation with the bot.
3. Open [@userinfobot](https://t.me/userinfobot) or use the **Check Recent Messages** button below to auto-detect your Chat ID.
4. Paste your numeric Chat ID into the field and click send.
"""


def fetch_telegram_updates(bot_token: Optional[str] = None) -> Tuple[bool, List[Dict[str, Any]], str]:
    """Fetch recent messages sent to the Telegram bot via getUpdates API to help auto-detect chat IDs.

    Args:
        bot_token: Optional override token.

    Returns:
        Tuple of (success: bool, list_of_recent_chats: List[dict], message: str).
    """
    token = bot_token
    if not token:
        try:
            token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        except Exception:
            token = ""

    if is_placeholder_or_empty(token):
        return False, [], "Telegram Bot Token not configured in secrets.toml."

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if not data.get("ok"):
            return False, [], f"Telegram API error: {data.get('description', 'Unknown error')}"

        results = data.get("result", [])
        chats = []
        seen_ids = set()
        for update in reversed(results):
            msg = update.get("message") or update.get("edited_message")
            if msg and "chat" in msg:
                chat = msg["chat"]
                cid = str(chat.get("id"))
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    chats.append(
                        {
                            "chat_id": cid,
                            "first_name": chat.get("first_name", ""),
                            "username": chat.get("username", ""),
                            "type": chat.get("type", "private"),
                        }
                    )
        return True, chats, f"Found {len(chats)} recent chat conversation(s)."
    except Exception as e:
        return False, [], f"Failed to fetch Telegram updates: {str(e)}"


def send_telegram(chat_id: str, text: str) -> Tuple[bool, str]:
    """Send deadline alert message to a Telegram Chat ID.

    Falls back to Dry-Run mode if TELEGRAM_BOT_TOKEN is not configured.

    Args:
        chat_id: Telegram numeric chat ID.
        text: Message string to send.

    Returns:
        Tuple of (success: bool, info_message: str).
    """
    cleaned_chat_id = str(chat_id).strip()
    if not cleaned_chat_id:
        return False, "Telegram Chat ID cannot be empty."

    try:
        bot_token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
    except Exception:
        bot_token = ""

    # DRY RUN fallback
    if is_placeholder_or_empty(bot_token):
        log_msg = f"[DRY_RUN TELEGRAM] Chat ID: {cleaned_chat_id}\n{text}"
        print(log_msg)
        return (
            True,
            "dry-run: Telegram message printed to console (TELEGRAM_BOT_TOKEN not configured).",
        )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": cleaned_chat_id,
        "text": text,
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        res_json = resp.json()
        if resp.status_code == 200 and res_json.get("ok"):
            return True, f"Telegram alert successfully sent to Chat ID {cleaned_chat_id}!"
        else:
            description = res_json.get("description", "Unknown Telegram API error.")
            return False, f"Telegram delivery failed: {description}"
    except Exception as e:
        return False, f"Telegram request exception: {str(e)}"


def send_whatsapp(to_number: str, name: str, summary: str) -> Tuple[bool, str]:
    """Send WhatsApp digest using Twilio WhatsApp Content API.

    # WhatsApp Business Messaging Note:
    # WhatsApp requires pre-approved Content Templates for business-initiated outgoing messages.
    # When using Twilio's WhatsApp Sandbox (+1 415 523 8886), the user must first send the sandbox
    # join code (e.g. 'join <word>') from their device, and this opt-in window expires after ~72 hours.

    Args:
        to_number: Target recipient phone number (E.164 formatted).
        name: Student recipient name.
        summary: Deadline digest summary text.

    Returns:
        Tuple of (success: bool, info_message: str).
    """
    if not validate_phone(to_number):
        return (
            False,
            f"Invalid phone number '{to_number}'. Must be E.164 format (e.g., +1234567890 or +919876543210).",
        )

    # Clean and cap summary at 1500 chars for WhatsApp templates
    clean_summary = sanitize_message_text(summary, max_length=1500)

    # Format destination phone with whatsapp: prefix
    raw_num = to_number.strip().replace(" ", "").replace("-", "")
    formatted_to = raw_num if raw_num.startswith("whatsapp:") else f"whatsapp:{raw_num}"

    try:
        account_sid = st.secrets.get("TWILIO_ACCOUNT_SID", "")
        auth_token = st.secrets.get("TWILIO_AUTH_TOKEN", "")
        from_number = st.secrets.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
        content_sid = st.secrets.get("TWILIO_CONTENT_SID", "")
    except Exception:
        account_sid, auth_token, from_number, content_sid = "", "", "", ""

    # DRY RUN fallback
    if is_placeholder_or_empty(account_sid) or is_placeholder_or_empty(auth_token):
        log_msg = (
            f"[DRY_RUN WHATSAPP] To: {formatted_to} | Name: {name}\nSummary:\n{clean_summary}"
        )
        print(log_msg)
        return (
            True,
            "dry-run: WhatsApp message printed to console (Twilio credentials not configured).",
        )

    client = get_twilio_client()
    if not client:
        return False, "Failed to initialize Twilio client. Please check credentials."

    try:
        if not is_placeholder_or_empty(content_sid):
            # Send using Twilio Content Template API (Parameters 1: name, 2: summary)
            msg = client.messages.create(
                from_=from_number,
                to=formatted_to,
                content_sid=content_sid,
                content_variables=json.dumps({"1": name, "2": clean_summary}),
            )
        else:
            # Fallback direct body dispatch (works within open 24h conversation windows / sandbox)
            body_text = f"Hi {name}! 🎓 Here is your DeadlineSnap digest:\n\n{clean_summary}"
            msg = client.messages.create(
                from_=from_number,
                to=formatted_to,
                body=body_text,
            )

        return True, f"WhatsApp digest dispatched successfully (SID: {msg.sid[:10]}...)!"

    except Exception as e:
        return False, f"Twilio WhatsApp delivery failed: {str(e)}"
