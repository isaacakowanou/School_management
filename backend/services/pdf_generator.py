import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"


def _safe_filename_part(value) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value).strip())
    cleaned = cleaned.strip("-")
    return cleaned or "unknown"


def _build_pdf_filename(report_data: dict) -> str:
    student = report_data.get("student", {})
    student_number = _safe_filename_part(student.get("student_number", "student"))
    term = _safe_filename_part(report_data.get("term", "term"))
    school_year = _safe_filename_part(report_data.get("school_year", "school-year"))
    return f"{student_number}_{term}_{school_year}.pdf"


def _render_report_html(report_data: dict) -> str:
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = environment.get_template("report_card.html")
    return template.render(report_data=report_data)


def _build_pdf_story(report_data: dict) -> list:
    styles = getSampleStyleSheet()
    student = report_data["student"]
    student_name = f"{student['first_name']} {student['last_name']}"

    story = [
        Paragraph("School AI System", styles["Title"]),
        Paragraph("Student Report Card", styles["Heading2"]),
        Spacer(1, 12),
        Table(
            [
                ["Student Name", student_name],
                ["Student Number", student["student_number"]],
                ["Grade Level", student["grade_level"]],
                ["Term / School Year", f"{report_data['term']} / {report_data['school_year']}"],
            ],
            colWidths=[144, 360],
        ),
        Spacer(1, 18),
        Paragraph("Academic Results", styles["Heading2"]),
    ]

    course_rows = [["Course Code", "Course Name", "Average", "Letter Grade"]]
    for course in report_data["courses"]:
        course_rows.append(
            [
                course["course_code"],
                course["course_name"],
                f"{course['average']:.2f}",
                course["letter_grade"],
            ]
        )

    course_table = Table(course_rows, colWidths=[94, 250, 80, 80])
    course_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f4f8")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#323f4b")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bcccdc")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (2, 1), (2, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([course_table, Spacer(1, 18)])

    summary_table = Table(
        [
            ["Overall Average", f"{report_data['overall_average']:.2f}"],
            ["GPA", f"{report_data['gpa']:.2f}"],
        ],
        colWidths=[150, 100],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bcccdc")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(summary_table)

    if report_data.get("ai_summary"):
        story.extend(
            [
                Spacer(1, 18),
                Paragraph("Academic Summary", styles["Heading2"]),
                Paragraph(report_data["ai_summary"], styles["BodyText"]),
            ]
        )

    footer_parts = []
    if report_data.get("status"):
        footer_parts.append(f"Status: {report_data['status']}")
    if report_data.get("generated_date"):
        footer_parts.append(f"Date: {report_data['generated_date']}")
    if footer_parts:
        story.extend(
            [
                Spacer(1, 18),
                Paragraph(" | ".join(footer_parts), styles["BodyText"]),
            ]
        )

    return story


def generate_report_card_pdf(report_data: dict, output_dir: str = "storage/pdfs") -> str:
    output_path = Path(output_dir)
    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path
    output_path.mkdir(parents=True, exist_ok=True)

    pdf_path = output_path / _build_pdf_filename(report_data)
    # Validate that the HTML template renders successfully before writing the PDF.
    _render_report_html(report_data)

    document = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54,
    )
    document.build(_build_pdf_story(report_data))

    return str(pdf_path)
