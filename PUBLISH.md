# Publishing PlannerMe

GitHub's repository **Packages** panel is not the normal place to publish a
Python package. GitHub Packages does not provide a native PyPI-compatible Python
package registry. For Python developers to install with `pip install plannerme`,
publish PlannerMe to PyPI.

This repo already includes the GitHub Actions workflow that builds and publishes
the package:

```text
.github/workflows/publish.yml
```

## Option 1: Install Directly From GitHub

This works now, even before publishing to PyPI.

Public repository:

```bash
python3 -m venv ~/.venvs/plannerme
~/.venvs/plannerme/bin/python -m pip install --upgrade pip
~/.venvs/plannerme/bin/python -m pip install "git+https://github.com/szafeiris-alphaomegazed/PlannerMe.git"
```

Private repository with SSH access:

```bash
python3 -m venv ~/.venvs/plannerme
~/.venvs/plannerme/bin/python -m pip install --upgrade pip
~/.venvs/plannerme/bin/python -m pip install "git+ssh://git@github.com/szafeiris-alphaomegazed/PlannerMe.git"
```

Verify:

```bash
~/.venvs/plannerme/bin/plannerme --help
~/.venvs/plannerme/bin/plannerme-mcp --help
```

## Option 2: Publish To PyPI

Use this when you want developers to install with:

```bash
python3 -m pip install plannerme
```

### 1. Create A PyPI Account

Create an account at:

```text
https://pypi.org/account/register/
```

Enable 2FA on the PyPI account before publishing.

### 2. Configure Trusted Publishing

In PyPI, create a **pending trusted publisher** for this project.

Use these values:

```text
PyPI project name: plannerme
Owner: szafeiris-alphaomegazed
Repository name: PlannerMe
Workflow filename: publish.yml
Environment name: pypi
```

The package name is the value in `pyproject.toml`:

```toml
name = "plannerme"
```

### 3. Create The GitHub Environment

In GitHub:

```text
Repository -> Settings -> Environments -> New environment
```

Create:

```text
pypi
```

You can add required reviewers if you want manual approval before publishing.

### 4. Create A Release

Make sure the version in `pyproject.toml` is correct:

```toml
version = "0.1.0"
```

Commit and push any version changes:

```bash
git add pyproject.toml
git commit -m "Bump version to 0.1.0"
git push
```

Create and push a tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Then create a GitHub release from that tag:

```text
Repository -> Releases -> Draft a new release -> Choose v0.1.0 -> Publish release
```

Publishing the GitHub release triggers:

```text
.github/workflows/publish.yml
```

The workflow builds the wheel/source distribution and uploads them to PyPI using
Trusted Publishing, without storing a PyPI token in GitHub secrets.

### 5. Install From PyPI

After the workflow succeeds:

```bash
python3 -m venv ~/.venvs/plannerme
~/.venvs/plannerme/bin/python -m pip install plannerme
~/.venvs/plannerme/bin/plannerme --help
```

## Updating The Package

For every new release:

1. Update `version` in `pyproject.toml`.
2. Commit and push.
3. Create a matching tag, for example `v0.1.1`.
4. Publish a GitHub release for that tag.
5. Confirm the GitHub Actions publish workflow succeeds.

PyPI does not allow replacing an already published version, so every upload
needs a new version number.
