import unittest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Course, CourseResult, Enrollment, Grade, GradeItem, Student, Teacher, User


class CourseRouteTests(unittest.TestCase):
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
            email="admin-courses@example.test",
            role="admin",
        )
        self.teacher_user = self._create_user(
            name="Taylor Teacher",
            email="teacher-courses@example.test",
            role="teacher",
        )
        self.parent_user = self._create_user(
            name="Pat Parent",
            email="parent-courses@example.test",
            role="parent",
        )
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="TCH-COURSE")
        self.db.add(self.teacher)
        self.db.flush()
        self.existing_course = Course(
            name="Existing Course",
            code="EXIST-101",
            teacher=self.teacher,
            term="1er Trimestre",
            school_year="2026-2027",
        )
        self.db.add(self.existing_course)
        self.db.commit()

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _course_payload(self, code: str = "NEW-101") -> dict[str, str]:
        return {
            "name": "New Course",
            "code": code,
            "teacher_id": str(self.teacher.id),
            "term": "1er Trimestre",
            "school_year": "2026-2027",
        }

    def test_teacher_course_list_includes_active_entry_progress_counts(self):
        deleted_at = datetime.now(timezone.utc)
        student_one = Student(first_name="Ada", last_name="Lovelace", student_number="COURSE-ST-1")
        student_two = Student(first_name="Grace", last_name="Hopper", student_number="COURSE-ST-2")
        deleted_student = Student(
            first_name="Hidden",
            last_name="Student",
            student_number="COURSE-ST-DEL",
            deleted_at=deleted_at,
        )
        self.db.add_all([student_one, student_two, deleted_student])
        self.db.flush()

        current_homework = GradeItem(
            course=self.existing_course,
            title="Homework 1",
            category="Homework",
            max_score=20,
            weight=0.5,
            term="1er Trimestre",
        )
        current_exam = GradeItem(
            course=self.existing_course,
            title="Exam 1",
            category="Exam",
            max_score=20,
            weight=0.5,
            term="1er Trimestre",
        )
        old_term_item = GradeItem(
            course=self.existing_course,
            title="Old Exam",
            category="Exam",
            max_score=20,
            weight=1,
            term="2ème Trimestre",
        )
        deleted_item = GradeItem(
            course=self.existing_course,
            title="Deleted Exam",
            category="Exam",
            max_score=20,
            weight=1,
            term="1er Trimestre",
            deleted_at=deleted_at,
        )
        self.db.add_all([current_homework, current_exam, old_term_item, deleted_item])
        self.db.flush()

        self.db.add_all(
            [
                Enrollment(student=student_one, course=self.existing_course),
                Enrollment(student=student_two, course=self.existing_course),
                Enrollment(student=deleted_student, course=self.existing_course),
                Grade(student=student_one, grade_item=current_homework, score=18, submitted_by_teacher=self.teacher),
                Grade(student=student_two, grade_item=current_homework, score=16, submitted_by_teacher=self.teacher),
                Grade(student=deleted_student, grade_item=current_homework, score=19, submitted_by_teacher=self.teacher),
                Grade(student=student_one, grade_item=old_term_item, score=17, submitted_by_teacher=self.teacher),
                Grade(student=student_one, grade_item=deleted_item, score=15, submitted_by_teacher=self.teacher),
            ]
        )
        self.db.commit()

        response = self.client.get(
            "/api/v1/courses",
            headers=self._headers(self.teacher_user.email),
        )

        self.assertEqual(response.status_code, 200)
        course = next(item for item in response.json() if item["id"] == str(self.existing_course.id))
        self.assertEqual(course["student_count"], 2)
        self.assertEqual(course["grade_item_count"], 2)
        self.assertEqual(course["filled_score_count"], 2)
        self.assertEqual(course["possible_score_count"], 4)

    def test_admin_can_create_course(self):
        response = self.client.post(
            "/api/v1/courses",
            json=self._course_payload(),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "New Course")
        self.assertEqual(data["code"], "NEW-101")
        self.assertEqual(data["teacher_id"], str(self.teacher.id))
        self.assertEqual(data["term"], "1er Trimestre")
        self.assertEqual(data["school_year"], "2026-2027")

        course = self.db.scalar(select(Course).where(Course.code == "NEW-101"))
        self.assertIsNotNone(course)
        self.assertIsNone(course.language_group)

    def test_create_course_with_language_group_sets_field(self):
        payload = self._course_payload("LANG-101")
        payload["language_group"] = "FRENCH"

        response = self.client.post(
            "/api/v1/courses",
            json=payload,
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["language_group"], "FRENCH")

        course = self.db.scalar(select(Course).where(Course.code == "LANG-101"))
        self.assertEqual(course.language_group, "FRENCH")

    def test_create_course_with_invalid_language_group_is_rejected(self):
        payload = self._course_payload("BAD-LANG-101")
        payload["language_group"] = "SPANISH"

        response = self.client.post(
            "/api/v1/courses",
            json=payload,
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 422)

    def test_create_course_trims_required_fields(self):
        response = self.client.post(
            "/api/v1/courses",
            json={
                "name": "  Trimmed Course  ",
                "code": "  TRIM-101  ",
                "teacher_id": str(self.teacher.id),
                "term": "2ème Trimestre",
                "school_year": "  2027-2028  ",
            },
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "Trimmed Course")
        self.assertEqual(data["code"], "TRIM-101")
        self.assertEqual(data["term"], "2ème Trimestre")
        self.assertEqual(data["school_year"], "2027-2028")

    def test_non_admin_cannot_create_course(self):
        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.post(
                    "/api/v1/courses",
                    json=self._course_payload(f"NEW-{user.role.upper()}"),
                    headers=self._headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_duplicate_course_code_is_rejected(self):
        response = self.client.post(
            "/api/v1/courses",
            json=self._course_payload(self.existing_course.code),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Course code already exists")

    def test_missing_teacher_is_rejected(self):
        payload = self._course_payload("NO-TCH-101")
        payload["teacher_id"] = str(uuid4())

        response = self.client.post(
            "/api/v1/courses",
            json=payload,
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Teacher not found")

    def test_empty_course_required_fields_are_rejected(self):
        payload = self._course_payload("EMPTY-101")
        payload["name"] = " "

        response = self.client.post(
            "/api/v1/courses",
            json=payload,
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "name cannot be empty")

    def test_create_course_writes_audit_log(self):
        response = self.client.post(
            "/api/v1/courses",
            json=self._course_payload("AUDIT-101"),
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 201)
        course_id = UUID(response.json()["id"])
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "course_created",
                AuditLog.entity_type == "course",
                AuditLog.entity_id == course_id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)
        self.assertIsNone(audit_log.old_value)
        self.assertEqual(
            audit_log.new_value,
            {
                "name": "New Course",
                "code": "AUDIT-101",
                "teacher_id": str(self.teacher.id),
                "term": "1er Trimestre",
                "school_year": "2026-2027",
                "language_group": None,
                "class_id": None,
                "subject_id": None,
                "coefficient": 1,
            },
        )

    def test_course_delete_blocked_when_dependent_academic_data_exists(self):
        student = Student(first_name="Ada", last_name="Lovelace", student_number="CDEL-STU")
        self.db.add(student)
        self.db.flush()
        self.db.add(Enrollment(student=student, course=self.existing_course))
        self.db.add(
            CourseResult(
                student=student,
                course=self.existing_course,
                term="1er Trimestre",
                average=18,
                letter_grade="A",
                scale="20",
            )
        )
        self.db.commit()

        response = self.client.delete(
            f"/api/v1/courses/{self.existing_course.id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["enrollment_count"], 1)
        self.assertEqual(response.json()["detail"]["course_result_count"], 1)
        self.assertIsNotNone(self.db.get(Course, self.existing_course.id))

    def test_course_delete_blocked_when_grade_items_exist(self):
        grade_item = GradeItem(
            course=self.existing_course,
            title="Exam",
            category="Exam",
            max_score=20,
            weight=1,
            term="1er Trimestre",
        )
        self.db.add(grade_item)
        self.db.commit()

        response = self.client.delete(
            f"/api/v1/courses/{self.existing_course.id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["grade_item_count"], 1)

    def test_admin_can_delete_safe_empty_course_and_audits(self):
        response = self.client.post(
            "/api/v1/courses",
            json=self._course_payload("SAFE-DELETE-101"),
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(response.status_code, 201)
        course_id = UUID(response.json()["id"])

        delete_response = self.client.delete(
            f"/api/v1/courses/{course_id}",
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(delete_response.status_code, 200)
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Course, course_id).deleted_at)
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "course_deleted",
                AuditLog.entity_type == "course",
                AuditLog.entity_id == course_id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)

    def test_non_admin_cannot_delete_course(self):
        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.delete(
                    f"/api/v1/courses/{self.existing_course.id}",
                    headers=self._headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_admin_can_update_course(self):
        response = self.client.put(
            f"/api/v1/courses/{self.existing_course.id}",
            json={
                "name": "  Edited Course  ",
                "code": "  EDIT-101  ",
                "teacher_id": str(self.teacher.id),
                "term": "2ème Trimestre",
                "school_year": "  2027-2028  ",
            },
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Edited Course")
        self.assertEqual(data["code"], "EDIT-101")
        self.assertEqual(data["teacher_id"], str(self.teacher.id))
        self.assertEqual(data["term"], "2ème Trimestre")
        self.assertEqual(data["school_year"], "2027-2028")

    def test_update_course_sets_language_group(self):
        self.assertIsNone(self.existing_course.language_group)

        response = self.client.put(
            f"/api/v1/courses/{self.existing_course.id}",
            json={"language_group": "ENGLISH"},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["language_group"], "ENGLISH")

        self.db.expire_all()
        course = self.db.get(Course, self.existing_course.id)
        self.assertEqual(course.language_group, "ENGLISH")

    def test_update_course_clears_language_group(self):
        self.existing_course.language_group = "FRENCH"
        self.db.commit()

        response = self.client.put(
            f"/api/v1/courses/{self.existing_course.id}",
            json={"language_group": None},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["language_group"])

        self.db.expire_all()
        course = self.db.get(Course, self.existing_course.id)
        self.assertIsNone(course.language_group)

    def test_update_course_omitting_language_group_preserves_existing(self):
        self.existing_course.language_group = "FRENCH"
        self.db.commit()

        response = self.client.put(
            f"/api/v1/courses/{self.existing_course.id}",
            json={"term": "2ème Trimestre"},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["language_group"], "FRENCH")

        self.db.expire_all()
        course = self.db.get(Course, self.existing_course.id)
        self.assertEqual(course.language_group, "FRENCH")

    def test_non_admin_cannot_update_course(self):
        for user in [self.teacher_user, self.parent_user]:
            with self.subTest(role=user.role):
                response = self.client.put(
                    f"/api/v1/courses/{self.existing_course.id}",
                    json={"name": "Blocked"},
                    headers=self._headers(user.email),
                )
                self.assertEqual(response.status_code, 403)

    def test_update_course_duplicate_code_is_rejected(self):
        other_course = Course(
            name="Other Course",
            code="OTHER-101",
            teacher=self.teacher,
            term="1er Trimestre",
            school_year="2026-2027",
        )
        self.db.add(other_course)
        self.db.commit()

        response = self.client.put(
            f"/api/v1/courses/{self.existing_course.id}",
            json={"code": "OTHER-101"},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Course code already exists")

    def test_update_course_missing_teacher_is_rejected(self):
        response = self.client.put(
            f"/api/v1/courses/{self.existing_course.id}",
            json={"teacher_id": str(uuid4())},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Teacher not found")

    def test_update_course_empty_required_field_is_rejected(self):
        response = self.client.put(
            f"/api/v1/courses/{self.existing_course.id}",
            json={"name": " "},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "name cannot be empty")

    def test_update_course_writes_audit_log(self):
        response = self.client.put(
            f"/api/v1/courses/{self.existing_course.id}",
            json={"name": "Audit Course"},
            headers=self._headers(self.admin_user.email),
        )

        self.assertEqual(response.status_code, 200)
        audit_log = self.db.scalar(
            select(AuditLog).where(
                AuditLog.action == "course_updated",
                AuditLog.entity_type == "course",
                AuditLog.entity_id == self.existing_course.id,
            )
        )
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.actor_user_id, self.admin_user.id)
        self.assertEqual(audit_log.old_value["name"], "Existing Course")
        self.assertEqual(audit_log.new_value["name"], "Audit Course")


if __name__ == "__main__":
    unittest.main()
