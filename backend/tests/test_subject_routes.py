import unittest
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import Base, Class, Course, Subject, Teacher, User


class SubjectRouteTests(unittest.TestCase):
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
        self.admin_user = self._user(name="Admin", email="admin-subj@example.test", role="admin")
        self.teacher_user = self._user(name="Teacher", email="teacher-subj@example.test", role="teacher")
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="T-SUBJ-1")
        self.db.add(self.teacher)
        self.db.commit()

    def _headers(self, email):
        r = self.client.post("/api/v1/auth/login", json={"email": email, "password": self.password})
        self.assertEqual(r.status_code, 200)
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def _admin(self):
        return self._headers(self.admin_user.email)

    def _subject_payload(self, **overrides):
        payload = {
            "name_fr": "Mathématique",
            "name_en": "Mathematics",
            "section": "FRENCH",
            "level_group": "COLLEGE_FIRST_CYCLE",
            "sort_order": 6,
            "applicable_classes": None,
        }
        payload.update(overrides)
        return payload

    def _create_subject(self, **overrides) -> dict:
        r = self.client.post("/api/v1/subjects", json=self._subject_payload(**overrides), headers=self._admin())
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def _create_class(self, name_fr, school_level="college", sort_order=1, school_year="2026-2027") -> Class:
        school_class = Class(
            name_fr=name_fr,
            school_level=school_level,
            sort_order=sort_order,
            school_year=school_year,
        )
        self.db.add(school_class)
        self.db.commit()
        self.db.refresh(school_class)
        return school_class

    def _course_payload(self, **overrides):
        payload = {
            "name": "Free text course",
            "code": "CRS-1",
            "teacher_id": str(self.teacher.id),
            "grade_level": "6ème",
            "term": "1er Trimestre",
            "school_year": "2026-2027",
        }
        payload.update(overrides)
        return payload

    # --- CRUD ---

    def test_create_and_get_subject(self):
        created = self._create_subject()
        r = self.client.get(f"/api/v1/subjects/{created['id']}", headers=self._admin())
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["name_fr"], "Mathématique")
        self.assertEqual(body["section"], "FRENCH")
        self.assertEqual(body["level_group"], "COLLEGE_FIRST_CYCLE")
        self.assertIsNone(body["applicable_classes"])
        self.assertEqual(body["course_count"], 0)

    def test_duplicate_name_level_section_conflicts(self):
        self._create_subject()
        r = self.client.post("/api/v1/subjects", json=self._subject_payload(), headers=self._admin())
        self.assertEqual(r.status_code, 409)

    def test_same_name_other_section_is_allowed(self):
        # Mathématique legitimately exists in both bulletin sections of a cycle.
        self._create_subject(section="FRENCH")
        created = self._create_subject(section="ENGLISH", sort_order=2)
        self.assertEqual(created["section"], "ENGLISH")

    def test_update_subject_and_clear_applicable_classes(self):
        created = self._create_subject(
            name_fr="Espagnol", name_en="Spanish", sort_order=9, applicable_classes=["4ème", "3ème"]
        )
        r = self.client.patch(
            f"/api/v1/subjects/{created['id']}",
            json={"sort_order": 10},
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["sort_order"], 10)
        # Omitted key leaves the restriction unchanged.
        self.assertEqual(r.json()["applicable_classes"], ["4ème", "3ème"])

        r = self.client.patch(
            f"/api/v1/subjects/{created['id']}",
            json={"applicable_classes": None},
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["applicable_classes"])

    def test_delete_subject_without_courses(self):
        created = self._create_subject()
        r = self.client.delete(f"/api/v1/subjects/{created['id']}", headers=self._admin())
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(self.db.scalar(select(Subject)))

    def test_delete_subject_with_courses_conflicts(self):
        created = self._create_subject()
        r = self.client.post(
            "/api/v1/courses",
            json=self._course_payload(name=None, subject_id=created["id"]),
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 201, r.text)

        r = self.client.delete(f"/api/v1/subjects/{created['id']}", headers=self._admin())
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["course_count"], 1)

    def test_non_admin_cannot_manage_subjects(self):
        teacher_headers = self._headers(self.teacher_user.email)
        r = self.client.get("/api/v1/subjects", headers=teacher_headers)
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/api/v1/subjects", json=self._subject_payload(), headers=teacher_headers)
        self.assertEqual(r.status_code, 403)

    # --- list filters ---

    def test_list_filters_by_section_and_level_group(self):
        self._create_subject()  # FRENCH / COLLEGE_FIRST_CYCLE
        self._create_subject(name_fr="Anglais", name_en="English language", section="ENGLISH",
                             level_group="PRIMARY", sort_order=1)

        r = self.client.get("/api/v1/subjects?section=ENGLISH", headers=self._admin())
        self.assertEqual([s["name_fr"] for s in r.json()], ["Anglais"])

        r = self.client.get("/api/v1/subjects?level_group=COLLEGE_FIRST_CYCLE", headers=self._admin())
        self.assertEqual([s["name_fr"] for s in r.json()], ["Mathématique"])

    def test_list_orders_by_level_then_section_then_sort_order(self):
        self._create_subject(name_fr="Etudes sociales", name_en="Social Studies", section="ENGLISH",
                             level_group="COLLEGE_FIRST_CYCLE", sort_order=13)
        self._create_subject(name_fr="Pré-Lecture", name_en="Pre-reading skills",
                             level_group="NURSERY", sort_order=2)
        self._create_subject()  # Mathématique FRENCH first-cycle sort 6
        self._create_subject(name_fr="EPS", name_en="Fitness", level_group="COLLEGE_FIRST_CYCLE",
                             sort_order=7)

        r = self.client.get("/api/v1/subjects", headers=self._admin())
        self.assertEqual(
            [s["name_fr"] for s in r.json()],
            ["Pré-Lecture", "Mathématique", "EPS", "Etudes sociales"],
        )

    def test_list_filters_by_class_respecting_overrides(self):
        sixieme = self._create_class("6ème")
        quatrieme = self._create_class("4ème", sort_order=3)
        maths = self._create_subject()
        espagnol = self._create_subject(
            name_fr="Espagnol", name_en="Spanish", sort_order=9, applicable_classes=["4ème", "3ème"]
        )
        self._create_subject(name_fr="Anglais", name_en="English language", section="ENGLISH",
                             level_group="PRIMARY", sort_order=1)

        r = self.client.get(f"/api/v1/subjects?class_id={sixieme.id}", headers=self._admin())
        self.assertEqual([s["id"] for s in r.json()], [maths["id"]])

        r = self.client.get(f"/api/v1/subjects?class_id={quatrieme.id}", headers=self._admin())
        self.assertEqual([s["id"] for s in r.json()], [maths["id"], espagnol["id"]])

    def test_list_filter_matches_unaccented_class_names(self):
        # Admin-typed class rows ("6eme", "4EME") must match the canonical
        # taxonomy ("6ème", "4ème") — including applicable_classes overrides.
        sixieme = self._create_class("6eme")
        quatrieme = self._create_class("4EME", sort_order=3)
        maths = self._create_subject()
        espagnol = self._create_subject(
            name_fr="Espagnol", name_en="Spanish", sort_order=9, applicable_classes=["4ème", "3ème"]
        )

        r = self.client.get(f"/api/v1/subjects?class_id={sixieme.id}", headers=self._admin())
        self.assertEqual([s["id"] for s in r.json()], [maths["id"]])

        r = self.client.get(f"/api/v1/subjects?class_id={quatrieme.id}", headers=self._admin())
        self.assertEqual([s["id"] for s in r.json()], [maths["id"], espagnol["id"]])

    def test_list_filter_for_class_outside_taxonomy_is_empty(self):
        self._create_subject()
        odd_class = self._create_class("Classe spéciale")
        r = self.client.get(f"/api/v1/subjects?class_id={odd_class.id}", headers=self._admin())
        self.assertEqual(r.json(), [])

    # --- course <-> subject wiring ---

    def test_course_from_french_subject_derives_french_name_and_group(self):
        subject = self._create_subject()
        r = self.client.post(
            "/api/v1/courses",
            json=self._course_payload(name=None, subject_id=subject["id"]),
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertEqual(body["name"], "Mathématique")
        self.assertEqual(body["language_group"], "FRENCH")
        self.assertEqual(body["subject_id"], subject["id"])

    def test_course_from_english_subject_derives_english_name_and_group(self):
        subject = self._create_subject(section="ENGLISH", sort_order=2)
        r = self.client.post(
            "/api/v1/courses",
            json=self._course_payload(name=None, subject_id=subject["id"]),
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertEqual(body["name"], "Mathematics")
        self.assertEqual(body["language_group"], "ENGLISH")

    def test_course_with_conflicting_language_group_rejected(self):
        subject = self._create_subject()  # FRENCH
        r = self.client.post(
            "/api/v1/courses",
            json=self._course_payload(name=None, subject_id=subject["id"], language_group="ENGLISH"),
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 422)

    def test_course_with_conflicting_name_rejected_matching_name_allowed(self):
        subject = self._create_subject()
        r = self.client.post(
            "/api/v1/courses",
            json=self._course_payload(name="Maths perso", subject_id=subject["id"]),
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 422)

        r = self.client.post(
            "/api/v1/courses",
            json=self._course_payload(name="Mathématique", subject_id=subject["id"]),
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 201, r.text)

    def test_course_without_subject_still_requires_name(self):
        r = self.client.post(
            "/api/v1/courses",
            json=self._course_payload(name=None),
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 422)

    def test_free_text_course_unchanged(self):
        r = self.client.post("/api/v1/courses", json=self._course_payload(), headers=self._admin())
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertEqual(body["name"], "Free text course")
        self.assertIsNone(body["subject_id"])
        self.assertIsNone(body["language_group"])

    def test_update_links_subject_and_derives_fields(self):
        subject = self._create_subject(section="ENGLISH", sort_order=2)
        r = self.client.post("/api/v1/courses", json=self._course_payload(), headers=self._admin())
        course_id = r.json()["id"]

        r = self.client.put(
            f"/api/v1/courses/{course_id}",
            json={"subject_id": subject["id"]},
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["name"], "Mathematics")
        self.assertEqual(body["language_group"], "ENGLISH")
        self.assertEqual(body["subject_id"], subject["id"])

    def test_update_name_on_subject_linked_course_rejected_until_cleared(self):
        subject = self._create_subject()
        r = self.client.post(
            "/api/v1/courses",
            json=self._course_payload(name=None, subject_id=subject["id"]),
            headers=self._admin(),
        )
        course_id = r.json()["id"]

        r = self.client.put(
            f"/api/v1/courses/{course_id}",
            json={"name": "Autre nom"},
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 422)

        # Clearing the subject link in the same request frees the name.
        r = self.client.put(
            f"/api/v1/courses/{course_id}",
            json={"name": "Autre nom", "subject_id": None},
            headers=self._admin(),
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["name"], "Autre nom")
        self.assertIsNone(body["subject_id"])
        # language_group is kept — clearing the link doesn't untag the course.
        self.assertEqual(body["language_group"], "FRENCH")

    def test_course_subject_survives_in_db(self):
        subject = self._create_subject()
        r = self.client.post(
            "/api/v1/courses",
            json=self._course_payload(name=None, subject_id=subject["id"]),
            headers=self._admin(),
        )
        course = self.db.get(Course, UUID(r.json()["id"]))
        self.assertIsNotNone(course.subject_id)
        self.assertEqual(str(course.subject_id), subject["id"])


if __name__ == "__main__":
    unittest.main()
