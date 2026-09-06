import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from auth import hash_password
from database import get_db
from main import app
from models import AuditLog, Base, Course, Parent, Student, StudentParent, Teacher, User


TEACHER_HEADERS = ["teacher_name", "teacher_email", "teacher_phone", "employee_number"]
PARENT_HEADERS = ["student_number", "parent_name", "parent_email", "parent_phone", "relationship"]


def workbook_bytes(rows: list[dict], headers: list[str]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(header) for header in headers])
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def teacher_row(**overrides) -> dict:
    row = {
        "teacher_name": "ZZ-TEST-Teacher One",
        "teacher_email": "teacher-one@example.test",
        "teacher_phone": "+229 01 61 00 00 01",
        "employee_number": "ZZ-TEST-TCH-001",
    }
    row.update(overrides)
    return row


def parent_link_row(**overrides) -> dict:
    row = {
        "student_number": "ZZ-TEST-STU-001",
        "parent_name": "ZZ-TEST-Additional Parent",
        "parent_email": "additional-parent@example.test",
        "parent_phone": "+229 01 62 00 00 01",
        "relationship": "Father",
    }
    row.update(overrides)
    return row


class PeopleImportTests(unittest.TestCase):
    password = "test-password-123"

    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

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

    def _user(self, name: str, email: str, role: str, *, deleted: bool = False) -> User:
        user = User(name=name, email=email, password_hash=hash_password(self.password), role=role)
        if deleted:
            user.deleted_at = datetime.now(timezone.utc)
        self.db.add(user)
        return user

    def _seed(self):
        self.admin = self._user("ZZ-TEST-Admin", "people-import-admin@example.test", "admin")
        self.teacher_user = self._user("ZZ-TEST-Existing Teacher", "people-import-teacher@example.test", "teacher")
        self.parent_user = self._user("ZZ-TEST-Existing Parent", "people-import-parent@example.test", "parent")
        self.db.flush()
        self.existing_teacher = Teacher(
            user=self.teacher_user,
            phone="111",
            employee_number="ZZ-TEST-TCH-EXISTING",
        )
        self.existing_parent = Parent(user=self.parent_user, phone="222")
        self.student = Student(
            first_name="ZZ-TEST-Active",
            last_name="Student",
            student_number="ZZ-TEST-STU-001",
            academic_status="active",
        )
        self.second_student = Student(
            first_name="ZZ-TEST-Second",
            last_name="Student",
            student_number="ZZ-TEST-STU-002",
            academic_status="active",
        )
        self.deleted_student = Student(
            first_name="ZZ-TEST-Deleted",
            last_name="Student",
            student_number="ZZ-TEST-STU-DELETED",
            academic_status="active",
            deleted_at=datetime.now(timezone.utc),
        )
        self.graduated_student = Student(
            first_name="ZZ-TEST-Graduated",
            last_name="Student",
            student_number="ZZ-TEST-STU-GRADUATED",
            academic_status="graduated",
        )
        self.db.add_all(
            [
                self.existing_teacher,
                self.existing_parent,
                self.student,
                self.second_student,
                self.deleted_student,
                self.graduated_student,
            ]
        )
        self.db.commit()
        self.admin_headers = self._headers(self.admin.email)

    def _headers(self, email: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def _post_workbook(
        self,
        path: str,
        rows: list[dict],
        headers: list[str],
        *,
        selected_rows: list[int] | None = None,
        auth: dict[str, str] | None = None,
        filename: str = "import.xlsx",
    ):
        data = {}
        if selected_rows is not None:
            data["selected_rows"] = json.dumps(selected_rows)
        return self.client.post(
            path,
            data=data,
            files={
                "file": (
                    filename,
                    workbook_bytes(rows, headers),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            headers=auth or self.admin_headers,
        )

    def _teacher_preview(self, rows: list[dict], headers: list[str] | None = None, **kwargs):
        return self._post_workbook(
            "/api/v1/teachers/import/preview",
            rows,
            headers or TEACHER_HEADERS,
            **kwargs,
        )

    def _teacher_commit(self, rows: list[dict], selected_rows: list[int] | None = None, **kwargs):
        return self._post_workbook(
            "/api/v1/teachers/import/commit",
            rows,
            TEACHER_HEADERS,
            selected_rows=selected_rows or list(range(2, len(rows) + 2)),
            **kwargs,
        )

    def _parent_preview(self, rows: list[dict], headers: list[str] | None = None, **kwargs):
        return self._post_workbook(
            "/api/v1/parents/link-import/preview",
            rows,
            headers or PARENT_HEADERS,
            **kwargs,
        )

    def _parent_commit(self, rows: list[dict], selected_rows: list[int] | None = None, **kwargs):
        return self._post_workbook(
            "/api/v1/parents/link-import/commit",
            rows,
            PARENT_HEADERS,
            selected_rows=selected_rows or list(range(2, len(rows) + 2)),
            **kwargs,
        )

    # Teacher import
    def test_01_teacher_preview_normalizes_rows_and_performs_no_writes(self):
        before = self.db.scalar(select(func.count(Teacher.id)))
        response = self._teacher_preview(
            [teacher_row(teacher_name="  ZZ-TEST-Teacher One  ", teacher_email=" Teacher-One@Example.Test ")]
        )
        self.assertEqual(response.status_code, 200, response.text)
        row = response.json()["rows"][0]
        self.assertEqual(row["teacher_name"], "ZZ-TEST-Teacher One")
        self.assertEqual(row["teacher_email"], "teacher-one@example.test")
        self.db.expire_all()
        self.assertEqual(self.db.scalar(select(func.count(Teacher.id))), before)

    def test_02_teacher_preview_rejects_bad_file_and_column_shapes(self):
        wrong_type = self._teacher_preview([teacher_row()], filename="teachers.csv")
        self.assertEqual(wrong_type.status_code, 422)
        missing = self._teacher_preview([teacher_row()], headers=["teacher_name"])
        self.assertEqual(missing.status_code, 422)
        unknown = self._teacher_preview([teacher_row(extra="x")], headers=TEACHER_HEADERS + ["extra"])
        self.assertEqual(unknown.status_code, 422)

    def test_03_teacher_preview_rejects_blank_required_values_and_bad_email(self):
        response = self._teacher_preview(
            [teacher_row(teacher_name=""), teacher_row(teacher_email="not-an-email", employee_number="ZZ-TEST-TCH-002")]
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["rows"][0]["is_valid"])
        self.assertFalse(response.json()["rows"][1]["is_valid"])

    def test_04_teacher_preview_rejects_duplicate_emails_in_workbook(self):
        response = self._teacher_preview(
            [
                teacher_row(employee_number="ZZ-TEST-TCH-010"),
                teacher_row(teacher_email="TEACHER-ONE@example.test", employee_number="ZZ-TEST-TCH-011"),
            ]
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(not row["is_valid"] for row in response.json()["rows"]))

    def test_05_teacher_preview_rejects_active_email_across_roles(self):
        response = self._teacher_preview(
            [teacher_row(teacher_email=self.parent_user.email, employee_number="ZZ-TEST-TCH-012")]
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("teacher_import_email_conflict", {x["code"] for x in response.json()["rows"][0]["errors"]})

    def test_06_teacher_preview_rejects_active_and_workbook_employee_duplicates(self):
        response = self._teacher_preview(
            [
                teacher_row(employee_number=self.existing_teacher.employee_number),
                teacher_row(teacher_email="two@example.test", employee_number="ZZ-TEST-TCH-DUP"),
                teacher_row(teacher_email="three@example.test", employee_number="ZZ-TEST-TCH-DUP"),
            ]
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(not row["is_valid"] for row in response.json()["rows"]))

    def test_07_teacher_preview_allows_soft_deleted_email_and_employee_number(self):
        deleted_user = self._user("ZZ-TEST-Deleted Teacher", "deleted-teacher@example.test", "teacher", deleted=True)
        self.db.flush()
        self.db.add(
            Teacher(
                user=deleted_user,
                employee_number="ZZ-TEST-TCH-DELETED",
                deleted_at=datetime.now(timezone.utc),
            )
        )
        self.db.commit()
        response = self._teacher_preview(
            [teacher_row(teacher_email=deleted_user.email, employee_number="ZZ-TEST-TCH-DELETED")]
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["rows"][0]["is_valid"])

    @patch("services.teacher_import.send_account_created_email", return_value={"success": True})
    def test_08_teacher_commit_creates_bare_forced_change_account_and_audit(self, send_email):
        response = self._teacher_commit([teacher_row()])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["created"], 1)
        self.db.expire_all()
        teacher = self.db.scalar(select(Teacher).join(User).where(User.email == "teacher-one@example.test"))
        self.assertTrue(teacher.user.must_change_password)
        self.assertEqual(teacher.user.role, "teacher")
        self.assertEqual(self.db.scalar(select(func.count(Course.id)).where(Course.teacher_id == teacher.id)), 0)
        audit = self.db.scalar(select(AuditLog).where(AuditLog.action == "teacher_created", AuditLog.entity_id == teacher.id))
        self.assertEqual(audit.new_value["source"], "teacher_import")
        send_email.assert_called_once()

    @patch("services.teacher_import.send_account_created_email", return_value={"success": True})
    def test_09_teacher_commit_generates_employee_number_when_omitted(self, _send_email):
        response = self._teacher_commit([teacher_row(employee_number=None)])
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.json()["rows"][0]["employee_number"], r"^TCH-\d{4}-\d{4}$")

    @patch("services.teacher_import.send_account_created_email", return_value={"success": True})
    def test_10_teacher_commit_uses_selected_rows_and_savepoint_partial_success(self, _send_email):
        rows = [
            teacher_row(teacher_email="selected@example.test", employee_number="ZZ-TEST-TCH-020"),
            teacher_row(teacher_email=self.parent_user.email, employee_number="ZZ-TEST-TCH-021"),
            teacher_row(teacher_email="not-selected@example.test", employee_number="ZZ-TEST-TCH-022"),
        ]
        response = self._teacher_commit(rows, selected_rows=[2, 3])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["failed"], 1)
        self.assertIsNone(self.db.scalar(select(User).where(User.email == "not-selected@example.test")))

    @patch("services.teacher_import.send_account_created_email", return_value={"success": True})
    def test_11_teacher_commit_revalidates_changes_since_preview(self, _send_email):
        row = teacher_row(teacher_email="concurrent@example.test", employee_number="ZZ-TEST-TCH-030")
        self.assertEqual(self._teacher_preview([row]).status_code, 200)
        self._user("ZZ-TEST-Concurrent", "concurrent@example.test", "admin")
        self.db.commit()
        response = self._teacher_commit([row])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertEqual(response.json()["failed"], 1)

    @patch("services.teacher_import.send_account_created_email", return_value={"success": False, "error": "offline"})
    def test_12_teacher_email_failure_does_not_rollback_and_returns_password(self, _send_email):
        response = self._teacher_commit([teacher_row()])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["emails_failed"], 1)
        self.assertTrue(response.json()["email_results"][0]["temp_password"])
        self.assertIsNotNone(self.db.scalar(select(User).where(User.email == "teacher-one@example.test")))

    def test_13_teacher_import_routes_are_admin_only(self):
        auth = self._headers(self.teacher_user.email)
        self.assertEqual(self._teacher_preview([teacher_row()], auth=auth).status_code, 403)
        self.assertEqual(self._teacher_commit([teacher_row()], auth=auth).status_code, 403)

    # Parent-link import
    def test_14_parent_link_preview_resolves_student_and_performs_no_writes(self):
        before = self.db.scalar(select(func.count(StudentParent.id)))
        response = self._parent_preview([parent_link_row(parent_email=" ADDITIONAL-PARENT@Example.Test ")])
        self.assertEqual(response.status_code, 200, response.text)
        row = response.json()["rows"][0]
        self.assertEqual(row["student_id"], str(self.student.id))
        self.assertEqual(row["parent_email"], "additional-parent@example.test")
        self.assertEqual(self.db.scalar(select(func.count(StudentParent.id))), before)

    def test_15_parent_link_preview_rejects_unknown_deleted_and_graduated_students(self):
        response = self._parent_preview(
            [
                parent_link_row(student_number="ZZ-TEST-MISSING"),
                parent_link_row(student_number=self.deleted_student.student_number, parent_email="deleted-student@example.test"),
                parent_link_row(student_number=self.graduated_student.student_number, parent_email="graduate@example.test"),
            ]
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(not row["is_valid"] for row in response.json()["rows"]))

    @patch("services.parent_link_import.send_account_created_email", return_value={"success": True})
    def test_16_parent_link_commit_allows_additional_parent_for_student(self, _send_email):
        self.db.add(StudentParent(student_id=self.student.id, parent_id=self.existing_parent.id, relationship="Mother"))
        self.db.commit()
        response = self._parent_commit([parent_link_row()])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["linked"], 1)
        self.assertEqual(
            self.db.scalar(select(func.count(StudentParent.id)).where(StudentParent.student_id == self.student.id)),
            2,
        )

    @patch("services.parent_link_import.send_account_created_email")
    def test_17_parent_link_reuses_active_parent_without_email_or_overwrite(self, send_email):
        response = self._parent_commit(
            [
                parent_link_row(
                    parent_name=self.parent_user.name,
                    parent_email=self.parent_user.email,
                    parent_phone=self.existing_parent.phone,
                )
            ]
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["parents_reused"], 1)
        self.assertEqual(response.json()["parents_created"], 0)
        self.db.refresh(self.existing_parent)
        self.assertEqual(self.existing_parent.user.name, self.parent_user.name)
        self.assertEqual(self.existing_parent.phone, "222")
        send_email.assert_not_called()

    def test_18_parent_link_reuse_mismatch_is_a_warning_and_does_not_overwrite(self):
        rows = [
            parent_link_row(
                parent_name="Different Parent Name",
                parent_email=self.parent_user.email,
                parent_phone="different-phone",
            )
        ]
        response = self._parent_preview(rows)
        self.assertEqual(response.status_code, 200)
        row = response.json()["rows"][0]
        self.assertTrue(row["is_valid"])
        self.assertIn("parent_link_import_parent_details_differ", {x["code"] for x in row["warnings"]})
        committed = self._parent_commit(rows)
        self.assertEqual(committed.status_code, 200)
        self.db.refresh(self.existing_parent)
        self.assertEqual(self.existing_parent.user.name, self.parent_user.name)
        self.assertEqual(self.existing_parent.phone, "222")

    @patch("services.parent_link_import.send_account_created_email", return_value={"success": True})
    def test_19_parent_link_creates_shared_parent_once_and_emails_once(self, send_email):
        rows = [
            parent_link_row(),
            parent_link_row(student_number=self.second_student.student_number),
        ]
        response = self._parent_commit(rows)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["linked"], 2)
        self.assertEqual(response.json()["parents_created"], 1)
        self.assertEqual(response.json()["emails_sent"], 1)
        send_email.assert_called_once()

    def test_20_parent_link_preview_rejects_active_non_parent_email(self):
        response = self._parent_preview([parent_link_row(parent_email=self.teacher_user.email)])
        self.assertEqual(response.status_code, 200)
        self.assertIn("parent_link_import_email_role_conflict", {x["code"] for x in response.json()["rows"][0]["errors"]})

    @patch("services.parent_link_import.send_account_created_email", return_value={"success": True})
    def test_21_parent_link_soft_deleted_parent_email_creates_new_account(self, _send_email):
        deleted_user = self._user("ZZ-TEST-Old Parent", "old-parent@example.test", "parent", deleted=True)
        self.db.flush()
        old_parent = Parent(user=deleted_user, deleted_at=datetime.now(timezone.utc))
        self.db.add(old_parent)
        self.db.commit()
        response = self._parent_commit([parent_link_row(parent_email=deleted_user.email)])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["parents_created"], 1)
        active = self.db.scalar(select(User).where(User.email == deleted_user.email, User.deleted_at.is_(None)))
        self.assertNotEqual(active.id, deleted_user.id)

    @patch("services.parent_link_import.send_account_created_email")
    def test_22_parent_link_existing_active_link_is_skipped_without_duplicate(self, send_email):
        self.db.add(StudentParent(student_id=self.student.id, parent_id=self.existing_parent.id, relationship="Guardian"))
        self.db.commit()
        response = self._parent_commit(
            [parent_link_row(parent_name=self.parent_user.name, parent_email=self.parent_user.email, parent_phone="222")]
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["skipped_existing"], 1)
        self.assertEqual(
            self.db.scalar(
                select(func.count(StudentParent.id)).where(
                    StudentParent.student_id == self.student.id,
                    StudentParent.parent_id == self.existing_parent.id,
                    StudentParent.deleted_at.is_(None),
                )
            ),
            1,
        )
        send_email.assert_not_called()

    @patch("services.parent_link_import.send_account_created_email")
    def test_23_parent_link_reactivates_deleted_link(self, send_email):
        link = StudentParent(
            student_id=self.student.id,
            parent_id=self.existing_parent.id,
            relationship="Old",
            deleted_at=datetime.now(timezone.utc),
        )
        self.db.add(link)
        self.db.commit()
        response = self._parent_commit(
            [
                parent_link_row(
                    parent_name=self.parent_user.name,
                    parent_email=self.parent_user.email,
                    parent_phone="222",
                    relationship="Father",
                )
            ]
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reactivated"], 1)
        self.db.refresh(link)
        self.assertIsNone(link.deleted_at)
        self.assertEqual(link.relationship, "Father")
        send_email.assert_not_called()

    @patch("services.parent_link_import.send_account_created_email", return_value={"success": True})
    def test_24_parent_link_conflicts_and_commit_partial_success_are_explicit(self, _send_email):
        conflicting = self._parent_preview(
            [
                parent_link_row(parent_name="Parent One"),
                parent_link_row(student_number=self.second_student.student_number, parent_name="Parent Two"),
            ]
        )
        self.assertEqual(conflicting.status_code, 200)
        self.assertTrue(all(not row["is_valid"] for row in conflicting.json()["rows"]))

        rows = [
            parent_link_row(parent_email="valid-parent@example.test"),
            parent_link_row(student_number="ZZ-TEST-MISSING", parent_email="invalid-parent@example.test"),
        ]
        committed = self._parent_commit(rows)
        self.assertEqual(committed.status_code, 200)
        self.assertEqual(committed.json()["linked"], 1)
        self.assertEqual(committed.json()["failed"], 1)


if __name__ == "__main__":
    unittest.main()
