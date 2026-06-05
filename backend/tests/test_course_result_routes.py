import unittest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import (
    Base,
    Course,
    CourseResult,
    Enrollment,
    Grade,
    GradeItem,
    ReportCard,
    ReportCardCourse,
    Student,
    Teacher,
    User,
)


class CourseResultRouteTests(unittest.TestCase):
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
        self.admin_user = self._user(name="Admin", email="course-admin@example.test", role="admin")
        self.teacher_user = self._user(name="Teacher", email="course-teacher@example.test", role="teacher")
        self.other_teacher_user = self._user(
            name="Other Teacher",
            email="other-course-teacher@example.test",
            role="teacher",
        )
        self.parent_user = self._user(name="Parent", email="course-parent@example.test", role="parent")
        self.db.flush()

        self.teacher = Teacher(user=self.teacher_user, employee_number="T-COURSE-1")
        self.other_teacher = Teacher(user=self.other_teacher_user, employee_number="T-COURSE-2")
        self.student_one = Student(
            first_name="Ada",
            last_name="Lovelace",
            grade_level="Grade 12",
            student_number="CR001",
        )
        self.student_two = Student(
            first_name="Grace",
            last_name="Hopper",
            grade_level="Grade 12",
            student_number="CR002",
        )
        self.unenrolled_student = Student(
            first_name="Katherine",
            last_name="Johnson",
            grade_level="Grade 12",
            student_number="CR003",
        )
        self.db.add_all(
            [
                self.teacher,
                self.other_teacher,
                self.student_one,
                self.student_two,
                self.unenrolled_student,
            ]
        )
        self.db.flush()

        self.course = Course(
            name="Mathematics",
            code="COURSE-RESULTS",
            teacher=self.teacher,
            grade_level="Grade 12",
            term="Fall",
            school_year="2026-2027",
        )
        self.db.add(self.course)
        self.db.flush()

        self.homework = GradeItem(
            course=self.course,
            title="Homework",
            category="Homework",
            max_score=100,
            weight=0.5,
            term="Fall",
        )
        self.final = GradeItem(
            course=self.course,
            title="Final",
            category="Final",
            max_score=100,
            weight=0.5,
            term="Fall",
        )
        self.db.add_all([self.homework, self.final])
        self.db.flush()

        self.db.add_all(
            [
                Enrollment(student=self.student_one, course=self.course),
                Enrollment(student=self.student_two, course=self.course),
                Grade(student=self.student_one, grade_item=self.homework, score=80, submitted_by_teacher=self.teacher),
                Grade(student=self.student_one, grade_item=self.final, score=90, submitted_by_teacher=self.teacher),
                Grade(student=self.student_two, grade_item=self.homework, score=70, submitted_by_teacher=self.teacher),
                Grade(student=self.student_two, grade_item=self.final, score=80, submitted_by_teacher=self.teacher),
            ]
        )
        self.db.flush()

        self.base_time = datetime.now() - timedelta(days=5)
        self.student_one_result = CourseResult(
            student=self.student_one,
            course=self.course,
            term="Fall",
            average=85.0,
            letter_grade="B",
            calculated_at=self.base_time,
        )
        self.student_two_result = CourseResult(
            student=self.student_two,
            course=self.course,
            term="Fall",
            average=75.0,
            letter_grade="C",
            calculated_at=self.base_time,
        )
        self.db.add_all([self.student_one_result, self.student_two_result])
        self.db.flush()

        self.student_one_report = self._approved_report(self.student_one, 85.0, "B")
        self.student_two_report = self._approved_report(self.student_two, 75.0, "C")
        self.db.commit()
        self.db.refresh(self.student_one_result)
        self.db.refresh(self.student_two_result)

    def _approved_report(self, student: Student, average: float, letter_grade: str) -> ReportCard:
        report = ReportCard(
            student=student,
            term="Fall",
            school_year="2026-2027",
            overall_average=average,
            gpa=3.0,
            status="approved",
            approved_by_admin_id=self.admin_user.id,
            approved_at=self.base_time + timedelta(hours=1),
        )
        self.db.add(report)
        self.db.flush()
        self.db.add(
            ReportCardCourse(
                report_card=report,
                course=self.course,
                course_name=self.course.name,
                average=average,
                letter_grade=letter_grade,
            )
        )
        return report

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _report_list_by_student_number(self) -> dict[str, dict]:
        response = self.client.get("/api/v1/reports", headers=self._headers(self.admin_user.email))
        self.assertEqual(response.status_code, 200)
        return {report["student_number"]: report for report in response.json()}

    def test_selected_recalculation_only_updates_selected_student_and_report_review_flag(self):
        original_one_calculated_at = self.student_one_result.calculated_at
        original_two_calculated_at = self.student_two_result.calculated_at
        grade = self.db.scalar(
            select(Grade).where(
                Grade.student_id == self.student_one.id,
                Grade.grade_item_id == self.homework.id,
            )
        )
        grade.score = 100
        self.db.commit()

        response = self.client.post(
            f"/api/v1/course-results/calculate/{self.course.id}/students",
            headers=self._headers(self.teacher_user.email),
            json={"student_ids": [str(self.student_one.id)]},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["calculated_count"], 1)
        self.assertEqual(data["results"][0]["student_id"], str(self.student_one.id))
        self.assertEqual(data["results"][0]["average"], 95.0)

        self.db.expire_all()
        student_one_result = self.db.get(CourseResult, self.student_one_result.id)
        student_two_result = self.db.get(CourseResult, self.student_two_result.id)
        self.assertGreater(student_one_result.calculated_at, original_one_calculated_at)
        self.assertEqual(student_two_result.calculated_at, original_two_calculated_at)

        reports = self._report_list_by_student_number()
        self.assertTrue(reports["CR001"]["needs_review"])
        self.assertFalse(reports["CR002"]["needs_review"])

    def test_teacher_grade_update_recalculate_is_visible_to_admin_and_marks_report_stale(self):
        original_calculated_at = self.student_one_result.calculated_at
        grade = self.db.scalar(
            select(Grade).where(
                Grade.student_id == self.student_one.id,
                Grade.grade_item_id == self.homework.id,
            )
        )

        grade_response = self.client.put(
            f"/api/v1/grades/{grade.id}",
            headers=self._headers(self.teacher_user.email),
            json={"score": 100},
        )
        self.assertEqual(grade_response.status_code, 200)
        self.assertEqual(grade_response.json()["score"], 100)

        recalc_response = self.client.post(
            f"/api/v1/course-results/calculate/{self.course.id}/students",
            headers=self._headers(self.teacher_user.email),
            json={"student_ids": [str(self.student_one.id)]},
        )
        self.assertEqual(recalc_response.status_code, 200)
        self.assertEqual(recalc_response.json()["calculated_count"], 1)
        self.assertEqual(recalc_response.json()["results"][0]["average"], 95.0)

        self.db.expire_all()
        course_result = self.db.get(CourseResult, self.student_one_result.id)
        self.assertEqual(course_result.average, 95.0)
        self.assertEqual(course_result.letter_grade, "A")
        self.assertGreater(course_result.calculated_at, original_calculated_at)

        admin_results_response = self.client.get(
            f"/api/v1/course-results/{self.course.id}",
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(admin_results_response.status_code, 200)
        admin_results = {
            result["student_id"]: result
            for result in admin_results_response.json()
        }
        self.assertEqual(admin_results[str(self.student_one.id)]["average"], 95.0)
        self.assertEqual(admin_results[str(self.student_one.id)]["letter_grade"], "A")

        reports = self._report_list_by_student_number()
        self.assertTrue(reports["CR001"]["needs_review"])

        staleness_response = self.client.get(
            f"/api/v1/reports/{self.student_one_report.id}/staleness",
            headers=self._headers(self.admin_user.email),
        )
        self.assertEqual(staleness_response.status_code, 200)
        staleness = staleness_response.json()
        self.assertTrue(staleness["is_stale"])
        self.assertEqual(staleness["snapshot_overall_average"], 85.0)
        self.assertEqual(staleness["current_overall_average"], 95.0)

    def test_whole_course_recalculation_still_updates_all_enrolled_students(self):
        original_one_calculated_at = self.student_one_result.calculated_at
        original_two_calculated_at = self.student_two_result.calculated_at

        response = self.client.post(
            f"/api/v1/course-results/calculate/{self.course.id}",
            headers=self._headers(self.teacher_user.email),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["calculated_count"], 2)
        self.db.expire_all()
        student_one_result = self.db.get(CourseResult, self.student_one_result.id)
        student_two_result = self.db.get(CourseResult, self.student_two_result.id)
        self.assertGreater(student_one_result.calculated_at, original_one_calculated_at)
        self.assertGreater(student_two_result.calculated_at, original_two_calculated_at)

    def test_selected_recalculation_permissions_and_enrollment_validation(self):
        payload = {"student_ids": [str(self.student_one.id)]}

        parent_response = self.client.post(
            f"/api/v1/course-results/calculate/{self.course.id}/students",
            headers=self._headers(self.parent_user.email),
            json=payload,
        )
        self.assertEqual(parent_response.status_code, 403)

        other_teacher_response = self.client.post(
            f"/api/v1/course-results/calculate/{self.course.id}/students",
            headers=self._headers(self.other_teacher_user.email),
            json=payload,
        )
        self.assertEqual(other_teacher_response.status_code, 403)

        unenrolled_response = self.client.post(
            f"/api/v1/course-results/calculate/{self.course.id}/students",
            headers=self._headers(self.admin_user.email),
            json={"student_ids": [str(self.unenrolled_student.id)]},
        )
        self.assertEqual(unenrolled_response.status_code, 400)

        admin_response = self.client.post(
            f"/api/v1/course-results/calculate/{self.course.id}/students",
            headers=self._headers(self.admin_user.email),
            json=payload,
        )
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response.json()["calculated_count"], 1)


if __name__ == "__main__":
    unittest.main()
