"""Generate synthetic test images: clean syllabus, blurry document, and non-document photo."""

import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont


def create_test_images(output_dir: str = "tests/fixtures") -> dict:
    os.makedirs(output_dir, exist_ok=True)
    paths = {}

    # 1. Clean Course Syllabus Image
    img_syllabus = Image.new("RGB", (1000, 800), color="#ffffff")
    draw = ImageDraw.Draw(img_syllabus)
    
    # Draw syllabus layout
    draw.rectangle([(20, 20), (980, 90)], fill="#1e3a8a")
    draw.text((40, 35), "CS 201: Data Structures & Algorithms - Fall 2026", fill="#ffffff")
    draw.text((40, 65), "Instructor: Prof. Turing | Office Hours: Tue/Thu 3 PM", fill="#93c5fd")

    draw.text((40, 110), "COURSE SCHEDULE & UPCOMING DEADLINES", fill="#1e293b")
    draw.line([(40, 135), (960, 135)], fill="#cbd5e1", width=2)

    rows = [
        ("Week 3", "Problem Set 1: Binary Search Trees", "12/10/2026", "23:59", "Assignment (10%)"),
        ("Week 5", "Midterm Exam 1 (In-Class)", "24/10/2026", "14:00", "Exam (25%)"),
        ("Week 7", "Programming Project: Graph Router", "08/11/2026", "23:59", "Project (20%)"),
        ("Week 9", "Quiz 3: Dynamic Programming", "20/11/2026", "10:00", "Quiz (5%)"),
        ("Week 12", "Final Capstone Submission", "10/12/2026", "17:00", "Project (30%)"),
    ]

    y = 160
    draw.text((40, y), "WEEK", fill="#64748b")
    draw.text((140, y), "TASK / EXAM TITLE", fill="#64748b")
    draw.text((540, y), "DUE DATE", fill="#64748b")
    draw.text((680, y), "TIME", fill="#64748b")
    draw.text((800, y), "WEIGHT", fill="#64748b")
    y += 30

    for week, task, due, time_str, weight in rows:
        draw.line([(40, y - 5), (960, y - 5)], fill="#f1f5f9", width=1)
        draw.text((40, y), week, fill="#334155")
        draw.text((140, y), task, fill="#0f172a")
        draw.text((540, y), due, fill="#2563eb")
        draw.text((680, y), time_str, fill="#334155")
        draw.text((800, y), weight, fill="#059669")
        y += 45

    syllabus_path = os.path.join(output_dir, "clean_syllabus.png")
    img_syllabus.save(syllabus_path)
    paths["syllabus"] = syllabus_path

    # 2. Blurry / Partially Degraded Image
    img_blurry = img_syllabus.copy()
    img_blurry = img_blurry.filter(ImageFilter.GaussianBlur(radius=7))
    blurry_path = os.path.join(output_dir, "blurry_syllabus.png")
    img_blurry.save(blurry_path)
    paths["blurry"] = blurry_path

    # 3. Random Non-Document Photo (Abstract Landscape)
    img_nature = Image.new("RGB", (800, 600), color="#87ceeb")
    draw_nat = ImageDraw.Draw(img_nature)
    # Sun
    draw_nat.ellipse([(600, 50), (720, 170)], fill="#f59e0b")
    # Mountains
    draw_nat.polygon([(0, 600), (250, 200), (500, 600)], fill="#475569")
    draw_nat.polygon([(300, 600), (550, 250), (800, 600)], fill="#334155")
    # Green Hills
    draw_nat.ellipse([(-100, 400), (900, 900)], fill="#15803d")
    draw_nat.ellipse([(200, 450), (1000, 950)], fill="#166534")

    nature_path = os.path.join(output_dir, "non_document_nature.png")
    img_nature.save(nature_path)
    paths["nature"] = nature_path

    return paths


if __name__ == "__main__":
    generated = create_test_images()
    print(f"Generated test fixtures: {generated}")
