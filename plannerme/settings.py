from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from plannerme.constants import DEFAULT_AUTH, DEFAULT_BASE_URL, DEFAULT_DAILY_HOURS, DEFAULT_LOG_TASK_PREFIX, DEFAULT_WEEKLY_HOURS
from plannerme.errors import PlannerMeError
from plannerme.user_config import UserConfigManager
from plannerme.utils import load_dotenv, parse_aliases, parse_env_hours


@dataclass(frozen=True)
class PlannerMeSettings:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    auth: str = DEFAULT_AUTH
    projects: dict[str, str] | None = None
    log_task_prefix: str = DEFAULT_LOG_TASK_PREFIX
    default_activity_id: str | None = None
    daily_hours: float = DEFAULT_DAILY_HOURS
    weekly_hours: float = DEFAULT_WEEKLY_HOURS
    user_config: dict[str, Any] | None = None

    @classmethod
    def from_env(cls, config_manager: UserConfigManager | None = None) -> "PlannerMeSettings":
        load_dotenv()
        config_manager = config_manager or UserConfigManager()

        api_key = os.getenv("PLANNERUS_API_KEY", "").strip()
        if not api_key:
            raise PlannerMeError("Missing PLANNERUS_API_KEY. Add it to .env or export it in your shell.")

        base_url = os.getenv("PLANNERUS_BASE_URL", DEFAULT_BASE_URL).strip()
        auth = os.getenv("PLANNERUS_AUTH", DEFAULT_AUTH).strip().lower()
        if auth not in {"basic", "bearer"}:
            raise PlannerMeError("PLANNERUS_AUTH must be either 'basic' or 'bearer'.")

        user_config = config_manager.load()
        projects = parse_aliases(os.getenv("PLANNERUS_PROJECTS", ""))
        projects.update(config_manager.project_refs(user_config))
        targets = user_config.get("targets", {})

        return cls(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            auth=auth,
            projects=projects,
            log_task_prefix=os.getenv("PLANNERUS_LOG_TASK_PREFIX", DEFAULT_LOG_TASK_PREFIX),
            default_activity_id=os.getenv("PLANNERUS_DEFAULT_ACTIVITY_ID", "").strip() or None,
            daily_hours=parse_env_hours("PLANNERUS_DAILY_HOURS", float(targets.get("dailyHours", DEFAULT_DAILY_HOURS))),
            weekly_hours=parse_env_hours("PLANNERUS_WEEKLY_HOURS", float(targets.get("weeklyHours", DEFAULT_WEEKLY_HOURS))),
            user_config=user_config,
        )
