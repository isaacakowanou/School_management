import unittest

from pydantic import ValidationError

from schemas import UserCreate


class PasswordStrengthTests(unittest.TestCase):
    def _valid_user_payload(self, password: str) -> dict:
        return {"name": "Test User", "email": "test@example.test", "password": password, "role": "admin"}

    def test_password_shorter_than_8_chars_rejected(self):
        for short in ("", "a", "1234567"):
            with self.subTest(password=short):
                with self.assertRaises(ValidationError) as ctx:
                    UserCreate(**self._valid_user_payload(short))
                errors = ctx.exception.errors()
                self.assertTrue(
                    any("8 characters" in str(e["msg"]) for e in errors),
                    f"Expected 8-char message for {short!r}, got {errors}",
                )

    def test_password_exactly_8_chars_accepted(self):
        user = UserCreate(**self._valid_user_payload("12345678"))
        self.assertEqual(user.password, "12345678")

    def test_password_longer_than_8_chars_accepted(self):
        user = UserCreate(**self._valid_user_payload("a-perfectly-fine-password"))
        self.assertEqual(user.password, "a-perfectly-fine-password")

    def test_empty_password_rejected(self):
        with self.assertRaises(ValidationError):
            UserCreate(**self._valid_user_payload(""))

    def test_whitespace_only_password_rejected(self):
        with self.assertRaises(ValidationError):
            UserCreate(**self._valid_user_payload("       "))

    def test_exactly_7_chars_rejected(self):
        with self.assertRaises(ValidationError):
            UserCreate(**self._valid_user_payload("1234567"))
