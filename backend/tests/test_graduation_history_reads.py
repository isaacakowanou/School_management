from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import (
    Base,
    Class,
    Course,
    CourseResult,
    Enrollment,
    Grade,
    GradeItem,
    Parent,
    ReportCard,
    ReportCardCourse,
    Student,
    StudentParent,
    StudentPassageDecision,
    Teacher,
    User,
)


PASSWORD = "test-password-123"
SOURCE_YEAR = "2026-2027"
TARGET_YEAR = "2027-2028"
FINAL_TERM = "3ème Trimestre"


@pytest.fixture()
def graduation_app():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    db = SessionLocal()
    client = TestClient(app)
    try:
        yield client, db
    finally:
        db.close()
        client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed_graduated_student(db):
    admin = User(
        name="ZZ-TEST Graduation Admin",
        email="zz-test-grad-admin@example.test",
        password_hash=hash_password(PASSWORD),
        role="admin",
    )
    teacher_user = User(
        name="ZZ-TEST Graduation Teacher",
        email="zz-test-grad-teacher@example.test",
        password_hash=hash_password(PASSWORD),
        role="teacher",
    )
    parent_user = User(
        name="ZZ-TEST Graduation Parent",
        email="zz-test-grad-parent@example.test",
        password_hash=hash_password(PASSWORD),
        role="parent",
    )
    db.add_all([admin, teacher_user, parent_user])
    db.flush()

    teacher = Teacher(user=teacher_user, employee_number="ZZ-TEST-GRAD-TCH")
    parent = Parent(user=parent_user, phone="+2290100000000")
    source_class = Class(
        name_fr="Terminale C",
        name_en=None,
        school_level="college",
        stream="C",
        sort_order=18,
        school_year=SOURCE_YEAR,
    )
    target_class = Class(
        name_fr="Terminale C",
        name_en=None,
        school_level="college",
        stream="C",
        sort_order=18,
        school_year=TARGET_YEAR,
    )
    db.add_all([teacher, parent, source_class, target_class])
    db.flush()

    student = Student(
        first_name="ZZ-TEST",
        last_name="Graduated",
        student_number="ZZ-TEST-GRAD-HISTORY",
        school_level="college",
        school_class=source_class,
    )
    db.add(student)
    db.flush()
    db.add(StudentParent(student=student, parent=parent, relationship="Guardian"))

    course = Course(
        name="ZZ-TEST Math",
        code="ZZ-TEST-GRAD-MATH",
        teacher=teacher,
        term=FINAL_TERM,
        school_year=SOURCE_YEAR,
        language_group="FRENCH",
        school_class=source_class,
        coefficient=1,
        grading_system="WEIGHTED",
    )
    db.add(course)
    db.flush()
    enrollment = Enrollment(student=student, course=course)
    db.add(enrollment)
    db.flush()

    item = GradeItem(
        course=course,
        title="ZZ-TEST Final",
        category="Final",
        max_score=20,
        weight=1,
        term=FINAL_TERM,
    )
    db.add(item)
    db.flush()
    grade = Grade(student=student, grade_item=item, score=16, submitted_by_teacher=teacher)
    result = CourseResult(
        student=student,
        course=course,
        term=FINAL_TERM,
        average=16,
        letter_grade="A",
        scale="20",
        calculated_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    report = ReportCard(
        student=student,
        term=FINAL_TERM,
        school_year=SOURCE_YEAR,
        overall_average=16,
        french_average=16,
        english_average=None,
        bilingual_average=None,
        gpa=4.0,
        scale="20",
        status="approved",
        approved_by_admin=admin,
        approved_at=datetime.now(timezone.utc) - timedelta(days=1),
        ai_summary="ZZ-TEST approved final bulletin.",
    )
    db.add_all([grade, result, report])
    db.flush()
    db.add(
        ReportCardCourse(
            report_card=report,
            course=course,
            course_name=course.name,
            average=16,
            letter_grade="A",
            coefficient=1,
        )
    )
    decision = StudentPassageDecision(
        student=student,
        school_year=SOURCE_YEAR,
        target_school_year=TARGET_YEAR,
        from_class=source_class,
        from_class_name=source_class.name_fr,
        result_class=None,
        result_class_name="Diplômé",
        suggested_decision="pass",
        final_decision="graduate",
        annual_french_average=16,
        annual_english_average=None,
        annual_bilingual_average=None,
        incomplete_data=False,
        decided_by_admin=admin,
    )
    db.add(decision)
    student.class_id = None
    student.academic_status = "graduated"
    student.graduated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "admin": admin,
        "teacher_user": teacher_user,
        "parent_user": parent_user,
        "teacher": teacher,
        "parent": parent,
        "student": student,
        "source_class": source_class,
        "target_class": target_class,
        "course": course,
        "enrollment": enrollment,
        "grade_item": item,
        "grade": grade,
        "result": result,
        "report": report,
        "decision": decision,
    }


