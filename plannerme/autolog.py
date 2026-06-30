from __future__ import annotations

import datetime as dt
from typing import Any

from plannerme.errors import PlannerMeError
from plannerme.services import PlannerService
from plannerme.user_config import UserConfigManager
from plannerme.utils import format_hours, hours_to_duration, parse_date, week_key, week_range, week_range_from_key


class AutologPlanner:
    def __init__(self, service: PlannerService, config_manager: UserConfigManager | None = None) -> None:
        self.service = service
        self.config_manager = config_manager or UserConfigManager()

    def range_from_args(self, args: Any) -> tuple[dt.date, dt.date]:
        if getattr(args, "date", None):
            day = parse_date(args.date)
            return day, day
        if getattr(args, "week_of", None):
            return week_range(parse_date(args.week_of))
        if getattr(args, "iso_week", None):
            return week_range_from_key(args.iso_week)
        if getattr(args, "week", False):
            return week_range(dt.date.today())
        today = dt.date.today()
        return today, today

    def plan_single_project(
        self,
        *,
        project: str,
        start: dt.date,
        end: dt.date,
        daily_hours: float,
        weekly_hours: float,
        task: str | None,
        comment: str,
        activity: str | None,
        apply: bool,
    ) -> dict[str, Any]:
        self._validate_targets(daily_hours, weekly_hours)
        work_package = self.service.resolve_log_task(project, task)
        activity_id = self.service.resolve_activity_id(activity)
        week_start, week_end = week_range(start)
        week_entries = self.service.list_time_entries(start=week_start, end=week_end, me=True)
        range_entries = [entry for entry in week_entries if start.isoformat() <= str(entry.get("spentOn", "")) <= end.isoformat()]
        week_existing = self.service.entries_total(week_entries)
        week_remaining = max(0.0, weekly_hours - week_existing)
        planned_entries = []

        for day in self.autolog_days(start, end):
            existing_day = self.service.entries_total_for_date(range_entries, day)
            planned_hours = min(max(0.0, daily_hours - existing_day), week_remaining)
            if planned_hours <= 0:
                planned_entries.append(self._covered_row(day, existing_day))
                continue

            body = self.service.make_time_entry_body(
                work_package,
                hours=hours_to_duration(planned_hours),
                spent_on=day,
                comment=comment,
                activity_id=activity_id,
            )
            created = None if not apply else self.service.client.post("/time_entries", body)
            week_remaining -= planned_hours
            planned_entries.append(self._planned_row(day, "", "", existing_day, planned_hours, apply, created, body))

        return self._plan_result(
            apply=apply,
            project=project,
            work_package=f"#{self.service.work_package_id(work_package)} {work_package.get('subject')}",
            start=start,
            end=end,
            daily_hours=daily_hours,
            weekly_hours=weekly_hours,
            range_entries=range_entries,
            week_existing=week_existing,
            planned_entries=planned_entries,
        )

    def plan_configured_projects(
        self,
        *,
        start: dt.date,
        end: dt.date,
        daily_hours: float,
        weekly_hours: float,
        task: str | None,
        comment: str | None,
        activity: str | None,
        apply: bool,
    ) -> dict[str, Any]:
        self._validate_targets(daily_hours, weekly_hours)
        config = self.service.client.settings.user_config or self.config_manager.default()
        key = week_key(start)
        specs = self.config_manager.project_specs(config, key)
        week_start, week_end = week_range(start)
        week_entries = self.service.list_time_entries(start=week_start, end=week_end, me=True)
        range_entries = [entry for entry in week_entries if start.isoformat() <= str(entry.get("spentOn", "")) <= end.isoformat()]
        week_existing = self.service.entries_total(week_entries)
        week_remaining = max(0.0, weekly_hours - week_existing)
        planned_entries = []
        resolved_tasks = {
            spec["alias"]: self.service.resolve_log_task(spec["alias"], task or spec.get("task"))
            for spec in specs
        }

        for day in self.autolog_days(start, end):
            existing_day = self.service.entries_total_for_date(range_entries, day)
            planned_day_hours = min(max(0.0, daily_hours - existing_day), week_remaining)
            if planned_day_hours <= 0:
                planned_entries.append(self._covered_row(day, existing_day))
                continue

            for spec, planned_hours in self.split_hours_by_weight(planned_day_hours, specs):
                work_package = resolved_tasks[spec["alias"]]
                body = self.service.make_time_entry_body(
                    work_package,
                    hours=hours_to_duration(planned_hours),
                    spent_on=day,
                    comment=comment if comment is not None else spec.get("comment") or "",
                    activity_id=self.service.resolve_activity_id(activity if activity is not None else spec.get("activity")),
                )
                created = None if not apply else self.service.client.post("/time_entries", body)
                planned_entries.append(
                    self._planned_row(
                        day,
                        spec["alias"],
                        format_hours(float(spec["weight"])),
                        existing_day,
                        planned_hours,
                        apply,
                        created,
                        body,
                    )
                )
            week_remaining -= planned_day_hours

        result = self._plan_result(
            apply=apply,
            project="configured projects",
            work_package="configured projects",
            start=start,
            end=end,
            daily_hours=daily_hours,
            weekly_hours=weekly_hours,
            range_entries=range_entries,
            week_existing=week_existing,
            planned_entries=planned_entries,
        )
        result["week"] = key
        return result

    @staticmethod
    def business_days(start: dt.date, end: dt.date) -> list[dt.date]:
        days = []
        current = start
        while current <= end:
            if current.weekday() < 5:
                days.append(current)
            current += dt.timedelta(days=1)
        return days

    def autolog_days(self, start: dt.date, end: dt.date) -> list[dt.date]:
        if start == end:
            return [start]
        return self.business_days(start, end)

    @staticmethod
    def split_hours_by_weight(total_hours: float, specs: list[dict[str, Any]]) -> list[tuple[dict[str, Any], float]]:
        total_minutes = round(total_hours * 60)
        total_weight = sum(float(spec["weight"]) for spec in specs)
        remaining = total_minutes
        splits = []
        for index, spec in enumerate(specs):
            if index == len(specs) - 1:
                minutes = remaining
            else:
                minutes = min(remaining, round(total_minutes * float(spec["weight"]) / total_weight))
            remaining -= minutes
            if minutes > 0:
                splits.append((spec, minutes / 60))
        return splits

    @staticmethod
    def rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "date": entry.get("date", ""),
                "project": entry.get("project", ""),
                "weight": entry.get("weight", ""),
                "existing": entry.get("existing", ""),
                "planned": entry.get("planned", ""),
                "status": entry.get("status", ""),
                "createdId": entry.get("createdId", ""),
            }
            for entry in plan.get("entries", [])
        ]

    @staticmethod
    def _validate_targets(daily_hours: float, weekly_hours: float) -> None:
        if daily_hours <= 0 or weekly_hours <= 0:
            raise PlannerMeError("--daily-hours and --weekly-hours must be greater than zero.")

    @staticmethod
    def _covered_row(day: dt.date, existing_day: float) -> dict[str, Any]:
        return {
            "date": day.isoformat(),
            "project": "",
            "weight": "",
            "existing": format_hours(existing_day),
            "planned": "0",
            "status": "already covered",
            "createdId": "",
        }

    @staticmethod
    def _planned_row(
        day: dt.date,
        project: str,
        weight: str,
        existing_day: float,
        planned_hours: float,
        apply: bool,
        created: dict[str, Any] | None,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "date": day.isoformat(),
            "project": project,
            "weight": weight,
            "existing": format_hours(existing_day),
            "planned": format_hours(planned_hours),
            "status": "created" if apply else "would create",
            "createdId": "" if created is None else str(created.get("id", "")),
            "body": body,
        }

    def _plan_result(
        self,
        *,
        apply: bool,
        project: str,
        work_package: str,
        start: dt.date,
        end: dt.date,
        daily_hours: float,
        weekly_hours: float,
        range_entries: list[dict[str, Any]],
        week_existing: float,
        planned_entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        planned_total = sum(float(entry["planned"]) for entry in planned_entries if entry["planned"])
        return {
            "apply": apply,
            "project": project,
            "workPackage": work_package,
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "targets": {"dailyHours": daily_hours, "weeklyHours": weekly_hours},
            "existing": {
                "selectedRangeHours": self.service.entries_total(range_entries),
                "weekHours": week_existing,
            },
            "plannedHours": planned_total,
            "entries": planned_entries,
        }
