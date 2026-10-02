"""Gemini Vision extraction logic, validation, retry mechanism, and demo fallback for DeadlineSnap."""

import json
from typing import Any, Dict, List, Optional, Union
import streamlit as st

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None  # type: ignore
    types = None  # type: ignore

from prompts import DEADLINE_EXTRACTION_SCHEMA, get_extraction_prompt


@st.cache_resource
def get_gemini_client(api_key: Optional[str] = None) -> Optional[Any]:
    """Cache and initialize the Gemini API client using google-genai SDK.

    Args:
        api_key: Optional API key override. If omitted, checks st.secrets.

    Returns:
        genai.Client instance or None if not configured/available.
    """
    if genai is None:
        return None

    resolved_key = api_key
    if not resolved_key:
        try:
            resolved_key = st.secrets.get("GEMINI_API_KEY", "")
        except Exception:
            resolved_key = ""

    if not resolved_key or resolved_key.startswith("your-"):
        return None

    try:
        return genai.Client(api_key=resolved_key)
    except Exception:
        return None


def get_demo_deadlines_result() -> Dict[str, Any]:
    """Return realistic mock extraction results for Demo Mode without API keys.

    Returns:
        Dict adhering to DEADLINE_EXTRACTION_SCHEMA.
    """
    return {
        "status": "ok",
        "reason": "",
        "deadlines": [
            {
                "title": "Problem Set 1: Graph Algorithms",
                "course": "CS 188",
                "date": "2026-10-10",
                "time": "23:59",
                "raw_date_text": "Oct 10 at 11:59 PM",
                "type": "assignment",
                "confidence": "high",
            },
            {
                "title": "Midterm Exam (Linear Systems & Eigenvalues)",
                "course": "MATH 54",
                "date": "2026-10-15",
                "time": "14:00",
                "raw_date_text": "15/10/2026 2:00 PM",
                "type": "exam",
                "confidence": "high",
            },
            {
                "title": "Weekly Quiz 4",
                "course": "PHYS 7A",
                "date": "2026-10-18",
                "time": "17:00",
                "raw_date_text": "Sunday, Oct 18 by 5 PM",
                "type": "quiz",
                "confidence": "medium",
            },
            {
                "title": "Final Term Project Submission",
                "course": "CS 188",
                "date": "2026-11-20",
                "time": "23:59",
                "raw_date_text": "Nov 20, 2026",
                "type": "project",
                "confidence": "high",
            },
            {
                "title": "Guest Lecture Attendance & Summary",
                "course": "ENG 1A",
                "date": None,
                "time": None,
                "raw_date_text": "Week 8 Friday TBA",
                "type": "class",
                "confidence": "low",
            },
        ],
    }


def validate_and_sanitize_result(data: Any) -> tuple[bool, Dict[str, Any]]:
    """Validate and sanitize the parsed JSON data against the deadline extraction schema.

    Args:
        data: Arbitrary object parsed from Gemini JSON response.

    Returns:
        Tuple of (is_valid: bool, sanitized_dict: Dict[str, Any]).
    """
    if not isinstance(data, dict):
        return False, {
            "status": "no_deadlines_found",
            "reason": "Extraction result was not a valid dictionary structure.",
            "deadlines": [],
        }

    status = data.get("status")
    if status not in ["ok", "partial", "no_deadlines_found"]:
        # Fallback heuristic if status key is missing but deadlines array is present
        if isinstance(data.get("deadlines"), list):
            status = "ok" if data["deadlines"] else "no_deadlines_found"
        else:
            status = "no_deadlines_found"

    reason = str(data.get("reason") or "")
    raw_deadlines = data.get("deadlines", [])

    if not isinstance(raw_deadlines, list):
        return False, {
            "status": "no_deadlines_found",
            "reason": "Extracted deadlines field is not a list.",
            "deadlines": [],
        }

    valid_types = {"assignment", "exam", "project", "quiz", "class", "other"}
    valid_confidences = {"high", "medium", "low"}

    sanitized_deadlines: List[Dict[str, Any]] = []
    for item in raw_deadlines:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title") or "").strip()
        if not title:
            continue

        item_type = str(item.get("type", "other")).lower().strip()
        if item_type not in valid_types:
            item_type = "other"

        confidence = str(item.get("confidence", "medium")).lower().strip()
        if confidence not in valid_confidences:
            confidence = "medium"

        raw_date = str(item.get("raw_date_text") or item.get("date") or "TBD").strip()

        sanitized_deadlines.append(
            {
                "title": title,
                "course": item.get("course"),
                "date": item.get("date"),
                "time": item.get("time"),
                "raw_date_text": raw_date,
                "type": item_type,
                "confidence": confidence,
            }
        )

    if not sanitized_deadlines and status == "ok":
        status = "no_deadlines_found"
        if not reason:
            reason = "No deadlines or scheduled dates found in document."

    return True, {
        "status": status,
        "reason": reason,
        "deadlines": sanitized_deadlines,
    }


