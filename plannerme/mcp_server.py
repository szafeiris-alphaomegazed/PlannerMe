from __future__ import annotations

import datetime as dt
import json
import sys
from typing import Any, Callable

from plannerme.automation import AutomationManager
from plannerme.autolog import AutologPlanner
from plannerme.client import PlannerUsClient
from plannerme.errors import PlannerMeError
from plannerme.services import PlannerService
from plannerme.settings import PlannerMeSettings
from plannerme.user_config import UserConfigManager
from plannerme.utils import coerce_positive_float, parse_date, parse_week_key, pretty_json, week_range


JsonObject = dict[str, Any]


class PlannerMeMcpServer:
    """Small dependency-free MCP stdio server for PlannerMe."""

    def __init__(self) -> None:
        self.config_manager = UserConfigManager()
        self.automation_manager = AutomationManager()
        self.tools: dict[str, tuple[str, JsonObject, Callable[[JsonObject], Any]]] = {
            "plannerme_ping": (
                "Verify PlannerUs API access and return the connected user.",
                {},
                self.ping,
            ),
            "plannerme_projects": (
                "List PlannerUs projects. Use me=true to show projects involving the connected user.",
                {
                    "me": {"type": "boolean", "default": False},
                    "page": {"type": "integer", "default": 1},
                    "page_size": {"type": "integer", "default": 25},
                },
                self.projects,
            ),
            "plannerme_tasks": (
                "List open tasks/work packages. By default returns all tasks; set log_tasks=true for LOG_ tasks.",
                {
                    "me": {"type": "boolean", "default": False},
                    "project": {"type": "string"},
                    "log_tasks": {"type": "boolean", "default": False},
                    "prefix": {"type": "string"},
                    "page": {"type": "integer", "default": 1},
                    "page_size": {"type": "integer", "default": 25},
                },
                self.tasks,
            ),
            "plannerme_logs": (
                "Show logged time for today, current week, one date, or the week containing a date.",
                {
                    "period": {
                        "type": "string",
                        "enum": ["today", "current_week", "date", "week_of"],
                        "default": "today",
                    },
                    "date": {"type": "string", "description": "YYYY-MM-DD; used with period=date or period=week_of."},
                    "project": {"type": "string"},
                    "all_users": {"type": "boolean", "default": False},
                    "page": {"type": "integer", "default": 1},
                    "page_size": {"type": "integer", "default": 25},
                },
                self.logs,
            ),
            "plannerme_log_time": (
                "Create or preview a time entry on a matching LOG_ task. Defaults to dry_run=true for safety.",
                {
                    "project": {"type": "string"},
                    "hours": {"type": "string", "description": "Examples: 2, 2.5, 1:30, PT2H30M."},
                    "date": {"type": "string", "description": "YYYY-MM-DD. Defaults to today."},
                    "task": {"type": "string", "description": "Work package id or subject text for the LOG_ task."},
                    "comment": {"type": "string", "default": ""},
                    "activity": {"type": "string"},
                    "dry_run": {"type": "boolean", "default": True},
                },
                self.log_time,
            ),
            "plannerme_autolog": (
                "Preview or apply automatic time logging up to daily/weekly targets. Defaults to preview.",
                {
                    "project": {"type": "string", "description": "Omit to use configured weighted projects."},
                    "period": {
                        "type": "string",
                        "enum": ["today", "current_week", "date", "week_of"],
                        "default": "today",
                    },
                    "date": {"type": "string", "description": "YYYY-MM-DD; used with period=date or period=week_of."},
                    "task": {"type": "string"},
                    "comment": {"type": "string"},
                    "activity": {"type": "string"},
                    "daily_hours": {"type": "number"},
                    "weekly_hours": {"type": "number"},
                    "apply": {"type": "boolean", "default": False},
                },
                self.autolog,
            ),
            "plannerme_config_show": (
                "Return the ~/.plannerme/config.json content, with defaults filled in.",
                {},
                self.config_show,
            ),
            "plannerme_config_init": (
                "Create ~/.plannerme/config.json if needed and return its path and content.",
                {},
                self.config_init,
            ),
            "plannerme_config_set_targets": (
                "Set default daily and/or weekly hour targets.",
                {
                    "daily_hours": {"type": "number"},
                    "weekly_hours": {"type": "number"},
                },
                self.config_set_targets,
            ),
            "plannerme_config_add_project": (
                "Add or replace a configured project alias used by weighted autolog.",
                {
                    "alias": {"type": "string"},
                    "ref": {"type": "string", "description": "Project id, identifier, or name."},
                    "weight": {"type": "number", "default": 1},
                    "task": {"type": "string"},
                    "comment": {"type": "string"},
                    "activity": {"type": "string"},
                    "force": {"type": "boolean", "default": False},
                },
                self.config_add_project,
            ),
            "plannerme_config_set_project": (
                "Update fields for an existing configured project alias.",
                {
                    "alias": {"type": "string"},
                    "ref": {"type": "string"},
                    "weight": {"type": "number"},
                    "task": {"type": "string"},
                    "comment": {"type": "string"},
                    "activity": {"type": "string"},
                },
                self.config_set_project,
            ),
            "plannerme_config_remove_project": (
                "Remove a configured project alias and its weekly weight overrides.",
                {"alias": {"type": "string"}},
                self.config_remove_project,
            ),
            "plannerme_config_set_week_weight": (
                "Set a project weight override for an ISO week such as 2026-W27.",
                {
                    "alias": {"type": "string"},
                    "week": {"type": "string"},
                    "weight": {"type": "number"},
                },
                self.config_set_week_weight,
            ),
            "plannerme_config_clear_week_weight": (
                "Clear a project weight override for an ISO week such as 2026-W27.",
                {
                    "alias": {"type": "string"},
                    "week": {"type": "string"},
                },
                self.config_clear_week_weight,
            ),
            "plannerme_config_add_automation": (
                "Save a weekly autolog automation in config. Use cron/apply tools separately to install/run it.",
                {
                    "name": {"type": "string"},
                    "project": {"type": "string"},
                    "day": {"type": "string", "default": "monday"},
                    "time": {"type": "string", "default": "09:00"},
                    "task": {"type": "string"},
                    "comment": {"type": "string"},
                    "apply": {"type": "boolean", "default": False},
                },
                self.config_add_automation,
            ),
            "plannerme_config_automation_cron": (
                "Return the cron line for a saved automation.",
                {"name": {"type": "string"}},
                self.config_automation_cron,
            ),
            "plannerme_config_install_automation": (
                "Install or update a saved automation in the user's crontab.",
                {"name": {"type": "string"}},
                self.config_install_automation,
            ),
        }

    def serve(self) -> int:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
                response = self.handle_message(message)
            except Exception as exc:  # noqa: BLE001 - last-resort JSON-RPC error boundary.
                response = self.error_response(None, -32700, f"Invalid MCP message: {exc}")
            if response is not None:
                self.send(response)
        return 0

    def handle_message(self, message: JsonObject) -> JsonObject | None:
        method = message.get("method")
        request_id = message.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": message.get("params", {}).get("protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "plannerme-mcp", "version": "0.1.0"},
                },
            }
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.tool_definitions()}}
        if method == "tools/call":
            return self.handle_tool_call(request_id, message.get("params", {}))
        if request_id is None:
            return None
        return self.error_response(request_id, -32601, f"Unsupported method: {method}")

    def handle_tool_call(self, request_id: Any, params: JsonObject) -> JsonObject:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in self.tools:
            return self.error_response(request_id, -32602, f"Unknown tool: {name}")

        handler = self.tools[name][2]
        try:
            result = handler(arguments)
            return self.tool_response(request_id, result)
        except PlannerMeError as exc:
            return self.tool_response(request_id, {"error": str(exc)}, is_error=True)
        except Exception as exc:  # noqa: BLE001 - keeps the MCP process alive for the client.
            return self.tool_response(request_id, {"error": f"{type(exc).__name__}: {exc}"}, is_error=True)

    def tool_definitions(self) -> list[JsonObject]:
        definitions = []
        required_by_tool = {
            "plannerme_log_time": ["project", "hours"],
            "plannerme_config_add_project": ["alias", "ref"],
            "plannerme_config_set_project": ["alias"],
            "plannerme_config_remove_project": ["alias"],
            "plannerme_config_set_week_weight": ["alias", "week", "weight"],
            "plannerme_config_clear_week_weight": ["alias", "week"],
            "plannerme_config_add_automation": ["name"],
            "plannerme_config_automation_cron": ["name"],
            "plannerme_config_install_automation": ["name"],
        }
        for name, (description, properties, _) in self.tools.items():
            definitions.append(
                {
                    "name": name,
                    "description": description,
                    "inputSchema": {
                        "type": "object",
                        "properties": properties,
                        "required": required_by_tool.get(name, []),
                        "additionalProperties": False,
                    },
                }
            )
        return definitions

    def app(self) -> tuple[PlannerUsClient, PlannerService]:
        settings = PlannerMeSettings.from_env(self.config_manager)
        client = PlannerUsClient(settings)
        return client, PlannerService(client)

    def ping(self, _: JsonObject) -> Any:
        client, _service = self.app()
        return client.ping()

    def projects(self, arguments: JsonObject) -> Any:
        _client, service = self.app()
        page, page_size = self.page_arguments(arguments)
        project_page = service.project_page(me=bool(arguments.get("me", False)), page_size=page_size, offset=page)
        return self.page_result(project_page, "projects", service.project_rows(project_page.elements))

    def tasks(self, arguments: JsonObject) -> Any:
        _client, service = self.app()
        page, page_size = self.page_arguments(arguments)
        task_page = service.task_page(
            project=self.optional_str(arguments, "project"),
            me=bool(arguments.get("me", False)),
            log_tasks=bool(arguments.get("log_tasks", False)),
            prefix=self.optional_str(arguments, "prefix"),
            page_size=page_size,
            offset=page,
        )
        return self.page_result(task_page, "tasks", service.task_rows(task_page.elements))

    def logs(self, arguments: JsonObject) -> Any:
        _client, service = self.app()
        start, end = self.date_range(arguments)
        page, page_size = self.page_arguments(arguments)
        entry_page = service.time_entry_page(
            start=start,
            end=end,
            me=not bool(arguments.get("all_users", False)),
            project=self.optional_str(arguments, "project"),
            page_size=page_size,
            offset=page,
        )
        return {
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "pageTotalHours": service.entries_total(entry_page.elements),
            **self.page_result(entry_page, "entries", service.time_entry_rows(entry_page.elements)),
        }

    def log_time(self, arguments: JsonObject) -> Any:
        _client, service = self.app()
        project = self.required_str(arguments, "project")
        hours = self.required_str(arguments, "hours")
        spent_on = parse_date(str(arguments.get("date") or dt.date.today().isoformat()))
        return service.create_time_entry(
            project=project,
            hours=hours,
            spent_on=spent_on,
            task=self.optional_str(arguments, "task"),
            comment=str(arguments.get("comment") or ""),
            activity=self.optional_str(arguments, "activity"),
            dry_run=bool(arguments.get("dry_run", True)),
        )

    def autolog(self, arguments: JsonObject) -> Any:
        client, service = self.app()
        planner = AutologPlanner(service, self.config_manager)
        start, end = self.date_range(arguments)
        daily_hours = float(arguments.get("daily_hours") or client.settings.daily_hours)
        weekly_hours = float(arguments.get("weekly_hours") or client.settings.weekly_hours)
        project = self.optional_str(arguments, "project")
        if project:
            return planner.plan_single_project(
                project=project,
                start=start,
                end=end,
                daily_hours=daily_hours,
                weekly_hours=weekly_hours,
                task=self.optional_str(arguments, "task"),
                comment=str(arguments.get("comment") or "Autolog"),
                activity=self.optional_str(arguments, "activity"),
                apply=bool(arguments.get("apply", False)),
            )
        return planner.plan_configured_projects(
            start=start,
            end=end,
            daily_hours=daily_hours,
            weekly_hours=weekly_hours,
            task=self.optional_str(arguments, "task"),
            comment=self.optional_str(arguments, "comment"),
            activity=self.optional_str(arguments, "activity"),
            apply=bool(arguments.get("apply", False)),
        )

    def config_show(self, _: JsonObject) -> Any:
        return {"path": str(self.config_manager.path), "config": self.config_manager.load()}

    def config_init(self, _: JsonObject) -> Any:
        config = self.config_manager.load()
        self.config_manager.save(config)
        return {"path": str(self.config_manager.path), "config": config}

    def config_set_targets(self, arguments: JsonObject) -> Any:
        config = self.config_manager.load()
        if "daily_hours" in arguments and arguments["daily_hours"] is not None:
            config["targets"]["dailyHours"] = coerce_positive_float(arguments["daily_hours"], "daily_hours")
        if "weekly_hours" in arguments and arguments["weekly_hours"] is not None:
            config["targets"]["weeklyHours"] = coerce_positive_float(arguments["weekly_hours"], "weekly_hours")
        self.config_manager.save(config)
        return {"path": str(self.config_manager.path), "targets": config["targets"]}

    def config_add_project(self, arguments: JsonObject) -> Any:
        config = self.config_manager.load()
        alias = self.required_str(arguments, "alias")
        if alias in config["projects"] and not bool(arguments.get("force", False)):
            raise PlannerMeError(f"Project alias '{alias}' already exists. Pass force=true to replace it.")
        config["projects"][alias] = {
            "ref": self.required_str(arguments, "ref"),
            "weight": coerce_positive_float(arguments.get("weight", 1), "weight"),
            "task": self.optional_str(arguments, "task"),
            "comment": self.optional_str(arguments, "comment"),
            "activity": self.optional_str(arguments, "activity"),
        }
        self.config_manager.save(config)
        return {"path": str(self.config_manager.path), "project": {alias: config["projects"][alias]}}

    def config_set_project(self, arguments: JsonObject) -> Any:
        config = self.config_manager.load()
        alias = self.required_str(arguments, "alias")
        if alias not in config["projects"]:
            raise PlannerMeError(f"Unknown project alias '{alias}'.")
        project = config["projects"][alias]
        for field in ("ref", "task", "comment", "activity"):
            if field in arguments:
                project[field] = self.optional_str(arguments, field)
        if "weight" in arguments and arguments["weight"] is not None:
            project["weight"] = coerce_positive_float(arguments["weight"], "weight")
        self.config_manager.save(config)
        return {"path": str(self.config_manager.path), "project": {alias: project}}

    def config_remove_project(self, arguments: JsonObject) -> Any:
        config = self.config_manager.load()
        alias = self.required_str(arguments, "alias")
        config["projects"].pop(alias, None)
        for weights in config.get("weeks", {}).values():
            if isinstance(weights, dict):
                weights.pop(alias, None)
        self.config_manager.save(config)
        return {"path": str(self.config_manager.path), "removed": alias}

    def config_set_week_weight(self, arguments: JsonObject) -> Any:
        config = self.config_manager.load()
        alias = self.required_str(arguments, "alias")
        if alias not in config["projects"]:
            raise PlannerMeError(f"Unknown project alias '{alias}'.")
        week = parse_week_key(self.required_str(arguments, "week"))
        config["weeks"].setdefault(week, {})[alias] = coerce_positive_float(arguments.get("weight"), "weight")
        self.config_manager.save(config)
        return {"path": str(self.config_manager.path), "week": week, "weights": config["weeks"][week]}

    def config_clear_week_weight(self, arguments: JsonObject) -> Any:
        config = self.config_manager.load()
        alias = self.required_str(arguments, "alias")
        week = parse_week_key(self.required_str(arguments, "week"))
        if week in config["weeks"]:
            config["weeks"][week].pop(alias, None)
            if not config["weeks"][week]:
                config["weeks"].pop(week)
        self.config_manager.save(config)
        return {"path": str(self.config_manager.path), "week": week, "cleared": alias}

    def config_add_automation(self, arguments: JsonObject) -> Any:
        config = self.config_manager.load()
        name = self.required_str(arguments, "name")
        automation = self.automation_manager.build_automation(
            day=str(arguments.get("day") or "monday"),
            time=str(arguments.get("time") or "09:00"),
            project=self.optional_str(arguments, "project"),
            period="week",
            task=self.optional_str(arguments, "task"),
            comment=self.optional_str(arguments, "comment"),
            apply=bool(arguments.get("apply", False)),
        )
        config["automations"][name] = automation
        self.config_manager.save(config)
        return {"path": str(self.config_manager.path), "automation": {name: automation}}

    def config_automation_cron(self, arguments: JsonObject) -> Any:
        config = self.config_manager.load()
        name = self.required_str(arguments, "name")
        automation = config["automations"].get(name)
        if not automation:
            raise PlannerMeError(f"Unknown automation '{name}'.")
        return {"name": name, "cron": self.automation_manager.cron_line(name, automation)}

    def config_install_automation(self, arguments: JsonObject) -> Any:
        cron = self.config_automation_cron(arguments)
        self.automation_manager.install_cron_line(str(cron["name"]), str(cron["cron"]))
        return {"installed": True, **cron}

    @staticmethod
    def date_range(arguments: JsonObject) -> tuple[dt.date, dt.date]:
        period = str(arguments.get("period") or "today")
        date_value = arguments.get("date")
        today = dt.date.today()
        if period == "date":
            day = parse_date(str(date_value or today.isoformat()))
            return day, day
        if period == "week_of":
            return week_range(parse_date(str(date_value or today.isoformat())))
        if period == "current_week":
            return week_range(today)
        if period == "today":
            return today, today
        raise PlannerMeError("period must be one of: today, current_week, date, week_of.")

    @staticmethod
    def required_str(arguments: JsonObject, key: str) -> str:
        value = arguments.get(key)
        if value is None or str(value).strip() == "":
            raise PlannerMeError(f"Missing required argument: {key}")
        return str(value)

    @staticmethod
    def optional_str(arguments: JsonObject, key: str) -> str | None:
        value = arguments.get(key)
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @staticmethod
    def page_arguments(arguments: JsonObject) -> tuple[int, int]:
        page = int(arguments.get("page") or 1)
        page_size = int(arguments.get("page_size") or 25)
        if page < 1:
            raise PlannerMeError("page must be 1 or greater.")
        if page_size < 1:
            raise PlannerMeError("page_size must be 1 or greater.")
        return page, page_size

    @staticmethod
    def page_result(page: Any, key: str, rows: list[dict[str, Any]]) -> JsonObject:
        return {
            "page": page.offset,
            "pageSize": page.page_size,
            "count": page.count,
            "total": page.total,
            "hasNext": page.has_next,
            key: rows,
            "raw": page.elements,
        }

    @staticmethod
    def tool_response(request_id: Any, result: Any, *, is_error: bool = False) -> JsonObject:
        payload: JsonObject = {
            "content": [{"type": "text", "text": pretty_json(result)}],
        }
        if is_error:
            payload["isError"] = True
        return {"jsonrpc": "2.0", "id": request_id, "result": payload}

    @staticmethod
    def error_response(request_id: Any, code: int, message: str) -> JsonObject:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    @staticmethod
    def send(message: JsonObject) -> None:
        sys.stdout.write(json.dumps(message, separators=(",", ":"), ensure_ascii=False) + "\n")
        sys.stdout.flush()


def main() -> int:
    return PlannerMeMcpServer().serve()


if __name__ == "__main__":
    raise SystemExit(main())
