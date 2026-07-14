"""Manually submit one SMS to the Africa's Talking sandbox.

This script is intentionally excluded from automated tests. It refuses live
credentials so an implementation smoke test cannot accidentally contact a
production recipient.
"""

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.sms_service import _get_messaging_config, send_sms_message  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phone", help="Sandbox recipient number")
    parser.add_argument("--message", default="GGFK Africa's Talking sandbox test")
    args = parser.parse_args()

    config = _get_messaging_config()
    if config.get("provider") != "africastalking":
        raise SystemExit("Set SMS_PROVIDER=africastalking before running this script.")
    if config.get("username", "").lower() != "sandbox":
        raise SystemExit("Refusing to run: AT_USERNAME must be sandbox.")

    results = send_sms_message(args.phone, args.message, config)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
