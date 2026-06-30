# PlannerMe CLI

Small command-line utility for PlannerUs/OpenProject. It uses your API key from
`.env`, so you can list projects/tasks and log time without browser login.

## Setup

Copy the example file and put your own values in `.env`:

```bash
cp .env.example .env
```

The file uses these variables:

```env
PLANNERUS_BASE_URL=https://app.plannerus.com
PLANNERUS_AUTH=basic
PLANNERUS_API_KEY=your_plannerus_api_key
PLANNERUS_LOG_TASK_PREFIX=LOG_
PLANNERUS_PROJECTS=
PLANNERUS_DEFAULT_ACTIVITY_ID=
PLANNERUS_DAILY_HOURS=8
PLANNERUS_WEEKLY_HOURS=40
```

Only `PLANNERUS_API_KEY` is required. The other values are defaults or optional
helpers.

`PLANNERUS_PROJECTS` lets you create short aliases:

```env
PLANNERUS_PROJECTS=clienta:123,internal:internal-project
```

After that, commands can use `clienta` instead of the project id or identifier.
Bare entries are also accepted and act as both alias and project reference:

```env
PLANNERUS_PROJECTS=whistleblowing-platform
```

You can also manage project aliases, weights, weekly overrides, and automations
in this config file:

```text
~/.plannerme/config.json
```

Create it with:

```bash
plannerme config init
```

The file is plain JSON, so you can edit it manually too. Its shape is:

```json
{
  "targets": {
    "dailyHours": 8,
    "weeklyHours": 40
  },
  "projects": {
    "clienta": {
      "ref": "123",
      "weight": 3,
      "task": "LOG_Development",
      "comment": "Autolog client A",
      "activity": null
    }
  },
  "weeks": {
    "2026-W28": {
      "clienta": 1,
      "clientb": 4
    }
  },
  "automations": {}
}
```

## Run

From this folder:

```bash
plannerme --help
```

Source-checkout compatibility form:

```bash
chmod +x plannerme.py
./plannerme.py --help
```

Run the MCP server from a source checkout:

```bash
chmod +x plannerme-mcp.py
./plannerme-mcp.py
```

## Commands

### Check Connection

Verify the API key and show the connected account:

```bash
plannerme ping
```

Show the raw current user object:

```bash
plannerme me
```

### Projects

Show the first page of projects visible to your API key:

```bash
plannerme projects
```

Show projects where your user is involved/member:

```bash
plannerme projects --me
```

Print raw JSON:

```bash
plannerme projects --me --json
```

List commands are paged. In an interactive terminal, press Enter or Space for
the next page, or `q` to quit. In scripts, only one page is printed.

Fetch a specific page:

```bash
plannerme projects --page 2
```

Change the API page size:

```bash
plannerme tasks --page-size 10
```

Print one page without prompting:

```bash
plannerme logs --week --no-pager
```

### Tasks

By default, `tasks` shows the first page of open work packages visible to your
API key.

Show open tasks:

```bash
plannerme tasks
```

Show open tasks assigned to you:

```bash
plannerme tasks --me
```

Show open tasks for one project:

```bash
plannerme tasks --project clienta
```

Show open tasks for one project assigned to you:

```bash
plannerme tasks --project clienta --me
```

Show only log tasks whose subject starts with `LOG_`:

```bash
plannerme tasks --log-tasks
plannerme tasks -l
```

Use a different log-task prefix:

```bash
plannerme tasks --log-tasks --prefix TIME_
```

Print raw JSON:

```bash
plannerme tasks --project clienta --json
```

JSON output is also paged:

```bash
plannerme tasks --project clienta --page 2 --page-size 10 --json
```

### Log Time

Create a time entry on the matching `LOG_...` task in a project:

```bash
plannerme log clienta 2.5 --comment "Planning"
```

Hours can be written as decimal, `hours:minutes`, or ISO duration:

```bash
plannerme log clienta 2
plannerme log clienta 1:30
plannerme log clienta PT1H30M
```

Log time for a specific date:

```bash
plannerme log clienta 2 --date 2026-06-30
```

If a project has multiple `LOG_...` tasks, select one by id or subject text:

```bash
plannerme log clienta 2 --task 456
plannerme log clienta 2 --task LOG_Development
```

Preview the request without creating the time entry:

```bash
plannerme log clienta 2 --dry-run
```

Force a time-entry activity id:

```bash
plannerme log clienta 2 --activity 1
```

PlannerMe refuses to create time entries that would put your user above 8 hours
for a day or 40 hours for an ISO week:

```bash
plannerme log clienta 1 --date 2026-06-30
```

Override the guard only when you really mean it:

```bash
plannerme log clienta 1 --date 2026-06-30 --force
```

You can also put the default activity in `.env`:

