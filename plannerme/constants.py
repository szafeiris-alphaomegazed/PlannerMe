from __future__ import annotations

from pathlib import Path


DEFAULT_BASE_URL = "https://app.plannerus.com"
DEFAULT_AUTH = "basic"
DEFAULT_LOG_TASK_PREFIX = "LOG_"
DEFAULT_DAILY_HOURS = 8.0
DEFAULT_WEEKLY_HOURS = 40.0
CONFIG_PATH = Path.home() / ".plannerme" / "config.json"
AUTOMATION_LOG_PATH = CONFIG_PATH.parent / "automation.log"
