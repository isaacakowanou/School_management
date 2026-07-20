import unittest
from datetime import date
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Course, Grade, GradeItem, Parent, Student, Teacher, User


class GradeItemRouteTests(unittest.TestCase):
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

    def _create_user(self, *, name: str, email: str, role: str) -> User:
        user = User(
            name=name,
            email=email,
            password_hash=hash_password(self.password),
            role=role,
        )
        self.db.add(user)
        return user

    def _seed(self) -> None:
        self.admin_user = self._create_user(
            name="Admin User",
            email="admin-grade-items@example.test",
            role="admin",
        )
        self.teacher_user = self._create_user(
            name="Taylor Teacher",
            email="teacher-grade-items@example.test",
            role="teacher",
        )
        self.other_teacher_user = self._create_user(
            name="Other Teacher",
            email="other-teacher-grade-items@example.test",
            role="teacher",
        )
        self.parent_user = self._create_user(
            name="Pat Parent",
            email="parent-grade-items@example.test",
            role="parent",
        )
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="TCH-GI-1")
        self.other_teacher = Teacher(user=self.other_teacher_user, employee_number="TCH-GI-2")
        self.parent = Parent(user=self.parent_user, phone="+2290100000086")
        self.db.add_all([self.teacher, self.other_teacher, self.parent])
        self.db.flush()
        self.course = Course(
            name="Grade Item Course",
            code="GI-101",
            teacher=self.teacher,
            term="1er Trimestre",
            school_year="2026-2027",
        )
        self.db.add(self.course)
        self.db.commit()

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _grade_item_payload(self, title: str = "Homework") -> dict:
        return {
            "course_id": str(self.course.id),
            "title": title,
            "category": "Homework",
            "max_score": 100,
            "weight": 0.3,
            "term": "1er Trimestre",
        }

    def _create_grade_item(self, title: str = "Existing Item") -> GradeItem:
        grade_item = GradeItem(
            course=self.course,
            title=title,
            category="Homework",
            max_score=100,
            weight=0.3,
            term="1er Trimestre",
        )
        self.db.add(grade_item)
        self.db.commit()
        self.db.refresh(grade_item)
        return grade_item

    def test_admin_can_create_grade_item(self):
        response = self.client.post(
            "/api/v1/grade-items",
            json=self._grade_item_payload(),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["course_id"], str(self.course.id))
        self.assertEqual(data["title"], "Homework")
        self.assertEqual(data["category"], "Homework")
        self.assertEqual(data["max_score"], 100)
        self.assertEqual(data["weight"], 0.3)
        self.assertEqual(data["term"], "1er Trimestre")

        grade_item = self.db.scalar(select(GradeItem).where(GradeItem.id == UUID(data["id"])))
        self.assertIsNotNone(grade_item)

    def test_create_grade_item_defaults_max_score_to_20(self):
        payload = self._grade_item_payload("No Max Score")
        del payload["max_score"]

        response = self.client.post(
            "/api/v1/grade-items",
            json=payload,
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["max_score"], 20)

    def test_assigned_teacher_can_create_grade_item(self):
        response = self.client.post(
            "/api/v1/grade-items",
            json=self._grade_item_payload("Quiz"),
            headers=self._headers(self.teacher_user.email),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["title"], "Quiz")

    def test_unauthorized_user_cannot_create_grade_item(self):
        for user in [self.other_teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.post(
                    "/api/v1/grade-items",
                    json=self._grade_item_payload(f"Blocked {user.role}"),
                    headers=self._headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_missing_course_is_rejected(self):
        payload = self._grade_item_payload("Missing Course")
        payload["course_id"] = str(uuid4())

        response = self.client.post(
            "/api/v1/grade-items",
            json=payload,
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Course not found")

    def test_invalid_max_score_or_weight_is_rejected(self):
        invalid_max_score = self._grade_item_payload("Bad Max")
        invalid_max_score["max_score"] = 0
        max_score_response = self.client.post(
            "/api/v1/grade-items",
            json=invalid_max_score,
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(max_score_response.status_code, 400)
        self.assertEqual(max_score_response.json()["detail"], "max_score must be greater than 0")

        invalid_weight = self._grade_item_payload("Bad Weight")
        invalid_weight["weight"] = 0
        weight_response = self.client.post(
            "/api/v1/grade-items",
            json=invalid_weight,
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(weight_response.status_code, 400)
        self.assertEqual(weight_response.json()["detail"], "weight must be greater than 0 and at most 1")

        too_large_weight = self._grade_item_payload("Large Weight")
        too_large_weight["weight"] = 1.1
        too_large_response = self.client.post(
            "/api/v1/grade-items",
            json=too_large_weight,
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(too_large_response.status_code, 400)
        self.assertEqual(too_large_response.json()["detail"], "weight must be greater than 0 and at most 1")

    def test_empty_required_fields_are_rejected(self):
        payload = self._grade_item_payload()
        payload["title"] = " "

        response = self.client.post(
            "/api/v1/grade-items",
            json=payload,
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "title cannot be empty")

    def test_create_grade_item_trims_text_fields(self):
        response = self.client.post(
            "/api/v1/grade-items",
            json={
                "course_id": str(self.course.id),
                "title": "  Midterm  ",
                "category": "  Exam  ",
                "max_score": 100,
                "weight": 0.3,
                "term": "1er Trimestre",
            },
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Midterm")
        self.assertEqual(data["category"], "Exam")
        self.assertEqual(data["term"], "1er Trimestre")

    def test_create_grade_item_writes_audit_log(self):
        response = self.client.post(
            "/api/v1/grade-items",
            json=self._grade_item_payload("Final Exam"),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        grade_item = self.db.get(GradeItem, UUID(response.json()["id"]))
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "grade_item_created",
                AuditLog.entity_type == "grade_item",
                AuditLog.entity_id == grade_item.id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)
        self.assertIsNone(audit_log.old_value)
        self.assertEqual(
            audit_log.new_value,
            {
                "course_id": str(self.course.id),
                "title": "Final Exam",
                "category": "Homework",
                "max_score": 100,
                "weight": 0.3,
                "item_type": None,
                "term": "1er Trimestre",
                "due_date": None,
            },
        )

    def test_admin_can_delete_grade_item_without_grades_and_audits(self):
        grade_item = self._create_grade_item("Delete Me")
        grade_item_id = grade_item.id

        response = self.client.delete(
            f"/api/v1/grade-items/{grade_item_id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(GradeItem, grade_item_id).deleted_at)
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "grade_item_deleted",
                AuditLog.entity_type == "grade_item",
                AuditLog.entity_id == grade_item_id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)

    def test_grade_item_delete_blocked_when_grades_exist(self):
        grade_item = self._create_grade_item("Has Grades")
        student = Student(first_name="Ada", last_name="Lovelace", student_number="GIDEL-STU")
        self.db.add(student)
        self.db.flush()
        grade = Grade(student=student, grade_item=grade_item, score=18, submitted_by_teacher=self.teacher)
        self.db.add(grade)
        self.db.commit()

        response = self.client.delete(
            f"/api/v1/grade-items/{grade_item.id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["grade_count"], 1)
        self.assertIsNotNone(self.db.get(GradeItem, grade_item.id))

    def test_non_admin_cannot_delete_grade_item(self):
        grade_item = self._create_grade_item("Admin Only Delete")

        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.delete(
                    f"/api/v1/grade-items/{grade_item.id}",
                    headers=self._headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_create_grade_item_audit_log_serializes_due_date_as_iso_string(self):
        payload = self._grade_item_payload("Project")
        payload["due_date"] = "2026-10-15"

        response = self.client.post(
            "/api/v1/grade-items",
            json=payload,
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        grade_item = self.db.get(GradeItem, UUID(response.json()["id"]))
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "grade_item_created",
                AuditLog.entity_type == "grade_item",
                AuditLog.entity_id == grade_item.id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.new_value["due_date"], "2026-10-15")

    def test_admin_can_update_grade_item(self):
        grade_item = self._create_grade_item("Editable Item")

        response = self.client.put(
            f"/api/v1/grade-items/{grade_item.id}",
            json={
                "title": "  Edited Homework  ",
                "category": "  Practice  ",
                "max_score": 50,
                "weight": 0.2,
                "term": "2ème Trimestre",
                "due_date": "2026-11-20",
            },
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Edited Homework")
        self.assertEqual(data["category"], "Practice")
        self.assertEqual(data["max_score"], 50)
        self.assertEqual(data["weight"], 0.2)
        self.assertEqual(data["term"], "2ème Trimestre")
        self.assertEqual(data["due_date"], "2026-11-20")

    def test_assigned_teacher_can_update_grade_item(self):
        grade_item = self._create_grade_item("Teacher Editable")

        response = self.client.put(
            f"/api/v1/grade-items/{grade_item.id}",
            json={"title": "Teacher Edited"},
            headers=self._headers(self.teacher_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Teacher Edited")

    def test_unauthorized_user_cannot_update_grade_item(self):
        grade_item = self._create_grade_item("Blocked Editable")

        for user in [self.other_teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.put(
                    f"/api/v1/grade-items/{grade_item.id}",
                    json={"title": f"Blocked {user.role}"},
                    headers=self._headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_update_grade_item_rejects_empty_text_fields(self):
        grade_item = self._create_grade_item("Empty Editable")

        for field in ["title", "category"]:
            with self.subTest(field=field):
                response = self.client.put(
                    f"/api/v1/grade-items/{grade_item.id}",
                    json={field: " "},
                    headers=self._headers(self.admin_user.email),
                )
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"], f"{field} cannot be empty")

        # term is enum-validated (A1.7c): blank is rejected by Pydantic with a
        # structured detail, not the route's "cannot be empty" message.
        response = self.client.put(
            f"/api/v1/grade-items/{grade_item.id}",
            json={"term": " "},
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(response.status_code, 422)

    def test_update_grade_item_rejects_invalid_max_score_or_weight(self):
        grade_item = self._create_grade_item("Invalid Editable")

        invalid_max_score = self.client.put(
            f"/api/v1/grade-items/{grade_item.id}",
            json={"max_score": 0},
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(invalid_max_score.status_code, 400)
        self.assertEqual(invalid_max_score.json()["detail"], "max_score must be greater than 0")

        invalid_weight = self.client.put(
            f"/api/v1/grade-items/{grade_item.id}",
            json={"weight": 0},
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(invalid_weight.status_code, 400)
        self.assertEqual(invalid_weight.json()["detail"], "weight must be greater than 0 and at most 1")

        too_large_weight = self.client.put(
            f"/api/v1/grade-items/{grade_item.id}",
            json={"weight": 1.1},
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(too_large_weight.status_code, 400)
        self.assertEqual(too_large_weight.json()["detail"], "weight must be greater than 0 and at most 1")

    def test_update_grade_item_can_clear_due_date(self):
        grade_item = self._create_grade_item("Due Date Editable")
        grade_item.due_date = date(2026, 10, 15)
        self.db.commit()

        response = self.client.put(
            f"/api/v1/grade-items/{grade_item.id}",
            json={"due_date": None},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["due_date"])

    def test_update_grade_item_writes_audit_log(self):
        grade_item = self._create_grade_item("Audit Editable")

        response = self.client.put(
            f"/api/v1/grade-items/{grade_item.id}",
            json={"title": "Audit Updated", "due_date": "2026-12-01"},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "grade_item_updated",
                AuditLog.entity_type == "grade_item",
                AuditLog.entity_id == grade_item.id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)
        self.assertEqual(audit_log.old_value["title"], "Audit Editable")
        self.assertIsNone(audit_log.old_value["due_date"])
        self.assertEqual(audit_log.new_value["title"], "Audit Updated")
        self.assertEqual(audit_log.new_value["due_date"], "2026-12-01")


if __name__ == "__main__":
    unittest.main()
