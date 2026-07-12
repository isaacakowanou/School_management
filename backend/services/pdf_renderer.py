"""WeasyPrint entry points for single and merged official bulletins (A1.7b).

Thin wrapper: report_data dict -> Jinja template -> WeasyPrint -> bytes. No disk
access, no file storage. The logo is embedded as a base64 data URI and skipped
gracefully if the asset is missing. Callers provide stored snapshot data so PDF
downloads remain reproducible after grades change. The template intentionally
omits screen-only ``ai_summary`` and course coefficients; do not add either to
the official layout without an explicit school-format decision.
"""
import base64
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
LOGO_PATH = BASE_DIR / "assets" / "ggfk_logo.png"

_environment = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def _logo_data_uri() -> str | None:
    """Base64 data URI for the school logo, or None if the file is missing."""
    try:
        raw = LOGO_PATH.read_bytes()
    except OSError:
        return None
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def _safe_filename_part(value) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value).strip()).strip("-")
    return cleaned or "unknown"


def _build_pdf_filename(report_data: dict) -> str:
    student = report_data.get("student", {})
    student_number = _safe_filename_part(student.get("student_number", "student"))
    term = _safe_filename_part(report_data.get("term", "term"))
    school_year = _safe_filename_part(report_data.get("school_year", "school-year"))
    return f"{student_number}_{term}_{school_year}.pdf"


def render_report_card_pdf_bytes(report_data: dict) -> bytes:
    """Render the bulletin template to PDF bytes."""
    # Imported lazily so the app (and the rest of the test suite) can load
    # without WeasyPrint's Pango/Cairo system libraries present; only actual
    # PDF rendering needs them.
    from weasyprint import HTML

    template = _environment.get_template("report_card.html")
    html = template.render(report_data=report_data, logo_data_uri=_logo_data_uri())
    return HTML(string=html, base_url=str(BASE_DIR)).write_pdf()


def render_class_bulletins_pdf_bytes(report_data_list: list[dict]) -> bytes:
    """Render every bulletin and merge them into one multi-page PDF.

    WeasyPrint documents merge natively (Document.copy over concatenated
    pages), so a class print run needs no extra dependency and no template
    changes — each bulletin keeps its own @page layout. Rendering is invoked by
    a background job because cost grows with the number of students.
    """
    if not report_data_list:
        raise ValueError("report_data_list cannot be empty")

    from weasyprint import HTML

    template = _environment.get_template("report_card.html")
    logo = _logo_data_uri()
    documents = [
        HTML(
            string=template.render(report_data=report_data, logo_data_uri=logo),
            base_url=str(BASE_DIR),
        ).render()
        for report_data in report_data_list
    ]
    all_pages = [page for document in documents for page in document.pages]
    return documents[0].copy(all_pages).write_pdf()
