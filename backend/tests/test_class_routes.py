import unittest
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, Class, Course, Student, Teacher, User


class ClassRouteTests(unittest.TestCase):
    password = "test-password-123"

    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        # Enforce FK constraints so the ON DELETE SET NULL belt-and-suspenders
        # test is meaningful (SQLite ignores FKs unless this pragma is on).
        @event.listens_for(self.engine, "connect")
        def _enable_fk(dbapi_conn, _record):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

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
        self.admin_user = self._user(name="Admin", email="admin-cls@example.test", role="admin")
        self.parent_user = self._user(name="Parent", email="parent-cls@example.test", role="parent")
        self.teacher_user = self._user(name="Teacher", email="teacher-cls@example.test", role="teacher")
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-CLS-1")
        self.db.add(self.teacher)
        self.db.commit()

    def _headers(self, email):
        r = self.client.post("/api/v1/auth/login", json={"email": email, "password": self.password})
        self.assertEqual(r.status_code, 200)
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def _admin(self):
        return self._headers(self.admin_user.email)

    def _class_payload(self, **overrides):
        payload = {
            "name_fr": "6ème",
            "name_en": "JSS1",
            "school_level": "college",
            "stream": None,
            "sort_order": 1,
            "school_year": "2026-2027",
        }
        payload.update(overrides)
        return payload

    def _create_class(self, **overrides):
        r = self.client.post("/api/v1/classes", json=self._class_payload(**overrides), headers=self._admin())
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def _create_student(self, number, class_id=None):
        body = {"first_name": "A", "last_name": "B", "student_number": number, "grade_level": "6"}
        if class_id is not None:
            body["class_id"] = class_id
        r = self.client.post("/api/v1/students", json=body, headers=self._admin())
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def _create_course(self, code, class_id=None):
        body = {
            "name": "Course", "code": code, "teacher_id": str(self.teacher.id),
            "grade_level": "6", "term": "1er Trimestre", "school_year": "2026-2027",
        }
        if class_id is not None:
            body["class_id"] = class_id
        r = self.client.post("/api/v1/courses", json=body, headers=self._admin())
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    # --- CRUD ---
    def test_admin_can_create_and_get_class(self):
        data = self._create_class()
        self.assertEqual(data["name_fr"], "6ème")
        self.assertEqual(data["name_en"], "JSS1")
        self.assertEqual(data["school_level"], "college")
        self.assertEqual(data["sort_order"], 1)
        self.assertEqual(data["student_count"], 0)
        self.assertEqual(data["course_count"], 0)

        got = self.client.get(f"/api/v1/classes/{data['id']}", headers=self._admin())
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["id"], data["id"])

    def test_patch_updates_and_clears_nullable_fields(self):
        cls = self._create_class(name_en="JSS1", stream="C")
        # Set name_fr + sort_order; omit name_en/stream (must stay unchanged).
        r = self.client.patch(
            f"/api/v1/classes/{cls['id']}",
            json={"name_fr": "6ème B", "sort_order": 5},
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name_fr"], "6ème B")
        self.assertEqual(r.json()["sort_order"], 5)
        self.assertEqual(r.json()["name_en"], "JSS1")
        self.assertEqual(r.json()["stream"], "C")

        # Explicit null clears name_en and stream.
        r2 = self.client.patch(
            f"/api/v1/classes/{cls['id']}",
            json={"name_en": None, "stream": None},
            headers=self._admin(),
        )
        self.assertEqual(r2.status_code, 200)
        self.assertIsNone(r2.json()["name_en"])
        self.assertIsNone(r2.json()["stream"])

    def test_duplicate_name_fr_and_school_year_rejected(self):
        self._create_class(name_fr="5ème", school_year="2026-2027")
        dup = self.client.post(
            "/api/v1/classes",
            json=self._class_payload(name_fr="5ème", school_year="2026-2027"),
            headers=self._admin(),
        )
        self.assertEqual(dup.status_code, 409)
        # Same name in a different school year is allowed.
        other = self.client.post(
            "/api/v1/classes",
            json=self._class_payload(name_fr="5ème", school_year="2027-2028"),
            headers=self._admin(),
        )
        self.assertEqual(other.status_code, 201)

    # --- Permissions ---
    def test_non_admin_forbidden_on_all_class_endpoints(self):
        cls = self._create_class()
        for user in [self.parent_user, self.teacher_user]:
            with self.subTest(role=user.role):
                h = self._headers(user.email)
                self.assertEqual(self.client.get("/api/v1/classes", headers=h).status_code, 403)
                self.assertEqual(self.client.get(f"/api/v1/classes/{cls['id']}", headers=h).status_code, 403)
                self.assertEqual(
                    self.client.post(
                        "/api/v1/classes",
                        json=self._class_payload(name_fr="ZZ", school_year="2099-2100"),
                        headers=h,
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    self.client.patch(f"/api/v1/classes/{cls['id']}", json={"stream": "C"}, headers=h).status_code, 403
                )
                self.assertEqual(self.client.delete(f"/api/v1/classes/{cls['id']}", headers=h).status_code, 403)

    # --- Delete guard ---
    def test_delete_empty_class_works(self):
        cls = self._create_class()
        r = self.client.delete(f"/api/v1/classes/{cls['id']}", headers=self._admin())
        self.assertEqual(r.status_code, 200)
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Class, UUID(cls["id"])).deleted_at)

    def test_delete_guard_fires_when_students_assigned(self):
        cls = self._create_class()
        self._create_student("S-GUARD-1", class_id=cls["id"])
        r = self.client.delete(f"/api/v1/classes/{cls['id']}", headers=self._admin())
        self.assertEqual(r.status_code, 409)
        detail = r.json()["detail"]
        self.assertEqual(detail["student_count"], 1)
        self.assertEqual(detail["course_count"], 0)

    def test_delete_guard_fires_when_courses_assigned(self):
        cls = self._create_class()
        self._create_course("C-GUARD-1", class_id=cls["id"])
        r = self.client.delete(f"/api/v1/classes/{cls['id']}", headers=self._admin())
        self.assertEqual(r.status_code, 409)
        detail = r.json()["detail"]
        self.assertEqual(detail["student_count"], 0)
        self.assertEqual(detail["course_count"], 1)

    def test_delete_guard_fires_when_both_assigned(self):
        cls = self._create_class()
        self._create_student("S-GUARD-2", class_id=cls["id"])
        self._create_course("C-GUARD-2", class_id=cls["id"])
        r = self.client.delete(f"/api/v1/classes/{cls['id']}", headers=self._admin())
        self.assertEqual(r.status_code, 409)
        detail = r.json()["detail"]
        self.assertEqual(detail["student_count"], 1)
        self.assertEqual(detail["course_count"], 1)

    def test_delete_sets_class_id_null_on_linked_rows(self):
        # Belt and suspenders: bypass the API guard and delete the class directly
        # to prove ON DELETE SET NULL (FK enforcement is enabled in setUp).
        cls = self._create_class()
        self._create_student("S-SETNULL", class_id=cls["id"])
        self._create_course("C-SETNULL", class_id=cls["id"])

        self.db.expire_all()
        school_class = self.db.get(Class, UUID(cls["id"]))
        self.db.delete(school_class)
        self.db.commit()

        self.db.expire_all()
        student = self.db.scalar(select(Student).where(Student.student_number == "S-SETNULL"))
        course = self.db.scalar(select(Course).where(Course.code == "C-SETNULL"))
        self.assertIsNone(student.class_id)
        self.assertIsNone(course.class_id)

    # --- Filters + counts ---
    def test_list_filters_by_school_year(self):
        self._create_class(name_fr="6ème", school_year="2026-2027")
        self._create_class(name_fr="6ème", school_year="2027-2028")
        r = self.client.get("/api/v1/classes?school_year=2026-2027", headers=self._admin())
        self.assertEqual(r.status_code, 200)
        self.assertEqual({c["school_year"] for c in r.json()}, {"2026-2027"})

    def test_list_filters_by_school_level(self):
        self._create_class(name_fr="Maternelle 2", school_level="maternelle", sort_order=1)
        self._create_class(name_fr="6ème", school_level="college", sort_order=1)
        r = self.client.get("/api/v1/classes?school_level=college", headers=self._admin())
        self.assertEqual(r.status_code, 200)
        self.assertEqual({c["school_level"] for c in r.json()}, {"college"})

    def test_list_filters_by_year_and_level_together(self):
        self._create_class(name_fr="6ème", school_level="college", school_year="2026-2027")
        self._create_class(name_fr="6ème", school_level="college", school_year="2027-2028")
        self._create_class(name_fr="Prim 1", school_level="primaire", school_year="2026-2027", sort_order=1)
        r = self.client.get(
            "/api/v1/classes?school_year=2026-2027&school_level=college", headers=self._admin()
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name_fr"], "6ème")

    def test_list_includes_student_and_course_counts(self):
        cls = self._create_class()
        self._create_student("S-COUNT", class_id=cls["id"])
        self._create_course("C-COUNT", class_id=cls["id"])
        r = self.client.get("/api/v1/classes?school_year=2026-2027", headers=self._admin())
        item = next(c for c in r.json() if c["id"] == cls["id"])
        self.assertEqual(item["student_count"], 1)
        self.assertEqual(item["course_count"], 1)

    # --- Student / Course class_id assignment ---
    def test_student_put_sets_and_clears_class_id(self):
        cls = self._create_class()
        student = self._create_student("S-PUT")
        self.assertIsNone(student["class_id"])

        r = self.client.put(
            f"/api/v1/students/{student['id']}", json={"class_id": cls["id"]}, headers=self._admin()
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["class_id"], cls["id"])

        r2 = self.client.put(
            f"/api/v1/students/{student['id']}", json={"class_id": None}, headers=self._admin()
        )
        self.assertEqual(r2.status_code, 200)
        self.assertIsNone(r2.json()["class_id"])

    def test_course_put_sets_and_clears_class_id(self):
        cls = self._create_class()
        course = self._create_course("C-PUT")
        self.assertIsNone(course["class_id"])

        r = self.client.put(
            f"/api/v1/courses/{course['id']}", json={"class_id": cls["id"]}, headers=self._admin()
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["class_id"], cls["id"])

        r2 = self.client.put(
            f"/api/v1/courses/{course['id']}", json={"class_id": None}, headers=self._admin()
        )
        self.assertEqual(r2.status_code, 200)
        self.assertIsNone(r2.json()["class_id"])

    def test_assigning_unknown_class_id_is_rejected(self):
        r = self.client.post(
            "/api/v1/students",
            json={
                "first_name": "A", "last_name": "B", "student_number": "S-BADCLASS",
                "grade_level": "6", "class_id": str(uuid4()),
            },
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
