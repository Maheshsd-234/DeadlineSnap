"""Unit tests for DeadlineSnap notification dispatchers."""

from unittest.mock import MagicMock, patch
import pytest

from notifiers import (
    is_placeholder_or_empty,
    sanitize_message_text,
    send_email,
    send_telegram,
    send_whatsapp,
    validate_email,
    validate_phone,
)


def test_input_validators():
    """Test email and phone number format validation."""
    assert validate_email("student@university.edu") is True
    assert validate_email("invalid-email") is False
    assert validate_email("") is False

    assert validate_phone("+14155552671") is True
    assert validate_phone("+919876543210") is True
    assert validate_phone("whatsapp:+14155552671") is True
    assert validate_phone("123") is False
    assert validate_phone("") is False


def test_sanitize_message_text():
    """Test whitespace collapsing and max length capping."""
    raw = "Line 1   with   spaces\n\n\n\nLine 2"
    cleaned = sanitize_message_text(raw, max_length=50)
    assert "Line 1 with spaces" in cleaned
    assert "\n\nLine 2" in cleaned

    long_text = "A" * 2000
    capped = sanitize_message_text(long_text, max_length=100)
    assert len(capped) <= 100
    assert "[Truncated for length limit]" in capped


def test_email_dry_run_when_secrets_missing():
    """Test send_email gracefully falls back to dry-run when secrets are unconfigured."""
    with patch("notifiers.st.secrets", {}):
        success, msg = send_email(
            to_email="test@example.com",
            name="Alice",
            subject="Test Deadlines",
            body="Hello world",
        )
        assert success is True
        assert "dry-run" in msg


def test_telegram_dry_run_when_token_missing():
    """Test send_telegram gracefully falls back to dry-run when token is unconfigured."""
    with patch("notifiers.st.secrets", {}):
        success, msg = send_telegram(
            chat_id="12345678",
            text="Hello Telegram",
        )
        assert success is True
        assert "dry-run" in msg


def test_whatsapp_dry_run_when_twilio_missing():
    """Test send_whatsapp gracefully falls back to dry-run when Twilio keys are unconfigured."""
    with patch("notifiers.st.secrets", {}):
        success, msg = send_whatsapp(
            to_number="+14155552671",
            name="Bob",
            summary="Deadline list",
        )
        assert success is True
        assert "dry-run" in msg


def test_invalid_recipient_errors_without_raising():
    """Test that invalid recipient inputs return (False, error_msg) without raising."""
    success, msg = send_email("bad-email", "Alex", "Subject", "Body")
    assert success is False
    assert "Invalid email" in msg

    success, msg = send_whatsapp("invalid-phone", "Alex", "Summary")
    assert success is False
    assert "Invalid phone" in msg

    success, msg = send_telegram("", "Message")
    assert success is False
    assert "cannot be empty" in msg
