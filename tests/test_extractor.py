"""Unit tests for DeadlineSnap extractor parsing and validation logic."""

import json
from unittest.mock import MagicMock, patch
import pytest

from extractor import (
    extract_deadlines,
    get_demo_deadlines_result,
    validate_and_sanitize_result,
)


def test_validate_and_sanitize_valid():
    """Test validation of a well-formed Gemini JSON response."""
    sample_data = {
        "status": "ok",
        "reason": "",
        "deadlines": [
            {
                "title": "Midterm Exam",
                "course": "MATH 54",
                "date": "2026-10-15",
                "time": "14:00",
                "raw_date_text": "Oct 15, 2 PM",
                "type": "exam",
                "confidence": "high",
            }
        ],
    }
    is_valid, sanitized = validate_and_sanitize_result(sample_data)
    assert is_valid is True
    assert sanitized["status"] == "ok"
    assert len(sanitized["deadlines"]) == 1
    assert sanitized["deadlines"][0]["title"] == "Midterm Exam"
    assert sanitized["deadlines"][0]["type"] == "exam"
    assert sanitized["deadlines"][0]["confidence"] == "high"


def test_validate_and_sanitize_no_deadlines():
    """Test validation when no deadlines are found in the document."""
    sample_data = {
        "status": "no_deadlines_found",
        "reason": "Image contains lecture notes without deadlines.",
        "deadlines": [],
    }
    is_valid, sanitized = validate_and_sanitize_result(sample_data)
    assert is_valid is True
    assert sanitized["status"] == "no_deadlines_found"
    assert sanitized["reason"] == "Image contains lecture notes without deadlines."
    assert sanitized["deadlines"] == []


def test_validate_and_sanitize_partial():
    """Test validation with partial visibility status and null dates."""
    sample_data = {
        "status": "partial",
        "reason": "Bottom portion of syllabus is blurred.",
        "deadlines": [
            {
                "title": "Lab Assignment 1",
                "course": None,
                "date": None,
                "time": None,
                "raw_date_text": "Due Week 3 Friday",
                "type": "assignment",
                "confidence": "low",
            }
        ],
    }
    is_valid, sanitized = validate_and_sanitize_result(sample_data)
    assert is_valid is True
    assert sanitized["status"] == "partial"
    assert len(sanitized["deadlines"]) == 1
    assert sanitized["deadlines"][0]["date"] is None
    assert sanitized["deadlines"][0]["confidence"] == "low"


def test_validate_and_sanitize_malformed_types():
    """Test sanitizer normalizes unknown types and confidences."""
    sample_data = {
        "status": "ok",
        "deadlines": [
            {
                "title": "Mystery Task",
                "type": "invalid_type",
                "confidence": "super_high",
                "raw_date_text": "Tomorrow",
            }
        ],
    }
    is_valid, sanitized = validate_and_sanitize_result(sample_data)
    assert is_valid is True
    assert sanitized["deadlines"][0]["type"] == "other"
    assert sanitized["deadlines"][0]["confidence"] == "medium"


def test_demo_mode_fallback():
    """Test extract_deadlines returns realistic demo data when no client is configured."""
    with patch("extractor.get_gemini_client", return_value=None):
        result = extract_deadlines(images=b"fake_image_bytes", mime_types="image/png")
        assert result["status"] == "ok"
        assert len(result["deadlines"]) > 0
        assert "Problem Set" in result["deadlines"][0]["title"]


def test_extract_deadlines_mocked_gemini_success():
    """Test extraction flow when Gemini returns valid JSON."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {
            "status": "ok",
            "reason": "",
            "deadlines": [
                {
                    "title": "Essay 1",
                    "course": "ENG 101",
                    "date": "2026-10-30",
                    "time": "23:59",
                    "raw_date_text": "Oct 30, 23:59",
                    "type": "assignment",
                    "confidence": "high",
                }
            ],
        }
    )
    mock_client.models.generate_content.return_value = mock_response

    with patch("extractor.get_gemini_client", return_value=mock_client):
        result = extract_deadlines(images=b"sample_bytes", mime_types="image/jpeg")
        assert result["status"] == "ok"
        assert len(result["deadlines"]) == 1
        assert result["deadlines"][0]["title"] == "Essay 1"


def test_extract_deadlines_retry_on_malformed_json():
    """Test that extractor retries on malformed JSON and succeeds on second attempt."""
    mock_client = MagicMock()
    mock_bad_response = MagicMock()
    mock_bad_response.text = "NOT JSON DATA {{"

    mock_good_response = MagicMock()
    mock_good_response.text = json.dumps(
        {
            "status": "ok",
            "reason": "",
            "deadlines": [
                {
                    "title": "Quiz 1",
                    "course": "CHEM 1A",
                    "date": "2026-10-12",
                    "time": "10:00",
                    "raw_date_text": "Oct 12 at 10 AM",
                    "type": "quiz",
                    "confidence": "high",
                }
            ],
        }
    )

    # First call returns malformed string, second call returns valid JSON
    mock_client.models.generate_content.side_effect = [
        mock_bad_response,
        mock_good_response,
    ]

    with patch("extractor.get_gemini_client", return_value=mock_client):
        result = extract_deadlines(images=[b"page1", b"page2"], mime_types=["image/png", "image/png"])
        assert result["status"] == "ok"
        assert len(result["deadlines"]) == 1
        assert result["deadlines"][0]["title"] == "Quiz 1"
        assert mock_client.models.generate_content.call_count == 2
