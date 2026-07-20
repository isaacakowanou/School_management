import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import AuditLog, Base, Parent, PasswordResetToken, Teacher, User
from scripts.purge_orphaned_users import find_orphaned_role_users
from services.trash import purge_user_accounts


class PurgeOrphanedUsersTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _user(self, *, name: str, email: str, role: str) -> User:
        user = User(
            name=name,
            email=email,
            password_hash="ZZ-TEST-not-a-login-password",
            role=role,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def test_finds_only_missing_role_profiles_and_purges_account_dependents(self):
        orphan_parent = self._user(
            name="ZZ-TEST-Orphan Parent",
            email="zz-test-orphan-parent@example.test",
            role="parent",
        )
        orphan_teacher = self._user(
            name="ZZ-TEST-Orphan Teacher",
            email="zz-test-orphan-teacher@example.test",
            role="teacher",
        )
        valid_parent_user = self._user(
            name="ZZ-TEST-Valid Parent",
            email="zz-test-valid-parent@example.test",
            role="parent",
        )
        valid_teacher_user = self._user(
            name="ZZ-TEST-Valid Teacher",
            email="zz-test-valid-teacher@example.test",
            role="teacher",
        )
        admin = self._user(
            name="ZZ-TEST-Admin",
            email="zz-test-admin@example.test",
            role="admin",
        )
        self.db.add_all(
            [
                Parent(user_id=valid_parent_user.id, phone="+2290100000091"),
                Teacher(user_id=valid_teacher_user.id, employee_number="ZZ-TEST-VALID-TCH"),
            ]
        )
        reset_token = PasswordResetToken(
            user_id=orphan_parent.id,
            token_hash="c" * 64,
            token_version=orphan_parent.token_version,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=45),
        )
        audit = AuditLog(
            actor_user_id=orphan_parent.id,
            action="ZZ-TEST-orphan-action",
            entity_type="auth",
            entity_id=orphan_parent.id,
        )
        self.db.add_all([reset_token, audit])
        self.db.commit()
        orphan_parent_id = orphan_parent.id
        orphan_teacher_id = orphan_teacher.id
        valid_parent_id = valid_parent_user.id
        valid_teacher_id = valid_teacher_user.id
        admin_id = admin.id
        token_id = reset_token.id
        audit_id = audit.id

        found_ids = {user.id for user in find_orphaned_role_users(self.db)}
        self.assertEqual(found_ids, {orphan_parent_id, orphan_teacher_id})

        counts = purge_user_accounts(self.db, found_ids)
        self.db.commit()
        self.assertEqual(counts, {"users": 2, "password_reset_tokens": 1})
        self.assertIsNone(self.db.get(User, orphan_parent_id))
        self.assertIsNone(self.db.get(User, orphan_teacher_id))
        self.assertIsNone(self.db.get(PasswordResetToken, token_id))
        self.assertIsNotNone(self.db.get(User, valid_parent_id))
        self.assertIsNotNone(self.db.get(User, valid_teacher_id))
        self.assertIsNotNone(self.db.get(User, admin_id))
        preserved_audit = self.db.get(AuditLog, audit_id)
        self.assertIsNotNone(preserved_audit)
        self.assertIsNone(preserved_audit.actor_user_id)


if __name__ == "__main__":
    unittest.main()
