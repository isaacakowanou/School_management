"""Implement deterministic numeric grading without database or AI calls.

Explicit course grading_system takes precedence; French-college inference is
only a fallback for legacy setup. Beninese mode normalizes to /20 and computes
Moy_Int from Interros, MCC from Moy_Int/Devoir, then Moy from MCC/Composition;
weighted courses use their separate item-weight calculation.
Academic letters use nine bands, while the retained GPA helper uses its distinct
legacy five-band /100 conversion rather than those academic letters.
"""


WEIGHT_TOLERANCE_MIN = 0.999
WEIGHT_TOLERANCE_MAX = 1.001

# Course averages are computed and stored on a /20 scale (Beninese system).
GRADE_SCALE_MAX = 20.0

# GPA still uses the legacy /100 bridge (scale /20 × 5 → map to A/B/C/D/F).
# This compatibility mapping is distinct from the nine academic letter bands.
LETTER_GRADE_SCALE_FACTOR = 100.0 / GRADE_SCALE_MAX  # 5.0


def _get_grade_value(grade, field_name):
    if isinstance(grade, dict):
        if field_name not in grade:
            raise ValueError(f"grade is missing required field: {field_name}")
        return grade[field_name]

    if not hasattr(grade, field_name):
        raise ValueError(f"grade is missing required field: {field_name}")

    return getattr(grade, field_name)


def _as_number(value, field_name):
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc


def calculate_course_average(grades):
    """Return a weighted /20 average, rounded to two decimals, from grade dictionaries or objects.

    Each item supplies score, max_score, and weight. Normalize scores before
    weighting; reject empty input, invalid score ranges, nonpositive maxima, and
    weights outside 0..1 or totals outside the configured tolerance.
    """
    if not grades:
        raise ValueError("grades list cannot be empty")

    total = 0.0
    total_weight = 0.0

    for grade in grades:
        score = _as_number(_get_grade_value(grade, "score"), "score")
        max_score = _as_number(_get_grade_value(grade, "max_score"), "max_score")
        weight = _as_number(_get_grade_value(grade, "weight"), "weight")

        if max_score <= 0:
            raise ValueError("max_score must be greater than 0")
        if score < 0:
            raise ValueError("score must be greater than or equal to 0")
        if score > max_score:
            raise ValueError("score cannot be greater than max_score")
        if weight < 0 or weight > 1:
            raise ValueError("weight must be between 0 and 1")

        normalized = score / max_score * GRADE_SCALE_MAX
        total += normalized * weight
        total_weight += weight

    if not WEIGHT_TOLERANCE_MIN <= total_weight <= WEIGHT_TOLERANCE_MAX:
        raise ValueError("grade weights must total 1.0")

    return round(total, 2)


def get_letter_grade(average):
    """Convert a /20 average to a BISC 9-letter grade code."""
    average = _as_number(average, "average")

    if average >= 19:
        return "A+"
    if average >= 17:
        return "A"
    if average >= 15:
        return "B+"
    if average >= 13:
        return "B"
    if average >= 11:
        return "C+"
    if average >= 9:
        return "C"
    if average >= 7:
        return "D"
    if average >= 4:
        return "E"
    return "F"


def normalize_average_to_20(average, scale):
    """Return the numeric average on /20, converting only an explicit scale of '100'.

    Legacy /100 values are multiplied by 0.2 and rounded to two decimals. Other
    scale values pass through unchanged so callers can combine stored generations
    without applying that conversion twice.
    """
    average = _as_number(average, "average")
    if scale == "100":
        return round(average * 0.2, 2)
    return average



def calculate_overall_average(course_averages):
    """Return the arithmetic mean of numeric course averages, rounded to two decimals.

    Empty input raises ValueError; this does not apply coefficients or change scale.
    """
    if not course_averages:
        raise ValueError("course averages list cannot be empty")

    averages = [_as_number(average, "course average") for average in course_averages]
    return round(sum(averages) / len(averages), 2)


def is_beninese_mode(course) -> bool:
    """Return whether the course uses the Beninese calculation chain.

    An explicit grading_system takes precedence, even when language or level
    suggests otherwise. Only when it is absent does a French-track college class
    select the Beninese engine through legacy inference.
    """
    grading_system = getattr(course, "grading_system", None)
    if grading_system is not None:
        return grading_system == "BENINESE"
    return (
        getattr(course, "language_group", None) == "FRENCH"
        and getattr(course, "school_class", None) is not None
        and getattr(course.school_class, "school_level", None) == "college"
    )


def calculate_beninese_average(interros, devoir, composition):
    """Apply the official Beninese Moy_Int -> MCC -> Moy chain on /20.

    Each item must be a dict or object with score and max_score fields.
    Step 1: Moy_Int = arithmetic mean of every Interro.
    Step 2: MCC = (Moy_Int + Devoir) / 2.
    Step 3: Moy = (MCC + Composition) / 2.

    These nested equal means are the Benin Ministry convention implemented for
    GGFK. Do not flatten the inputs or assign direct weights to Interros,
    Devoir, and Composition; that would produce a different official result.
    Returns (moy, moy_int, mcc), all rounded to 2 decimal places.
    """
    if not interros:
        raise ValueError("At least one interro is required for the Beninese formula")

    def norm(item):
        s = _as_number(_get_grade_value(item, "score"), "score")
        m = _as_number(_get_grade_value(item, "max_score"), "max_score")
        if m <= 0:
            raise ValueError("max_score must be greater than 0")
        if s < 0 or s > m:
            raise ValueError("score must be between 0 and max_score")
        return s / m * GRADE_SCALE_MAX

    moy_int = sum(norm(i) for i in interros) / len(interros)
    mcc = (moy_int + norm(devoir)) / 2
    moy = (mcc + norm(composition)) / 2
    return round(moy, 2), round(moy_int, 2), round(mcc, 2)


def calculate_weighted_average(course_averages, coefficients):
    """Return a coefficient-weighted mean, rounded to two decimals, for paired lists.

    Require nonempty averages, matching list lengths, and a positive coefficient
    total. Individual coefficient signs and average ranges are not checked here.
    """
    if not course_averages:
        raise ValueError("course averages list cannot be empty")
    if len(course_averages) != len(coefficients):
        raise ValueError("course_averages and coefficients must have the same length")

    averages = [_as_number(a, "course average") for a in course_averages]
    coefs = [_as_number(c, "coefficient") for c in coefficients]
    total_coef = sum(coefs)
    if total_coef <= 0:
        raise ValueError("sum of coefficients must be greater than 0")

    return round(sum(a * c for a, c in zip(averages, coefs)) / total_coef, 2)


def calculate_gpa(course_averages):
    """Return the legacy five-band GPA mean, rounded to two decimals, for /20 averages.

    Scale each value to /100 and use A/B/C/D/F at 90/80/70/60 for 4/3/2/1/0
    points. This is separate from the nine-band academic letters returned by
    get_letter_grade. Empty input raises ValueError.
    """
    if not course_averages:
        raise ValueError("course averages list cannot be empty")

    _grade_points = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}

    def _legacy_letter(avg):
        # Preserve the legacy GPA mapping independently of academic letters.
        scaled = _as_number(avg, "course average") * LETTER_GRADE_SCALE_FACTOR
        if scaled >= 90: return "A"
        if scaled >= 80: return "B"
        if scaled >= 70: return "C"
        if scaled >= 60: return "D"
        return "F"

    points = [_grade_points[_legacy_letter(average)] for average in course_averages]
    return round(sum(points) / len(points), 2)
