from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from plannerme.constants import AUTOMATION_LOG_PATH
from plannerme.errors import PlannerMeError
from plannerme.utils import shell_quote


class AutomationManager:
    def day_to_cron(self, value: str) -> str:
        days = {
            "sunday": "0",
            "monday": "1",
            "tuesday": "2",
            "wednesday": "3",
            "thursday": "4",
            "friday": "5",
            "saturday": "6",
        }
        normalized = value.strip().lower()
        if normalized not in days:
            raise PlannerMeError("Day must be one of: monday, tuesday, wednesday, thursday, friday, saturday, sunday.")
        return days[normalized]

    def parse_time(self, value: str) -> tuple[str, str]:
        match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", value.strip())
        if not match:
            raise PlannerMeError("Time must be HH:MM in 24-hour format.")
        return match.group(2), match.group(1)

    def cron_line(self, name: str, automation: dict[str, Any]) -> str:
        minute, hour = self.parse_time(str(automation.get("time", "09:00")))
        day = self.day_to_cron(str(automation.get("day", "monday")))
        cwd = automation.get("cwd") or os.getcwd()
        command = self.command(automation)
        return f"{minute} {hour} * * {day} cd {shell_quote(cwd)} && {command} # plannerme:{name}"

    def command(self, automation: dict[str, Any]) -> str:
        executable = automation.get("executable") or "plannerme"
        args = " ".join(shell_quote(str(arg)) for arg in automation.get("args", []))
        log_path = str(AUTOMATION_LOG_PATH)
        return f"/usr/bin/env {shell_quote(executable)} {args} >> {shell_quote(log_path)} 2>&1"

    def install_cron_line(self, name: str, line: str) -> None:
        marker = f"# plannerme:{name}"
        current = subprocess.run(
            ["crontab", "-l"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        existing = current.stdout.splitlines() if current.returncode == 0 else []
        kept = [item for item in existing if marker not in item]
        kept.append(line)
        subprocess.run(["crontab", "-"], input="\n".join(kept) + "\n", text=True, check=True)

    def build_automation(
        self,
        *,
        day: str,
        time: str,
        project: str | None,
        period: str,
        task: str | None,
        comment: str | None,
        apply: bool,
    ) -> dict[str, Any]:
        self.day_to_cron(day)
        self.parse_time(time)
        command_args = ["autolog"]
        if project:
            command_args.append(project)
        if period == "week":
            command_args.append("--week")
        if apply:
            command_args.append("--apply")
        if task:
            command_args.extend(["--task", task])
        if comment:
            command_args.extend(["--comment", comment])
        return {
            "enabled": True,
            "day": day.lower(),
            "time": time,
            "args": command_args,
            "cwd": os.getcwd(),
            "executable": "plannerme",
            "script": str(Path(__file__).resolve()),
        }
