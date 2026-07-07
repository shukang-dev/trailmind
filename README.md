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
trailmind task set-status T-123456-001 ready --actor alice
trailmind task next --owner alice

trailmind status --overview
trailmind status --project demo_app
trailmind status --epic projects/demo_app/mvp

trailmind tree
trailmind activity --limit 10
trailmind search "login" --type task

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

Trailmind includes workflow helpers for task status changes, dependencies,
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
  --deliverables "tests pass,docs updated" \
  --priority high

trailmind task set-status T-123456-003 ready --actor alice --note "Ready to start."
trailmind task start T-123456-003 --actor alice
trailmind task done T-123456-003 --actor alice --note "Shipped."
trailmind task reopen T-123456-003 --actor alice

trailmind task depend add T-123456-003 T-123456-004 --actor alice
trailmind task depend remove T-123456-003 T-123456-004 --actor alice
trailmind task move T-123456-003 projects/demo_app/other_epic --actor alice

trailmind task deliverable add T-123456-003 --item "docs updated" --actor alice
trailmind task deliverable complete T-123456-003 --item "docs updated" --actor alice

trailmind task list --sort priority --group-by status --compact
trailmind task next --owner alice

trailmind inbox add --epic projects/demo_app/mvp --author alice --title "Review release checklist" --note "Confirm before release."
trailmind inbox list --epic projects/demo_app/mvp
trailmind inbox resolve IN-20260630-001 --resolver alice --note "Filed a follow-up task."

trailmind issue move I-123456-001 projects/demo_app/other_epic --actor alice

trailmind activity --type task --since 2026-07-01
trailmind search "login" --type task,issue
trailmind tree
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

## Plan Breakdown

Trailmind can preview and create task drafts from an approved implementation plan:

```sh
trailmind plan breakdown docs/plans/v0.4.md \
  --epic projects/demo_app/mvp \
  --filer alice@example.com \
  --owner alice@example.com

trailmind plan breakdown docs/plans/v0.4.md \
  --epic projects/demo_app/mvp \
  --filer alice@example.com \
  --owner alice@example.com \
  --write
```

Preview is read-only by default. See `docs/v0.4-plan-breakdown.md` for details.

## Planning Artifacts

Trailmind can manage spec and plan artifacts with formal frontmatter and CLI commands:

```sh
trailmind plan spec init --epic projects/demo_app/mvp --title "Parser Redesign" --author alice@example.com
trailmind plan init --epic projects/demo_app/mvp --title "Implementation" --author alice@example.com --spec docs/specs/2026-07-02-parser-redesign.md
trailmind plan spec list --epic projects/demo_app/mvp
trailmind plan list --epic projects/demo_app/mvp
```

See `docs/v0.4-planning-artifacts.md` for details.

See `docs/planning-workflow.md` for a complete walkthrough of the spec → plan → tasks workflow.

See `docs/github-workflow.md` for a guide to using Trailmind with GitHub CI, PRs, and project boards.

See `docs/migration-guide.md` for upgrade instructions between versions. See `CHANGELOG.md` for release notes.

## Example Project

A complete demo project is available at
[`examples/demo_project/`](examples/demo_project/README.md) with projects,
epics, tasks, issues, milestones, inbox items, and planning artifacts.

```sh
cd examples/demo_project
trailmind status --overview
trailmind sweep --project taskflow
trailmind task pickup projects/taskflow/mvp/tasks/T-123456-001-build-task-list-view.md
trailmind serve --port 8888
```

## Features

- Project, Epic, Task, Issue, Milestone, and Inbox records stored as Markdown.
- YAML frontmatter for structured state and Markdown bodies for context.
- Activity Logs appended to tracked records for durable history.
- Task dependencies through `depends_on`, `soft_depends_on`, and linked issues.
- Full CRUD: every entity supports `add`, `list`, `show`, `edit`, and status transitions.
- `task next` — see the most actionable tasks sorted by priority and due date.
- `task move` / `issue move` — relocate tasks and issues between epics.
- `task depend add/remove` — manage hard and soft dependencies after creation.
- `task reopen` / `issue reopen` — bring closed items back to active state.
- Rich list views: `--sort`, `--group-by`, `--compact`, `--csv`, `--project` filters.
- `activity` — cross-entity activity log with type, actor, and date filters.
- `search` — keyword search across all entities with type filtering.
- `tree` — project structure overview with entity counts.
- Generated dashboard HTML for overview, project, and epic scopes with navigation,
  breadcrumbs, progress bars, status badges, dark mode, and responsive layout.
- Local dashboard server (`trailmind serve`) with a generated index page linking
  all projects and epics.
- Library-level Git safety helpers that stage and commit only requested paths.
- Release scan for non-example emails, sensitive environment files, token-like
  text, and blocked release markers.
