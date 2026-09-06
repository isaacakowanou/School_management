import unittest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import (
    Base,
    Class,
    Course,
    Parent,
    ReportCard,
    ReportCardCourse,
    ReportConductItem,
    ReportWorkHabitItem,
    Student,
    StudentClassAssignment,
    StudentParent,
    Teacher,
    User,
)
from services.annual_averages import compute_student_annual_averages
from services.class_stats import compute_class_stats
from services.report_builder import build_report_card_data_from_report_card


class WebBulletinParityTests(unittest.TestCase):
    password = "test-password-123"
    school_year = "2026-2027"

    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.db = self.SessionLocal()
        self._seed()

    def tearDown(self):
        self.db.close()
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _user(self, name, email, role):
        user = User(name=name, email=email, password_hash=hash_password(self.password), role=role)
        self.db.add(user)
        return user

    def _report(self, student, term, status, average, *, created_at, course=None):
        report = ReportCard(
            student=student,
            term=term,
            school_year=self.school_year,
            overall_average=average,
            french_average=average,
            bilingual_average=average,
            status=status,
            created_at=created_at,
        )
        self.db.add(report)
        self.db.flush()
        if course is not None:
            self.db.add(
                ReportCardCourse(
                    report_card_id=report.id,
                    course_id=course.id,
                    course_name=course.name,
                    average=average,
                    letter_grade="B",
                    coefficient=3,
                    moy_int=13.0,
                    devoir_score=14.0,
                    mcc=13.5,
                    composition_score=15.0,
                )
            )
        return report

    def _seed(self):
        now = datetime.now()
        self.admin = self._user("ZZ-TEST-Admin", "zz-test-web-admin@example.test", "admin")
        self.parent_user = self._user("ZZ-TEST-Parent", "zz-test-web-parent@example.test", "parent")
        self.other_parent_user = self._user("ZZ-TEST-Other", "zz-test-web-other@example.test", "parent")
        self.teacher_user = self._user("ZZ-TEST-Teacher", "zz-test-web-teacher@example.test", "teacher")
        self.db.flush()
        self.parent = Parent(user=self.parent_user)
        self.other_parent = Parent(user=self.other_parent_user)
        self.teacher = Teacher(user=self.teacher_user, employee_number="ZZ-TEST-WEB-T1")
        self.historical_class = Class(
            name_fr="6ème",
            name_en="JSS1",
            school_level="college",
            sort_order=10,
            school_year=self.school_year,
        )
        self.current_class = Class(
            name_fr="5ème",
            name_en="JSS2",
            school_level="college",
            sort_order=11,
            school_year="2027-2028",
        )
        self.db.add_all([self.parent, self.other_parent, self.teacher, self.historical_class, self.current_class])
        self.db.flush()
        self.student = Student(
            first_name="ZZ-TEST-Web",
            last_name="Student",
            student_number="ZZ-TEST-WEB-001",
            educmaster_number="ZZ-TEST-EDU-001",
            class_id=self.current_class.id,
        )
        self.db.add(self.student)
        self.db.flush()
        self.db.add_all(
            [
                StudentParent(student=self.student, parent=self.parent, relationship="Guardian"),
                StudentClassAssignment(
                    student_id=self.student.id,
                    school_year=self.school_year,
                    class_id=self.historical_class.id,
                    class_name_snapshot=self.historical_class.name_fr,
                ),
            ]
        )
        self.course = Course(
            name="Mathématiques",
            code="ZZ-TEST-WEB-MATH",
            teacher=self.teacher,
            school_class=self.historical_class,
            school_year=self.school_year,
            term="3ème Trimestre",
            language_group="FRENCH",
            grading_system="BENINESE",
            coefficient=3,
        )
        self.db.add(self.course)
        self.db.flush()

        self.first = self._report(
            self.student, "1er Trimestre", "approved", 12.0,
            created_at=now - timedelta(days=90), course=self.course,
        )
        self.second = self._report(
            self.student, "2ème Trimestre", "approved", 14.0,
            created_at=now - timedelta(days=60), course=self.course,
        )
        self.third = self._report(
            self.student, "3ème Trimestre", "sent", 16.0,
            created_at=now - timedelta(days=30), course=self.course,
        )
        self.third.teacher_comment_fr = "Bon travail."
        self.third.teacher_comment_en = "Good work."
        self.third.principal_comment_fr = "Continuez."
        self.third.principal_comment_en = "Keep going."
        self.db.add_all(
            [
                ReportConductItem(report_card=self.third, item_key="controls_talking", letter_grade="A"),
                ReportWorkHabitItem(report_card=self.third, item_key="good_listening", letter_grade="B"),
            ]
        )

        # A newer withdrawn second-term snapshot must not replace the published one.
        self.withdrawn_second = self._report(
            self.student, "2ème Trimestre", "needs_review", 20.0,
            created_at=now - timedelta(days=10), course=self.course,
        )

        # Same-class peers prove unpublished reports do not affect class statistics.
        self.peer_published = Student(first_name="ZZ-TEST-Published", last_name="Peer", student_number="ZZ-TEST-WEB-002")
        self.peer_draft = Student(first_name="ZZ-TEST-Draft", last_name="Peer", student_number="ZZ-TEST-WEB-003")
        self.peer_withdrawn = Student(first_name="ZZ-TEST-Withdrawn", last_name="Peer", student_number="ZZ-TEST-WEB-004")
        self.db.add_all([self.peer_published, self.peer_draft, self.peer_withdrawn])
        self.db.flush()
        for peer in (self.peer_published, self.peer_draft, self.peer_withdrawn):
            self.db.add(
                StudentClassAssignment(
                    student_id=peer.id,
                    school_year=self.school_year,
                    class_id=self.historical_class.id,
                    class_name_snapshot=self.historical_class.name_fr,
                )
            )
        self._report(self.peer_published, "3ème Trimestre", "approved", 17.0, created_at=now, course=None)
        self._report(self.peer_draft, "3ème Trimestre", "draft", 20.0, created_at=now, course=None)
        self._report(self.peer_withdrawn, "3ème Trimestre", "needs_review", 19.0, created_at=now, course=None)

        self.draft = self._report(
            self.student, "3ème Trimestre", "draft", 16.0,
            created_at=now + timedelta(days=1), course=self.course,
        )
        self.withdrawn = self._report(
            self.student, "3ème Trimestre", "needs_review", 16.0,
            created_at=now + timedelta(days=2), course=self.course,
        )
        self.db.commit()

    def _headers(self, user):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _admin_detail(self, report=None):
        target = report or self.third
        return self.client.get(f"/api/v1/reports/admin/{target.id}", headers=self._headers(self.admin))

    def _parent_detail(self, report=None, user=None):
        target = report or self.third
        return self.client.get(
            f"/api/v1/reports/{target.id}",
            headers=self._headers(user or self.parent_user),
        )

    def test_01_final_detail_exposes_complete_annual_averages(self):
        bulletin = self._admin_detail().json()["bulletin"]
        self.assertEqual(bulletin["annual_averages"]["french"], 14.0)
        self.assertEqual(bulletin["annual_averages"]["complete_term_count"], 3)
        self.assertFalse(bulletin["annual_averages"]["is_partial"])

    def test_02_non_final_detail_does_not_expose_annual_values(self):
        bulletin = self._admin_detail(self.first).json()["bulletin"]
        self.assertFalse(bulletin["is_final_trimester"])
        self.assertIsNone(bulletin["annual_averages"]["french"])

    def test_03_partial_annual_exposes_completeness_signal(self):
        self.second.status = "draft"
        self.db.commit()
        bulletin = self._admin_detail().json()["bulletin"]
        self.assertEqual(bulletin["annual_averages"]["complete_term_count"], 2)
        self.assertEqual(bulletin["annual_averages"]["total_term_count"], 3)
        self.assertTrue(bulletin["annual_averages"]["is_partial"])

    def test_04_beninese_course_breakdown_is_exposed(self):
        course = self._admin_detail().json()["bulletin"]["courses_by_language"]["french_courses"][0]
        self.assertEqual(
            {key: course[key] for key in ("moy_int", "devoir_score", "mcc", "composition_score", "average", "letter_grade")},
            {"moy_int": 13.0, "devoir_score": 14.0, "mcc": 13.5, "composition_score": 15.0, "average": 16.0, "letter_grade": "B"},
        )

    def test_05_bulletin_course_payload_has_no_coefficient(self):
        course = self._admin_detail().json()["bulletin"]["courses_by_language"]["french_courses"][0]
        self.assertNotIn("coefficient", course)

    def test_06_appreciation_and_language_group_match_pdf_data(self):
        course = self._admin_detail().json()["bulletin"]["courses_by_language"]["french_courses"][0]
        self.assertEqual(course["language_group"], "FRENCH")
        self.assertTrue(course["appreciation"])

    def test_07_admin_and_parent_receive_identical_bulletin_academic_data(self):
        admin = self._admin_detail().json()["bulletin"]
        parent = self._parent_detail().json()["bulletin"]
        self.assertEqual(admin, parent)

    def test_08_parent_can_read_published_bulletin_parity_payload(self):
        for report in (self.first, self.third):
            with self.subTest(status=report.status):
                response = self._parent_detail(report)
                self.assertEqual(response.status_code, 200)
                self.assertIn("bulletin", response.json())

    def test_09_parent_visibility_boundary_still_blocks_unpublished_and_unrelated_access(self):
        for report in (self.draft, self.withdrawn):
            with self.subTest(status=report.status):
                self.assertEqual(self._parent_detail(report).status_code, 403)
        self.assertEqual(self._parent_detail(user=self.other_parent_user).status_code, 403)
        teacher_response = self.client.get(
            f"/api/v1/reports/{self.third.id}", headers=self._headers(self.teacher_user)
        )
        self.assertEqual(teacher_response.status_code, 403)
        self.assertIn("bulletin", self._parent_detail().json())

    def test_10_class_stats_exclude_draft_and_needs_review_reports(self):
        stats = compute_class_stats(self.db, self.student, "3ème Trimestre", self.school_year)
        self.assertEqual(stats["french"]["highest"], 17.0)
        self.assertEqual(stats["french"]["lowest"], 16.0)

    def test_11_annual_averages_exclude_needs_review_reports(self):
        annual = compute_student_annual_averages(self.db, self.student.id, self.school_year)
        self.assertEqual(annual.french, 14.0)
        self.assertEqual(len(annual.complete_terms), 3)

    def test_12_detail_uses_historical_assignment_not_live_class_pointer(self):
        bulletin = self._admin_detail().json()["bulletin"]
        self.assertEqual(bulletin["school_class"]["name_fr"], "6ème")
        self.assertEqual(bulletin["student"]["class_name"], "6ème")

    def test_13_parent_bulletin_includes_behavior_and_comments(self):
        bulletin = self._parent_detail().json()["bulletin"]
        self.assertEqual(bulletin["teacher_comment_fr"], "Bon travail.")
        self.assertEqual(bulletin["principal_comment_en"], "Keep going.")
        self.assertEqual(next(item for item in bulletin["conduct_items"] if item["key"] == "controls_talking")["letter_grade"], "A")
        self.assertEqual(next(item for item in bulletin["work_habit_items"] if item["key"] == "good_listening")["letter_grade"], "B")

    def test_14_pdf_template_has_no_coefficient_column(self):
        data = build_report_card_data_from_report_card(self.db, self.third)
        environment = Environment(loader=FileSystemLoader("templates"))
        html = environment.get_template("report_card.html").render(report_data=data, logo_data_uri=None)
        self.assertNotIn(">Coef<", html)


if __name__ == "__main__":
    unittest.main()
