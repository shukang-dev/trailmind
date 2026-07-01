# Trailmind

[中文说明](README.zh-CN.md)

Trailmind is a Markdown-backed project tracker and AI agent handoff tool. It
keeps project state in ordinary repository files so humans and AI agents can
inspect, review, diff, and update work without a separate service.

Trailmind is a clean-room open-source implementation. The repository is intended
to contain no private code, private fixtures, organization-specific
integrations, internal service names, or proprietary examples.

## How It Works

Markdown files with YAML frontmatter are the source of truth. Projects, epics,
tasks, issues, and milestones are stored as readable `.md` files under
`projects/`, with structured fields in frontmatter and narrative context in the
body.

Trailmind is designed for human and AI agent collaboration. Project and epic
creation generate `AGENTS.md` protocol files that describe local handoff rules,
expected context, and safe operating boundaries for agents working in the repo.

## Quick Start

Install Trailmind from a checkout:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Create a demo repository and add a public fixture user:

```sh
mkdir demo-trailmind
cd demo-trailmind
git init

trailmind roster add \
  --email alice@example.com \
  --shortname alice \
  --name "Alice Example" \
  --uid 123456

trailmind roster list
```

Create a project, an epic, and a task:

```sh
trailmind project init \
  --slug demo_app \
  --title "Demo App" \
  --goal "Build a useful demo." \
  --owners alice@example.com \
  --tags demo,agent

trailmind epic init \
  --project demo_app \
  --slug mvp \
  --title "MVP" \
  --goal "First usable release" \
  --start 2026-06-29 \
  --target 2026-07-15 \
  --roster alice \
  --repos demo_app

trailmind task add \
  --epic projects/demo_app/mvp \
  --filer alice@example.com \
  --owner alice@example.com \
  --title "Build Login Flow" \
  --code-paths "src/app.py,tests/test_app.py"
```

Update work, render dashboards, and serve them locally:

```sh
trailmind log T-123456-001 --author alice --note "Started implementation."
trailmind task update T-123456-001 --status in_progress

trailmind status --overview
trailmind status --project demo_app
trailmind status --epic projects/demo_app/mvp

trailmind serve --host 127.0.0.1 --port 8888
```

Optional issue and milestone records:

```sh
trailmind issue add \
  --epic projects/demo_app/mvp \
  --filer alice@example.com \
  --title "Login Fails" \
  --description "Users cannot sign in." \
  --severity high

trailmind issue link --issue I-123456-001 --task T-123456-001

trailmind milestone add \
  --epic projects/demo_app/mvp \
  --title "Beta Freeze" \
  --date 2026-07-15
```

Run the release scan:

```sh
trailmind scan
```

## Project Automation

Trailmind v0.2 includes workflow helpers for task status changes, dependencies,
deliverables, inbox triage, and sweep reports. See the
[v0.2 Project Automation guide](docs/v0.2-project-automation.md) for details.

```sh
trailmind task add \
  --epic projects/demo_app/mvp \
  --filer alice@example.com \
  --owner alice@example.com \
  --title "Build Sign-In Form" \
  --depends-on T-123456-001 \
  --soft-depends-on T-123456-002 \
  --known-issues I-123456-001 \
  --deliverables "tests pass,docs updated"

trailmind task set-status T-123456-003 ready --actor alice --note "Ready to start."
trailmind task normalize-statuses
trailmind task normalize-statuses --write

trailmind task deliverable add T-123456-003 --item "docs updated" --actor alice
trailmind task deliverable complete T-123456-003 --item "docs updated" --actor alice

trailmind inbox add --epic projects/demo_app/mvp --author alice --title "Review release checklist" --note "Confirm before release."
trailmind inbox list --epic projects/demo_app/mvp
trailmind inbox resolve IN-20260630-001 --resolver alice --note "Filed a follow-up task."

trailmind sweep --epic projects/demo_app/mvp
```

## Agent Handoff

Trailmind can produce bounded pickup context for a task or issue:

```sh
trailmind task pickup T-123456-001
trailmind task pickup T-123456-001 --json
trailmind issue pickup I-123456-001
trailmind issue pickup I-123456-001 --log --actor alice
```

Pickup is read-only by default. See `docs/v0.3-agent-handoff.md` for details.

## Features

- Project, Epic, Task, Issue, and Milestone records stored as Markdown.
- YAML frontmatter for structured state and Markdown bodies for context.
- Activity Logs appended to tracked records for durable history.
- Task dependencies through `depends_on`, `soft_depends_on`, and linked issues.
- Generated dashboard HTML for overview, project, and epic scopes.
- Local dashboard server with `trailmind serve`.
- Library-level Git safety helpers that stage and commit only requested paths.
- Release scan for non-example emails, sensitive environment files, token-like
  text, and blocked release markers.
- Generated `AGENTS.md` protocol files for human and AI agent handoff.

## License

Trailmind is released under the [MIT License](LICENSE).