- Generated `AGENTS.md` protocol files for human and AI agent handoff.
- Spec and Plan artifacts with formal frontmatter and workflow commands.
- Plan breakdown: preview and create task drafts from approved implementation plans.
- Agent pickup context for bounded task/issue handoff.

## Command Reference

### Projects & Epics

```sh
trailmind project init --slug demo --title "Demo" --goal "Build."
trailmind project list
trailmind project show demo
trailmind project edit demo --title "New" --goal "Updated." --owners alice --tags tag1,tag2
trailmind project set-status demo active --actor alice

trailmind epic init --project demo --slug mvp --title "MVP" --goal "Ship." --roster alice --repos demo
trailmind epic list --project demo
trailmind epic show projects/demo/mvp
trailmind epic edit projects/demo/mvp --title "New" --target 2026-08-15 --roster alice,bob
trailmind epic set-status projects/demo/mvp completed --actor alice
```

### Tasks

```sh
trailmind task add --epic projects/demo/mvp --filer alice@example.com --owner alice@example.com --title "Build it" --priority high
trailmind task list --sort priority --group-by status --compact
trailmind task list --project demo --owner alice --csv
trailmind task show T-123456-001
trailmind task edit T-123456-001 --title "New" --code-paths src/app.py
trailmind task set-status T-123456-001 ready --actor alice
trailmind task start T-123456-001 --actor alice
trailmind task done T-123456-001 --actor alice
trailmind task reopen T-123456-001 --actor alice
trailmind task due T-123456-001 2026-08-01 --actor alice
trailmind task due T-123456-001 --clear --actor alice
trailmind task assign T-123456-001 bob --actor alice
trailmind task priority T-123456-001 critical --actor alice
trailmind task next --owner alice --limit 5
trailmind task depend add T-123456-001 T-123456-002 --actor alice
trailmind task depend add T-123456-001 T-123456-003 --soft --actor alice
trailmind task depend remove T-123456-001 T-123456-002 --actor alice
trailmind task move T-123456-001 projects/demo/other_epic --actor alice
trailmind task deliverable add T-123456-001 --item "tests pass" --actor alice
trailmind task deliverable complete T-123456-001 --item "tests pass" --actor alice
```

### Issues

```sh
trailmind issue add --epic projects/demo/mvp --filer alice@example.com --title "Bug" --description "Details" --severity high
trailmind issue list --sort severity --group-by owner --compact
trailmind issue list --project demo --csv
trailmind issue show I-123456-001
trailmind issue edit I-123456-001 --title "New" --description "Updated"
trailmind issue assign I-123456-001 bob --actor alice
trailmind issue set-severity I-123456-001 critical --actor alice
trailmind issue close I-123456-001 --actor alice
trailmind issue reopen I-123456-001 --actor alice
trailmind issue move I-123456-001 projects/demo/other_epic --actor alice
trailmind issue link --issue I-123456-001 --task T-123456-001
```

### Milestones & Inbox

```sh
trailmind milestone add --epic projects/demo/mvp --title "Alpha" --date 2026-08-01
trailmind milestone list
trailmind milestone show M-001
trailmind milestone edit M-001 --title "Beta" --date 2026-09-01 --status done --actor alice

trailmind inbox add --epic projects/demo/mvp --author alice --title "Review" --note "Check before release"
trailmind inbox list --epic projects/demo/mvp
trailmind inbox show IN-20260702-001
trailmind inbox edit IN-20260702-001 --title "Updated" --actor alice
trailmind inbox resolve IN-20260702-001 --resolver alice --note "Done"
```

### Discovery & Reporting

```sh
trailmind tree                                    # project structure with entity counts
trailmind activity --limit 20 --type task         # recent activity across entities
trailmind search "dashboard" --type task,issue    # keyword search
trailmind stats                                   # repository statistics
trailmind sweep --project demo                    # PMO health check
trailmind scan                                    # security scan before release
trailmind doctor                                  # diagnose common issues
```

### Dashboards

```sh
trailmind status --overview                       # render overview dashboard
trailmind status --project demo                   # render project dashboard
trailmind status --epic projects/demo/mvp        # render epic dashboard
trailmind serve --port 8888                       # serve dashboards with index page
```

### Plans & Specs

```sh
trailmind plan spec init --epic projects/demo/mvp --title "Parser" --author alice
trailmind plan init --epic projects/demo/mvp --title "Implementation" --author alice --spec docs/specs/parser.md
trailmind plan breakdown docs/plans/impl.md --epic projects/demo/mvp --filer alice --owner alice
trailmind plan breakdown docs/plans/impl.md --epic projects/demo/mvp --filer alice --owner alice --write
```

### Agent Handoff

```sh
trailmind task pickup T-123456-001                # read-only pickup context
trailmind task pickup T-123456-001 --log --actor alice
trailmind issue pickup I-123456-001
```

## License

Trailmind is released under the [MIT License](LICENSE).
