"""Unit tests for DeadlineSnap deadline normalization, urgency bucketing, and digest creation."""

from datetime import date, timedelta
import pytest

from deadlines import (
    build_digest,
    days_left,
    normalize,
    parse_date_safe,
    split_by_urgency,
    to_ics,
)


def test_parse_date_safe():
    """Test date parsing with various formats and invalid inputs."""
    assert parse_date_safe("2026-10-15") == date(2026, 10, 15)
    assert parse_date_safe("15/10/2026") == date(2026, 10, 15)
    assert parse_date_safe("Oct 15, 2026") == date(2026, 10, 15)
    assert parse_date_safe(None) is None
    assert parse_date_safe("TBA") is None
    assert parse_date_safe("") is None


def test_days_left():
    """Test days_left relative to reference date."""
    ref_today = date(2026, 10, 1)
    assert days_left("2026-10-01", ref_today) == 0
    assert days_left("2026-10-05", ref_today) == 4
    assert days_left("2026-09-25", ref_today) == -6

    with pytest.raises(ValueError):
        days_left("invalid-date", ref_today)


def test_normalize_and_sorting():
    """Test normalization keeps undated items in needs_review and sorts dated items."""
    raw_items = [
        {"title": "Exam 2", "date": "2026-11-01", "course": "CS101"},
        {"title": "Mystery Quiz", "date": None, "raw_date_text": "TBD"},
        {"title": "Assignment 1", "date": "2026-10-05", "course": "CS101"},
    ]
    dated, needs_review = normalize(raw_items)

    assert len(dated) == 2
    assert len(needs_review) == 1
    # Check chronological ordering
    assert dated[0]["title"] == "Assignment 1"
    assert dated[1]["title"] == "Exam 2"
    assert needs_review[0]["title"] == "Mystery Quiz"


def test_split_by_urgency():
    """Test bucketing by urgency relative to reference date."""
    ref_today = date(2026, 10, 10)
    items = [
        {"title": "Overdue Paper", "date": "2026-10-08"},      # -2 days (overdue)
        {"title": "Due Today", "date": "2026-10-10"},          # 0 days (due_soon)
        {"title": "Due Tomorrow", "date": "2026-10-11"},       # 1 day (due_soon)
        {"title": "Quiz This Week", "date": "2026-10-15"},     # 5 days (this_week)
        {"title": "Final Project Later", "date": "2026-11-20"}, # 41 days (later)
        {"title": "Check Syllabus", "date": None},             # needs_review
    ]

    buckets = split_by_urgency(items, today=ref_today)

    assert len(buckets["overdue"]) == 1
    assert buckets["overdue"][0]["title"] == "Overdue Paper"

    assert len(buckets["due_soon"]) == 2
    assert buckets["due_soon"][0]["title"] == "Due Today"
    assert buckets["due_soon"][1]["title"] == "Due Tomorrow"

    assert len(buckets["this_week"]) == 1
    assert buckets["this_week"][0]["title"] == "Quiz This Week"

    assert len(buckets["later"]) == 1
    assert buckets["later"][0]["title"] == "Final Project Later"

    assert len(buckets["needs_review"]) == 1
    assert buckets["needs_review"][0]["title"] == "Check Syllabus"


def test_build_digest_content_and_buckets():
    """Test plain text digest generation with urgency markers."""
    ref_today = date(2026, 10, 10)
    items = [
        {"title": "Problem Set 1", "course": "CS101", "date": "2026-10-11", "time": "23:59"},
        {"title": "Midterm", "course": "MATH54", "date": "2026-10-15"},
        {"title": "Final Paper", "course": "ENG1A", "date": "2026-12-01"},
        {"title": "Guest Lecture", "course": "BIO1", "date": None, "raw_date_text": "Week 7"},
    ]

    digest = build_digest("Alex", items, today=ref_today)

    assert "Alex" in digest
    assert "🔴 Due Soon / Overdue" in digest
    assert "Problem Set 1" in digest
    assert "🟡 This Week" in digest
    assert "Midterm" in digest
    assert "🟢 Later" in digest
    assert "Final Paper" in digest
    assert "⚠️ Check these dates manually" in digest
    assert "Week 7" in digest


def test_build_digest_truncation_under_limit():
    """Test that digest enforces max character length gracefully with many items."""
    ref_today = date(2026, 10, 1)
    # Generate 50 items to exceed 1500 chars
    many_items = []
    for i in range(50):
        d = ref_today + timedelta(days=i)
        many_items.append(
            {
                "title": f"Extremely Long Assignment Title For Testing Purposes Number {i}",
                "course": f"COURSE{i}",
                "date": d.isoformat(),
                "time": "23:59",
            }
        )

    digest = build_digest("Alex", many_items, today=ref_today, max_chars=1200)

    assert len(digest) <= 1200
    assert "... and" in digest
    assert "more deadline(s) not shown." in digest


def test_to_ics_generation():
    """Test generation of valid RFC 5545 iCalendar content."""
    items = [
        {
            "title": "Lab 1",
            "course": "PHYS101",
            "date": "2026-10-20",
            "time": "14:00",
            "type": "assignment",
            "raw_date_text": "Oct 20 2 PM",
        },
        {
            "title": "TBD Task",
            "date": None,
        },
    ]

    ics_content = to_ics(items)

    assert "BEGIN:VCALENDAR" in ics_content
    assert "END:VCALENDAR" in ics_content
    assert "SUMMARY:[PHYS101] Lab 1" in ics_content
    assert "DTSTART" in ics_content
    assert "20261020" in ics_content
    # Undated item should not be in ICS events
    assert "TBD Task" not in ics_content
