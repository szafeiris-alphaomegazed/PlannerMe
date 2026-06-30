# Installing PlannerMe

PlannerMe is a Python command-line app. After installation, run it as:

```bash
plannerme <command> <subcommand> [options]
```

## Requirements

- Python 3.10 or newer
- A PlannerUs/OpenProject API key
- `cron` if you want scheduled automations on Linux/macOS

## Install For Development

From the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --upgrade setuptools
python -m pip install -e .
```

Verify:

```bash
plannerme --help
plannerme config init
```

## Install From GitHub

You can install directly from a GitHub repository:

```bash
python3 -m venv ~/.venvs/plannerme
~/.venvs/plannerme/bin/python -m pip install --upgrade pip setuptools
~/.venvs/plannerme/bin/python -m pip install "git+https://github.com/OWNER/REPO.git"
ln -sf ~/.venvs/plannerme/bin/plannerme ~/.local/bin/plannerme
ln -sf ~/.venvs/plannerme/bin/plannerme-mcp ~/.local/bin/plannerme-mcp
```

For a specific tag:

```bash
~/.venvs/plannerme/bin/python -m pip install "git+https://github.com/OWNER/REPO.git@v0.1.0"
```

## Why Not `pip install --user`?

On newer Debian/Ubuntu systems, `python3 -m pip install --user .` can fail with:

```text
error: externally-managed-environment
```

That is Python's PEP 668 protection for OS-managed Python installs. Use a
virtualenv as shown above, or install with `pipx` once this package is published
to a package index.

Verify:

```bash
plannerme --help
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}' | plannerme-mcp
```

## Configure PlannerUs Access

Copy `.env.example` to `.env` in the directory where you run `plannerme`, or
export the variables in your shell:

```bash
cp .env.example .env
```

```env
PLANNERUS_BASE_URL=https://app.plannerus.com
PLANNERUS_AUTH=basic
PLANNERUS_API_KEY=your_plannerus_api_key
PLANNERUS_LOG_TASK_PREFIX=LOG_
PLANNERUS_DEFAULT_ACTIVITY_ID=
```

`PLANNERUS_PROJECTS` can use `alias:project_ref` pairs, or a bare project
identifier:

```env
PLANNERUS_PROJECTS=clienta:123,whistleblowing-platform
```

Check the connection:

```bash
plannerme ping
```

## Create User Config

PlannerMe stores project weights and automations in:

```text
~/.plannerme/config.json
```

Create it:

```bash
plannerme config init
```

Add projects:

```bash
plannerme config project add projectA 123 --weight 3 --task LOG_A
plannerme config project add projectB project-b --weight 1 --task LOG_B
```

Set targets:

```bash
plannerme config target set --daily-hours 8 --weekly-hours 40
```

## Run Commands

Show the first page of open tasks:

```bash
plannerme tasks
```

Show only log tasks:

```bash
plannerme tasks --log-tasks
plannerme tasks -l
```

Paged list commands fetch one API page at a time. In an interactive terminal,
press Enter or Space for the next page, or `q` to quit. In scripts, use `--page`
and `--page-size`:

```bash
plannerme tasks --page 2 --page-size 10 --no-pager
```

Preview weighted weekly autolog:

```bash
plannerme autolog --week
```

Apply it:

```bash
plannerme autolog --week --apply
```

Autolog creates entries with an empty comment by default. Pass `--comment` only
when you want one.

Show this week's logs:

```bash
plannerme logs --week
```

Show today's logs:

```bash
plannerme logs --today
```

Show one selected day:

```bash
plannerme logs --day 2026-06-30
```

Show a selected ISO week:

```bash
plannerme logs --iso-week 2026-W27
```

Fill today if it is missing hours:

```bash
plannerme autolog PROJECT_ALIAS --today --apply
```

## Automations

Create an automation that runs every Monday at 09:00:

```bash
plannerme config automation add monday-autolog --day monday --time 09:00 --apply
```

Inspect the cron line:

```bash
plannerme config automation cron monday-autolog
```

Install it into your user crontab:

```bash
plannerme config automation install monday-autolog
```

Cron runs with the `plannerme` executable, so ensure the command is available on
the cron environment's `PATH`. If cron cannot find it, use an absolute path in
`~/.plannerme/config.json` under the automation's `executable` field.

## MCP Server

PlannerMe includes an MCP stdio server for Claude Desktop and other MCP clients.
After package installation, the command is:

```bash
plannerme-mcp
```

From a source checkout, use:

```bash
./plannerme-mcp.py
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
claude mcp add --scope local \
  --transport stdio \
  --env PLANNERME_ENV_FILE=/path/to/planner-me/.env \
  plannerme \
  -- /path/to/planner-me/.venv/bin/plannerme-mcp
```

For a user-wide Claude Code setup, use `--scope user` instead of
`--scope local`.

Verify:

```bash
claude mcp list
claude mcp get plannerme
```

The MCP server reads PlannerUs settings from the env file referenced by
`PLANNERME_ENV_FILE`.

The MCP server exposes tools for projects, tasks, logs, manual time logging,
autolog previews/apply, config projects, weekly weights, and automations.
Time-writing tools default to preview/dry-run unless explicitly told to apply.

## Publishing From GitHub

This repository includes GitHub Actions:

- `.github/workflows/ci.yml` compiles, installs, smoke-tests, builds, and uploads
  package artifacts.
- `.github/workflows/publish.yml` builds and publishes the package when a GitHub
  release is published.

To publish to PyPI, configure PyPI Trusted Publishing for this GitHub
repository, environment `pypi`, then create a GitHub release such as `v0.1.0`.
The publish workflow uses `pypa/gh-action-pypi-publish`.

See `PUBLISH.md` for the full step-by-step publishing checklist.

## Uninstall

If installed editably in a virtualenv:

```bash
python -m pip uninstall plannerme
```

If installed in `~/.venvs/plannerme`:

```bash
~/.venvs/plannerme/bin/python -m pip uninstall plannerme
rm -f ~/.local/bin/plannerme ~/.local/bin/plannerme-mcp
```
