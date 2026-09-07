import os
import unittest
from unittest.mock import Mock, patch

from services.sms_service import (
    _get_messaging_config,
    _send_africastalking_messages,
    send_account_created_sms,
    send_sms_message,
    send_temporary_password_reset_sms,
    to_e164,
)


AT_CONFIG = {
    "provider": "africastalking",
    "username": "sandbox",
    "api_key": "test-key",
    "sender_id": "GGFK",
    "app_base_url": "https://portal.example.test",
}


def at_response(*recipients):
    return {
        "SMSMessageData": {
            "Message": f"Sent to {len(recipients)}/{len(recipients)}",
            "Recipients": list(recipients),
        }
    }


def recipient(number, *, status_code=101, status="Success", message_id="AT-test-id"):
    return {
        "statusCode": status_code,
        "number": number,
        "status": status,
        "cost": "KES 0.8000",
        "messageId": message_id,
    }


class PhoneNormalizationTests(unittest.TestCase):
    def test_normalizes_current_and_legacy_benin_formats(self):
        expected = "+2290197123456"
        cases = [
            "97 12 34 56",
            "01 97 12 34 56",
            "+229 97 12 34 56",
            "+229 01 97 12 34 56",
            "00229 97 12 34 56",
            "2290197123456",
        ]

        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(to_e164(value), expected)

    def test_preserves_valid_foreign_e164_number(self):
        self.assertEqual(to_e164("+1 (312) 555-0199"), "+13125550199")

    def test_rejects_malformed_benin_number(self):
        with self.assertRaises(ValueError):
            to_e164("971234")