def extract_deadlines(
    images: Union[bytes, List[bytes]],
    mime_types: Union[str, List[str]] = "image/png",
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract structured deadlines from one or more document/syllabus images using Gemini Vision.

    Args:
        images: Single image bytes or list of image bytes (multi-page syllabus).
        mime_types: Single MIME type string or list of MIME types corresponding to images.
        api_key: Optional Gemini API key override.
        model_name: Optional model override.

    Returns:
        Dict matching DEADLINE_EXTRACTION_SCHEMA with status, reason, and deadlines list.
    """
    client = get_gemini_client(api_key=api_key)

    # Demo mode fallback if no API key is available
    if not client:
        return get_demo_deadlines_result()

    # Normalize image inputs to lists
    image_list = [images] if isinstance(images, bytes) else images
    if isinstance(mime_types, str):
        mime_list = [mime_types] * len(image_list)
    else:
        mime_list = mime_types

    if not image_list:
        return {
            "status": "no_deadlines_found",
            "reason": "No image data provided for extraction.",
            "deadlines": [],
        }

    resolved_model = model_name
    if not resolved_model:
        try:
            resolved_model = st.secrets.get("GEMINI_MODEL", "gemini-2.5-flash")
        except Exception:
            resolved_model = "gemini-2.5-flash"

    prompt_text = get_extraction_prompt()

    # Build Gemini content parts
    contents: List[Any] = []
    for img_bytes, m_type in zip(image_list, mime_list):
        contents.append(types.Part.from_bytes(data=img_bytes, mime_type=m_type))
    contents.append(prompt_text)

    generation_config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=DEADLINE_EXTRACTION_SCHEMA,
        temperature=0.1,
    )

    try:
        # Initial attempt
        response = client.models.generate_content(
            model=resolved_model,
            contents=contents,
            config=generation_config,
        )

        response_text = (response.text or "").strip()
        try:
            parsed = json.loads(response_text)
            is_valid, sanitized = validate_and_sanitize_result(parsed)
            if is_valid:
                return sanitized
        except json.JSONDecodeError:
            pass

        # Retry once with strict nudge if JSON was malformed
        retry_contents = contents + [
            "The previous response was not valid JSON. Return ONLY valid JSON adhering strictly to the schema without markdown."
        ]
        retry_response = client.models.generate_content(
            model=resolved_model,
            contents=retry_contents,
            config=generation_config,
        )
        retry_text = (retry_response.text or "").strip()
        try:
            retry_parsed = json.loads(retry_text)
            _, sanitized_retry = validate_and_sanitize_result(retry_parsed)
            return sanitized_retry
        except json.JSONDecodeError:
            return {
                "status": "no_deadlines_found",
                "reason": "Failed to parse structured JSON from vision model response.",
                "deadlines": [],
            }

    except Exception as e:
        return {
            "status": "no_deadlines_found",
            "reason": f"Extraction request failed: {str(e)}",
            "deadlines": [],
        }
