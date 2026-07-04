import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import (
    AuditLog,
    Base,
    Course,
    CourseResult,
    Parent,
    ReportCard,
    ReportConductItem,
    ReportWorkHabitItem,
    Student,
    StudentParent,
    Teacher,
    User,
)


class ReportDetailsRouteTests(unittest.TestCase):
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

    def _user(self, *, name: str, email: str, role: str) -> User:
        user = User(name=name, email=email, password_hash=hash_password(self.password), role=role)
        self.db.add(user)
        return user

    def _seed(self) -> None:
        self.admin_user = self._user(name="Admin", email="admin-det@example.test", role="admin")
        self.parent_user = self._user(name="Parent", email="parent-det@example.test", role="parent")
        self.teacher_user = self._user(name="Teacher", email="teacher-det@example.test", role="teacher")
        self.db.flush()
        self.parent = Parent(user=self.parent_user, phone="555-0100")
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-DET-1")
        self.student = Student(
            first_name="Ada", last_name="Lovelace", student_number="DET001"
        )
        self.db.add_all([self.parent, self.teacher, self.student])
        self.db.flush()
        self.db.add(StudentParent(student=self.student, parent=self.parent, relationship="Guardian"))

        self.course = Course(
            name="Mathematics", code="MATH-DET", teacher=self.teacher,
            term="1er Trimestre", school_year="2026-2027",
        )
        self.db.add(self.course)
        self.db.flush()
        self.db.add(
            CourseResult(
                student=self.student, course=self.course, term="1er Trimestre",
                average=15.0, letter_grade="B", scale="20",
            )
        )
        # Report created directly with no conduct/work-habit rows and no comments —
        # this stands in for an existing production report (everything null).
        self.report_card = ReportCard(
            student=self.student, term="1er Trimestre", school_year="2026-2027",
            overall_average=15.0, gpa=3.0, status="draft",
        )
        self.db.add(self.report_card)
        self.db.commit()
        self.db.refresh(self.report_card)

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login", json={"email": email, "password": self.password}
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _admin_get(self) -> dict:
        response = self.client.get(
            f"/api/v1/reports/admin/{self.report_card.id}",
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _patch(self, payload: dict, *, email: str | None = None):
        return self.client.patch(
            f"/api/v1/reports/{self.report_card.id}",
            json=payload,
            headers=self._headers(email or self.admin_user.email),
        )

    def test_existing_report_returns_full_item_lists_all_null(self):
        data = self._admin_get()

        self.assertEqual(len(data["conduct_items"]), 6)
        self.assertEqual(len(data["work_habit_items"]), 7)
        self.assertTrue(all(item["letter_grade"] is None for item in data["conduct_items"]))
        self.assertTrue(all(item["letter_grade"] is None for item in data["work_habit_items"]))

        first = data["conduct_items"][0]
        self.assertEqual(first["item_key"], "controls_talking")
        self.assertEqual(first["label_en"], "Controls talking")
        self.assertEqual(first["label_fr"], "Contrôle de langage")

        for field in [
            "teacher_comment_fr", "teacher_comment_en",
            "principal_comment_fr", "principal_comment_en",
        ]:
            self.assertIsNone(data[field])

    def test_patch_sets_items_and_comments_and_persists(self):
        payload = {
            "conduct_items": [
                {"item_key": "controls_talking", "letter_grade": "A"},
                {"item_key": "respects_authority", "letter_grade": "B+"},
            ],
            "work_habit_items": [
                {"item_key": "good_listening", "letter_grade": "C"},
            ],
            "teacher_comment_fr": "Bon travail.",
            "teacher_comment_en": "Good work.",
            "principal_comment_fr": "Continuez.",
            "principal_comment_en": "Keep it up.",
        }
        response = self._patch(payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        conduct = {item["item_key"]: item["letter_grade"] for item in data["conduct_items"]}
        self.assertEqual(conduct["controls_talking"], "A")
        self.assertEqual(conduct["respects_authority"], "B+")
        self.assertIsNone(conduct["practices_self_control"])  # unset stays null
        work = {item["item_key"]: item["letter_grade"] for item in data["work_habit_items"]}
        self.assertEqual(work["good_listening"], "C")
        self.assertEqual(data["teacher_comment_fr"], "Bon travail.")
        self.assertEqual(data["principal_comment_en"], "Keep it up.")

        # Persists across a reload.
        reload = self._admin_get()
        reload_conduct = {i["item_key"]: i["letter_grade"] for i in reload["conduct_items"]}
        self.assertEqual(reload_conduct["controls_talking"], "A")
        self.assertEqual(reload["teacher_comment_en"], "Good work.")

        # Only assessed rows are stored (2 conduct + 1 work habit).
        self.db.expire_all()
        self.assertEqual(
            self.db.query(ReportConductItem).filter_by(report_card_id=self.report_card.id).count(), 2
        )
        self.assertEqual(
            self.db.query(ReportWorkHabitItem).filter_by(report_card_id=self.report_card.id).count(), 1
        )

        audit = (
            self.db.query(AuditLog)
            .filter(AuditLog.action == "report_details_edited", AuditLog.entity_id == self.report_card.id)
            .one()
        )
        self.assertEqual(audit.actor_user_id, self.admin_user.id)

    def test_patch_clears_item_via_blank_and_comment_via_null(self):
        self._patch(
            {
                "conduct_items": [{"item_key": "controls_talking", "letter_grade": "A"}],
                "teacher_comment_fr": "Temporaire.",
            }
        )

        # Blank dropdown → item sent with null grade; empty textarea → null comment.
        response = self._patch(
            {
                "conduct_items": [{"item_key": "controls_talking", "letter_grade": None}],
                "teacher_comment_fr": None,
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        conduct = {item["item_key"]: item["letter_grade"] for item in data["conduct_items"]}
        self.assertIsNone(conduct["controls_talking"])
        self.assertIsNone(data["teacher_comment_fr"])

        self.db.expire_all()
        self.assertEqual(
            self.db.query(ReportConductItem).filter_by(report_card_id=self.report_card.id).count(), 0
        )

    def test_patch_omitted_fields_are_unchanged(self):
        self._patch(
            {
                "conduct_items": [{"item_key": "controls_talking", "letter_grade": "A"}],
                "teacher_comment_fr": "À garder",
            }
        )

        # Patch only work habits; conduct + comment must survive.
        self._patch({"work_habit_items": [{"item_key": "good_listening", "letter_grade": "B"}]})

        data = self._admin_get()
        conduct = {i["item_key"]: i["letter_grade"] for i in data["conduct_items"]}
        work = {i["item_key"]: i["letter_grade"] for i in data["work_habit_items"]}
        self.assertEqual(conduct["controls_talking"], "A")
        self.assertEqual(data["teacher_comment_fr"], "À garder")
        self.assertEqual(work["good_listening"], "B")

    def test_patch_requires_admin(self):
        for user in [self.parent_user, self.teacher_user]:
            with self.subTest(role=user.role):
                response = self._patch({"teacher_comment_fr": "x"}, email=user.email)
                self.assertEqual(response.status_code, 403)

    def test_patch_rejects_unknown_item_key(self):
        response = self._patch({"conduct_items": [{"item_key": "not_real", "letter_grade": "A"}]})
        self.assertEqual(response.status_code, 422)

    def test_patch_rejects_invalid_letter_grade(self):
        response = self._patch({"conduct_items": [{"item_key": "controls_talking", "letter_grade": "Z"}]})
        self.assertEqual(response.status_code, 422)

    def test_regenerate_preserves_conduct_work_habits_and_comments(self):
        self._patch(
            {
                "conduct_items": [{"item_key": "controls_talking", "letter_grade": "A"}],
                "work_habit_items": [{"item_key": "good_listening", "letter_grade": "B"}],
                "teacher_comment_fr": "Garder",
                "principal_comment_en": "Keep",
            }
        )

        response = self.client.post(
            f"/api/v1/reports/{self.report_card.id}/regenerate",
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        conduct = {i["item_key"]: i["letter_grade"] for i in data["conduct_items"]}
        work = {i["item_key"]: i["letter_grade"] for i in data["work_habit_items"]}
        self.assertEqual(conduct["controls_talking"], "A")
        self.assertEqual(work["good_listening"], "B")
        self.assertEqual(data["teacher_comment_fr"], "Garder")
        self.assertEqual(data["principal_comment_en"], "Keep")


if __name__ == "__main__":
    unittest.main()