class AfricasTalkingAdapterTests(unittest.TestCase):
    @patch("services.sms_service.send_sms_message", return_value=[{"success": True}])
    def test_account_created_sms_is_bilingual_french_first_and_non_urgent(self, send_message):
        results = send_account_created_sms(
            "Marie Parent",
            "97123456",
            "TempPass123",
            config=AT_CONFIG,
        )

        self.assertTrue(results[0]["success"])
        body = send_message.call_args.args[1]
        self.assertLess(body.index("Bonjour Marie Parent"), body.index("Hello Marie Parent"))
        self.assertIn("TempPass123", body)
        self.assertIn("https://portal.example.test", body)
        self.assertNotIn("immediately", body.lower())
        self.assertNotIn("immédiatement", body.lower())

    @patch("services.sms_service.send_sms_message", return_value=[{"success": True}])
    def test_admin_password_reset_sms_does_not_claim_account_was_created(self, send_message):
        results = send_temporary_password_reset_sms(
            "Marie Parent",
            "97123456",
            "ResetPass123",
            config=AT_CONFIG,
        )

        self.assertTrue(results[0]["success"])
        body = send_message.call_args.args[1]
        self.assertNotIn("account has been created", body.lower())
        self.assertNotIn("compte ggfk a été créé", body.lower())
        self.assertIn("ResetPass123", body)
        self.assertNotIn("immediately", body.lower())
        self.assertNotIn("immédiatement", body.lower())

    @patch("services.sms_service._post_africastalking_sms")
    def test_all_success_and_whatsapp_is_explicitly_skipped(self, post_sms):
        number = "+2290197123456"
        post_sms.return_value = at_response(recipient(number))

        results = send_sms_message("97 12 34 56", "Test", AT_CONFIG)

        post_sms.assert_called_once_with(AT_CONFIG, [number], "Test")
        self.assertEqual(len(results), 2)
        self.assertEqual(
            results[0],
            {
                "provider": "africastalking",
                "channel": "sms",
                "to": number,
                "sent": True,
                "success": True,
                "skipped": False,
                "provider_message_id": "AT-test-id",
                "sid": "AT-test-id",
                "error": None,
            },
        )
        self.assertEqual(results[1]["channel"], "whatsapp")
        self.assertTrue(results[1]["skipped"])
        self.assertFalse(results[1]["sent"])

    @patch("services.sms_service._post_africastalking_sms")
    def test_partial_failure_maps_each_recipient(self, post_sms):
        first = "+2290197123456"
        second = "+2290198123456"
        post_sms.return_value = at_response(
            recipient(first, message_id="AT-success"),
            recipient(second, status_code=405, status="InvalidPhoneNumber", message_id=None),
        )

        results = _send_africastalking_messages(
            ["97123456", "98123456"], "Test", AT_CONFIG
        )
        sms_results = [result for result in results if result["channel"] == "sms"]

        self.assertEqual([result["sent"] for result in sms_results], [True, False])
        self.assertEqual(sms_results[1]["error"], "InvalidPhoneNumber")

    @patch("services.sms_service._post_africastalking_sms")
    def test_all_failure_is_reported(self, post_sms):
        number = "+2290197123456"
        post_sms.return_value = at_response(
            recipient(number, status_code=401, status="InsufficientBalance", message_id=None)
        )

        results = send_sms_message("97123456", "Test", AT_CONFIG)
        sms_result = next(result for result in results if result["channel"] == "sms")

        self.assertFalse(sms_result["sent"])
        self.assertFalse(sms_result["skipped"])
        self.assertEqual(sms_result["error"], "InsufficientBalance")

    @patch("services.sms_service._post_africastalking_sms")
    def test_missing_recipient_in_response_is_failure(self, post_sms):
        post_sms.return_value = at_response()

        results = send_sms_message("97123456", "Test", AT_CONFIG)
        sms_result = next(result for result in results if result["channel"] == "sms")

        self.assertFalse(sms_result["sent"])
        self.assertFalse(sms_result["skipped"])
        self.assertIn("missing", sms_result["error"].lower())

    @patch("services.sms_service._post_africastalking_sms", side_effect=OSError("offline"))
    def test_transport_failure_fails_sms_but_still_skips_whatsapp(self, _post_sms):
        results = send_sms_message("97123456", "Test", AT_CONFIG)

        sms_result = next(result for result in results if result["channel"] == "sms")
        whatsapp_result = next(
            result for result in results if result["channel"] == "whatsapp"
        )
        self.assertFalse(sms_result["sent"])
        self.assertFalse(sms_result["skipped"])
        self.assertTrue(whatsapp_result["skipped"])

    def test_missing_or_invalid_configuration_is_skipped(self):
        cases = [
            {},
            {"SMS_PROVIDER": "unsupported"},
            {
                "SMS_PROVIDER": "africastalking",
                "AT_USERNAME": "sandbox",
                "APP_BASE_URL": "https://portal.example.test",
            },
        ]
        for environment in cases:
            with self.subTest(environment=environment):
                with patch.dict(os.environ, environment, clear=True):
                    results = send_sms_message("97123456", "Test")

                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["channel"], "sms")
                self.assertTrue(results[0]["skipped"])
                self.assertFalse(results[0]["sent"])

    @patch.dict(
        os.environ,
        {
            "SMS_PROVIDER": "africastalking",
            "AT_USERNAME": "sandbox",
            "AT_API_KEY": "test-key",
            "APP_BASE_URL": "https://portal.example.test",
        },
        clear=True,
    )
    def test_africastalking_config_allows_optional_sender_id(self):
        config = _get_messaging_config()

        self.assertEqual(config["provider"], "africastalking")
        self.assertEqual(config["sender_id"], "")


class TwilioMessagingCompatibilityTests(unittest.TestCase):
    @patch("services.sms_service._twilio_client")
    def test_twilio_keeps_sms_and_whatsapp_attempts(self, twilio_client):
        messages = Mock()
        messages.create.side_effect = [
            Mock(sid="SM-sms"),
            Mock(sid="SM-whatsapp"),
        ]
        twilio_client.return_value.messages = messages
        config = {
            "provider": "twilio",
            "account_sid": "test-sid",
            "auth_token": "test-token",
            "phone_number": "+13125550100",
            "app_base_url": "https://portal.example.test",
        }

        results = send_sms_message("97123456", "Test", config)

        self.assertEqual([result["channel"] for result in results], ["sms", "whatsapp"])
        self.assertTrue(all(result["sent"] for result in results))
        self.assertEqual(results[0]["sid"], "SM-sms")
        self.assertEqual(results[1]["sid"], "SM-whatsapp")


if __name__ == "__main__":
    unittest.main()
