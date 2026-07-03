# GitHub Workflow Guide

How to use Trailmind in a GitHub repository with CI, PRs, and project boards.

## Setting Up

### 1. Initialize the repo

```sh
mkdir my-project && cd my-project
git init

# Install Trailmind
python3.11 -m venv .venv
. .venv/bin/activate
pip install trailmind  # or pip install -e /path/to/trailmind

# Scaffold recommended files
trailmind init
```

This creates:
- `roster.yaml` — developer registry
- `projects/` — project records directory
- `.github/workflows/ci.yml` — CI with pytest + scan
- `.github/PULL_REQUEST_TEMPLATE.md` — PR template
- `.github/ISSUE_TEMPLATE/` — issue templates

### 2. Add your team

```sh
trailmind roster add \
  --email alice@example.com \
  --shortname alice \
  --name "Alice" \
  --uid 123456

trailmind roster add \
  --email bob@example.com \
  --shortname bob \
  --name "Bob" \
  --uid 654321
```

### 3. Create a project and epic

```sh
trailmind project init \
  --slug myapp \
  --title "My App" \
  --goal "Build something useful." \
  --owners alice@example.com \
  --tags web,production

trailmind epic init \
  --project myapp \
  --slug mvp \
  --title "MVP" \
  --goal "First usable release" \
  --start 2026-07-01 \
  --target 2026-07-31 \
  --roster alice,bob \
  --repos myapp
```

## CI/CD

The generated `.github/workflows/ci.yml` runs on every push and PR:

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: pip install -e ".[dev]"
      - run: python -m pytest -v
      - run: PYTHONPATH=src python -m trailmind scan
```

The security scan (`trailmind scan`) fails the build if it finds:
- Non-example.com email addresses
- Sensitive environment files (`.env`, `secrets.yaml`, etc.)
- Token-like strings (JWTs, API keys)
- Blocked release markers

## PR Workflow

### Creating a feature branch

```sh
git checkout -b feature/login-flow
```

### Adding tasks

```sh
trailmind task add \
  --epic projects/myapp/mvp \
  --filer alice@example.com \
  --owner alice@example.com \
  --title "Build login form" \
  --code-paths "src/login.py,tests/test_login.py" \
  --deliverables "tests pass,UI renders correctly"
```

### Opening a PR

When you open a PR, the template prompts you to:
- Describe what changed
- Run tests locally
- Run the security scan
- Update docs if needed

### Linking PRs to tasks

Use the task ID in your branch name or PR description:

```sh
git checkout -b feature/T-123456-001-login-form
```

Or in the PR description:

```
Implements T-123456-001 (Build login form)
```

## Planning Workflow

### 1. Write a spec

Create a design spec at `projects/myapp/mvp/docs/specs/`:

```markdown
---
title: Login Flow
status: draft-for-review
created: '2026-07-03'
scope: mvp
---

# Login Flow

## Purpose
Users need to sign in.

## Design
Use session-based auth.
```

### 2. Review and approve

```sh
# Review the spec
cat projects/myapp/mvp/docs/specs/2026-07-03-login-flow.md

# Approve (update frontmatter status)
```

### 3. Write an implementation plan

```markdown
---
title: Login Implementation
status: draft
created: '2026-07-03'
linked_spec: docs/specs/2026-07-03-login-flow.md
---

# Login Implementation

### Task 1: Login Form
**Files:**
- Create: `src/login.py`
- Test: `tests/test_login.py`

- [ ] **Step 1: Build the form**
- [ ] **Step 2: Add validation**
```

### 4. Break down into tasks

```sh
# Preview
trailmind plan breakdown projects/myapp/mvp/docs/plans/2026-07-03-login-impl.md \
  --epic projects/myapp/mvp \
  --filer alice@example.com \
  --owner alice@example.com

# Create tasks
trailmind plan breakdown projects/myapp/mvp/docs/plans/2026-07-03-login-impl.md \
  --epic projects/myapp/mvp \
  --filer alice@example.com \
  --owner alice@example.com \
  --write
```

### 5. Track progress

```sh
# See what's ready, blocked, stale
trailmind sweep --epic projects/myapp/mvp

# Pick up a task
trailmind task pickup T-123456-001

# Update status
trailmind task set-status T-123456-001 ready --actor alice
trailmind task set-status T-123456-001 in_progress --actor alice
trailmind task close T-123456-001 --closer alice --note "Done!"
```

## Dashboard

```sh
# Generate HTML dashboards
trailmind status --overview
trailmind status --project myapp
trailmind status --epic projects/myapp/mvp

# Serve locally
trailmind serve --port 8888
```

## Issues

```sh
# File an issue
trailmind issue add \
  --epic projects/myapp/mvp \
  --filer alice@example.com \
  --title "Login crashes on empty email" \
  --description "Crashes with IndexError" \
  --severity high

# Link to a task
trailmind issue link --issue I-123456-001 --task T-123456-001

# Close when fixed
trailmind issue close I-123456-001 --closer alice --status done --note "Fixed in PR #42"
```

## Inbox Triage

Capture ideas and reminders that aren't full tasks yet:

```sh
trailmind inbox add \
  --epic projects/myapp/mvp \
  --author alice \
  --title "Consider OAuth" \
  --note "Maybe add Google login for v2"

# Later, resolve it
trailmind inbox resolve IN-20260703-001 \
  --resolver alice \
  --note "Filed task T-123456-005 for OAuth research"
```

## Milestones

```sh
trailmind milestone add \
  --epic projects/myapp/mvp \
  --title "Alpha" \
  --date 2026-07-15

trailmind milestone add \
  --epic projects/myapp/mvp \
  --title "Beta" \
  --date 2026-07-25
```

## Quick Reference

| Command | What it does |
|---------|-------------|
| `trailmind init` | Scaffold repo files |
| `trailmind roster add` | Add a developer |
| `trailmind project init` | Create a project |
| `trailmind epic init` | Create an epic |
| `trailmind task add` | Create a task |
| `trailmind task list` | List tasks |
| `trailmind task pickup` | Get task context for AI |
| `trailmind task set-status` | Change task status |
| `trailmind task close` | Mark task done |
| `trailmind issue add` | File an issue |
| `trailmind issue link` | Link issue to task |
| `trailmind issue close` | Close an issue |
| `trailmind inbox add` | Capture an idea |
| `trailmind inbox resolve` | Triage an inbox item |
| `trailmind milestone add` | Add a milestone |
| `trailmind plan breakdown` | Create tasks from a plan |
| `trailmind sweep` | Find ready/blocked/stale work |
| `trailmind status` | Generate dashboard |
| `trailmind serve` | Serve dashboard locally |
| `trailmind scan` | Security scan |

All `list` commands support `--json` for structured output.
