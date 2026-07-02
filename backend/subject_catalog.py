"""GGFK subject catalog loader (A1.9).

``ggfk_subject_catalog.json`` (backend root, committed) is the canonical list
of the 78 bulletin subjects, extracted from GGFK's paper bulletin templates.
The Alembic seed migration and the seed-integrity tests both build rows
through this module, so the tests exercise exactly what the migration inserts.
"""

import json
import uuid
from pathlib import Path

CATALOG_PATH = Path(__file__).with_name("ggfk_subject_catalog.json")

# JSON section key -> Subject.section value (== Course.language_group value).
_SECTION_BY_KEY = {"french_section": "FRENCH", "english_section": "ENGLISH"}


def load_catalog(path=CATALOG_PATH):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build_subject_rows(catalog):
    """Flatten the catalog into subjects-table row dicts (fresh ids included)."""
    rows = []
    for level_group, level in catalog["subjects_by_level"].items():
        for section_key, section in _SECTION_BY_KEY.items():
            for entry in level[section_key]:
                rows.append(
                    {
                        "id": uuid.uuid4(),
                        "name_fr": entry["name_fr"],
                        "name_en": entry["name_en"],
                        "section": section,
                        "level_group": level_group,
                        "sort_order": entry["sort_order"],
                        "applicable_classes": entry.get("applicable_classes_override"),
                    }
                )
    return rows