def test_01_course_roster_history_includes_graduated_student_identity(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)

    response = client.get(
        f"/api/v1/courses/{data['course'].id}/students",
        headers=_headers(client, data["admin"].email),
    )

    assert response.status_code == 200, response.text
    assert any(row["student_number"] == "ZZ-TEST-GRAD-HISTORY" for row in response.json())


def test_02_course_results_include_graduated_student_identity_for_admin(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)

    response = client.get(
        f"/api/v1/course-results/{data['course'].id}",
        headers=_headers(client, data["admin"].email),
    )

    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row["student_name"] == "ZZ-TEST Graduated"
    assert row["student_number"] == "ZZ-TEST-GRAD-HISTORY"
    assert row["academic_status"] == "graduated"


def test_03_course_results_include_graduated_student_identity_for_teacher(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)

    response = client.get(
        f"/api/v1/course-results/{data['course'].id}",
        headers=_headers(client, data["teacher_user"].email),
    )

    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row["student_name"] == "ZZ-TEST Graduated"
    assert row["student_number"] == "ZZ-TEST-GRAD-HISTORY"


def test_04_course_grades_include_graduated_student_identity_for_history(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)

    response = client.get(
        f"/api/v1/courses/{data['course'].id}/grades",
        headers=_headers(client, data["teacher_user"].email),
    )

    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row["student_name"] == "ZZ-TEST Graduated"
    assert row["student_number"] == "ZZ-TEST-GRAD-HISTORY"
    assert row["academic_status"] == "graduated"


def test_05_parent_grades_default_to_graduated_students_enrollment_year(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)
    db.add(
        Class(
            name_fr="6ème",
            name_en=None,
            school_level="college",
            stream=None,
            sort_order=7,
            school_year=TARGET_YEAR,
        )
    )
    db.commit()

    response = client.get(
        f"/api/v1/parents/me/students/{data['student'].id}/grades?term={FINAL_TERM}",
        headers=_headers(client, data["parent_user"].email),
    )

    assert response.status_code == 200, response.text
    assert [row["school_year"] for row in response.json()] == [SOURCE_YEAR]


def test_06_parent_child_card_payload_marks_graduated_display_class(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)

    response = client.get(
        f"/api/v1/parents/{data['parent'].id}/students",
        headers=_headers(client, data["parent_user"].email),
    )

    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row["academic_status"] == "graduated"
    assert row["class_name"] == "Diplômé"


def test_07_admin_students_can_filter_graduated_students(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)

    response = client.get(
        "/api/v1/students?academic_status=graduated",
        headers=_headers(client, data["admin"].email),
    )

    assert response.status_code == 200, response.text
    assert any(row["student_number"] == "ZZ-TEST-GRAD-HISTORY" for row in response.json())


def test_08_parent_approved_reports_remain_visible_for_graduated_child(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)

    response = client.get(
        f"/api/v1/reports/student/{data['student'].id}",
        headers=_headers(client, data["parent_user"].email),
    )

    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row["id"] == str(data["report"].id)
    assert row["student_name"] == "ZZ-TEST Graduated"
    assert row["student_number"] == "ZZ-TEST-GRAD-HISTORY"
    assert row["academic_status"] == "graduated"


def test_09_report_pdf_history_keeps_historical_class_context_after_graduation(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)

    response = client.get(
        f"/api/v1/reports/{data['report'].id}",
        headers=_headers(client, data["parent_user"].email),
    )

    assert response.status_code == 200, response.text
    assert response.json()["student_class_name"] == "Terminale C"


def test_10_direct_student_detail_returns_graduated_student_with_display_context(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)

    response = client.get(
        f"/api/v1/students/{data['student'].id}",
        headers=_headers(client, data["admin"].email),
    )

    assert response.status_code == 200, response.text
    row = response.json()
    assert row["academic_status"] == "graduated"
    assert row["class_name"] == "Diplômé"


