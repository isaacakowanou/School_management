import os


DEFAULT_MODEL = "gpt-4o-mini"


def _create_openai_client(api_key: str):
    from openai import OpenAI

    return OpenAI(api_key=api_key)


def _scale_suffix(scale) -> str:
    # Label numbers so the model is not confused about the grading scale.
    return "/100" if scale == "100" else "/20"


def _format_course_lines(courses: list[dict], scale_suffix: str) -> str:
    return "\n".join(
        f"- {course['course_name']}: {course['average']:.2f}{scale_suffix}, {course['letter_grade']}"
        for course in courses
    )


def _format_optional_number(value, scale_suffix: str = "") -> str:
    if value is None:
        return "Not provided"
    return f"{value:.2f}{scale_suffix}"


def _build_summary_prompt(report_data: dict) -> str:
    student = report_data["student"]
    student_name = f"{student['first_name']} {student['last_name']}"
    scale_suffix = _scale_suffix(report_data.get("scale"))

    return f"""Write a short parent-friendly academic summary using only the data below.

Student name: {student_name}
Grade level: {student['grade_level']}
Term: {report_data['term']}
School year: {report_data['school_year']}
Averages use a {scale_suffix} scale.
Courses:
{_format_course_lines(report_data['courses'], scale_suffix)}
Overall average: {_format_optional_number(report_data['overall_average'], scale_suffix)}
GPA: {_format_optional_number(report_data['gpa'])}

Rules:
- Plain text only.
- One paragraph.
- 2-4 sentences.
- Under 100 words.
- Parent-friendly tone.
- No jargon.
- Do not invent facts.
- Do not change or recalculate grades.
- Do not mention exact letter grades unless already provided and necessary.
- Do not mention discipline, attendance, finance, health, personality, behavior, or effort.
- Mention strengths and areas for improvement only when supported by the course data."""


def generate_report_summary(report_data: dict) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required to generate an AI summary")

    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    client = _create_openai_client(api_key)
    prompt = _build_summary_prompt(report_data)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You write concise, accurate academic summaries for parents. "
                    "Use only provided data and never alter official grades."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=150,
    )

    summary = response.choices[0].message.content.strip()
    if not summary:
        raise ValueError("AI summary response was empty")

    return summary
