"""Load backend-local development environment values without overriding process configuration.

Deployment-provided variables must win over ``backend/.env``; otherwise local
defaults could silently replace production database or credential settings.
"""

from pathlib import Path

from dotenv import load_dotenv


ENV_FILE = Path(__file__).with_name(".env")

load_dotenv(ENV_FILE, override=False)
