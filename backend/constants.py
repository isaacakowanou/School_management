"""Reference data for report-card conduct and work-habit items (A1.7a).

Each item is ``(item_key, label_en, label_fr)``. ``item_key`` is what gets
stored in the ``report_conduct_items`` / ``report_work_habit_items`` tables; the
labels are display data owned by the backend and returned in the report
response so the admin UI never has to duplicate them.
"""

import unicodedata

CONDUCT_ITEMS = [
    ("controls_talking", "Controls talking", "Contrôle de langage"),
    ("respects_authority", "Respects Authority", "Respect de l'autorité"),
    ("practices_self_control", "Practices self control", "Maîtrise de soi"),
    ("follows_directions", "Follow directions", "Suivi des consignes"),
    ("behaves_in_dismissal", "Behaves in dismissal group", "Attitude à la fin des classes"),
    ("behaves_in_cafeteria", "Behaves in cafeteria", "Attitude pendant la récréation et à la cantine"),
]

WORK_HABIT_ITEMS = [
    ("good_listening", "Practice good listening habits", "Pratique une bonne écoute"),
    ("works_with_others", "Works and plays well with others", "Bonne collaboration avec les autres"),
    ("uses_time_well", "Makes good use of time", "Fait bon usage du temps"),
    ("works_independently", "Works independently", "Travail de façon indépendante"),
    ("takes_pride", "Takes pride in his/her work", "Fier de son travail"),
    ("completes_on_time", "Completes work in a timely manner", "Fini le travail à temps"),
    ("returns_homework", "Returns homework daily", "Fait et ramène les devoirs de maison chaque jour"),
]

CONDUCT_ITEM_KEYS = [key for key, _, _ in CONDUCT_ITEMS]
WORK_HABIT_ITEM_KEYS = [key for key, _, _ in WORK_HABIT_ITEMS]


# --- A1.9 Subject catalog reference data ---

# Locked 18-class GGFK taxonomy grouped by subject level group. Used to resolve
# which catalog subjects apply to a class: Subject.applicable_classes null
# means "every class in the subject's level_group". Mirrors the
# applicable_classes lists in ggfk_subject_catalog.json (seed test asserts the
# two stay in sync).
CLASSES_BY_LEVEL_GROUP = {
    "NURSERY": ["Pré-maternelle", "Maternelle 1", "Maternelle 2"],
    "PRIMARY": ["CI", "CP", "CE1", "CE2", "CM1", "CM2"],
    "COLLEGE_FIRST_CYCLE": ["6ème", "5ème", "4ème", "3ème"],
    "COLLEGE_SECOND_CYCLE": ["2nde", "1ère C", "1ère D", "Terminale C", "Terminale D"],
}

def normalize_class_name(name):
    """Accent-, case-, and whitespace-insensitive key for class-name matching.

    Class rows are created by admins (A1.8), so the same taxonomy class shows
    up as "6ème", "6eme", or "6EME " depending on who typed it; taxonomy
    lookups must not depend on the spelling.
    """
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(stripped.lower().split())


_LEVEL_GROUP_BY_NORMALIZED_CLASS_NAME = {
    normalize_class_name(class_name): level_group
    for level_group, class_names in CLASSES_BY_LEVEL_GROUP.items()
    for class_name in class_names
}


def level_group_for_class_name(name):
    """Resolve a class name to its subject level group, else None."""
    return _LEVEL_GROUP_BY_NORMALIZED_CLASS_NAME.get(normalize_class_name(name))


# --- A1.7b Collège bulletin (PDF) reference data ---

# Letter grade -> French appreciation shown on the academic table.
APPRECIATION_BY_LETTER = {
    "A+": "EXCELLENT",
    "A": "TRES SATISFAISANT",
    "B+": "SATISFAISANT",
    "B": "ACCEPTABLE",
    "C+": "PEUT MIEUX FAIRE",
    "C": "INSUFFISANT",
    "D": "TRES INSUFFISANT",
    "E": "FAIBLE",
    "F": "TRES FAIBLE",
}

# Footer grading-key legend (BISC 9-letter /20 bands, A1.3).
GRADING_KEY_LEGEND = (
    "Grading key/Code: A+ = 20-19; A = 18-17; B+ = 16-15; B = 14-13; "
    "C+ = 12-11; C = 10-9; D = 8-7; E = 6-4; F = 3-0"
)

# Canonical GGFK trimester term values; list position == trimester number.
TRIMESTER_TERMS = ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"]
FINAL_TRIMESTER_NUMBER = len(TRIMESTER_TERMS)  # 3

TERM_ORDINAL_EN = {1: "1st", 2: "2nd", 3: "3rd"}
TERM_ORDINAL_FR = {1: "1er", 2: "2ème", 3: "3ème"}

# Hardcoded date ranges per trimester (english, french); real academic-calendar
# handling is a future ticket.
TRIMESTER_DATE_RANGES = {
    1: ("Sept 15 - Dec 20", "15 Sept - 20 Déc"),
    2: ("Jan 8 - Mar 28", "8 Janv - 28 Mars"),
    3: ("Apr 16 - Jun 5", "16 Avr - 5 Juin"),
}


def appreciation_for_letter(letter_grade):
    """French appreciation for a letter grade; '' when unknown or None."""
    return APPRECIATION_BY_LETTER.get(letter_grade or "", "")


def term_number(term):
    """Resolve a term string to a trimester number (1/2/3), else None.

    Match order: exact -> case-insensitive -> loose 'contains the digit'.
    Unrecognized terms return None so the template degrades to '-'.
    """
    if not term:
        return None
    for index, value in enumerate(TRIMESTER_TERMS, start=1):
        if term == value:
            return index
    lowered = term.strip().lower()
    for index, value in enumerate(TRIMESTER_TERMS, start=1):
        if lowered == value.lower():
            return index
    for digit in ("1", "2", "3"):
        if digit in term:
            return int(digit)
    return None
