import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import (
    AuditLog,
    Base,
    Class,
    Course,
    CourseResult,
    Enrollment,
    ReportCard,
    Student,
    Teacher,
    User,
)

YEAR = "2026-2027"
TERM = "1er Trimestre"


class ReportBatchTests(unittest.TestCase):
    password = "test-password-123"

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

    def _user(self, *, name, email, role) -> User:
        user = User(name=name, email=email, password_hash=hash_password(self.password), role=role)
        self.db.add(user)
        return user

    def _seed(self):
        self.admin_user = self._user(name="Admin", email="admin-batch@example.test", role="admin")
        self.teacher_user = self._user(name="Teacher", email="teacher-batch@example.test", role="teacher")
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-BATCH-1")
        self.db.add(self.teacher)

        self.terminale = Class(name_fr="Terminale C", school_level="college", sort_order=8, school_year=YEAR)
        self.db.add(self.terminale)
        self.db.flush()

        self.course = Course(
            name="Mathématique",
            code="BATCH-MATH",
            teacher_id=self.teacher.id,
            term=TERM,
            school_year=YEAR,
            language_group="FRENCH",
            class_id=self.terminale.id,
        )
        self.db.add(self.course)

        # Three students in the class: two with course results, one without.
        self.student_a = Student(first_name="Ayo", last_name="Akowanou", student_number="B-001", class_id=self.terminale.id)
        self.student_b = Student(first_name="Bola", last_name="Dossou", student_number="B-002", class_id=self.terminale.id)
        self.student_c = Student(first_name="Chidi", last_name="Hounton", student_number="B-003", class_id=self.terminale.id)
        # A student in another class must never be touched.
        self.other_class = Class(name_fr="6ème", school_level="college", sort_order=1, school_year=YEAR)
        self.db.add(self.other_class)
        self.db.flush()
        self.student_other = Student(
            first_name="Dede", last_name="Gbaguidi", student_number="B-999", class_id=self.other_class.id
        )
        self.db.add_all([self.student_a, self.student_b, self.student_c, self.student_other])
        self.db.flush()

        for student, average in ((self.student_a, 14.0), (self.student_b, 11.5), (self.student_other, 13.0)):
            self.db.add(Enrollment(student_id=student.id, course_id=self.course.id))
            self.db.add(
                CourseResult(
                    student_id=student.id,
                    course_id=self.course.id,
                    term=TERM,
                    average=average,
                    letter_grade="B",
                    scale="20",
                    calculated_at=datetime.now(timezone.utc),
                )
            )
        self.db.commit()

    def _login(self, email) -> dict:
        response = self.client.post("/api/v1/auth/login", json={"email": email, "password": self.password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _admin(self) -> dict:
        return self._login("admin-batch@example.test")

    def _payload(self) -> dict:
        return {"class_id": str(self.terminale.id), "school_year": YEAR, "term": TERM}

    def _generate(self, headers=None) -> dict:
        response = self.client.post("/api/v1/reports/batch-generate", json=self._payload(), headers=headers or self._admin())
        assert response.status_code == 200, response.text
        return response.json()

    # --- batch-generate ---

    def test_batch_generate_creates_for_students_with_results_only(self):
        body = self._generate()
        self.assertEqual(body["generated_count"], 2)
        self.assertEqual(body["skipped_existing_count"], 0)
        self.assertEqual(body["skipped_no_results_count"], 1)

        reports = self.db.scalars(select(ReportCard)).all()
        self.assertEqual(len(reports), 2)
        student_ids = {report.student_id for report in reports}
        self.assertEqual(student_ids, {self.student_a.id, self.student_b.id})
        self.assertTrue(all(report.status == "draft" for report in reports))
        # Snapshot rows exist for each generated report.
        for report in reports:
            self.assertEqual(len(report.courses), 1)

    def test_batch_generate_skips_existing_reports(self):
        self._generate()
        body = self._generate()
        self.assertEqual(body["generated_count"], 0)
        self.assertEqual(body["skipped_existing_count"], 2)
        self.assertEqual(body["skipped_no_results_count"], 1)
        self.assertEqual(self.db.scalar(select(func.count(ReportCard.id))), 2)

    def test_batch_generate_never_touches_other_classes(self):
        self._generate()
        reports = self.db.scalars(select(ReportCard)).all()
        self.assertNotIn(self.student_other.id, {report.student_id for report in reports})

    def test_batch_generate_audit_entry(self):
        self._generate()
        log = self.db.scalar(select(AuditLog).where(AuditLog.action == "reports_batch_generated"))
        self.assertIsNotNone(log)
        self.assertEqual(log.new_value["generated_count"], 2)
        self.assertEqual(log.new_value["term"], TERM)

    def test_batch_generate_requires_admin(self):
        response = self.client.post(
            "/api/v1/reports/batch-generate",
            json=self._payload(),
            headers=self._login("teacher-batch@example.test"),
        )
        self.assertEqual(response.status_code, 403)

    def test_batch_generate_unknown_class_404(self):
        payload = self._payload()
        payload["class_id"] = "00000000-0000-0000-0000-000000000000"
        response = self.client.post("/api/v1/reports/batch-generate", json=payload, headers=self._admin())
        self.assertEqual(response.status_code, 404)

    # --- batch-approve ---

    def test_batch_approve_approves_drafts_only(self):
        self._generate()
        # Manually mark one report approved already.
        report_a = self.db.scalar(select(ReportCard).where(ReportCard.student_id == self.student_a.id))
        report_a.status = "approved"
        report_a.approved_at = datetime.now(timezone.utc)
        self.db.commit()

        response = self.client.post("/api/v1/reports/batch-approve", json=self._payload(), headers=self._admin())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["approved_count"], 1)
        self.assertEqual(body["skipped_count"], 1)

        statuses = {r.student_id: r.status for r in self.db.scalars(select(ReportCard)).all()}
        self.assertEqual(statuses[self.student_a.id], "approved")
        self.assertEqual(statuses[self.student_b.id], "approved")
        report_b = self.db.scalar(select(ReportCard).where(ReportCard.student_id == self.student_b.id))
        self.assertIsNotNone(report_b.approved_at)
        self.assertIsNotNone(report_b.approved_by_admin_id)

    def test_batch_approve_does_not_touch_sent_reports(self):
        self._generate()
        report_a = self.db.scalar(select(ReportCard).where(ReportCard.student_id == self.student_a.id))
        report_a.status = "sent"
        self.db.commit()

        response = self.client.post("/api/v1/reports/batch-approve", json=self._payload(), headers=self._admin())
        self.assertEqual(response.json()["approved_count"], 1)
        self.db.expire_all()
        report_a = self.db.scalar(select(ReportCard).where(ReportCard.student_id == self.student_a.id))
        self.assertEqual(report_a.status, "sent")

    def test_batch_approve_requires_admin(self):
        response = self.client.post(
            "/api/v1/reports/batch-approve",
            json=self._payload(),
            headers=self._login("teacher-batch@example.test"),
        )
        self.assertEqual(response.status_code, 403)

    # --- batch-send ---

    def _approve_all(self):
        self.client.post("/api/v1/reports/batch-approve", json=self._payload(), headers=self._admin())

    def test_batch_send_marks_sent_on_success(self):
        self._generate()
        self._approve_all()
        send_results = [{"email": "p@example.test", "sent": True, "success": True, "provider": "resend", "provider_message_id": "m1", "error": None}]
        with patch("routes.reports.send_report_notification_to_parents", return_value=send_results):
            response = self.client.post("/api/v1/reports/batch-send", json=self._payload(), headers=self._admin())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["sent_count"], 2)
        self.assertEqual(body["failed_count"], 0)
        self.assertEqual(body["no_recipient_count"], 0)
        statuses = [r.status for r in self.db.scalars(select(ReportCard)).all()]
        self.assertEqual(statuses.count("sent"), 2)

    def test_batch_send_failure_keeps_reports_approved(self):
        self._generate()
        self._approve_all()
        send_results = [{"email": "p@example.test", "sent": False, "success": False, "provider": "resend", "provider_message_id": None, "error": "boom"}]
        with patch("routes.reports.send_report_notification_to_parents", return_value=send_results):
            response = self.client.post("/api/v1/reports/batch-send", json=self._payload(), headers=self._admin())
        body = response.json()
        self.assertEqual(body["sent_count"], 0)
        self.assertEqual(body["failed_count"], 2)
        statuses = [r.status for r in self.db.scalars(select(ReportCard)).all()]
        self.assertEqual(statuses.count("approved"), 2)

    def test_batch_send_config_missing_counts_failed(self):
        self._generate()
        self._approve_all()
        with patch(
            "routes.reports.send_report_notification_to_parents",
            side_effect=ValueError("Missing email configuration: RESEND_API_KEY"),
        ):
            response = self.client.post("/api/v1/reports/batch-send", json=self._payload(), headers=self._admin())
        body = response.json()
        self.assertEqual(body["sent_count"], 0)
        self.assertEqual(body["failed_count"], 2)

    def test_batch_send_no_recipients_counted_separately(self):
        self._generate()
        self._approve_all()
        with patch("routes.reports.send_report_notification_to_parents", return_value=[]):
            response = self.client.post("/api/v1/reports/batch-send", json=self._payload(), headers=self._admin())
        body = response.json()
        self.assertEqual(body["no_recipient_count"], 2)
        self.assertEqual(body["sent_count"], 0)
        statuses = [r.status for r in self.db.scalars(select(ReportCard)).all()]
        self.assertEqual(statuses.count("approved"), 2)

    def test_batch_send_ignores_drafts(self):
        self._generate()
        send_results = [{"email": "p@example.test", "sent": True, "success": True, "provider": "resend", "provider_message_id": "m1", "error": None}]
        with patch("routes.reports.send_report_notification_to_parents", return_value=send_results) as send_mock:
            response = self.client.post("/api/v1/reports/batch-send", json=self._payload(), headers=self._admin())
        self.assertEqual(response.json()["sent_count"], 0)
        send_mock.assert_not_called()

    def test_batch_send_audit_entry(self):
        self._generate()
        self._approve_all()
        send_results = [{"email": "p@example.test", "sent": True, "success": True, "provider": "resend", "provider_message_id": "m1", "error": None}]
        with patch("routes.reports.send_report_notification_to_parents", return_value=send_results):
            self.client.post("/api/v1/reports/batch-send", json=self._payload(), headers=self._admin())
        log = self.db.scalar(select(AuditLog).where(AuditLog.action == "reports_batch_sent"))
        self.assertIsNotNone(log)
        self.assertEqual(log.new_value["sent_count"], 2)

    # --- class-status ---

    def test_class_status_shape_and_counts(self):
        self._generate()
        self._approve_all()
        response = self.client.get(
            "/api/v1/reports/class-status",
            params={"class_id": str(self.terminale.id), "school_year": YEAR, "term": TERM},
            headers=self._admin(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["class_name"], "Terminale C")
        self.assertEqual(body["total_students"], 3)
        self.assertEqual(body["without_report_count"], 1)
        self.assertEqual(body["approved_count"], 2)
        self.assertEqual(body["draft_count"], 0)
        self.assertEqual(body["needs_review_count"], 0)

        by_number = {row["student_number"]: row for row in body["students"]}
        self.assertEqual(by_number["B-001"]["results_count"], 1)
        self.assertEqual(by_number["B-001"]["report_status"], "approved")
        self.assertIsNotNone(by_number["B-001"]["overall_average"])
        self.assertEqual(by_number["B-003"]["results_count"], 0)
        self.assertIsNone(by_number["B-003"]["report_id"])
        # Alphabetical by last name: Akowanou, Dossou, Hounton.
        self.assertEqual([row["student_number"] for row in body["students"]], ["B-001", "B-002", "B-003"])

    def test_class_status_flags_needs_review(self):
        self._generate()
        self._approve_all()
        # A newer course-result calculation than approved_at marks it stale.
        result = self.db.scalar(select(CourseResult).where(CourseResult.student_id == self.student_a.id))
        result.calculated_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
        self.db.commit()

        response = self.client.get(
            "/api/v1/reports/class-status",
            params={"class_id": str(self.terminale.id), "school_year": YEAR, "term": TERM},
            headers=self._admin(),
        )
        body = response.json()
        self.assertEqual(body["needs_review_count"], 1)
        by_number = {row["student_number"]: row for row in body["students"]}
        self.assertTrue(by_number["B-001"]["needs_review"])
        self.assertFalse(by_number["B-002"]["needs_review"])

    def test_class_status_requires_admin(self):
        response = self.client.get(
            "/api/v1/reports/class-status",
            params={"class_id": str(self.terminale.id), "school_year": YEAR, "term": TERM},
            headers=self._login("teacher-batch@example.test"),
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
