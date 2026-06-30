from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any

from plannerme.errors import PlannerMeError


def load_dotenv(path: str | os.PathLike[str] = ".env") -> None:
    env_path = Path(path)
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def pretty_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def print_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> None:
    if not rows:
        print("No results.")
        return

    widths = []
    for key, heading in columns:
        width = max(len(heading), *(len(str(row.get(key, ""))) for row in rows))
        widths.append(min(width, 80))

    print("  ".join(heading.ljust(widths[index]) for index, (_, heading) in enumerate(columns)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        values = []
        for index, (key, _) in enumerate(columns):
            value = str(row.get(key, ""))
            if len(value) > widths[index]:
                value = value[: widths[index] - 1] + "..."
            values.append(value.ljust(widths[index]))
        print("  ".join(values))


def parse_aliases(value: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            alias, project = item.split(":", 1)
        else:
            alias, project = item, item
        aliases[alias.strip()] = project.strip()
    return aliases


def parse_env_hours(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        hours = float(value)
    except ValueError as exc:
        raise PlannerMeError(f"{name} must be a number.") from exc
    if hours <= 0:
        raise PlannerMeError(f"{name} must be greater than zero.")
    return hours


def make_filters(*filters: dict[str, Any]) -> str:
    return json.dumps([item for item in filters if item], separators=(",", ":"))


def filter_eq(name: str, values: list[str] | str) -> dict[str, Any]:
    if isinstance(values, str):
        values = [values]
    return {name: {"operator": "=", "values": values}}


def filter_date_range(name: str, start: dt.date, end: dt.date) -> dict[str, Any]:
    return {name: {"operator": "<>d", "values": [start.isoformat(), end.isoformat()]}}


def hal_id(value: dict[str, Any]) -> str:
    href = value.get("_links", {}).get("self", {}).get("href", "")
    match = re.search(r"/(\d+)$", href)
    return match.group(1) if match else str(value.get("id", ""))


def link_title(value: dict[str, Any], name: str) -> str:
    link = value.get("_links", {}).get(name, {})
    return str(link.get("title", ""))


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise PlannerMeError(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc


def week_range(day: dt.date) -> tuple[dt.date, dt.date]:
    start = day - dt.timedelta(days=day.weekday())
    return start, start + dt.timedelta(days=6)


def week_key(day: dt.date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def parse_week_key(value: str) -> str:
    if not re.fullmatch(r"\d{4}-W\d{2}", value):
        raise PlannerMeError("Week must use ISO format YYYY-Www, for example 2026-W27.")
    return value


def parse_hours_to_duration(value: str) -> str:
    value = value.strip().upper()
    if value.startswith("PT"):
        return value

    if ":" in value:
        hours_part, minutes_part = value.split(":", 1)
        hours = int(hours_part)
        minutes = int(minutes_part)
    else:
        hours_float = float(value)
        hours = int(hours_float)
        minutes = round((hours_float - hours) * 60)

    if hours < 0 or minutes < 0 or minutes >= 60:
        raise PlannerMeError("Hours must be positive, for example 2, 2.5, 1:30, or PT2H30M.")
    if hours == 0 and minutes == 0:
        raise PlannerMeError("Hours must be greater than zero.")

    parts = ["PT"]
    if hours:
        parts.append(f"{hours}H")
    if minutes:
        parts.append(f"{minutes}M")
    return "".join(parts)


def hours_to_duration(value: float) -> str:
    if value <= 0:
        raise PlannerMeError("Hours must be greater than zero.")
    total_minutes = round(value * 60)
    hours, minutes = divmod(total_minutes, 60)
    parts = ["PT"]
    if hours:
        parts.append(f"{hours}H")
    if minutes:
        parts.append(f"{minutes}M")
    return "".join(parts)


def duration_to_hours(value: str) -> float:
    match = re.fullmatch(r"PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?", value or "")
    if not match:
        return 0.0
    return float(match.group(1) or 0) + float(match.group(2) or 0) / 60


def format_hours(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def coerce_positive_float(value: str | float | int, label: str = "Value") -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PlannerMeError(f"{label} must be a positive number.") from exc
    if number <= 0:
        raise PlannerMeError(f"{label} must be greater than zero.")
    return number


def shell_quote(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:=@+-]+", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"