```env
PLANNERUS_DEFAULT_ACTIVITY_ID=1
```

If no activity is set, PlannerUs will use its default activity when available.

### Autolog

`autolog` fills missing time up to your targets:

- `PLANNERUS_DAILY_HOURS=8`
- `PLANNERUS_WEEKLY_HOURS=40`

It checks your existing time entries first. It will not add more time for a day
that already has 8 hours, and it will not push the week above 40 hours unless
you explicitly pass `--force`.

Autolog previews by default:

```bash
plannerme autolog clienta
```

The default range is today. If you omit the project, `autolog` uses the weighted
projects from `~/.plannerme/config.json`:

```bash
plannerme autolog
plannerme autolog --week
```

To actually create the planned entry or entries, add `--apply`:

```bash
plannerme autolog clienta --apply
plannerme autolog --week --apply
```

Fill the current ISO week, Monday through Friday:

```bash
plannerme autolog clienta --week
plannerme autolog clienta --week --apply
```

Fill a selected ISO week:

```bash
plannerme autolog clienta --iso-week 2026-W27
plannerme autolog clienta --iso-week 2026-W27 --apply
```

Fill the ISO week containing a specific date:

```bash
plannerme autolog clienta --week-of 2026-06-30
plannerme autolog clienta --week-of 2026-06-30 --apply
```

Fill one specific day:

```bash
plannerme autolog clienta --today
plannerme autolog clienta --date 2026-06-30
plannerme autolog clienta --day 2026-06-30
plannerme autolog clienta --date 2026-06-30 --apply
```

Daily autolog only fills missing time up to the daily target. If the day already
has 8 hours, it creates nothing.

If a project has multiple `LOG_...` tasks, select one:

```bash
plannerme autolog clienta --week --task 456
plannerme autolog clienta --week --task LOG_Development
```

Override the targets for one run:

```bash
plannerme autolog clienta --week --daily-hours 7.5 --weekly-hours 37.5
```

Targets above 8 hours/day or 40 hours/week require `--force`:

```bash
plannerme autolog clienta --week --daily-hours 9 --weekly-hours 45 --force
```

Set a custom comment:

```bash
plannerme autolog clienta --week --comment "Automatic weekly fill"
```

By default, `autolog` creates time entries with an empty comment.

### Config

Show the config file path:

```bash
plannerme config path
```

Create the config file:

```bash
plannerme config init
```

Print the full config JSON:

```bash
plannerme config show
```

Show or update daily/weekly targets:

```bash
plannerme config target show
plannerme config target set --daily-hours 8 --weekly-hours 40
```

Add projects you work on:

```bash
plannerme config project add clienta 123 --weight 3 --task LOG_Development
plannerme config project add clientb client-b-identifier --weight 1 --task LOG_Support
```

List configured projects:

```bash
plannerme config project list
```

Update a project:

```bash
plannerme config project set clienta --weight 1
plannerme config project set clienta --task 456
plannerme config project set clienta --comment "Autolog client A"
```

Remove a project:

```bash
plannerme config project remove clienta
```

Set weekly weight overrides. This is useful when one week should favor project A
and another week should favor project B:

```bash
plannerme config weight set clienta 4 --week 2026-W27
plannerme config weight set clientb 1 --week 2026-W27
plannerme config weight set clienta 1 --week 2026-W28
plannerme config weight set clientb 4 --week 2026-W28
```

List weekly overrides:

```bash
plannerme config weight list
plannerme config weight list --week 2026-W27
```

Clear one weekly override:

```bash
plannerme config weight clear clienta --week 2026-W27
```

Add an automation that autologs every Monday:

```bash
plannerme config automation add monday-autolog --day monday --time 09:00 --apply
```

This stores the automation in `~/.plannerme/config.json`. To see the cron line:

```bash
plannerme config automation cron monday-autolog
```

To install or update it in your user crontab:

```bash
plannerme config automation install monday-autolog
```

List or remove automations:

```bash
plannerme config automation list
plannerme config automation remove monday-autolog
```

### Logged Time

Show your entries for today:

```bash
plannerme logs
plannerme logs --today
```

Show your entries for the current ISO week:

```bash
plannerme logs --week
```

Show your entries for a selected ISO week:

```bash
plannerme logs --iso-week 2026-W27
```

Show your entries for one date:

```bash
plannerme logs --date 2026-06-30
plannerme logs --day 2026-06-30
```

Show your entries for the ISO week containing a date:

```bash
plannerme logs --week-of 2026-06-30
```

Limit logs to one project:

```bash
plannerme logs --week --project clienta
```

Show visible entries for all users instead of only your user:

```bash
plannerme logs --today --all-users
```

Print raw JSON:

```bash
plannerme logs --week --json
```

