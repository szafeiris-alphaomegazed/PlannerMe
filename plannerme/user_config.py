from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plannerme.constants import CONFIG_PATH, DEFAULT_DAILY_HOURS, DEFAULT_WEEKLY_HOURS
from plannerme.errors import PlannerMeError
from plannerme.utils import coerce_positive_float, format_hours, parse_week_key, pretty_json


DEFAULT_USER_CONFIG: dict[str, Any] = {
    "targets": {"dailyHours": DEFAULT_DAILY_HOURS, "weeklyHours": DEFAULT_WEEKLY_HOURS},
    "projects": {},
    "weeks": {},
    "automations": {},
}


class UserConfigManager:
    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path

    def default(self) -> dict[str, Any]:
        return json.loads(json.dumps(DEFAULT_USER_CONFIG))

    def normalize(self, config: dict[str, Any]) -> dict[str, Any]:
        normalized = self.default()
        normalized.update(config)
        for key in ("projects", "weeks", "automations"):
            if not isinstance(normalized.get(key), dict):
                normalized[key] = {}
        if not isinstance(normalized.get("targets"), dict):
            normalized["targets"] = self.default()["targets"]
        normalized["targets"].setdefault("dailyHours", DEFAULT_DAILY_HOURS)
        normalized["targets"].setdefault("weeklyHours", DEFAULT_WEEKLY_HOURS)
        return normalized

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self.default()
        try:
            return self.normalize(json.loads(self.path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise PlannerMeError(f"Invalid JSON in {self.path}: {exc}") from exc

    def save(self, config: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(pretty_json(self.normalize(config)) + "\n", encoding="utf-8")

    def project_refs(self, config: dict[str, Any]) -> dict[str, str]:
        refs = {}
        for alias, project in config.get("projects", {}).items():
            if isinstance(project, dict) and project.get("ref"):
                refs[alias] = str(project["ref"])
        return refs

    def project_specs(self, config: dict[str, Any], week: str | None = None) -> list[dict[str, Any]]:
        projects = config.get("projects", {})
        if not projects:
            raise PlannerMeError("No projects configured. Add one with: config project add ALIAS PROJECT_REF")

        week_weights = config.get("weeks", {}).get(week or "", {})
        specs = []
        for alias, project in projects.items():
            if not isinstance(project, dict) or not project.get("ref"):
                continue
            weight = coerce_positive_float(week_weights.get(alias, project.get("weight", 1)), "Weight")
            specs.append(
                {
                    "alias": alias,
                    "ref": str(project["ref"]),
                    "weight": weight,
                    "task": project.get("task"),
                    "comment": project.get("comment"),
                    "activity": project.get("activity"),
                }
            )

        if not specs:
            raise PlannerMeError("No usable projects configured.")
        return specs

    def project_rows(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for alias, project in sorted(config.get("projects", {}).items()):
            if not isinstance(project, dict):
                continue
            rows.append(
                {
                    "alias": alias,
                    "ref": project.get("ref", ""),
                    "weight": format_hours(float(project.get("weight", 1))),
                    "task": project.get("task", ""),
                    "comment": project.get("comment", ""),
                    "activity": project.get("activity", ""),
                }
            )
        return rows

    def weight_rows(self, config: dict[str, Any], week: str | None = None) -> list[dict[str, Any]]:
        rows = []
        week = parse_week_key(week) if week else None
        weeks = {week: config.get("weeks", {}).get(week, {})} if week else config.get("weeks", {})
        for week_name, weights in sorted(weeks.items()):
            if not isinstance(weights, dict):
                continue
            for alias, weight in sorted(weights.items()):
                rows.append({"week": week_name, "alias": alias, "weight": format_hours(float(weight))})
        return rows

    def automation_rows(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for name, automation in sorted(config.get("automations", {}).items()):
            if not isinstance(automation, dict):
                continue
            rows.append(
                {
                    "name": name,
                    "enabled": automation.get("enabled", True),
                    "day": automation.get("day", ""),
                    "time": automation.get("time", ""),
                    "args": " ".join(automation.get("args", [])),
                }
            )
        return rows
