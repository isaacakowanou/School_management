import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Class, Parent, ReportCard, Student, StudentClassAssignment, StudentParent, StudentPassageDecision, User
from services.annual_averages import compute_student_annual_averages
from services.passages import suggest_passage_decision


class PassageRouteTests(unittest.TestCase):
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
        self._seed_users()

    def tearDown(self):
        self.db.close()
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _seed_users(self):
        self.admin = User(name="ZZ-TEST Passage Admin", email="passage-admin@example.test", password_hash=hash_password(self.password), role="admin")
        self.parent_user = User(name="ZZ-TEST Passage Parent", email="passage-parent@example.test", password_hash=hash_password(self.password), role="parent")
        self.db.add_all([self.admin, self.parent_user])
        self.db.flush()
        self.parent = Parent(user=self.parent_user, phone="+2290100001111")
        self.db.add(self.parent)
        self.db.commit()

    def _headers(self, email):
        response = self.client.post("/api/v1/auth/login", json={"email": email, "password": self.password})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _admin(self):
        return self._headers(self.admin.email)

    def _parent(self):
        return self._headers(self.parent_user.email)

    def _class(self, name, year, order=1, stream=None):
        school_class = Class(
            name_fr=name,
            name_en=None,
            school_level="college" if name not in {"CI", "CP", "CE1", "CE2", "CM1", "CM2"} else "primaire",
            stream=stream,
            sort_order=order,
            school_year=year,
        )
        self.db.add(school_class)
        self.db.flush()
        return school_class

    def _student(self, number, school_class):
        student = Student(
            first_name="ZZ-TEST",
            last_name=number,
            student_number=number,
            school_level=school_class.school_level,
            school_class=school_class,
        )
        self.db.add(student)
        self.db.flush()
        self.db.add(StudentClassAssignment(
            student_id=student.id,
            school_year=school_class.school_year,
            class_id=school_class.id,
            class_name_snapshot=school_class.name_fr,
        ))
        return student

    def _reports(self, student, year, values):
        terms = ["1er Trimestre", "2ème Trimestre", "3ème Trimestre"]
        for index, value in enumerate(values):
            self.db.add(
                ReportCard(
                    student=student,
                    term=terms[index],
                    school_year=year,
                    overall_average=value,
                    french_average=value,
                    english_average=value,
                    bilingual_average=value,
                    gpa=4.0 if value >= 10 else 0.0,
                    status="approved",
                    scale="20",
                )
            )
        self.db.flush()

    def test_triage_boundaries_and_incomplete_data(self):
        cls = self._class("6ème", "2026-2027")
        pass_student = self._student("ZZ-TEST-PASS-1000", cls)
        deliberation_student = self._student("ZZ-TEST-DELIB-0900", cls)
        repeat_student = self._student("ZZ-TEST-REPEAT-0899", cls)
        incomplete_student = self._student("ZZ-TEST-INCOMPLETE", cls)
        self._reports(pass_student, "2026-2027", [10.0, 10.0, 10.0])
        self._reports(deliberation_student, "2026-2027", [9.0, 9.0, 9.0])
        self._reports(repeat_student, "2026-2027", [8.99, 8.99, 8.99])
        self._reports(incomplete_student, "2026-2027", [12.0])
        self.db.commit()

        cases = [
            (pass_student, "pass", False),
            (deliberation_student, "deliberation", True),
            (repeat_student, "repeat", False),
            (incomplete_student, "deliberation", True),
        ]
        for student, expected, required in cases:
            annual = compute_student_annual_averages(self.db, student.id, "2026-2027")
            suggestion = suggest_passage_decision(annual)
            self.assertEqual(suggestion.decision, expected)
            self.assertEqual(suggestion.requires_decision, required)

    def test_preview_reports_missing_target_year_classes_plainly(self):
        source = self._class("6ème", "2026-2027")
        student = self._student("ZZ-TEST-MISSING-TARGET", source)
        self._reports(student, "2026-2027", [12, 12, 12])
        self.db.commit()

        response = self.client.get(
            f"/api/v1/passages/classes/{source.id}?target_school_year=2027-2028",
            headers=self._admin(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertFalse(data["target_classes_ready"])
        self.assertIn("5ème", data["missing_target_class_names"])
        self.assertIn("Créez les classes", data["target_class_guidance"])

    def test_confirm_blocks_unresolved_deliberation_then_allows_override(self):
        source = self._class("6ème", "2026-2027")
        target = self._class("5ème", "2027-2028")
        student = self._student("ZZ-TEST-DELIB-CONFIRM", source)
        self._reports(student, "2026-2027", [9.5, 9.5, 9.5])
        self.db.commit()

        empty = self.client.post(
            "/api/v1/passages/confirm",
            json={"school_year": "2026-2027", "target_school_year": "2027-2028", "class_id": str(source.id), "decisions": []},
            headers=self._admin(),
        )
        self.assertEqual(empty.status_code, 400)

        response = self.client.post(
            "/api/v1/passages/confirm",
            json={
                "school_year": "2026-2027",
                "target_school_year": "2027-2028",
                "class_id": str(source.id),
                "decisions": [{"student_id": str(student.id), "final_decision": "pass"}],
            },
            headers=self._admin(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.db.refresh(student)
        self.assertEqual(student.class_id, target.id)

    def test_redouble_moves_to_same_class_name_in_target_year(self):
        source = self._class("6ème", "2026-2027")
        target_repeat = self._class("6ème", "2027-2028")
        student = self._student("ZZ-TEST-REPEAT-TARGET-YEAR", source)
        self._reports(student, "2026-2027", [8.5, 8.5, 8.5])
        self.db.commit()

        response = self.client.post(
            "/api/v1/passages/confirm",
            json={
                "school_year": "2026-2027",
                "target_school_year": "2027-2028",
                "decisions": [{"student_id": str(student.id), "final_decision": "repeat"}],
            },
            headers=self._admin(),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.db.refresh(student)
        self.assertEqual(student.class_id, target_repeat.id)

    def test_ladder_stream_terminale_graduation_idempotence_and_audit(self):
        seconde = self._class("2nde", "2026-2027")
        premiere_c = self._class("1ère C", "2027-2028", stream="C")
        terminale = self._class("Terminale C", "2026-2027", order=8, stream="C")
        promoted = self._student("ZZ-TEST-STREAM", seconde)
        graduate = self._student("ZZ-TEST-GRADUATE", terminale)
        self._reports(promoted, "2026-2027", [13, 13, 13])
        self._reports(graduate, "2026-2027", [14, 14, 14])
        self.db.commit()

        missing_stream = self.client.post(
            "/api/v1/passages/confirm",
            json={
                "school_year": "2026-2027",
                "target_school_year": "2027-2028",
                "decisions": [{"student_id": str(promoted.id), "final_decision": "pass"}],
            },
            headers=self._admin(),
        )
        self.assertEqual(missing_stream.status_code, 400)
        self.assertEqual(missing_stream.json()["detail"]["code"], "passage_stream_required")

        payload = {
            "school_year": "2026-2027",
            "target_school_year": "2027-2028",
            "decisions": [
                {"student_id": str(promoted.id), "final_decision": "pass", "target_class_name": "1ère C"},
                {"student_id": str(graduate.id), "final_decision": "pass"},
            ],
        }
        first = self.client.post("/api/v1/passages/confirm", json=payload, headers=self._admin())
        self.assertEqual(first.status_code, 200, first.text)
        self.db.refresh(promoted)
        self.db.refresh(graduate)
        self.assertEqual(promoted.class_id, premiere_c.id)
        self.assertEqual(graduate.academic_status, "graduated")
        self.assertIsNone(graduate.class_id)

        second = self.client.post("/api/v1/passages/confirm", json=payload, headers=self._admin())
        self.assertEqual(second.status_code, 200, second.text)
        decision_count = self.db.scalar(
            select(func.count(StudentPassageDecision.id)).where(StudentPassageDecision.student_id == promoted.id)
        )
        self.assertEqual(decision_count, 1)
        audit_count = len(self.db.scalars(select(AuditLog).where(AuditLog.action == "student_passage_decided")).all())
        self.assertGreaterEqual(audit_count, 2)

    def test_parent_keeps_approved_report_access_for_graduated_child(self):
        terminale = self._class("Terminale D", "2026-2027", order=9, stream="D")
        student = self._student("ZZ-TEST-GRAD-PARENT", terminale)
        self.db.add(StudentParent(student=student, parent=self.parent, relationship="Guardian"))
        self._reports(student, "2026-2027", [15, 15, 15])
        report = self.db.scalar(select(ReportCard).where(ReportCard.student_id == student.id, ReportCard.term == "3ème Trimestre"))
        self.db.commit()

        response = self.client.post(
            "/api/v1/passages/confirm",
            json={
                "school_year": "2026-2027",
                "target_school_year": "2027-2028",
                "decisions": [{"student_id": str(student.id), "final_decision": "pass"}],
            },
            headers=self._admin(),
        )
        self.assertEqual(response.status_code, 200, response.text)

        linked = self.client.get(f"/api/v1/parents/{self.parent.id}/students", headers=self._parent())
        self.assertEqual(linked.status_code, 200, linked.text)
        self.assertEqual([row["student_number"] for row in linked.json()], ["ZZ-TEST-GRAD-PARENT"])
        reports = self.client.get(f"/api/v1/reports/student/{student.id}", headers=self._parent())
        self.assertEqual(reports.status_code, 200, reports.text)
        self.assertIn(str(report.id), {row["id"] for row in reports.json()})