def test_11_graduated_final_bulletin_can_be_recalled_regenerated_reapproved_and_resent(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)
    admin_headers = _headers(client, data["admin"].email)

    edit = client.patch(
        f"/api/v1/reports/{data['report'].id}",
        json={"teacher_comment_fr": "ZZ-TEST rappel"},
        headers=admin_headers,
    )
    assert edit.status_code == 200, edit.text
    assert edit.json()["status"] == "needs_review"

    status_response = client.get(
        f"/api/v1/reports/class-status?class_id={data['source_class'].id}&school_year={SOURCE_YEAR}&term={FINAL_TERM}",
        headers=admin_headers,
    )
    assert status_response.status_code == 200, status_response.text
    assert any(
        row["student_number"] == "ZZ-TEST-GRAD-HISTORY" and row["needs_review"]
        for row in status_response.json()["students"]
    )

    regenerated = client.post(f"/api/v1/reports/{data['report'].id}/regenerate", headers=admin_headers)
    assert regenerated.status_code == 200, regenerated.text
    assert regenerated.json()["status"] == "draft"

    approved = client.post(f"/api/v1/reports/{data['report'].id}/approve", headers=admin_headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    with patch(
        "routes.reports.send_report_notification_to_parents",
        return_value=[{"recipient": "zz-test-grad-parent@example.test", "sent": True}],
    ):
        sent = client.post(f"/api/v1/reports/{data['report'].id}/send", headers=admin_headers)

    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"


def test_12a_parent_passage_history_returns_limited_fields_for_linked_child(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)

    response = client.get(
        f"/api/v1/passages/parents/students/{data['student'].id}/history",
        headers=_headers(client, data["parent_user"].email),
    )

    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert set(row) == {"school_year", "from_class_name", "decision", "result_class_name"}
    assert row["from_class_name"] == "Terminale C"
    assert row["decision"] == "graduate"
    assert row["result_class_name"] == "Diplômé"


def test_12b_parent_passage_history_excludes_conseil_internal_fields(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)

    response = client.get(
        f"/api/v1/passages/parents/students/{data['student'].id}/history",
        headers=_headers(client, data["parent_user"].email),
    )

    assert response.status_code == 200, response.text
    forbidden = {
        "annual_french_average",
        "annual_english_average",
        "annual_bilingual_average",
        "incomplete_data",
        "note",
        "decided_by_admin_id",
        "suggested_decision",
        "final_decision",
        "suggested_reason",
        "requires_decision",
    }
    assert forbidden.isdisjoint(response.json()[0])


def test_12c_parent_passage_history_blocks_unlinked_child(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)
    other = Student(
        first_name="ZZ-TEST",
        last_name="Other",
        student_number="ZZ-TEST-GRAD-OTHER",
        school_level="college",
        academic_status="graduated",
    )
    db.add(other)
    db.commit()

    response = client.get(
        f"/api/v1/passages/parents/students/{other.id}/history",
        headers=_headers(client, data["parent_user"].email),
    )

    assert response.status_code == 403, response.text


def test_13_historical_class_context_uses_enrolled_course_class_when_student_class_is_null(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)

    response = client.get(
        f"/api/v1/course-results/{data['course'].id}",
        headers=_headers(client, data["admin"].email),
    )

    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row["historical_class_name"] == "Terminale C"
    assert row["historical_school_year"] == SOURCE_YEAR


def test_14_historical_class_context_survives_soft_deleted_and_purged_past_course(graduation_app):
    client, db = graduation_app
    data = _seed_graduated_student(db)
    data["course"].deleted_at = datetime.now(timezone.utc)
    db.commit()

    soft_deleted = client.get(
        f"/api/v1/reports/{data['report'].id}",
        headers=_headers(client, data["parent_user"].email),
    )
    assert soft_deleted.status_code == 200, soft_deleted.text
    assert soft_deleted.json()["student_class_name"] == "Terminale C"

    db.delete(data["grade"])
    db.delete(data["result"])
    for snapshot_course in data["report"].courses:
        db.delete(snapshot_course)
    db.delete(data["grade_item"])
    db.delete(data["enrollment"])
    db.delete(data["course"])
    db.commit()

    purged = client.get(
        f"/api/v1/reports/{data['report'].id}",
        headers=_headers(client, data["parent_user"].email),
    )
    assert purged.status_code == 200, purged.text
    assert purged.json()["student_class_name"] == "Terminale C"
