"""Find or purge parent/teacher users whose required role profile is missing.

Dry-run is the default. ``--execute`` permanently removes each orphan account,
its reset tokens, and nullable account references while preserving audit rows.
Accounts owning non-nullable deletion-batch history are reported and skipped.
"""

import argparse
import sys
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import and_, or_, select


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import SessionLocal  # noqa: E402
from models import Parent, Teacher, User  # noqa: E402
from services.trash import purge_user_accounts  # noqa: E402


def find_orphaned_role_users(db) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .outerjoin(Parent, Parent.user_id == User.id)
            .outerjoin(Teacher, Teacher.user_id == User.id)
            .where(
                or_(
                    and_(User.role == "parent", Parent.id.is_(None)),
                    and_(User.role == "teacher", Teacher.id.is_(None)),
                )
            )
            .order_by(User.role, User.email, User.id)
        ).all()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Permanently delete detected orphan accounts. Default is dry-run.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        orphaned_users = find_orphaned_role_users(db)
        mode = "EXECUTE" if args.execute else "DRY RUN"
        print(f"{mode}: found {len(orphaned_users)} orphaned parent/teacher user(s).")
        for user in orphaned_users:
            print(f"- {user.id} | {user.role} | {user.email or '(no email)'} | {user.name}")

        if not args.execute:
            print("No changes made. Run again with --execute to purge these accounts.")
            return

        deleted = 0
        skipped = 0
        for user in orphaned_users:
            try:
                with db.begin_nested():
                    purge_user_accounts(db, {user.id})
            except HTTPException as exc:
                skipped += 1
                detail = exc.detail.get("message") if isinstance(exc.detail, dict) else str(exc.detail)
                print(f"SKIPPED {user.id}: {detail}")
            else:
                deleted += 1
        db.commit()
        print(f"Deleted {deleted} orphaned user(s); skipped {skipped}.")


if __name__ == "__main__":
    main()
