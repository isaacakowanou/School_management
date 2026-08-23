"""Bulk student XLSX import: preview, validation, identity reuse, and commit."""

import io
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Class, Parent, Student, StudentClassAssignment, StudentParent, Teacher, User


YEAR = "2027-2028"
HEADERS = [
    "student_first_name",
    "student_last_name",
    "class_name",
    "parent_name",
    "parent_email",
    "student_number",
    "educmaster_number",
    "parent_phone",
    "relationship",
]


def workbook_bytes(rows: list[dict], headers: list[str] | None = None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    selected_headers = headers or HEADERS
    sheet.append(selected_headers)
    for row in rows:
        sheet.append([row.get(header) for header in selected_headers])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def row(**overrides) -> dict:
    values = {
        "student_first_name": "Awa",
        "student_last_name": "Mensah",
        "class_name": "6eme",
        "parent_name": "Ama Mensah",
        "parent_email": "ama@example.test",
        "student_number": "ZZ-TEST-IMPORT-001",
        "educmaster_number": "EDU-001",
        "parent_phone": "+2290100000000",
        "relationship": "Mere",
    }
    values.update(overrides)
    return values


class StudentImportTests(unittest.TestCase):
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
        self.admin = self._user("ZZ-TEST Import Admin", "import-admin@example.test", "admin")
        self.teacher_user = self._user("ZZ-TEST Import Teacher", "import-teacher@example.test", "teacher")
        self.parent_user = self._user("ZZ-TEST Import Parent", "existing-parent@example.test", "parent")
        self.db.flush()
        self.teacher = Teacher(user=self.teacher_user, employee_number="ZZ-TEST-IMPORT-TCH")
        self.existing_parent = Parent(user=self.parent_user, phone="+2290100000001")
        self.sixth = Class(
            name_fr="6eme",
            name_en="JSS1",
            school_level="college",
            sort_order=1,
            school_year=YEAR,
        )
        self.first_c = Class(
            name_fr="1ere C",
            name_en="SS2",
            school_level="college",
            stream="C",
            sort_order=6,
            school_year=YEAR,
        )
        self.first_d = Class(
            name_fr="1ere D",
            name_en="SS2",
            school_level="college",
            stream="D",
            sort_order=7,
            school_year=YEAR,
        )
        self.db.add_all([self.teacher, self.existing_parent, self.sixth, self.first_c, self.first_d])
        self.db.commit()
        self.admin_headers = self._headers(self.admin.email)

    def tearDown(self):
        self.db.close()
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _user(self, name: str, email: str, role: str, *, deleted=False) -> User:
        user = User(name=name, email=email, password_hash=hash_password(self.password), role=role)
        if deleted:
            from datetime import datetime, timezone

            user.deleted_at = datetime.now(timezone.utc)
        self.db.add(user)
        return user

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _post_file(self, path: str, rows: list[dict], *, headers=None, data=None, auth=None):
        return self.client.post(
            path,
            data={"school_year": YEAR, **(data or {})},
            files={
                "file": (
                    "students.xlsx",
                    workbook_bytes(rows, headers),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            headers=auth or self.admin_headers,
        )

    def _preview(self, rows: list[dict], *, headers=None):
        return self._post_file("/api/v1/students/import/preview", rows, headers=headers)

    def _commit(self, rows: list[dict], selected_rows: list[int] | None = None):
        selected_rows = selected_rows or list(range(2, len(rows) + 2))
        return self._post_file(
            "/api/v1/students/import/commit",
            rows,
            data={"selected_rows": json.dumps(selected_rows)},
        )

    def test_preview_normalizes_class_and_performs_no_writes(self):
        before = self.db.scalar(select(func.count(Student.id)))
        response = self._preview([row(class_name="  6EME  ")])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["valid_rows"], 1)
        self.assertEqual(data["rows"][0]["class_name"], "6eme")
        self.assertEqual(data["rows"][0]["school_level"], "college")
        self.db.expire_all()
        self.assertEqual(self.db.scalar(select(func.count(Student.id))), before)

    def test_preview_rejects_missing_unknown_and_forbidden_columns(self):
        missing = self._preview([row()], headers=[header for header in HEADERS if header != "parent_email"])
        self.assertEqual(missing.status_code, 422)
        self.assertEqual(missing.json()["detail"]["code"], "student_import_missing_columns")

        forbidden_headers = HEADERS + ["school_year"]
        forbidden = self._preview([row(school_year=YEAR)], headers=forbidden_headers)
        self.assertEqual(forbidden.status_code, 422)
        self.assertEqual(forbidden.json()["detail"]["code"], "student_import_unknown_columns")

    def test_preview_reports_blank_required_values_and_bad_email(self):
        response = self._preview(
            [
                row(student_first_name=" "),
                row(student_number="ZZ-TEST-IMPORT-002", parent_email="not-an-email"),
            ]
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()["rows"]
        self.assertFalse(rows[0]["is_valid"])
        self.assertIn("student_import_required", {issue["code"] for issue in rows[0]["errors"]})
        self.assertFalse(rows[1]["is_valid"])
        self.assertIn("student_import_invalid_email", {issue["code"] for issue in rows[1]["errors"]})

    def test_preview_rejects_invalid_workbook(self):
        response = self.client.post(
            "/api/v1/students/import/preview",
            data={"school_year": YEAR},
            files={"file": ("students.xlsx", b"not-an-xlsx", "application/octet-stream")},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "student_import_invalid_workbook")

    def test_preview_rejects_non_xlsx_extension_and_duplicate_headers(self):
        wrong_type = self.client.post(
            "/api/v1/students/import/preview",
            data={"school_year": YEAR},
            files={"file": ("students.csv", b"a,b", "text/csv")},
            headers=self.admin_headers,
        )
        self.assertEqual(wrong_type.status_code, 422)
        self.assertEqual(wrong_type.json()["detail"]["code"], "student_import_invalid_file_type")

        duplicate_headers = HEADERS + ["parent_email"]
        duplicate = self._preview([row()], headers=duplicate_headers)
        self.assertEqual(duplicate.status_code, 422)
        self.assertEqual(duplicate.json()["detail"]["code"], "student_import_duplicate_columns")

    def test_commit_rejects_empty_or_mismatched_selection(self):
        empty = self._post_file(
            "/api/v1/students/import/commit",
            [row()],
            data={"selected_rows": "[]"},
        )
        self.assertEqual(empty.status_code, 422)
        self.assertEqual(empty.json()["detail"]["code"], "student_import_no_rows_selected")

        mismatched = self._post_file(
            "/api/v1/students/import/commit",
            [row()],
            data={"selected_rows": "[99]"},
        )
        self.assertEqual(mismatched.status_code, 422)
        self.assertEqual(mismatched.json()["detail"]["code"], "student_import_invalid_selection")

    def test_preview_reports_missing_and_ambiguous_classes_without_creating_them(self):
        response = self._preview(
            [
                row(class_name="Classe inventee"),
                row(student_number="ZZ-TEST-IMPORT-002", class_name="SS2"),
            ]
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()["rows"]
        self.assertIn("student_import_class_not_found", {issue["code"] for issue in rows[0]["errors"]})
        self.assertIn("student_import_class_ambiguous", {issue["code"] for issue in rows[1]["errors"]})
        self.assertIsNone(
            self.db.scalar(select(Class).where(Class.name_fr == "Classe inventee", Class.school_year == YEAR))
        )

    def test_preview_rejects_active_trashed_and_within_file_student_number_duplicates(self):
        active = Student(first_name="Existing", last_name="Active", student_number="ZZ-TEST-ACTIVE")
        trashed = Student(first_name="Existing", last_name="Trashed", student_number="ZZ-TEST-TRASHED")
        from datetime import datetime, timezone

        trashed.deleted_at = datetime.now(timezone.utc)
        self.db.add_all([active, trashed])
        self.db.commit()
        response = self._preview(
            [
                row(student_number="ZZ-TEST-ACTIVE"),
                row(student_number="ZZ-TEST-TRASHED"),
                row(student_number="ZZ-TEST-WITHIN"),
                row(student_number="ZZ-TEST-WITHIN", parent_email="other@example.test", parent_name="Other Parent"),
            ]
        )
        self.assertEqual(response.status_code, 200)
        for preview_row in response.json()["rows"]:
            self.assertIn("student_import_duplicate_student_number", {issue["code"] for issue in preview_row["errors"]})

    def test_preview_reuses_sibling_parent_and_rejects_conflicting_upload_names(self):
        reusable = self._preview(
            [
                row(student_number="ZZ-TEST-SIB-001", parent_email="Sibling@Example.Test"),
                row(student_number="ZZ-TEST-SIB-002", parent_email=" sibling@example.test "),
            ]
        )
        self.assertEqual(reusable.status_code, 200)
        self.assertEqual([item["parent_action"] for item in reusable.json()["rows"]], ["create", "reuse"])

        conflict = self._preview(
            [
                row(student_number="ZZ-TEST-CONFLICT-001", parent_email="same@example.test", parent_name="Parent One"),
                row(student_number="ZZ-TEST-CONFLICT-002", parent_email="SAME@example.test", parent_name="Parent Two"),
            ]
        )
        self.assertEqual(conflict.status_code, 200)
        for preview_row in conflict.json()["rows"]:
            self.assertIn("student_import_parent_name_conflict", {issue["code"] for issue in preview_row["errors"]})

    def test_preview_reuses_active_parent_but_rejects_cross_role_email(self):
        response = self._preview(
            [
                row(parent_email=self.parent_user.email, parent_name=self.parent_user.name),
                row(
                    student_number="ZZ-TEST-IMPORT-002",
                    parent_email=self.teacher_user.email,
                    parent_name=self.teacher_user.name,
                ),
            ]
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()["rows"]
        self.assertEqual(rows[0]["parent_action"], "reuse")
        self.assertIn("student_import_email_role_conflict", {issue["code"] for issue in rows[1]["errors"]})

    def test_preview_warns_without_overwriting_existing_parent_identity(self):
        response = self._preview([row(parent_email=self.parent_user.email, parent_name="Different Name")])
        self.assertEqual(response.status_code, 200)
        preview_row = response.json()["rows"][0]
        self.assertTrue(preview_row["is_valid"])
        self.assertIn("student_import_parent_details_differ", {issue["code"] for issue in preview_row["warnings"]})

    def test_preview_warns_when_sibling_rows_disagree_on_parent_phone(self):
        response = self._preview(
            [
                row(student_number="ZZ-TEST-PHONE-001", parent_email="phone@example.test", parent_phone="111"),
                row(student_number="ZZ-TEST-PHONE-002", parent_email="PHONE@example.test", parent_phone="222"),
            ]
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(item["is_valid"] for item in response.json()["rows"]))
        self.assertTrue(
            all(
                "student_import_parent_details_differ" in {issue["code"] for issue in item["warnings"]}
                for item in response.json()["rows"]
            )
        )

    def test_soft_deleted_parent_email_is_available_for_new_account(self):
        from datetime import datetime, timezone

        deleted_user = self._user("Deleted Parent", "deleted@example.test", "parent", deleted=True)
        self.db.flush()
        deleted_parent = Parent(user=deleted_user, deleted_at=datetime.now(timezone.utc))
        self.db.add(deleted_parent)
        self.db.commit()
        preview = self._preview([row(parent_email="DELETED@example.test", parent_name="New Parent")])
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["rows"][0]["parent_action"], "create")

        with patch("services.student_import.send_account_created_email", return_value={"success": True}):
            committed = self._commit([row(parent_email="DELETED@example.test", parent_name="New Parent")])
        self.assertEqual(committed.status_code, 200)
        self.assertEqual(committed.json()["parents_created"], 1)
        self.db.expire_all()
        active_users = self.db.scalars(
            select(User).where(func.lower(User.email) == "deleted@example.test", User.deleted_at.is_(None))
        ).all()
        self.assertEqual(len(active_users), 1)
        self.assertNotEqual(active_users[0].id, deleted_user.id)

    @patch("services.student_import.send_account_created_email", return_value={"success": True})
    def test_commit_creates_student_assignment_parent_link_and_audits(self, send_email):
        response = self._commit([row()])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["created"], 1)
        self.assertEqual(data["failed"], 0)
        self.assertEqual(data["parents_created"], 1)
        self.assertEqual(data["emails_sent"], 1)
        self.db.expire_all()
        student = self.db.scalar(select(Student).where(Student.student_number == "ZZ-TEST-IMPORT-001"))
        self.assertEqual(student.school_level, "college")
        assignment = self.db.scalar(
            select(StudentClassAssignment).where(
                StudentClassAssignment.student_id == student.id,
                StudentClassAssignment.school_year == YEAR,
            )
        )
        self.assertEqual(assignment.class_id, self.sixth.id)
        self.assertIsNotNone(self.db.scalar(select(StudentParent).where(StudentParent.student_id == student.id)))
        actions = set(self.db.scalars(select(AuditLog.action)).all())
        self.assertTrue({"student_created", "parent_created", "parent_linked_to_student"}.issubset(actions))
        send_email.assert_called_once()

    @patch("services.student_import.send_account_created_email", return_value={"success": True})
    def test_commit_generates_student_number_and_returns_it(self, _send_email):
        response = self._commit([row(student_number=None)])
        self.assertEqual(response.status_code, 200)
        number = response.json()["rows"][0]["student_number"]
        self.assertRegex(number, r"^STU-\d{4}-\d{4}$")

    @patch("services.student_import.send_account_created_email", return_value={"success": True})
    def test_commit_creates_one_parent_and_sends_one_email_for_siblings(self, send_email):
        rows = [
            row(student_number="ZZ-TEST-SIB-001", parent_email="siblings@example.test"),
            row(student_number="ZZ-TEST-SIB-002", parent_email="SIBLINGS@example.test"),
        ]
        response = self._commit(rows)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["created"], 2)
        self.assertEqual(data["parents_created"], 1)
        self.assertEqual(data["parents_reused"], 0)
        self.assertEqual(data["emails_sent"], 1)
        send_email.assert_called_once()
        self.db.expire_all()
        self.assertEqual(
            self.db.scalar(
                select(func.count(Parent.id)).join(User).where(func.lower(User.email) == "siblings@example.test")
            ),
            1,
        )

    @patch("services.student_import.send_account_created_email")
    def test_existing_parent_is_reused_without_password_or_welcome_email(self, send_email):
        response = self._commit([row(parent_email=self.parent_user.email, parent_name=self.parent_user.name)])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["parents_created"], 0)
        self.assertEqual(data["parents_reused"], 1)
        self.assertEqual(data["emails_sent"], 0)
        send_email.assert_not_called()

    @patch("services.student_import.send_account_created_email", return_value={"success": True})
    def test_commit_partial_success_and_selected_rows(self, _send_email):
        rows = [
            row(student_number="ZZ-TEST-PARTIAL-001"),
            row(student_number="ZZ-TEST-PARTIAL-002", class_name="Missing"),
            row(student_number="ZZ-TEST-PARTIAL-003", parent_email="third@example.test", parent_name="Third Parent"),
        ]
        response = self._commit(rows, selected_rows=[2, 3])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["created"], 1)
        self.assertEqual(data["failed"], 1)
        self.assertEqual(data["failures"][0]["row_number"], 3)
        self.db.expire_all()
        self.assertIsNotNone(self.db.scalar(select(Student).where(Student.student_number == "ZZ-TEST-PARTIAL-001")))
        self.assertIsNone(self.db.scalar(select(Student).where(Student.student_number == "ZZ-TEST-PARTIAL-003")))

    @patch("services.student_import.send_account_created_email", return_value={"success": False, "error": "offline"})
    def test_email_failure_does_not_roll_back_committed_students(self, _send_email):
        response = self._commit([row()])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["emails_failed"], 1)
        self.db.expire_all()
        self.assertIsNotNone(self.db.scalar(select(Student).where(Student.student_number == "ZZ-TEST-IMPORT-001")))

    @patch("services.student_import.send_account_created_email", return_value={"success": True})
    def test_commit_revalidates_database_changes_since_preview(self, _send_email):
        preview = self._preview([row()])
        self.assertEqual(preview.status_code, 200)
        self.db.add(Student(first_name="Concurrent", last_name="Student", student_number="ZZ-TEST-IMPORT-001"))
        self.db.commit()
        response = self._commit([row()])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertEqual(response.json()["failed"], 1)

    @patch("services.student_import.send_account_created_email", return_value={"success": True})
    def test_deselecting_one_duplicate_allows_the_selected_row_to_commit(self, _send_email):
        rows = [
            row(student_number="ZZ-TEST-DESELECT-DUP"),
            row(
                student_number="ZZ-TEST-DESELECT-DUP",
                parent_email="second@example.test",
                parent_name="Second Parent",
            ),
        ]
        preview = self._preview(rows)
        self.assertEqual(preview.json()["invalid_rows"], 2)
        response = self._commit(rows, selected_rows=[2])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["failed"], 0)

    def test_teacher_and_parent_cannot_preview_or_commit(self):
        for user in [self.teacher_user, self.parent_user]:
            auth = self._headers(user.email)
            with self.subTest(role=user.role):
                preview = self._post_file("/api/v1/students/import/preview", [row()], auth=auth)
                self.assertEqual(preview.status_code, 403)
                commit = self._post_file(
                    "/api/v1/students/import/commit",
                    [row()],
                    data={"selected_rows": "[2]"},
                    auth=auth,
                )
                self.assertEqual(commit.status_code, 403)


if __name__ == "__main__":
    unittest.main()
