"""WeasyPrint HTML -> PDF renderer for the GGFK Collège bulletin (A1.7b).

Thin wrapper: report_data dict -> Jinja template -> WeasyPrint -> bytes. No disk
access, no file storage. The logo is embedded as a base64 data URI and skipped
gracefully if the asset is missing.
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
