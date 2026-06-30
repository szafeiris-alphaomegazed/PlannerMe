from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Any

from plannerme.automation import AutomationManager
from plannerme.autolog import AutologPlanner
from plannerme.client import CollectionPage, PlannerUsClient
from plannerme.constants import CONFIG_PATH
from plannerme.errors import PlannerMeError
from plannerme.services import PlannerService
from plannerme.settings import PlannerMeSettings
from plannerme.user_config import UserConfigManager
from plannerme.utils import (
    coerce_positive_float,
    duration_to_hours,
    format_hours,
    parse_date,
    parse_week_key,
    pretty_json,
    print_table,
    week_range_from_key,
)


class PlannerMeCLI:
    def __init__(self, config_manager: UserConfigManager | None = None) -> None:
        self.config_manager = config_manager or UserConfigManager()
        self.automation_manager = AutomationManager()

    def run(self, argv: list[str] | None = None) -> int:
        parser = self.build_parser()
        args = parser.parse_args(argv)
        try:
            self.validate_pagination(args)
            if args.command == "config":
                return self.handle_config(args)

            settings = PlannerMeSettings.from_env(self.config_manager)
            client = PlannerUsClient(settings)
            service = PlannerService(client)
            return self.handle_api_command(args, client, service)
        except PlannerMeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    def handle_api_command(self, args: argparse.Namespace, client: PlannerUsClient, service: PlannerService) -> int:
        if args.command == "ping":
            print(pretty_json(client.ping()))
            return 0
        if args.command == "me":
            print(pretty_json(client.get("/users/me")))
            return 0
        if args.command == "projects":
            page = service.project_page(me=args.me, page_size=args.page_size, offset=args.page)
            if args.json:
                print(pretty_json(self.page_json(page, "projects", page.elements)))
            else:
                self.print_paged_table(
                    fetch_page=lambda offset: service.project_page(me=args.me, page_size=args.page_size, offset=offset),
                    row_factory=service.project_rows,
                    columns=[("id", "ID"), ("identifier", "Identifier"), ("name", "Name"), ("active", "Active")],
                    first_page=page,
                    interactive=not args.no_pager,
                )
            return 0
        if args.command == "tasks":
            page = service.task_page(
                project=args.project,
                me=args.me,
                log_tasks=args.log_tasks,
                prefix=args.prefix,
                page_size=args.page_size,
                offset=args.page,
            )
            if args.json:
                print(pretty_json(self.page_json(page, "tasks", page.elements)))
            else:
                self.print_paged_table(
                    fetch_page=lambda offset: service.task_page(
                        project=args.project,
                        me=args.me,
                        log_tasks=args.log_tasks,
                        prefix=args.prefix,
                        page_size=args.page_size,
                        offset=offset,
                    ),
                    row_factory=service.task_rows,
                    columns=[
                        ("id", "ID"),
                        ("subject", "Subject"),
                        ("project", "Project"),
                        ("assignee", "Assignee"),
                        ("status", "Status"),
                    ],
                    first_page=page,
                    interactive=not args.no_pager,
                )
            return 0
        if args.command == "logs":
            start, end = self.log_range(args)
            page = service.time_entry_page(
                start=start,
                end=end,
                me=not args.all_users,
                project=args.project,
                page_size=args.page_size,
                offset=args.page,
            )
            if args.json:
                print(pretty_json(self.page_json(page, "entries", page.elements, {"range": {"start": start.isoformat(), "end": end.isoformat()}})))
            else:
                self.print_paged_table(
                    fetch_page=lambda offset: service.time_entry_page(
                        start=start,
                        end=end,
                        me=not args.all_users,
                        project=args.project,
                        page_size=args.page_size,
                        offset=offset,
                    ),
                    row_factory=service.time_entry_rows,
                    columns=[
                        ("date", "Date"),
                        ("hours", "Hours"),
                        ("project", "Project"),
                        ("task", "Task"),
                        ("activity", "Activity"),
                        ("comment", "Comment"),
                    ],
                    first_page=page,
                    interactive=not args.no_pager,
                    footer_factory=lambda current_page: (
                        "Page total: "
                        f"{format_hours(sum(duration_to_hours(str(entry.get('hours', ''))) for entry in current_page.elements))} "
                        f"hours ({start} to {end})"
                    ),
                )
            return 0
        if args.command == "log":
            result = service.create_time_entry(
                project=args.project,
                hours=args.hours,
                spent_on=parse_date(args.date),
                task=args.task,
                comment=args.comment,
                activity=args.activity,
                dry_run=args.dry_run,
            )
            if args.json or args.dry_run:
                print(pretty_json(result))
            else:
                print_table(
                    service.time_entry_rows([result]),
                    [
                        ("date", "Date"),
                        ("hours", "Hours"),
                        ("project", "Project"),
                        ("task", "Task"),
                        ("activity", "Activity"),
                        ("comment", "Comment"),
                    ],
                )
            return 0
        if args.command == "autolog":
            planner = AutologPlanner(service, self.config_manager)
            start, end = planner.range_from_args(args)
            if args.project:
                result = planner.plan_single_project(
                    project=args.project,
                    start=start,
                    end=end,
                    daily_hours=args.daily_hours or client.settings.daily_hours,
                    weekly_hours=args.weekly_hours or client.settings.weekly_hours,
                    task=args.task,
                    comment=args.comment or "",
                    activity=args.activity,
                    apply=args.apply,
                )
            else:
                result = planner.plan_configured_projects(
                    start=start,
                    end=end,
                    daily_hours=args.daily_hours or client.settings.daily_hours,
                    weekly_hours=args.weekly_hours or client.settings.weekly_hours,
                    task=args.task,
                    comment=args.comment,
                    activity=args.activity,
                    apply=args.apply,
                )
            self.print_autolog_result(result, args.json, args.apply)
            return 0
        if args.command == "activities":
            activities = service.list_activities()
            if args.json:
                print(pretty_json(activities))
            else:
                print_table([{"id": item.get("id"), "name": item.get("name")} for item in activities], [("id", "ID"), ("name", "Name")])
            return 0
        if args.command == "get":
            print(pretty_json(client.get(args.path, self.parse_params(args.param))))
            return 0
        if args.command == "post":
            print(pretty_json(client.post(args.path, self.parse_json_body(args.json))))
            return 0
        if args.command == "patch":
            print(pretty_json(client.patch(args.path, self.parse_json_body(args.json))))
            return 0
        if args.command == "delete":
            print(pretty_json(client.delete(args.path)))
            return 0
        raise PlannerMeError(f"Unknown command {args.command}")

    def handle_config(self, args: argparse.Namespace) -> int:
        config = self.config_manager.load()

        if args.config_command == "path":
            print(self.config_manager.path)
            return 0
        if args.config_command == "init":
            self.config_manager.save(config)
            print(f"Config ready: {self.config_manager.path}")
            return 0
        if args.config_command == "show":
            print(pretty_json(config))
            return 0
        if args.config_command == "target":
            return self.handle_config_target(args, config)
        if args.config_command == "project":
            return self.handle_config_project(args, config)
        if args.config_command == "weight":
            return self.handle_config_weight(args, config)
        if args.config_command == "automation":
            return self.handle_config_automation(args, config)
        raise PlannerMeError("Unknown config command.")

    def handle_config_target(self, args: argparse.Namespace, config: dict[str, Any]) -> int:
        if args.target_command == "show":
            print(pretty_json(config["targets"]))
            return 0
        if args.target_command == "set":
            if args.daily_hours is not None:
                config["targets"]["dailyHours"] = coerce_positive_float(args.daily_hours, "Daily hours")
            if args.weekly_hours is not None:
                config["targets"]["weeklyHours"] = coerce_positive_float(args.weekly_hours, "Weekly hours")
            self.config_manager.save(config)
            print(
                "Updated targets: "
                f"{format_hours(float(config['targets']['dailyHours']))} hours/day, "
                f"{format_hours(float(config['targets']['weeklyHours']))} hours/week"
            )
            return 0
        raise PlannerMeError("Unknown target command.")

    def handle_config_project(self, args: argparse.Namespace, config: dict[str, Any]) -> int:
        projects = config["projects"]
        if args.project_command == "list":
            print_table(
                self.config_manager.project_rows(config),
                [
                    ("alias", "Alias"),
                    ("ref", "Project Ref"),
                    ("weight", "Weight"),
                    ("task", "Task"),
                    ("comment", "Comment"),
                    ("activity", "Activity"),
                ],
            )
            return 0
        if args.project_command == "add":
            if args.alias in projects and not args.force:
                raise PlannerMeError(f"Project alias '{args.alias}' already exists. Use --force to replace it.")
            projects[args.alias] = {
                "ref": args.ref,
                "weight": coerce_positive_float(args.weight, "Weight"),
                "task": args.task,
                "comment": args.comment,
                "activity": args.activity,
            }
            self.config_manager.save(config)
            print(f"Saved project '{args.alias}' in {self.config_manager.path}")
            return 0
        if args.project_command == "set":
            if args.alias not in projects:
                raise PlannerMeError(f"Unknown project alias '{args.alias}'.")
            project = projects[args.alias]
            if args.ref is not None:
                project["ref"] = args.ref
            if args.weight is not None:
                project["weight"] = coerce_positive_float(args.weight, "Weight")
            if args.task is not None:
                project["task"] = args.task or None
            if args.comment is not None:
                project["comment"] = args.comment or None
            if args.activity is not None:
                project["activity"] = args.activity or None
            self.config_manager.save(config)
            print(f"Updated project '{args.alias}'")
            return 0
        if args.project_command == "remove":
            projects.pop(args.alias, None)
            for weights in config.get("weeks", {}).values():
                if isinstance(weights, dict):
                    weights.pop(args.alias, None)
            self.config_manager.save(config)
            print(f"Removed project '{args.alias}'")
            return 0
        raise PlannerMeError("Unknown project config command.")

    def handle_config_weight(self, args: argparse.Namespace, config: dict[str, Any]) -> int:
        week = parse_week_key(args.week) if getattr(args, "week", None) else None
        if args.weight_command == "list":
            print_table(self.config_manager.weight_rows(config, week), [("week", "Week"), ("alias", "Alias"), ("weight", "Weight")])
            return 0
        if args.weight_command == "set":
            if week is None:
                raise PlannerMeError("--week is required.")
            if args.alias not in config.get("projects", {}):
                raise PlannerMeError(f"Unknown project alias '{args.alias}'.")
            config["weeks"].setdefault(week, {})[args.alias] = coerce_positive_float(args.weight, "Weight")
            self.config_manager.save(config)
            print(f"Set {week} weight for '{args.alias}' to {format_hours(float(args.weight))}")
            return 0
        if args.weight_command == "clear":
            if week is None:
                raise PlannerMeError("--week is required.")
            if week in config["weeks"]:
                config["weeks"][week].pop(args.alias, None)
                if not config["weeks"][week]:
                    config["weeks"].pop(week)
            self.config_manager.save(config)
            print(f"Cleared {week} weight for '{args.alias}'")
            return 0
        raise PlannerMeError("Unknown weight config command.")

    def handle_config_automation(self, args: argparse.Namespace, config: dict[str, Any]) -> int:
        automations = config["automations"]
        if args.automation_command == "list":
            print_table(
                self.config_manager.automation_rows(config),
                [("name", "Name"), ("enabled", "Enabled"), ("day", "Day"), ("time", "Time"), ("args", "Command Args")],
            )
            return 0
        if args.automation_command == "add":
            automations[args.name] = self.automation_manager.build_automation(
                day=args.day,
                time=args.time,
                project=args.project,
                period=args.period,
                task=args.task,
                comment=args.comment,
                apply=args.apply,
            )
            self.config_manager.save(config)
            print(f"Saved automation '{args.name}'. Use 'config automation cron {args.name}' to see the cron line.")
            return 0
        if args.automation_command == "remove":
            automations.pop(args.name, None)
            self.config_manager.save(config)
            print(f"Removed automation '{args.name}'")
            return 0
        if args.automation_command in {"cron", "install"}:
            automation = automations.get(args.name)
            if not automation:
                raise PlannerMeError(f"Unknown automation '{args.name}'.")
            line = self.automation_manager.cron_line(args.name, automation)
            if args.automation_command == "cron":
                print(line)
            else:
                self.automation_manager.install_cron_line(args.name, line)
                print(f"Installed cron automation '{args.name}'")
            return 0
        raise PlannerMeError("Unknown automation config command.")

    def print_autolog_result(self, result: dict[str, Any], as_json: bool, apply: bool) -> None:
        if as_json:
            print(pretty_json(result))
            return
        print(f"Mode: {'apply' if apply else 'preview'}")
        print(f"Work package: {result['workPackage']}")
        print(
            "Targets: "
            f"{format_hours(result['targets']['dailyHours'])} hours/day, "
            f"{format_hours(result['targets']['weeklyHours'])} hours/week"
        )
        print(
            "Existing: "
            f"{format_hours(result['existing']['selectedRangeHours'])} hours in range, "
            f"{format_hours(result['existing']['weekHours'])} hours in week"
        )
        print_table(
            AutologPlanner.rows(result),
            [
                ("date", "Date"),
                ("project", "Project"),
                ("weight", "Weight"),
                ("existing", "Existing"),
                ("planned", "Planned"),
                ("status", "Status"),
                ("createdId", "Created ID"),
            ],
        )
        print(f"\nPlanned total: {format_hours(result['plannedHours'])} hours")
        if not apply:
            print("Preview only. Re-run with --apply to create these entries.")

    def build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description="Log time in PlannerUs without browser login.")
        subparsers = parser.add_subparsers(dest="command", required=True)

        subparsers.add_parser("ping", help="Verify the API key and show the connected user.")
        subparsers.add_parser("me", help="Show the connected PlannerUs user.")

        projects_parser = subparsers.add_parser("projects", help="Show PlannerUs projects.")
        projects_parser.add_argument("--me", action="store_true", help="Only projects where your user is a member.")
        projects_parser.add_argument("--json", action="store_true", help="Print raw JSON.")
        self.add_pagination_arguments(projects_parser)

        tasks_parser = subparsers.add_parser("tasks", help="Show open tasks/work packages.")
        tasks_parser.add_argument("--me", action="store_true", help="Only tasks assigned to you.")
        tasks_parser.add_argument("--project", help="Project id, identifier, name, or alias.")
        tasks_parser.add_argument("-l", "--log-tasks", action="store_true", help="Only show tasks whose subject starts with LOG_.")
        tasks_parser.add_argument("--prefix", help="Prefix used with --log-tasks. Defaults to PLANNERUS_LOG_TASK_PREFIX.")
        tasks_parser.add_argument("--json", action="store_true", help="Print raw JSON.")
        self.add_pagination_arguments(tasks_parser)

        logs_parser = subparsers.add_parser("logs", help="Show logged time for a day or ISO week.")
        logs_range = logs_parser.add_mutually_exclusive_group()
        logs_range.add_argument("--today", action="store_true", help="Show today's log entries. This is the default.")
        logs_range.add_argument("--week", action="store_true", help="Show the current ISO week.")
        logs_range.add_argument("--iso-week", help="Show a specific ISO week, YYYY-Www.")
        logs_range.add_argument("--date", help="Show one date, YYYY-MM-DD.")
        logs_range.add_argument("--week-of", help="Show the ISO week containing this date, YYYY-MM-DD.")
        logs_parser.add_argument("--project", help="Limit to a project id, identifier, name, or alias.")
        logs_parser.add_argument("--all-users", action="store_true", help="Show visible entries for all users.")
        logs_parser.add_argument("--json", action="store_true", help="Print raw JSON.")
        self.add_pagination_arguments(logs_parser)

        log_parser = subparsers.add_parser("log", help="Create a time entry on a matching LOG_ task.")
        log_parser.add_argument("project", help="Project id, identifier, name, or alias.")
        log_parser.add_argument("hours", help="Hours like 2, 2.5, 1:30, or PT2H30M.")
        log_parser.add_argument("--date", default=dt.date.today().isoformat(), help="Spent-on date, YYYY-MM-DD.")
        log_parser.add_argument("--task", help="Work package id or text to match against LOG_ task subject.")
        log_parser.add_argument("--comment", default="", help="Time entry comment.")
        log_parser.add_argument("--activity", help="Time-entry activity id.")
        log_parser.add_argument("--dry-run", action="store_true", help="Print the request body without creating it.")
        log_parser.add_argument("--json", action="store_true", help="Print raw JSON response.")

        autolog_parser = subparsers.add_parser("autolog", help="Fill missing time up to configured daily/weekly targets.")
        autolog_parser.add_argument("project", nargs="?", help="Project id, identifier, or alias. Omit to use configured weighted projects.")
        autolog_range_group = autolog_parser.add_mutually_exclusive_group()
        autolog_range_group.add_argument("--date", help="Fill one date up to the daily target, YYYY-MM-DD.")
        autolog_range_group.add_argument("--week", action="store_true", help="Fill the current ISO week.")
        autolog_range_group.add_argument("--week-of", help="Fill the ISO week containing this date, YYYY-MM-DD.")
        autolog_parser.add_argument("--task", help="Work package id or text to match against LOG_ task subject.")
        autolog_parser.add_argument("--comment", help="Time entry comment.")
        autolog_parser.add_argument("--activity", help="Time-entry activity id.")
        autolog_parser.add_argument("--daily-hours", type=float, help="Daily target.")
        autolog_parser.add_argument("--weekly-hours", type=float, help="Weekly target.")
        autolog_parser.add_argument("--apply", action="store_true", help="Actually create entries. Without this, autolog only previews the plan.")
        autolog_parser.add_argument("--json", action="store_true", help="Print raw JSON response.")

        activities_parser = subparsers.add_parser("activities", help="Show time-entry activities.")
        activities_parser.add_argument("--json", action="store_true", help="Print raw JSON.")

        self.add_config_parser(subparsers)
        self.add_raw_api_parsers(subparsers)
        return parser

    def add_config_parser(self, subparsers: argparse._SubParsersAction) -> None:
        config_parser = subparsers.add_parser("config", help=f"Manage {CONFIG_PATH}.")
        config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
        config_subparsers.add_parser("path", help="Print the config file path.")
        config_subparsers.add_parser("init", help="Create the config file if it does not exist.")
        config_subparsers.add_parser("show", help="Print the full config JSON.")

        target_config = config_subparsers.add_parser("target", help="Manage daily and weekly hour targets.")
        target_subparsers = target_config.add_subparsers(dest="target_command", required=True)
        target_subparsers.add_parser("show", help="Show hour targets.")
        target_set = target_subparsers.add_parser("set", help="Update hour targets.")
        target_set.add_argument("--daily-hours", type=float)
        target_set.add_argument("--weekly-hours", type=float)

        project_config = config_subparsers.add_parser("project", help="Manage configured projects.")
        project_subparsers = project_config.add_subparsers(dest="project_command", required=True)
        project_subparsers.add_parser("list", help="List configured projects.")
        project_add = project_subparsers.add_parser("add", help="Add a configured project.")
        project_add.add_argument("alias")
        project_add.add_argument("ref")
        project_add.add_argument("--weight", default=1.0)
        project_add.add_argument("--task")
        project_add.add_argument("--comment")
        project_add.add_argument("--activity")
        project_add.add_argument("--force", action="store_true")
        project_set = project_subparsers.add_parser("set", help="Update a configured project.")
        project_set.add_argument("alias")
        project_set.add_argument("--ref")
        project_set.add_argument("--weight")
        project_set.add_argument("--task")
        project_set.add_argument("--comment")
        project_set.add_argument("--activity")
        project_remove = project_subparsers.add_parser("remove", help="Remove a configured project.")
        project_remove.add_argument("alias")

        weight_config = config_subparsers.add_parser("weight", help="Manage per-week project weights.")
        weight_subparsers = weight_config.add_subparsers(dest="weight_command", required=True)
        weight_list = weight_subparsers.add_parser("list", help="List weekly weight overrides.")
        weight_list.add_argument("--week")
        weight_set = weight_subparsers.add_parser("set", help="Set one weekly weight override.")
        weight_set.add_argument("alias")
        weight_set.add_argument("weight")
        weight_set.add_argument("--week", required=True)
        weight_clear = weight_subparsers.add_parser("clear", help="Clear one weekly weight override.")
        weight_clear.add_argument("alias")
        weight_clear.add_argument("--week", required=True)

        automation_config = config_subparsers.add_parser("automation", help="Manage scheduled automations.")
        automation_subparsers = automation_config.add_subparsers(dest="automation_command", required=True)
        automation_subparsers.add_parser("list", help="List automations.")
        automation_add = automation_subparsers.add_parser("add", help="Add an autolog automation.")
        automation_add.add_argument("name")
        automation_add.add_argument("--project")
        automation_add.add_argument("--day", default="monday")
        automation_add.add_argument("--time", default="09:00")
        automation_add.add_argument("--period", choices=["week"], default="week")
        automation_add.add_argument("--task")
        automation_add.add_argument("--comment")
        automation_add.add_argument("--apply", action="store_true")
        automation_remove = automation_subparsers.add_parser("remove", help="Remove an automation from config.")
        automation_remove.add_argument("name")
        automation_cron = automation_subparsers.add_parser("cron", help="Print the cron line for an automation.")
        automation_cron.add_argument("name")
        automation_install = automation_subparsers.add_parser("install", help="Install or update the automation in crontab.")
        automation_install.add_argument("name")

    @staticmethod
    def add_raw_api_parsers(subparsers: argparse._SubParsersAction) -> None:
        get_parser = subparsers.add_parser("get", help="GET an API v3 path.")
        get_parser.add_argument("path")
        get_parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
        for method in ("post", "patch"):
            method_parser = subparsers.add_parser(method, help=f"{method.upper()} an API v3 path.")
            method_parser.add_argument("path")
            method_parser.add_argument("--json", default=None, metavar="BODY")
        delete_parser = subparsers.add_parser("delete", help="DELETE an API v3 path.")
        delete_parser.add_argument("path")

    @staticmethod
    def add_pagination_arguments(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--page", type=int, default=1, help="API page number to start at. Defaults to 1.")
        parser.add_argument("--page-size", type=int, default=25, help="Rows fetched per API page. Defaults to 25.")
        parser.add_argument("--no-pager", action="store_true", help="Print only one page without prompting for the next page.")

    @staticmethod
    def validate_pagination(args: argparse.Namespace) -> None:
        if hasattr(args, "page") and args.page < 1:
            raise PlannerMeError("--page must be 1 or greater.")
        if hasattr(args, "page_size") and args.page_size < 1:
            raise PlannerMeError("--page-size must be 1 or greater.")

    def print_paged_table(
        self,
        *,
        fetch_page: Any,
        row_factory: Any,
        columns: list[tuple[str, str]],
        first_page: CollectionPage,
        interactive: bool,
        footer_factory: Any | None = None,
    ) -> None:
        page = first_page
        use_prompt = interactive and sys.stdin.isatty() and sys.stdout.isatty()

        while True:
            if not self.print_page_header(page):
                return
            print_table(row_factory(page.elements), columns)
            if footer_factory is not None:
                print(f"\n{footer_factory(page)}")
            if not page.has_next:
                return
            if not use_prompt:
                print(f"\nMore results available. Use --page {page.offset + 1} to fetch the next page.")
                return
            if not self.prompt_next_page(page):
                return
            page = fetch_page(page.offset + 1)

    @staticmethod
    def print_page_header(page: CollectionPage) -> bool:
        if page.total == 0:
            print("No results.")
            return False
        if page.count == 0:
            print(f"No results on page {page.offset}. Total results: {page.total}.")
            return False
        print(f"Page {page.offset}: showing {page.start_index}-{page.end_index} of {page.total}\n")
        return True

    def prompt_next_page(self, page: CollectionPage) -> bool:
        prompt = f"\n-- More ({page.end_index}/{page.total}) -- Press Enter/Space for next page, q to quit "
        print(prompt, end="", flush=True)
        try:
            key = self.read_single_key()
        except KeyboardInterrupt:
            print()
            return False
        print()
        return key not in {"q", "Q"}

    @staticmethod
    def read_single_key() -> str:
        try:
            import termios
            import tty

            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                return sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            return sys.stdin.readline()[:1]

    @staticmethod
    def page_json(page: CollectionPage, key: str, elements: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> dict[str, Any]:
        value = {
            "page": page.offset,
            "pageSize": page.page_size,
            "count": page.count,
            "total": page.total,
            "hasNext": page.has_next,
            key: elements,
        }
        if extra:
            value.update(extra)
        return value

    @staticmethod
    def parse_params(values: list[str]) -> dict[str, str]:
        params = {}
        for value in values:
            if "=" not in value:
                raise PlannerMeError(f"Invalid --param value '{value}'. Use key=value.")
            key, param_value = value.split("=", 1)
            params[key] = param_value
        return params

    @staticmethod
    def parse_json_body(value: str | None) -> Any | None:
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise PlannerMeError(f"Invalid JSON body: {exc}") from exc

    @staticmethod
    def log_range(args: argparse.Namespace) -> tuple[dt.date, dt.date]:
        today = dt.date.today()
        if args.date:
            day = parse_date(args.date)
            return day, day
        if args.week_of:
            from plannerme.utils import week_range

            return week_range(parse_date(args.week_of))
        if getattr(args, "iso_week", None):
            return week_range_from_key(args.iso_week)
        if args.week:
            from plannerme.utils import week_range

            return week_range(today)
        return today, today


def main(argv: list[str] | None = None) -> int:
    return PlannerMeCLI().run(argv)
