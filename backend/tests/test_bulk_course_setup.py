import unittest
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Class, Course, CourseResult, Enrollment, Grade, GradeItem, Parent, Subject, Teacher, User


YEAR = "2031-2032"
OTHER_YEAR = "2032-2033"
TERM = "1er Trimestre"


class BulkCourseSetupTests(unittest.TestCase):
    password = "test-password-123"

    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        event.listen(self.engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
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

    def _seed(self):
        self.admin = self._user("ZZ-TEST Admin", "zz-bulk-admin@example.test", "admin")
        self.teacher_user = self._user("ZZ-TEST Teacher", "zz-bulk-teacher@example.test", "teacher")
        self.parent = self._user("ZZ-TEST Parent", "zz-bulk-parent@example.test", "parent")
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="ZZ-BULK-T-1")
        self.parent_profile = Parent(user=self.parent)
        self.sixth = Class(
            name_fr="6ème", name_en="JSS1", school_level="college", sort_order=1, school_year=YEAR
        )
        self.fourth = Class(
            name_fr="4ème", name_en="JSS3", school_level="college", sort_order=3, school_year=YEAR
        )
        self.primary = Class(name_fr="CI", school_level="primaire", sort_order=1, school_year=YEAR)
        self.other_year_class = Class(
            name_fr="6ème", name_en="JSS1", school_level="college", sort_order=1, school_year=OTHER_YEAR
        )
        self.french_math = Subject(
            name_fr="ZZ-TEST Mathématique",
            name_en="ZZ-TEST Mathematics",
            section="FRENCH",
            level_group="COLLEGE_FIRST_CYCLE",
            sort_order=1,
        )
        self.english_science = Subject(
            name_fr="ZZ-TEST Science de base",
            name_en="ZZ-TEST Basic science",
            section="ENGLISH",
            level_group="PRIMARY",
            sort_order=1,
        )
        self.spanish = Subject(
            name_fr="ZZ-TEST Espagnol",
            name_en="ZZ-TEST Spanish",
            section="FRENCH",
            level_group="COLLEGE_FIRST_CYCLE",
            sort_order=2,
            applicable_classes=["4ème", "3ème"],
        )
        self.french_history = Subject(
            name_fr="ZZ-TEST Histoire",
            name_en="ZZ-TEST History",
            section="FRENCH",
            level_group="COLLEGE_FIRST_CYCLE",
            sort_order=3,
        )
        self.french_science = Subject(
            name_fr="ZZ-TEST Sciences",
            name_en="ZZ-TEST Science",
            section="FRENCH",
            level_group="COLLEGE_FIRST_CYCLE",
            sort_order=4,
        )
        self.db.add_all(
            [
                self.teacher,
                self.parent_profile,
                self.sixth,
                self.fourth,
                self.primary,
                self.other_year_class,
                self.french_math,
                self.english_science,
                self.spanish,
                self.french_history,
                self.french_science,
            ]
        )
        self.db.commit()

    def _headers(self, user):
        response = self.client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": self.password}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _preview(self, class_ids=None, headers=None):
        return self.client.post(
            "/api/v1/courses/bulk-setup/preview",
            json={
                "school_year": YEAR,
                "term": TERM,
                "class_ids": [str(value) for value in (class_ids or [self.sixth.id])],
            },
            headers=headers or self._headers(self.admin),
        )

    def _item(self, *, school_class=None, subject=None, code="ZZ-BULK-001", teacher_id=None, coefficient=1, grading_system="BENINESE"):
        return {
            "class_id": str((school_class or self.sixth).id),
            "subject_id": str((subject or self.french_math).id),
            "code": code,
            "teacher_id": str(teacher_id) if teacher_id else None,
            "coefficient": coefficient,
            "grading_system": grading_system,
        }

    def _create(self, items, headers=None, school_year=YEAR):
        return self.client.post(
            "/api/v1/courses/bulk-setup",
            json={"school_year": school_year, "term": TERM, "items": items},
            headers=headers or self._headers(self.admin),
        )

    def test_preview_filters_applicable_subjects_and_derives_grading_defaults(self):
        response = self._preview([self.sixth.id, self.fourth.id, self.primary.id])
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()["rows"]
        keys = {(row["class_id"], row["subject_id"]) for row in rows}
        self.assertIn((str(self.sixth.id), str(self.french_math.id)), keys)
        self.assertNotIn((str(self.sixth.id), str(self.spanish.id)), keys)
        self.assertIn((str(self.fourth.id), str(self.spanish.id)), keys)
        self.assertIn((str(self.primary.id), str(self.english_science.id)), keys)

        french_row = next(row for row in rows if row["subject_id"] == str(self.french_math.id))
        primary_row = next(row for row in rows if row["subject_id"] == str(self.english_science.id))
        self.assertEqual(french_row["grading_system"], "BENINESE")
        self.assertEqual(primary_row["grading_system"], "WEIGHTED")
        self.assertEqual(french_row["coefficient"], 1)

    def test_bulk_create_accepts_unassigned_and_assigned_courses_with_editable_values(self):
        items = [
            self._item(code="ZZ-BULK-UNASSIGNED", coefficient=4),
            self._item(
                school_class=self.primary,
                subject=self.english_science,
                code="ZZ-BULK-ASSIGNED",
                teacher_id=self.teacher.id,
                coefficient=2,
                grading_system="WEIGHTED",
            ),
        ]
        response = self._create(items)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["created_count"], 2)
        courses = self.db.scalars(select(Course).where(Course.code.in_([row["code"] for row in items]))).all()
        by_code = {course.code: course for course in courses}
        self.assertIsNone(by_code["ZZ-BULK-UNASSIGNED"].teacher_id)
        self.assertEqual(by_code["ZZ-BULK-UNASSIGNED"].coefficient, 4)
        self.assertEqual(by_code["ZZ-BULK-ASSIGNED"].teacher_id, self.teacher.id)
        self.assertEqual(by_code["ZZ-BULK-ASSIGNED"].coefficient, 2)

        self.assertEqual(self.db.scalar(select(func.count(Enrollment.id))), 0)
        self.assertEqual(self.db.scalar(select(func.count(GradeItem.id))), 0)
        self.assertEqual(self.db.scalar(select(func.count(Grade.id))), 0)
        self.assertEqual(self.db.scalar(select(func.count(CourseResult.id))), 0)

    def test_existing_setup_is_skipped_and_rerun_is_idempotent(self):
        item = self._item(code="ZZ-BULK-IDEMPOTENT")
        first = self._create([item])
        second = self._create([item])
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json()["created_count"], 0)
        self.assertEqual(second.json()["skipped_existing_count"], 1)
        self.assertEqual(
            self.db.scalar(
                select(func.count(Course.id)).where(
                    Course.school_year == YEAR,
                    Course.class_id == self.sixth.id,
                    Course.subject_id == self.french_math.id,
                    Course.deleted_at.is_(None),
                )
            ),
            1,
        )

    def test_validation_failures_are_atomic_for_year_applicability_teacher_and_code(self):
        self.db.add(
            Course(
                name="ZZ-TEST Conflict",
                code="ZZ-CODE-CONFLICT",
                teacher_id=None,
                term=TERM,
                school_year=YEAR,
            )
        )
        self.db.commit()
        items = [
            self._item(code="ZZ-VALID-WOULD-CREATE"),
            self._item(school_class=self.other_year_class, code="ZZ-WRONG-YEAR"),
            self._item(subject=self.spanish, code="ZZ-INAPPLICABLE"),
            self._item(subject=self.french_history, code="ZZ-MISSING-TEACHER", teacher_id=uuid4()),
            self._item(subject=self.french_science, code="ZZ-CODE-CONFLICT"),
        ]
        response = self._create(items)
        self.assertEqual(response.status_code, 422, response.text)
        codes = {row["code"] for row in response.json()["detail"]["validation_failures"]}
        self.assertEqual(
            codes,
            {
                "course_class_year_mismatch",
                "course_subject_not_applicable",
                "teacher_not_found",
                "course_code_conflict",
            },
        )
        self.assertIsNone(self.db.scalar(select(Course).where(Course.code == "ZZ-VALID-WOULD-CREATE")))

    def test_invalid_coefficient_is_rejected_before_route_and_creates_nothing(self):
        response = self._create([self._item(code="ZZ-ZERO-COEF", coefficient=0)])
        self.assertEqual(response.status_code, 422)
        self.assertIsNone(self.db.scalar(select(Course).where(Course.code == "ZZ-ZERO-COEF")))

    def test_duplicate_payload_key_and_code_are_reported_without_partial_writes(self):
        duplicate_key = self._create(
            [self._item(code="ZZ-KEY-A"), self._item(code="ZZ-KEY-B")]
        )
        self.assertEqual(duplicate_key.status_code, 422)
        self.assertEqual(
            duplicate_key.json()["detail"]["validation_failures"][0]["code"], "duplicate_selection"
        )

        duplicate_code = self._create(
            [
                self._item(code="ZZ-SAME-CODE"),
                self._item(
                    school_class=self.primary,
                    subject=self.english_science,
                    code="ZZ-SAME-CODE",
                    grading_system="WEIGHTED",
                ),
            ]
        )
        self.assertEqual(duplicate_code.status_code, 422)
        self.assertEqual(
            duplicate_code.json()["detail"]["validation_failures"][0]["code"], "course_code_conflict"
        )
        self.assertEqual(self.db.scalar(select(func.count(Course.id)).where(Course.code == "ZZ-SAME-CODE")), 0)

    def test_bulk_setup_is_admin_only(self):
        for user in (self.teacher_user, self.parent):
            with self.subTest(role=user.role):
                preview = self._preview(headers=self._headers(user))
                create = self._create([self._item()], headers=self._headers(user))
                self.assertEqual(preview.status_code, 403)
                self.assertEqual(create.status_code, 403)

    def test_bulk_create_writes_per_course_and_batch_audit_logs(self):
        response = self._create([self._item(code="ZZ-AUDIT-BULK")])
        self.assertEqual(response.status_code, 201, response.text)
        course_id = UUID(response.json()["created_course_ids"][0])
        per_course = self.db.scalar(
            select(AuditLog).where(AuditLog.action == "course_created", AuditLog.entity_id == course_id)
        )
        batch = self.db.scalar(select(AuditLog).where(AuditLog.action == "courses_bulk_created"))
        self.assertIsNotNone(per_course)
        self.assertTrue(per_course.new_value["bulk_setup"])
        self.assertIsNotNone(batch)
        self.assertEqual(batch.new_value["created_count"], 1)

    def test_preview_marks_existing_setup_and_generated_code_conflict(self):
        preview = self._preview()
        generated_code = preview.json()["rows"][0]["code"]
        self.db.add(
            Course(
                name="ZZ-TEST Unrelated",
                code=generated_code,
                teacher_id=None,
                term=TERM,
                school_year=OTHER_YEAR,
            )
        )
        self.db.commit()
        conflict_preview = self._preview()
        self.assertTrue(conflict_preview.json()["rows"][0]["code_conflict"])

        created = self._create([self._item(code="ZZ-PREVIEW-EXISTING")])
        self.assertEqual(created.status_code, 201)
        existing_preview = self._preview()
        row = existing_preview.json()["rows"][0]
        self.assertTrue(row["already_exists"])
        self.assertIsNotNone(row["existing_course_id"])

    def test_single_create_enforces_class_year_and_subject_applicability(self):
        base = {
            "code": "ZZ-SINGLE-GAP",
            "teacher_id": None,
            "term": TERM,
            "school_year": YEAR,
            "class_id": str(self.other_year_class.id),
            "subject_id": str(self.french_math.id),
        }
        wrong_year = self.client.post("/api/v1/courses", json=base, headers=self._headers(self.admin))
        self.assertEqual(wrong_year.status_code, 422)
        self.assertEqual(wrong_year.json()["detail"]["code"], "course_class_year_mismatch")

        base.update({"code": "ZZ-SINGLE-INAPPLICABLE", "class_id": str(self.sixth.id), "subject_id": str(self.spanish.id)})
        inapplicable = self.client.post("/api/v1/courses", json=base, headers=self._headers(self.admin))
        self.assertEqual(inapplicable.status_code, 422)
        self.assertEqual(inapplicable.json()["detail"]["code"], "course_subject_not_applicable")

    def test_unassigned_course_is_not_visible_or_editable_as_teacher_until_assigned(self):
        created = self._create([self._item(code="ZZ-UNASSIGNED-HIDDEN")])
        course_id = created.json()["created_course_ids"][0]
        teacher_headers = self._headers(self.teacher_user)
        listing = self.client.get("/api/v1/courses", headers=teacher_headers)
        detail = self.client.get(f"/api/v1/courses/{course_id}", headers=teacher_headers)
        self.assertNotIn(course_id, {row["id"] for row in listing.json()})
        self.assertEqual(detail.status_code, 403)

        assigned = self.client.put(
            f"/api/v1/courses/{course_id}",
            json={"teacher_id": str(self.teacher.id)},
            headers=self._headers(self.admin),
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        self.assertEqual(assigned.json()["teacher_id"], str(self.teacher.id))
        listing = self.client.get("/api/v1/courses", headers=teacher_headers)
        self.assertIn(course_id, {row["id"] for row in listing.json()})

    def test_single_course_can_be_created_unassigned_and_later_unassigned_again(self):
        response = self.client.post(
            "/api/v1/courses",
            json={
                "name": "ZZ-TEST Free course",
                "code": "ZZ-FREE-UNASSIGNED",
                "teacher_id": None,
                "term": TERM,
                "school_year": YEAR,
            },
            headers=self._headers(self.admin),
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertIsNone(response.json()["teacher_id"])
        course_id = response.json()["id"]
        assigned = self.client.put(
            f"/api/v1/courses/{course_id}",
            json={"teacher_id": str(self.teacher.id)},
            headers=self._headers(self.admin),
        )
        self.assertEqual(assigned.status_code, 200)
        unassigned = self.client.put(
            f"/api/v1/courses/{course_id}",
            json={"teacher_id": None},
            headers=self._headers(self.admin),
        )
        self.assertEqual(unassigned.status_code, 200, unassigned.text)
        self.assertIsNone(unassigned.json()["teacher_id"])


if __name__ == "__main__":
    unittest.main()
