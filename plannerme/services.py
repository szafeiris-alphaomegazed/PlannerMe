from __future__ import annotations

import datetime as dt
import json
from typing import Any

from plannerme.client import CollectionPage, PlannerUsClient
from plannerme.errors import PlannerMeError
from plannerme.utils import (
    duration_to_hours,
    filter_date_range,
    filter_eq,
    format_hours,
    hal_id,
    hours_to_duration,
    link_title,
    make_filters,
    parse_hours_to_duration,
)


class PlannerService:
    def __init__(self, client: PlannerUsClient) -> None:
        self.client = client

    def resolve_project(self, value: str) -> dict[str, Any]:
        ref = (self.client.settings.projects or {}).get(value, value)
        if ref.isdigit():
            return self.client.get(f"/projects/{ref}")

        projects = self.client.collection(
            "/projects",
            {
                "filters": make_filters({"name_and_identifier": {"operator": "~", "values": [ref]}}),
                "sortBy": json.dumps([["name", "asc"]]),
            },
        )
        exact = [
            project
            for project in projects
            if str(project.get("identifier", "")).lower() == ref.lower()
            or str(project.get("name", "")).lower() == ref.lower()
        ]
        if len(exact) == 1:
            return exact[0]
        if len(projects) == 1:
            return projects[0]
        if not projects:
            raise PlannerMeError(f"No project matched '{value}'.")

        choices = ", ".join(f"{project.get('id')}:{project.get('identifier')}" for project in projects[:8])
        raise PlannerMeError(f"More than one project matched '{value}': {choices}")

    def list_projects(self, *, me: bool) -> list[dict[str, Any]]:
        filters = []
        if me:
            filters.append(filter_eq("principal", self.client.current_user_id()))
        return self.client.collection(
            "/projects",
            {"filters": make_filters(*filters), "sortBy": json.dumps([["name", "asc"]])},
        )

    def project_page(self, *, me: bool, page_size: int, offset: int) -> CollectionPage:
        filters = []
        if me:
            filters.append(filter_eq("principal", self.client.current_user_id()))
        return self.client.collection_page(
            "/projects",
            {"filters": make_filters(*filters), "sortBy": json.dumps([["name", "asc"]])},
            page_size=page_size,
            offset=offset,
        )

    def list_tasks(
        self,
        *,
        project: str | None = None,
        me: bool = False,
        log_tasks: bool = False,
        prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        filters = [{"status": {"operator": "o", "values": None}}]
        if project:
            resolved = self.resolve_project(project)
            filters.append(filter_eq("project", str(resolved["id"])))
        if me:
            filters.append(filter_eq("assigned_to", self.client.current_user_id()))

        tasks = self.client.collection(
            "/work_packages",
            {"filters": make_filters(*filters), "sortBy": json.dumps([["id", "asc"]])},
        )
        if not log_tasks:
            return tasks

        prefix = prefix if prefix is not None else self.client.settings.log_task_prefix
        return [task for task in tasks if str(task.get("subject", "")).startswith(prefix)]

    def task_page(
        self,
        *,
        project: str | None = None,
        me: bool = False,
        log_tasks: bool = False,
        prefix: str | None = None,
        page_size: int,
        offset: int,
    ) -> CollectionPage:
        filters = [{"status": {"operator": "o", "values": None}}]
        if project:
            resolved = self.resolve_project(project)
            filters.append(filter_eq("project", str(resolved["id"])))
        if me:
            filters.append(filter_eq("assigned_to", self.client.current_user_id()))
        if log_tasks:
            prefix = prefix if prefix is not None else self.client.settings.log_task_prefix
            filters.append({"subject": {"operator": "~", "values": [prefix]}})

        page = self.client.collection_page(
            "/work_packages",
            {"filters": make_filters(*filters), "sortBy": json.dumps([["id", "asc"]])},
            page_size=page_size,
            offset=offset,
        )
        if log_tasks:
            prefix = prefix if prefix is not None else self.client.settings.log_task_prefix
            page = CollectionPage(
                elements=[task for task in page.elements if str(task.get("subject", "")).startswith(prefix)],
                count=page.count,
                total=page.total,
                offset=page.offset,
                page_size=page.page_size,
            )
        return page

    def resolve_log_task(self, project: str, task: str | None) -> dict[str, Any]:
        if task and task.isdigit():
            return self.client.get(f"/work_packages/{task}")

        tasks = self.list_tasks(project=project, log_tasks=True)
        if task:
            needle = task.lower()
            tasks = [
                item
                for item in tasks
                if needle in str(item.get("subject", "")).lower() or needle == self.work_package_id(item)
            ]

        if len(tasks) == 1:
            return tasks[0]
        if not tasks:
            raise PlannerMeError("No matching LOG task found.")

        choices = ", ".join(f"#{self.work_package_id(item)} {item.get('subject')}" for item in tasks[:8])
        raise PlannerMeError(f"More than one LOG task matched. Use --task with one of: {choices}")

    def list_activities(self) -> list[dict[str, Any]]:
        schema = self.client.get("/time_entries/schema")
        activity = schema.get("activity", {})
        allowed_values = activity.get("_links", {}).get("allowedValues", [])
        if isinstance(allowed_values, list) and allowed_values:
            return [
                {
                    "id": hal_id({"_links": {"self": {"href": value.get("href", "")}}}),
                    "name": value.get("title", ""),
                }
                for value in allowed_values
            ]

        return [
            {
                "id": self.client.settings.default_activity_id or "",
                "name": (
                    "PlannerUs will use its default activity. Set "
                    "PLANNERUS_DEFAULT_ACTIVITY_ID or pass --activity to force one."
                ),
            }
        ]

    def resolve_activity_id(self, activity: str | None) -> str | None:
        return activity or self.client.settings.default_activity_id

    def list_time_entries(
        self,
        *,
        start: dt.date,
        end: dt.date,
        me: bool = True,
        project: str | None = None,
    ) -> list[dict[str, Any]]:
        filters = [filter_date_range("spent_on", start, end)]
        if me:
            filters.append(filter_eq("user_id", self.client.current_user_id()))
        if project:
            resolved = self.resolve_project(project)
            filters.append(filter_eq("project_id", str(resolved["id"])))

        return self.client.collection(
            "/time_entries",
            {
                "filters": make_filters(*filters),
                "sortBy": json.dumps([["spent_on", "asc"], ["id", "asc"]]),
            },
        )

    def time_entry_page(
        self,
        *,
        start: dt.date,
        end: dt.date,
        me: bool = True,
        project: str | None = None,
        page_size: int,
        offset: int,
    ) -> CollectionPage:
        filters = [filter_date_range("spent_on", start, end)]
        if me:
            filters.append(filter_eq("user_id", self.client.current_user_id()))
        if project:
            resolved = self.resolve_project(project)
            filters.append(filter_eq("project_id", str(resolved["id"])))

        return self.client.collection_page(
            "/time_entries",
            {
                "filters": make_filters(*filters),
                "sortBy": json.dumps([["spent_on", "asc"], ["id", "asc"]]),
            },
            page_size=page_size,
            offset=offset,
        )

    def make_time_entry_body(
        self,
        work_package: dict[str, Any],
        *,
        hours: str,
        spent_on: dt.date,
        comment: str,
        activity_id: str | None,
    ) -> dict[str, Any]:
        body = {
            "spentOn": spent_on.isoformat(),
            "hours": hours,
            "comment": {"format": "plain", "raw": comment},
            "_links": {"workPackage": {"href": f"/api/v3/work_packages/{self.work_package_id(work_package)}"}},
        }
        if activity_id:
            body["_links"]["activity"] = {"href": f"/api/v3/time_entries/activities/{activity_id}"}
        return body

    def create_time_entry(
        self,
        *,
        project: str,
        hours: str,
        spent_on: dt.date,
        task: str | None,
        comment: str,
        activity: str | None,
        dry_run: bool,
    ) -> dict[str, Any]:
        work_package = self.resolve_log_task(project, task)
        body = self.make_time_entry_body(
            work_package,
            hours=parse_hours_to_duration(hours),
            spent_on=spent_on,
            comment=comment,
            activity_id=self.resolve_activity_id(activity),
        )
        if dry_run:
            return {"dryRun": True, "workPackage": work_package.get("subject"), "body": body}
        return self.client.post("/time_entries", body)

    @staticmethod
    def work_package_id(value: dict[str, Any]) -> str:
        return str(value.get("id") or hal_id(value))

    @staticmethod
    def entries_total(entries: list[dict[str, Any]]) -> float:
        return sum(duration_to_hours(str(entry.get("hours", ""))) for entry in entries)

    def entries_total_for_date(self, entries: list[dict[str, Any]], day: dt.date) -> float:
        return self.entries_total([entry for entry in entries if entry.get("spentOn") == day.isoformat()])

    def project_rows(self, projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "id": project.get("id"),
                "identifier": project.get("identifier"),
                "name": project.get("name"),
                "active": project.get("active"),
            }
            for project in projects
        ]

    def task_rows(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "id": self.work_package_id(task),
                "subject": task.get("subject"),
                "project": link_title(task, "project"),
                "assignee": link_title(task, "assignee"),
                "status": link_title(task, "status"),
            }
            for task in tasks
        ]

    @staticmethod
    def time_entry_rows(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for entry in entries:
            hours = duration_to_hours(str(entry.get("hours", "")))
            rows.append(
                {
                    "date": entry.get("spentOn"),
                    "hours": format_hours(hours),
                    "project": link_title(entry, "project"),
                    "task": link_title(entry, "workPackage") or link_title(entry, "entity"),
                    "activity": link_title(entry, "activity"),
                    "comment": entry.get("comment", {}).get("raw", ""),
                }
            )
        return rows

    def duration_for_hours(self, hours: float) -> str:
        return hours_to_duration(hours)
