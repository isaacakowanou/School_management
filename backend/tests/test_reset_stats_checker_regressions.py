"""Protect reset delivery ordering, current class extrema, and trimester weights.

Each test uses a disposable FK-enforced database and mocked delivery. The original
six repro cases retain their safety assertions unchanged.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from auth import hash_password, verify_password
from constants import TRIMESTER_TERMS
from models import (
    AuditLog, Base, Class, Course, GradeItem, Parent, ReportCard, Student,
    StudentClassAssignment, User,
)
from services import account_security
from services.ai_checker import check_course_grade_data
from services.class_stats import compute_class_stats


YEAR = "2026-2027"
TERM = TRIMESTER_TERMS[0]


@pytest.fixture
def isolated_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        assert db.scalar(text("PRAGMA foreign_keys")) == 1
        try:
            yield db, sessions
        finally:
            db.rollback()
    engine.dispose()


@pytest.mark.parametrize("channel", ["email", "sms"])
def test_reset_commit_failure_does_not_deliver_invalid_credentials(isolated_db, monkeypatch, channel):
    db, sessions = isolated_db
    old_password = "ZZ-TEST-original-password"
    admin = User(name="ZZ-TEST-Admin", role="admin", password_hash="unused")
    parent = Parent(
        user=User(
            name="ZZ-TEST-Parent", role="parent",
            email="ZZ-TEST-parent@example.test" if channel == "email" else None,
            password_hash=hash_password(old_password),
        ),
        phone="+2290100000000",
    )
    db.add_all([admin, parent])
    db.commit()
    user_id = parent.user_id
    old_version = parent.user.token_version
    delivered_passwords = []

    def deliver_email(**kwargs):
        delivered_passwords.append(kwargs["temp_password"])
        return {"success": True}

    def deliver_sms(**kwargs):
        delivered_passwords.append(kwargs["temp_password"])
        return [{"success": True}]

    monkeypatch.setattr(account_security, "send_temporary_password_reset_email", Mock(side_effect=deliver_email))
    monkeypatch.setattr(account_security, "send_temporary_password_reset_sms", Mock(side_effect=deliver_sms))

    def fail_commit(session):
        # Flush real writes, then simulate failure before the transaction commits.
        session.flush()
        raise OperationalError("COMMIT", {}, RuntimeError("ZZ-TEST-commit-failure"))

    event.listen(db, "before_commit", fail_commit)
    try:
        with pytest.raises(OperationalError, match="ZZ-TEST-commit-failure"):
            account_security.reset_profile_password(
                db, profile=parent, actor=admin, entity_type="parent",
            )
    finally:
        event.remove(db, "before_commit", fail_commit)
        db.rollback()

    # A new session proves persisted state, rather than inspecting the dirty ORM object.
    with sessions() as persisted:
        user = persisted.get(User, user_id)
        assert verify_password(old_password, user.password_hash)
        assert user.token_version == old_version
        assert persisted.scalar(select(AuditLog.id)) is None
        invalid_deliveries = sum(
            not verify_password(password, user.password_hash)
            for password in delivered_passwords
        )
    assert invalid_deliveries == 0, (
        f"{channel}: delivered {invalid_deliveries} password(s) that never became valid"
    )


@pytest.mark.parametrize("old_average", [2.0, 19.0], ids=["obsolete-low", "obsolete-high"])
def test_class_extremes_use_one_current_published_report_per_student(isolated_db, old_average):
    db, _ = isolated_db
    school_class = Class(
        name_fr="ZZ-TEST-Class", school_level="college", sort_order=1, school_year=YEAR,
    )
    students = [
        Student(first_name="ZZ-TEST-Student", last_name=str(index), student_number=f"ZZ-TEST-{index}")
        for index in range(2)
    ]
    db.add_all([school_class, *students])
    db.flush()
    for student in students:
        db.add(StudentClassAssignment(
            student=student, school_class=school_class, school_year=YEAR,
            class_name_snapshot=school_class.name_fr,
        ))
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    for student, average, created, status in [
        (students[0], old_average, now - timedelta(days=1), "approved"),
        (students[0], 12.0, now, "sent"),
        (students[1], 14.0, now, "approved"),
    ]:
        db.add(ReportCard(
            student=student, term=TERM, school_year=YEAR, status=status,
            overall_average=average, french_average=average, scale="20",
            created_at=created, approved_at=created,
        ))
    db.commit()

    actual = compute_class_stats(db, students[0], TERM, YEAR)["french"]
    assert actual == {"highest": 14.0, "lowest": 12.0}, (
        f"Obsolete report ({old_average}) still affects class extremes: {actual}"
    )


def test_beninese_checker_accepts_null_item_weights(isolated_db):
    db, _ = isolated_db
    course = Course(
        name="ZZ-TEST-Beninese", code="ZZ-TEST-BENINESE", term=TERM,
        school_year=YEAR, grading_system="BENINESE", language_group="FRENCH",
    )
    for item_type in ("INTERRO", "DEVOIR", "COMPOSITION"):
        course.grade_items.append(GradeItem(
            title=f"ZZ-TEST-{item_type}", item_type=item_type,
            max_score=20, weight=None, term=TERM,
        ))
    db.add(course)
    db.commit()

    # No enrolled students: only the valid definition set is under test.
    warnings = check_course_grade_data(db, course.id)
    assert warnings == []


def test_checker_does_not_combine_weight_totals_across_trimesters(isolated_db):
    db, _ = isolated_db
    course = Course(
        name="ZZ-TEST-Weighted", code="ZZ-TEST-WEIGHTED", term=TERM,
        school_year=YEAR, grading_system="WEIGHTED",
    )
    for term in TRIMESTER_TERMS[:2]:
        for index, weight in enumerate((0.3, 0.3, 0.4)):
            course.grade_items.append(GradeItem(
                title=f"ZZ-TEST-{index}", category="ZZ-TEST-Assessment",
                max_score=20, weight=weight, term=term,
            ))
    db.add(course)
    db.commit()
    for term in TRIMESTER_TERMS[:2]:
        assert sum(item.weight for item in course.grade_items if item.term == term) == pytest.approx(1)

    warnings = check_course_grade_data(db, course.id)
    weight_warnings = [warning["message"] for warning in warnings if warning["warning_type"] == "grade_weight_total"]
    assert weight_warnings == [], f"Each trimester totals 1.0, but checker returned: {weight_warnings}"


@pytest.mark.parametrize("channel", ["email", "sms"])
def test_failed_reset_delivery_keeps_committed_password_and_admin_fallback(isolated_db, monkeypatch, channel):
    db, sessions = isolated_db
    admin = User(name="ZZ-TEST-Admin", role="admin", password_hash="unused")
    parent = Parent(
        user=User(
            name="ZZ-TEST-Parent", role="parent",
            email="ZZ-TEST-parent@example.test" if channel == "email" else None,
            password_hash=hash_password("ZZ-TEST-old-password"),
        ),
        phone="+2290100000000",
    )
    db.add_all([admin, parent])
    db.commit()
    user_id = parent.user_id
    old_version = parent.user.token_version
    observed = {}

    def failed_delivery(**kwargs):
        with sessions() as persisted:
            user = persisted.get(User, user_id)
            observed["password_valid_before_delivery"] = verify_password(
                kwargs["temp_password"], user.password_hash,
            )
            observed["audit_exists_before_delivery"] = persisted.scalar(select(AuditLog.id)) is not None
        raise RuntimeError("ZZ-TEST-delivery-unavailable")

    email = Mock(side_effect=failed_delivery)
    sms = Mock(side_effect=failed_delivery)
    monkeypatch.setattr(account_security, "send_temporary_password_reset_email", email)
    monkeypatch.setattr(account_security, "send_temporary_password_reset_sms", sms)

    result = account_security.reset_profile_password(
        db, profile=parent, actor=admin, entity_type="parent",
    )

    assert observed == {
        "password_valid_before_delivery": True,
        "audit_exists_before_delivery": True,
    }
    assert result[f"{channel}_sent"] is False
    (email if channel == "email" else sms).assert_called_once()
    (sms if channel == "email" else email).assert_not_called()
    with sessions() as persisted:
        user = persisted.get(User, user_id)
        assert verify_password(result["temp_password"], user.password_hash)
        assert user.must_change_password is True
        assert user.token_version == old_version + 1
        audits = persisted.scalars(select(AuditLog)).all()
        assert len(audits) == 1
        assert audits[0].action == "admin_password_reset"
        assert audits[0].new_value[f"{channel}_sent"] is False
        assert result["temp_password"] not in str(audits[0].new_value)


def test_checker_reports_each_invalid_trimester_weight_total(isolated_db):
    db, _ = isolated_db
    course = Course(
        name="ZZ-TEST-Weighted", code="ZZ-TEST-INVALID-WEIGHTS", term=TERM,
        school_year=YEAR, grading_system="WEIGHTED",
    )
    for term, weight in zip(TRIMESTER_TERMS[:2], (0.4, 0.6)):
        for index in range(2):
            course.grade_items.append(GradeItem(
                title=f"ZZ-TEST-{index}", category="ZZ-TEST-Assessment",
                max_score=20, weight=weight, term=term,
            ))
    db.add(course)
    db.commit()

    warnings = check_course_grade_data(db, course.id)
    weight_warnings = [warning for warning in warnings if warning["warning_type"] == "grade_weight_total"]
    assert len(weight_warnings) == 2
    for term, total in zip(TRIMESTER_TERMS[:2], ("0.80", "1.20")):
        matching = [warning for warning in weight_warnings if term in warning["message"]]
        assert len(matching) == 1
        assert total in matching[0]["message"]
