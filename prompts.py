"""Prompts, JSON schemas, and digest formatting templates for DeadlineSnap."""

from datetime import date
from typing import Any, Dict, Optional

# Structured JSON Schema for Gemini Vision response
DEADLINE_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "status": {
            "type": "STRING",
            "enum": ["ok", "partial", "no_deadlines_found"],
            "description": "Overall outcome of the extraction.",
        },
        "reason": {
            "type": "STRING",
            "description": "Short explanation or note if status is 'partial' or 'no_deadlines_found', otherwise empty string.",
        },
        "deadlines": {
            "type": "ARRAY",
            "description": "List of extracted deadlines, exam dates, submission dates, or class/event dates.",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {
                        "type": "STRING",
                        "description": "Name or title of the assignment, exam, quiz, milestone, class, or task.",
                    },
                    "course": {
                        "type": "STRING",
                        "nullable": True,
                        "description": "Course name, code, or subject (e.g. CS101, Linear Algebra), or null if unknown.",
                    },
                    "date": {
                        "type": "STRING",
                        "nullable": True,
                        "description": "Resolved due/event date in ISO format (YYYY-MM-DD). If ambiguous, null.",
                    },
                    "time": {
                        "type": "STRING",
                        "nullable": True,
                        "description": "Time of due date or class in HH:MM format (24-hour) or 12-hour (e.g. 23:59 or 11:59 PM), or null.",
                    },
                    "raw_date_text": {
                        "type": "STRING",
                        "description": "The exact original text for the date/time as written on the document.",
                    },
                    "type": {
                        "type": "STRING",
                        "enum": ["assignment", "exam", "project", "quiz", "class", "other"],
                        "description": "Category of the deadline or event.",
                    },
                    "confidence": {
                        "type": "STRING",
                        "enum": ["high", "medium", "low"],
                        "description": "Confidence level in date resolution and extraction accuracy.",
                    },
                },
                "required": ["title", "raw_date_text", "type", "confidence"],
            },
        },
    },
    "required": ["status", "deadlines"],
}

EXTRACTION_SYSTEM_PROMPT_TEMPLATE: str = """You are an academic document reader specialized solely in deadline extraction.
Your ONLY job is to find deadlines, due dates, exam dates, submission dates, project milestones, and class/event dates in the provided image(s) of syllabi, timetables, course schedules, or assignment sheets.

Today's date is: {today}

RULES & INSTRUCTIONS:
1. Strict JSON output: Output ONLY valid JSON adhering precisely to the specified schema. Do not include markdown codeblocks (no ```json), commentary, or extra text.
2. No Guessing / No Inventing: Never guess or invent dates. If a date is ambiguous, incomplete, or relative (e.g., "Next Friday", "Week 5", "TBA", missing year):
   - Set "date": null
   - Preserve the exact document wording in "raw_date_text"
   - Set "confidence": "low"
3. Year Resolution: Use today's date ({today}) ONLY to infer the relevant academic year if the month/day is explicit but year is omitted. Do NOT use it to invent dates.
4. Date Format Ambiguity: When dates are formatted numerically (e.g., 05/06/2026), assume day-first / DD/MM/YYYY (Indian format) unless the document explicitly indicates MM/DD/YYYY or provides unambiguous context.
5. Graceful Failure:
   - If the image is not a syllabus, timetable, assignment sheet, or contains no readable dates/deadlines at all, return:
     {{"status": "no_deadlines_found", "reason": "<one short sentence explaining why>", "deadlines": []}}
   - If the image is blurry, partially cropped, or partly unreadable, return:
     "status": "partial" with whatever valid items could be read, plus a concise "reason".
   - If clear and valid dates are found, return "status": "ok" and populate "deadlines".
"""

DIGEST_PROMPT_TEMPLATE: str = """Format the following list of student deadlines into a short, friendly, plain-text digest message for messaging alerts (WhatsApp/SMS).
Rules:
- Include 1 or 2 friendly emojis at most.
- Plain text only. No markdown formatting (no asterisks, backticks, or hashes).
- Group or list items clearly by date and title.
- Keep it concise, motivational, and easy to skim.

Deadlines:
{deadlines_summary}
"""


def get_extraction_prompt(today: Optional[str] = None) -> str:
    """Generate the extraction system prompt populated with the current date.

    Args:
        today: Optional ISO date string (YYYY-MM-DD). If omitted, uses current date.

    Returns:
        Formatted prompt string.
    """
    current_date = today or date.today().isoformat()
    return EXTRACTION_SYSTEM_PROMPT_TEMPLATE.format(today=current_date)


def get_digest_prompt(deadlines_summary: str) -> str:
    """Generate the plain-text digest formatting prompt.

    Args:
        deadlines_summary: Textual summary of deadlines to format.

    Returns:
        Formatted digest prompt string.
    """
    return DIGEST_PROMPT_TEMPLATE.format(deadlines_summary=deadlines_summary)
