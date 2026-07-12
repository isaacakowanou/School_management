"""Canonical GGFK school taxonomy and bulletin reference data.

This module owns the locked Nursery/Primary/Collège class taxonomy, bilingual
French/JSS naming, second-cycle C/D streams, the nine-letter /20 grading key,
conduct/work-habit definitions, and the three canonical trimester strings.
Term-bearing tables must use exactly ``1er Trimestre``, ``2ème Trimestre``, or
``3ème Trimestre``; ``scripts/count_legacy_terms.py`` audits historical drift.

Conduct and work-habit items store letter assessments directly. They share the
A+/A/B+/B/C+/C/D/E/F vocabulary with academic results but are not numeric
course grades and must not feed course-average calculations.
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

# Locked 18-class GGFK taxonomy (A1.8/A1.10). Nursery, Primary, and Collège
# are distinct school stages; Collège uses dual French/English names and C/D
# streams at 1ère/Terminale. These are school-owned names, not display aliases
# that may be freely consolidated. Single source of truth: the
# subject level-group mapping derives from it and the bulk-create action seeds
# from it. name_en is the anglophone track name printed on the bulletin header
# (e.g. "JSS4/3eme"); nursery and primary bulletins print the French name only,
# so name_en None is canon there, not missing data. sort_order is the position
# within the class's school level.
GGFK_CLASSES = [
    {"name_fr": "Pré-maternelle", "name_en": None, "school_level": "maternelle", "level_group": "NURSERY", "stream": None, "sort_order": 1},
    {"name_fr": "Maternelle 1", "name_en": None, "school_level": "maternelle", "level_group": "NURSERY", "stream": None, "sort_order": 2},
    {"name_fr": "Maternelle 2", "name_en": None, "school_level": "maternelle", "level_group": "NURSERY", "stream": None, "sort_order": 3},
    {"name_fr": "CI", "name_en": None, "school_level": "primaire", "level_group": "PRIMARY", "stream": None, "sort_order": 1},
    {"name_fr": "CP", "name_en": None, "school_level": "primaire", "level_group": "PRIMARY", "stream": None, "sort_order": 2},
    {"name_fr": "CE1", "name_en": None, "school_level": "primaire", "level_group": "PRIMARY", "stream": None, "sort_order": 3},
    {"name_fr": "CE2", "name_en": None, "school_level": "primaire", "level_group": "PRIMARY", "stream": None, "sort_order": 4},
    {"name_fr": "CM1", "name_en": None, "school_level": "primaire", "level_group": "PRIMARY", "stream": None, "sort_order": 5},
    {"name_fr": "CM2", "name_en": None, "school_level": "primaire", "level_group": "PRIMARY", "stream": None, "sort_order": 6},
    {"name_fr": "6ème", "name_en": "JSS1", "school_level": "college", "level_group": "COLLEGE_FIRST_CYCLE", "stream": None, "sort_order": 1},
    {"name_fr": "5ème", "name_en": "JSS2", "school_level": "college", "level_group": "COLLEGE_FIRST_CYCLE", "stream": None, "sort_order": 2},
    {"name_fr": "4ème", "name_en": "JSS3", "school_level": "college", "level_group": "COLLEGE_FIRST_CYCLE", "stream": None, "sort_order": 3},
    # GGFK genuinely uses JSS4 for 3ème (bulletin header "JSS4/3eme").
    {"name_fr": "3ème", "name_en": "JSS4", "school_level": "college", "level_group": "COLLEGE_FIRST_CYCLE", "stream": None, "sort_order": 4},
    {"name_fr": "2nde", "name_en": "SS1", "school_level": "college", "level_group": "COLLEGE_SECOND_CYCLE", "stream": None, "sort_order": 5},
    # Streamed classes carry the full name in name_fr (subject filtering matches
    # on it) with the stream also populated on its own column.
    {"name_fr": "1ère C", "name_en": "SS2", "school_level": "college", "level_group": "COLLEGE_SECOND_CYCLE", "stream": "C", "sort_order": 6},
    {"name_fr": "1ère D", "name_en": "SS2", "school_level": "college", "level_group": "COLLEGE_SECOND_CYCLE", "stream": "D", "sort_order": 7},
    {"name_fr": "Terminale C", "name_en": "SS3", "school_level": "college", "level_group": "COLLEGE_SECOND_CYCLE", "stream": "C", "sort_order": 8},
    {"name_fr": "Terminale D", "name_en": "SS3", "school_level": "college", "level_group": "COLLEGE_SECOND_CYCLE", "stream": "D", "sort_order": 9},
]

# Taxonomy class names grouped by subject level group, derived from
# GGFK_CLASSES. Used to resolve which catalog subjects apply to a class:
# Subject.applicable_classes null means "every class in the subject's
# level_group". Mirrors the applicable_classes lists in
# ggfk_subject_catalog.json (seed test asserts the two stay in sync).
CLASSES_BY_LEVEL_GROUP = {}
for _entry in GGFK_CLASSES:
    CLASSES_BY_LEVEL_GROUP.setdefault(_entry["level_group"], []).append(_entry["name_fr"])

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

# Exactly three canonical cycles per school year. Persist only these strings;
# aliases below exist solely to recognize legacy data, not to permit new labels.
# scripts/count_legacy_terms.py provides the read-only production drift audit.
TRIMESTER_TERMS = ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"]
FINAL_TRIMESTER_NUMBER = len(TRIMESTER_TERMS)  # 3

# A1.7c: legacy free-text term variants -> canonical trimester. Covers only
# forms the old UI suggestions (Fall / Spring / Summer / Trimester N) and
# French typing habits could have produced; anything else is deliberately NOT
# mapped (the normalization migration leaves it untouched and reports it).
# Keys are matching keys (accent/case/whitespace-insensitive).
_TERM_VARIANTS = {
    "1er Trimestre": ["1e trimestre", "trimestre 1", "trimester 1", "term 1", "1st term", "1er", "fall"],
    "2ème Trimestre": ["2e trimestre", "trimestre 2", "trimester 2", "term 2", "2nd term", "2eme", "spring"],
    # Summer -> 3ème: the old suggestions offered Fall/Spring/Summer as the
    # trio, so Summer can only have meant the third trimester.
    "3ème Trimestre": ["3e trimestre", "trimestre 3", "trimester 3", "term 3", "3rd term", "3eme", "summer"],
}

_CANONICAL_TERM_BY_KEY = {}
for _canonical, _variants in _TERM_VARIANTS.items():
    # normalize_class_name is a general accent/case/whitespace normalizer;
    # reused here so "2ème", "2eme" and "2EME " all key identically.
    _CANONICAL_TERM_BY_KEY[normalize_class_name(_canonical)] = _canonical
    for _variant in _variants:
        _CANONICAL_TERM_BY_KEY[_variant] = _canonical


def normalize_term(value):
    """Map a term string to its canonical trimester value, else None.

    Canonical values pass through; recognized legacy variants map onto their
    trimester; unknown strings return None (callers must not guess).
    """
    return _CANONICAL_TERM_BY_KEY.get(normalize_class_name(value))

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
