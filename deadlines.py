"""Deadline date processing, urgency bucketing, plain-text digest formatting, and ICS calendar export."""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
from dateutil import parser


def parse_date_safe(date_val: Any) -> Optional[date]:
    """Safely parse a date value (str, date, datetime, or None) into a date object.

    Args:
        date_val: Raw date input.

    Returns:
        datetime.date object if successfully parsed, else None.
    """
    if date_val is None:
        return None
    if isinstance(date_val, date) and not isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, datetime):
        return date_val.date()
    if isinstance(date_val, str):
        cleaned = date_val.strip()
        if not cleaned:
            return None
        try:
            # Try ISO format first
            return datetime.strptime(cleaned[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
        try:
            # Fuzzy dateutil parse
            return parser.parse(cleaned, fuzzy=True, dayfirst=True).date()
        except (ValueError, OverflowError):
            return None
    return None


def days_left(target_date: Union[date, datetime, str], today: Optional[date] = None) -> int:
    """Calculate the number of days remaining until the target date.

    Args:
        target_date: Target deadline date.
        today: Reference date (defaults to today's local date).

    Returns:
        Integer number of days (negative if past/overdue).
    """
    ref_today = today or date.today()
    parsed_date = parse_date_safe(target_date)
    if parsed_date is None:
        raise ValueError(f"Cannot calculate days_left for invalid date: {target_date}")
    return (parsed_date - ref_today).days


def normalize(
    deadlines: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Normalize deadline objects, parsing dates into date objects without dropping any item.

    Separates deadlines into:
    1. Valid dated items (sorted by date)
    2. Undated / needs-review items

    Args:
        deadlines: Raw list of deadline dictionaries.

    Returns:
        Tuple of (dated_deadlines, needs_review_deadlines).
    """
    dated: List[Dict[str, Any]] = []
    needs_review: List[Dict[str, Any]] = []

    for item in deadlines:
        item_copy = dict(item)
        raw_date_val = item.get("date")
        parsed = parse_date_safe(raw_date_val)

        item_copy["date_obj"] = parsed
        if parsed:
            item_copy["date_iso"] = parsed.isoformat()
            dated.append(item_copy)
        else:
            item_copy["date_iso"] = None
            needs_review.append(item_copy)

    # Sort dated items chronologically
    dated.sort(key=lambda x: x["date_obj"])
    return dated, needs_review


def split_by_urgency(
    deadlines: List[Dict[str, Any]], today: Optional[date] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """Bucket deadlines by urgency relative to reference date.

    Buckets:
    - overdue: days_left < 0
    - due_soon: 0 <= days_left <= 2 (today, tomorrow, next day)
    - this_week: 3 <= days_left <= 7
    - later: days_left > 7
    - needs_review: no valid date

    Args:
        deadlines: List of deadline dictionaries.
        today: Reference date (defaults to today).

    Returns:
        Dict mapping bucket names to lists of deadline dictionaries.
    """
    ref_today = today or date.today()
    dated, needs_review = normalize(deadlines)

    buckets: Dict[str, List[Dict[str, Any]]] = {
        "overdue": [],
        "due_soon": [],
        "this_week": [],
        "later": [],
        "needs_review": needs_review,
    }

    for item in dated:
        d_obj = item["date_obj"]
        delta = (d_obj - ref_today).days
        item_with_delta = dict(item)
        item_with_delta["days_left"] = delta

        if delta < 0:
            buckets["overdue"].append(item_with_delta)
        elif 0 <= delta <= 2:
            buckets["due_soon"].append(item_with_delta)
        elif 3 <= delta <= 7:
            buckets["this_week"].append(item_with_delta)
        else:
            buckets["later"].append(item_with_delta)

    return buckets


def format_deadline_line(item: Dict[str, Any], days_delta: Optional[int] = None) -> str:
    """Format a single deadline item into a clean plain text line."""
    title = item.get("title", "Task").strip()
    course = item.get("course")
    course_str = f" [{course}]" if course else ""
    date_str = item.get("date_iso") or item.get("raw_date_text") or "TBD"
    time_str = f" {item.get('time')}" if item.get("time") else ""

    if days_delta is not None:
        if days_delta < 0:
            urgency_text = f" (Overdue by {abs(days_delta)}d!)"
        elif days_delta == 0:
            urgency_text = " (Due TODAY!)"
        elif days_delta == 1:
            urgency_text = " (Due Tomorrow!)"
        else:
            urgency_text = f" ({days_delta} days left)"
    else:
        raw = item.get("raw_date_text")
        urgency_text = f" (Note: {raw})" if raw else ""

    return f"• {title}{course_str} - {date_str}{time_str}{urgency_text}"


def build_digest(
    name: str,
    deadlines: List[Dict[str, Any]],
    today: Optional[date] = None,
    max_chars: int = 1500,
) -> str:
    """Generate a clean, plain-text digest message grouped by urgency.

    Keeps the output under max_chars and truncates gracefully if needed for WhatsApp/SMS.

    Args:
        name: Recipient student's name.
        deadlines: List of deadline items.
        today: Reference date.
        max_chars: Maximum character limit for output string (default 1500).

    Returns:
        Structured plain-text summary message.
    """
    ref_today = today or date.today()
    buckets = split_by_urgency(deadlines, ref_today)

    total_items = (
        len(buckets["overdue"])
        + len(buckets["due_soon"])
        + len(buckets["this_week"])
        + len(buckets["later"])
        + len(buckets["needs_review"])
    )

    if total_items == 0:
        return f"Hi {name}! 🎓 You have no upcoming deadlines scheduled right now. Enjoy your day!"

    header = f"📅 DeadlineSnap for {name} ({ref_today.strftime('%b %d, %Y')})\n"
    footer = "\nStay on top of your goals! 🚀"

    sections: List[Tuple[str, List[Dict[str, Any]]]] = [
        ("🔴 Due Soon / Overdue", buckets["overdue"] + buckets["due_soon"]),
        ("🟡 This Week (3-7 days)", buckets["this_week"]),
        ("🟢 Later", buckets["later"]),
        ("⚠️ Check these dates manually", buckets["needs_review"]),
    ]

    rendered_sections: List[str] = []
    lines_added_count = 0

    for sec_title, sec_items in sections:
        if not sec_items:
            continue
        sec_lines = [f"\n{sec_title}:"]
        for it in sec_items:
            days_delta = it.get("days_left")
            sec_lines.append(format_deadline_line(it, days_delta))
            lines_added_count += 1
        rendered_sections.append("\n".join(sec_lines))

    # Assemble full message
    full_body = "".join(rendered_sections)
    full_message = f"{header}{full_body}\n{footer}"

    # If within limit, return immediately
    if len(full_message) <= max_chars:
        return full_message

    # Graceful truncation algorithm: build section by section, item by item
    truncated_lines: List[str] = [header]
    current_length = len(header) + len(footer) + 50  # reserve buffer for overflow notice
    included_count = 0

    for sec_title, sec_items in sections:
        if not sec_items:
            continue
        header_line = f"\n{sec_title}:\n"
        if current_length + len(header_line) >= max_chars:
            break
        truncated_lines.append(header_line)
        current_length += len(header_line)

        for it in sec_items:
            days_delta = it.get("days_left")
            line = format_deadline_line(it, days_delta) + "\n"
            if current_length + len(line) >= max_chars:
                break
            truncated_lines.append(line)
            current_length += len(line)
            included_count += 1

    remaining = total_items - included_count
    if remaining > 0:
        truncated_lines.append(f"\n... and {remaining} more deadline(s) not shown.")

    truncated_lines.append(f"\n{footer}")
    return "".join(truncated_lines)


def to_ics(deadlines: List[Dict[str, Any]], calendar_name: str = "DeadlineSnap Schedule") -> str:
    """Generate an RFC 5545 compliant iCalendar (.ics) string for export to Google/Apple Calendar.

    Args:
        deadlines: List of deadline items.
        calendar_name: Name of the calendar.

    Returns:
        Standard iCalendar string content.
    """
    dated, _ = normalize(deadlines)
    now_stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DeadlineSnap//AI Deadline Extractor//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{calendar_name}",
    ]

    for idx, item in enumerate(dated):
        d_obj = item["date_obj"]
        title = item.get("title", "Assignment").replace("\n", " ").strip()
        course = item.get("course", "")
        time_str = item.get("time")
        raw_text = item.get("raw_date_text", "")
        task_type = item.get("type", "assignment").upper()

        summary = f"[{course}] {title}" if course else title
        description = f"Type: {task_type}\\nOriginal: {raw_text}"

        uid = f"deadlinesnap-{d_obj.strftime('%Y%m%d')}-{idx}-{abs(hash(title)) % 10000}@deadlinesnap.local"

        if time_str:
            try:
                t_parts = time_str.split(":")
                hour = int(t_parts[0])
                minute = int(t_parts[1][:2])
                start_dt = datetime(d_obj.year, d_obj.month, d_obj.day, hour, minute)
                end_dt = start_dt + timedelta(hours=1)
                dtstart = f"VALUE=DATE-TIME:{start_dt.strftime('%Y%m%dT%H%M%S')}"
                dtend = f"VALUE=DATE-TIME:{end_dt.strftime('%Y%m%dT%H%M%S')}"
            except (ValueError, IndexError):
                dtstart = f"VALUE=DATE:{d_obj.strftime('%Y%m%d')}"
                dtend = f"VALUE=DATE:{(d_obj + timedelta(days=1)).strftime('%Y%m%d')}"
        else:
            # Full-day event
            dtstart = f"VALUE=DATE:{d_obj.strftime('%Y%m%d')}"
            dtend = f"VALUE=DATE:{(d_obj + timedelta(days=1)).strftime('%Y%m%d')}"

        ics_lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_stamp}",
                f"DTSTART;{dtstart}",
                f"DTEND;{dtend}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                f"CATEGORIES:{task_type}",
                "STATUS:CONFIRMED",
                "END:VEVENT",
            ]
        )

    ics_lines.append("END:VCALENDAR")
    return "\r\n".join(ics_lines)