Paged log output shows the hours total for the current page. Use `--page` to
move through the range without loading every time entry at once.

### Activities

Show time-entry activity information:

```bash
plannerme activities
```

Print raw JSON:

```bash
plannerme activities --json
```

### Raw API Escape Hatch

These commands call PlannerUs API v3 paths directly.

GET:

```bash
plannerme get /projects
plannerme get /work_packages --param pageSize=10
```

POST:

```bash
plannerme post /some_path --json '{"key":"value"}'
```

Raw `post /time_entries` is also protected by the 8h/day and 40h/week guard.
Use `--force` to override it.

PATCH:

```bash
plannerme patch /some_path/123 --json '{"key":"value"}'
```

DELETE:

```bash
plannerme delete /some_path/123
```

## MCP Server

PlannerMe includes a dependency-free MCP stdio server so AI clients such as
Claude Desktop can use the same project, task, log, config, automation, and
autolog features.

After installing the package, run:

```bash
plannerme-mcp
```

Example Claude Desktop config:

```json
{
  "mcpServers": {
    "plannerme": {
      "command": "/home/YOU/.venvs/plannerme/bin/plannerme-mcp",
      "cwd": "/path/to/planner-me",
      "env": {
        "PLANNERUS_BASE_URL": "https://app.plannerus.com",
        "PLANNERUS_AUTH": "basic",
        "PLANNERUS_API_KEY": "your_plannerus_api_key"
      }
    }
  }
}
```

### Claude Code

From a source checkout, install or refresh the editable package first:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Then add the MCP server to Claude Code:

```bash
claude mcp add plannerme \
  --scope local \
  --transport stdio \
  --env PLANNERME_ENV_FILE=/path/to/planner-me/.env \
  -- /path/to/planner-me/.venv/bin/plannerme-mcp
```

Place `--env` after the server name. In current Claude Code versions, `--env`
accepts multiple values and can consume the server name if it appears earlier.

For a user-wide Claude Code setup, use `--scope user` instead of
`--scope local`.

Verify:

```bash
claude mcp list
claude mcp get plannerme
```

Then start Claude Code from the project and ask for PlannerMe actions, for
example:

```text
Use plannerme to show my LOG_ tasks for whistleblowing-platform.
Use plannerme to preview this week's autolog plan.
```

Available MCP tools mirror the CLI command groups:

- API/account: `plannerme_ping`, `plannerme_me`, `plannerme_activities`
- Work: `plannerme_projects`, `plannerme_tasks`, `plannerme_logs`, `plannerme_log_time`, `plannerme_autolog`
- Config: `plannerme_config_path`, `plannerme_config_show`, `plannerme_config_targets`, `plannerme_config_projects`, `plannerme_config_week_weights`, `plannerme_config_automations`
- Config writes: `plannerme_config_init`, `plannerme_config_set_targets`, `plannerme_config_add_project`, `plannerme_config_set_project`, `plannerme_config_remove_project`, `plannerme_config_set_week_weight`, `plannerme_config_clear_week_weight`, `plannerme_config_add_automation`, `plannerme_config_remove_automation`, `plannerme_config_automation_cron`, `plannerme_config_install_automation`
- Raw API escape hatch: `plannerme_raw_get`, `plannerme_raw_post`, `plannerme_raw_patch`, `plannerme_raw_delete`

`plannerme_log_time` defaults to `dry_run: true`, and `plannerme_autolog`
defaults to `apply: false`, so models preview writes unless explicitly asked to
create entries.

MCP time-writing tools also enforce the 8h/day and 40h/week guard unless a tool
call passes `force: true`.

The MCP list tools `plannerme_projects`, `plannerme_tasks`, and
`plannerme_logs` accept `page` and `page_size` arguments, so AI clients can page
through results instead of loading everything at once.

`plannerme_logs` can select a week with:

```json
{"period": "iso_week", "week": "2026-W27"}
```

It can select today or one day with:

```json
{"period": "today"}
{"period": "day", "date": "2026-06-30"}
```

MCP time logging and autolog tools also use empty comments by default unless a
model explicitly passes a `comment` argument.

## Typical Flow

1. Check the API key:

```bash
plannerme ping
```

2. Find project ids or identifiers:

```bash
plannerme projects --me
```

3. Add configured projects:

```bash
plannerme config project add clienta 123 --weight 3 --task LOG_Development
plannerme config project add clientb client-b-identifier --weight 1 --task LOG_Support
```

4. Check the available log tasks:

```bash
plannerme tasks --project clienta --log-tasks
```

5. Log time:

```bash
plannerme log clienta 2.5 --comment "Worked on task"
```

6. Or autolog missing time:

```bash
plannerme autolog --week
plannerme autolog --week --apply
```

7. Verify:

```bash
plannerme logs --today
```
