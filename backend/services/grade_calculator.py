"""Deterministic grade calculation helpers."""


WEIGHT_TOLERANCE_MIN = 0.999
WEIGHT_TOLERANCE_MAX = 1.001

# Course averages are computed and stored on a /20 scale (Beninese system).
GRADE_SCALE_MAX = 20.0

# A1.2 bridge: the letter-grade and GPA thresholds still use the legacy /100
# scale. A /20 average is scaled back up by this factor before being mapped to
# a letter, so letter grades and GPA stay byte-for-byte identical to the old
# /100 behavior. A1.3 will rescale the letter thresholds to /20 and remove this
# bridge entirely.
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
    """Calculate a weighted course average on the /20 scale.

    Each grade item's raw score is normalized to /20 via (score / max_score) * 20,
    so items with any max_score (20, 10, 100, ...) contribute correctly.
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
    """Convert a /100 average to the current letter-grade scale.

    A1.2 note: thresholds are still on the legacy /100 scale. Course averages
    are now on /20, so callers go through letter_grade_for_course_average(),
    which scales the value up first. A1.3 will rescale these thresholds to /20.
    """
    average = _as_number(average, "average")

    if average >= 90:
        return "A"
    if average >= 80:
        return "B"
    if average >= 70:
        return "C"
    if average >= 60:
        return "D"
    return "F"


def normalize_average_to_20(average, scale):
    """Return a course average on the /20 scale.

    Historical results stored on the legacy /100 scale (scale == "100") are
    scaled down by 0.2; results already on /20 (the default) pass through
    unchanged. Used by the report builder so a report mixing pre- and
    post-A1.2 course results is always computed on a single /20 scale.
    """
    average = _as_number(average, "average")
    if scale == "100":
        return round(average * 0.2, 2)
    return average


def letter_grade_for_course_average(course_average):
    """Map a /20 course average to a letter grade.

    A1.2 bridge: get_letter_grade still uses /100 thresholds, so scale the /20
    average up by LETTER_GRADE_SCALE_FACTOR before mapping. This keeps letters
    identical to the old /100 behavior. A1.3 will rescale get_letter_grade to
    /20 and let callers use it directly, removing this bridge.
    """
    scaled = _as_number(course_average, "course average") * LETTER_GRADE_SCALE_FACTOR
    return get_letter_grade(scaled)


def calculate_overall_average(course_averages):
    """Calculate the arithmetic mean of course averages."""
    if not course_averages:
        raise ValueError("course averages list cannot be empty")

    averages = [_as_number(average, "course average") for average in course_averages]
    return round(sum(averages) / len(averages), 2)


def calculate_gpa(course_averages):
    """Calculate GPA from course averages using the current letter-grade scale."""
    if not course_averages:
        raise ValueError("course averages list cannot be empty")

    grade_points = {
        "A": 4.0,
        "B": 3.0,
        "C": 2.0,
        "D": 1.0,
        "F": 0.0,
    }

    points = [grade_points[letter_grade_for_course_average(average)] for average in course_averages]
    return round(sum(points) / len(points), 2)
