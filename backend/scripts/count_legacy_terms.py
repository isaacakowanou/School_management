"""Report non-canonical trimester labels without modifying the database."""

import sys
from pathlib import Path

from sqlalchemy import inspect, text


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from constants import TRIMESTER_TERMS, normalize_term  # noqa: E402
from database import engine  # noqa: E402


TERM_COLUMN_NAMES = {"term", "trimester"}


def find_term_columns() -> list[tuple[str, str]]:
    inspector = inspect(engine)
    found = []
    for table_name in sorted(inspector.get_table_names()):
        for column in inspector.get_columns(table_name):
            if column["name"].lower() in TERM_COLUMN_NAMES:
                found.append((table_name, column["name"]))
    return found


def main() -> None:
    quote = engine.dialect.identifier_preparer.quote
    canonical = set(TRIMESTER_TERMS)
    print("Canonical values: " + ", ".join(TRIMESTER_TERMS))
    print()

    with engine.connect() as connection:
        term_columns = find_term_columns()
        if not term_columns:
            print("No term/trimester columns found.")
        for table_name, column_name in term_columns:
            table_sql = quote(table_name)
            column_sql = quote(column_name)
            total = connection.execute(text(f"SELECT COUNT(*) FROM {table_sql}")).scalar_one()
            values = connection.execute(
                text(
                    f"SELECT {column_sql}, COUNT(*) AS row_count "
                    f"FROM {table_sql} GROUP BY {column_sql} ORDER BY row_count DESC, {column_sql}"
                )
            ).all()
            legacy = [(value, count) for value, count in values if value not in canonical]
            print(f"{table_name}.{column_name}: total={total}, non_canonical={sum(count for _, count in legacy)}")
            if not legacy:
                print("  (none)")
            for value, count in legacy:
                normalized = normalize_term(value) if isinstance(value, str) else None
                target = f" -> recognized as {normalized!r}" if normalized else " -> unrecognized"
                print(f"  {value!r}: {count}{target}")
            print()

    print("READ-ONLY — no changes made")


if __name__ == "__main__":
    main()
