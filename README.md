# Trailmind

[中文说明](README.zh-CN.md)

Trailmind is a Markdown-backed project tracker and AI agent handoff tool. It
keeps project state in ordinary repository files so humans and AI agents can
inspect, review, diff, and update work without a separate service.

Trailmind is a clean-room open-source implementation. The repository is intended
to contain no private code, private fixtures, organization-specific
integrations, internal service names, or proprietary examples.

## Current Version: v1.0+

Trailmind v1.0 is released and actively iterating. The CLI covers full CRUD
across all entity types with rich filtering, grouping, and reporting.

## How It Works

Markdown files with YAML frontmatter are the source of truth. Projects, epics,
tasks, issues, milestones, inbox items, specs, and plans are stored as readable
`.md` files under `projects/`, with structured fields in frontmatter and
narrative context in the body.

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
```

Create a project, an epic, and a task:

```sh
trailmind project init \
  --slug demo_app \
  --title "Demo App" \
  --goal "Build a useful demo."

trailmind epic init \
  --project demo_app \
  --slug mvp \
  --title "MVP" \
  --goal "First usable release" \
  --roster alice \
  --repos demo_app

trailmind task add \
  --epic projects/demo_app/mvp \
  --filer alice@example.com \
  --owner alice@example.com \
  --title "Build Login Flow" \
  --priority high \
  --tags frontend,auth \
  --code-paths "src/app.py,tests/test_app.py"
```

Update work and view dashboards:

```sh
trailmind task set-status T-123456-001 ready --actor alice
trailmind task start T-123456-001 --actor alice
trailmind task done T-123456-001 --actor alice --note "Shipped."

trailmind task next --owner alice          # what should I work on?
trailmind task list --active --compact     # all active tasks
trailmind task list --due-within 7         # due this week
trailmind task list --blocked              # what's stuck
trailmind task list --group-by epic        # organized by epic

trailmind tree                              # project structure
trailmind stats                             # repository statistics
trailmind activity --limit 10               # recent activity
trailmind search "login" --type task        # keyword search
```

Issues, milestones, and inbox:

```sh
trailmind issue add \
  --epic projects/demo_app/mvp \
  --filer alice@example.com \
  --title "Login Fails" \
  --description "Users cannot sign in." \
  --severity high

trailmind issue list --active --sort severity
trailmind issue comment I-123456-001 --author alice --text "Reproduced in v0.3"

trailmind milestone add --epic projects/demo_app/mvp --title "Beta" --date 2026-08-15
trailmind milestone set-status M-001 done --actor alice

trailmind inbox add --epic projects/demo_app/mvp --author alice --title "Review deploy"
trailmind inbox list --status open
```

Dashboards and serving:

```sh
trailmind status --overview
trailmind status --project demo_app
trailmind status --epic projects/demo_app/mvp

trailmind serve --host 127.0.0.1 --port 8888
```

Export and scan:

```sh
trailmind export --format json -o backup.json
trailmind export --format csv -o data.csv
trailmind scan
trailmind sweep --project demo_app
```

## Command Reference

### Projects

```sh
trailmind project init --slug demo --title "Demo" --goal "Build."
trailmind project list [--active]
trailmind project show demo
trailmind project edit demo --title "New" --goal "Updated." --owners alice --tags tag1,tag2
trailmind project set-status demo active --actor alice
```

### Epics

```sh
trailmind epic init --project demo --slug mvp --title "MVP" --goal "Ship." --roster alice --repos demo
trailmind epic list [--project demo] [--active]
trailmind epic show projects/demo/mvp
trailmind epic edit projects/demo/mvp --title "New" --target 2026-08-15 --roster alice,bob
trailmind epic set-status projects/demo/mvp completed --actor alice
```

### Tasks

```sh
# Create and view
trailmind task add --epic projects/demo/mvp --filer alice --owner alice --title "Build" --priority high --tags frontend
trailmind task list [--epic ...] [--project ...] [--status ...] [--owner ...] [--priority ...]
                    [--due-before ...] [--due-after ...] [--due-within N] [--due-today] [--overdue]
                    [--has-due | --no-due] [--tag ...] [--has-deliverables] [--has-deps]
                    [--active] [--blocked] [--ready-only] [--in-progress]
                    [--sort created|priority|due|status|title]
                    [--group-by status|owner|priority|epic|project|tag]
                    [--compact] [--csv] [--json] [--limit N]
trailmind task show T-123456-001
trailmind task edit T-123456-001 --title "New" --code-paths src/app.py --design-doc docs/design.md --tags backend,api

# Status transitions
trailmind task set-status T-123456-001 ready --actor alice
trailmind task start T-123456-001 --actor alice
trailmind task done T-123456-001 --actor alice [--note "Done."]
trailmind task reopen T-123456-001 --actor alice

# Assignment and metadata
trailmind task assign T-123456-001 bob --actor alice
trailmind task priority T-123456-001 critical --actor alice
trailmind task due T-123456-001 2026-08-01 --actor alice
trailmind task due T-123456-001 --clear --actor alice

# Dependencies
trailmind task depend add T-123456-001 T-123456-002 --actor alice
trailmind task depend add T-123456-001 T-123456-003 --soft --actor alice
trailmind task depend remove T-123456-001 T-123456-002 --actor alice

# Deliverables
trailmind task deliverable add T-123456-001 --item "tests pass" --actor alice
trailmind task deliverable complete T-123456-001 --item "tests pass" --actor alice

# Tags
trailmind task tag add T-123456-001 frontend --actor alice
trailmind task tag remove T-123456-001 ui --actor alice

# Move, clone, bulk
trailmind task move T-123456-001 projects/demo/other_epic --actor alice
trailmind task clone T-123456-001 --actor alice [--title "New"] [--owner bob] [--to-epic ...]
trailmind task bulk-status T-001 T-002 T-003 ready --actor alice

# Comments
trailmind task comment T-123456-001 --author alice --text "Looking good!"

# Next actions
trailmind task next [--owner alice] [--project demo] [--epic ...] [--tag ...] [--limit 5]
```

### Issues

```sh
# Create and view
trailmind issue add --epic projects/demo/mvp --filer alice --title "Bug" --description "Details" --severity high
trailmind issue list [--epic ...] [--project ...] [--status ...] [--severity ...] [--owner ...]
                     [--active] [--sort created|severity|status|title]
                     [--group-by status|severity|owner|epic|project]
                     [--compact] [--csv] [--json] [--limit N]
trailmind issue show I-123456-001
trailmind issue edit I-123456-001 --title "New" --description "Updated"

# Status
trailmind issue assign I-123456-001 bob --actor alice
trailmind issue set-severity I-123456-001 critical --actor alice
trailmind issue close I-123456-001 --actor alice
trailmind issue reopen I-123456-001 --actor alice

# Move, clone, link, comment
trailmind issue move I-123456-001 projects/demo/other --actor alice
trailmind issue clone I-123456-001 --actor alice [--title "New"] [--owner bob] [--to-epic ...]
trailmind issue link --issue I-123456-001 --task T-123456-001
trailmind issue comment I-123456-001 --author alice --text "Investigating"
```

### Milestones

```sh
trailmind milestone add --epic projects/demo/mvp --title "Alpha" --date 2026-08-01
trailmind milestone list [--epic ...] [--project ...] [--status ...] [--active]
                         [--sort date|created|status|title] [--limit N] [--json]
trailmind milestone show M-001
trailmind milestone edit M-001 --title "Beta" --date 2026-09-01 --status done --actor alice
trailmind milestone set-status M-001 done --actor alice
```

### Inbox

```sh
trailmind inbox add --epic projects/demo/mvp --author alice --title "Review deploy" --note "Check before release."
trailmind inbox list [--project demo] [--epic ...] [--status open|resolved] [--limit N] [--json]
trailmind inbox show IN-20260702-001
trailmind inbox edit IN-20260702-001 --title "Updated" --actor alice
trailmind inbox resolve IN-20260702-001 --resolver alice --note "Done"
```

### Discovery & Reporting

```sh
trailmind tree                                    # project structure with entity counts
trailmind activity [--type task] [--actor alice] [--since 2026-07-01]
                  [--project demo] [--epic projects/demo/mvp] [--limit 20]
trailmind search "keyword" [--type task,issue]    # cross-entity keyword search
trailmind stats                                    # repository statistics
trailmind sweep [--project demo] [--epic ...]      # PMO health check
trailmind scan                                     # security scan before release
trailmind doctor                                   # diagnose common issues
```

### Dashboards

```sh
trailmind status --overview                        # render overview dashboard
trailmind status --project demo                    # render project dashboard
trailmind status --epic projects/demo/mvp          # render epic dashboard
trailmind serve --host 127.0.0.1 --port 8888       # serve dashboards with index page
```

### Plans & Specs

```sh
trailmind plan spec init --epic projects/demo/mvp --title "Parser Redesign" --author alice
trailmind plan init --epic projects/demo/mvp --title "Implementation" --author alice --spec docs/specs/parser.md
trailmind plan spec list --epic projects/demo/mvp
trailmind plan list --epic projects/demo/mvp
trailmind plan breakdown docs/plans/impl.md --epic projects/demo/mvp --filer alice --owner alice
trailmind plan breakdown docs/plans/impl.md --epic projects/demo/mvp --filer alice --owner alice --write
```

### Import & Export

```sh
trailmind export --format json -o backup.json
trailmind export --format csv -o data.csv
trailmind import backup.json [--force]
```

### Agent Handoff

```sh
trailmind task pickup T-123456-001                  # read-only pickup context
trailmind task pickup T-123456-001 --log --actor alice
trailmind issue pickup I-123456-001
```

## Task List Filter Cheat Sheet

| Flag | Purpose |
|------|---------|
| `--epic PATH` | Filter by epic |
| `--project SLUG` | Filter by project |
| `--status STATUS` | Filter by status |
| `--owner NAME` | Filter by owner |
| `--priority LEVEL` | Filter by priority |
| `--active` | Exclude done/wontfix |
| `--blocked` | Only blocked tasks |
| `--ready-only` | Only ready/created tasks |
| `--in-progress` | Only in-progress tasks |
| `--overdue` | Overdue tasks only |
| `--due-within N` | Due in next N days |
| `--due-today` | Due today (shortcut) |
| `--due-before DATE` | Due before date |
| `--due-after DATE` | Due after date |
| `--has-due` / `--no-due` | Has/hasn't a due date |
| `--tag NAME` | Filter by tag |
| `--has-deliverables` | Has deliverables defined |
| `--has-deps` | Has dependencies |
| `--sort FIELD` | Sort by field |
| `--group-by FIELD` | Group by field |
| `--compact` | Single-line output |
| `--csv` / `--json` | Machine-readable output |
| `--limit N` | Limit results |

## Features

- Full CRUD for Projects, Epics, Tasks, Issues, Milestones, Inbox, Specs, and Plans.
- YAML frontmatter for structured state and Markdown bodies for narrative context.
- Activity Logs appended to tracked records for durable history.
- Comments on tasks and issues with author and timestamp.
- Tag system on tasks with add/remove and filtering.
- Task dependencies (hard and soft) with dependency gating on status transitions.
- Deliverables tracking with completion markers.
- Rich list filtering: 30+ filter combinations across status, owner, priority, due date, tags, deliverables, dependencies.
- Group-by views: status, owner, priority, epic, project, tag.
- `task next` — most actionable tasks sorted by priority and due date.
- `task bulk-status` — batch status updates.
- `task clone` and `issue clone` — duplicate preserving metadata.
- `task move` and `issue move` — relocate between epics.
- Cross-entity `activity` log with type, actor, project, epic, and date filtering.
- `search` — keyword search across all entities.
- `tree` — project structure overview with entity counts.
- `stats` — repository statistics with completion progress, overdue, and upcoming counts.
- `sweep` — PMO health check.
- `scan` — security scan for sensitive data.
- Generated dashboard HTML with navigation, breadcrumbs, progress bars, dark mode, and responsive layout.
- Local dashboard server with auto-generated index page.
- Export to JSON and CSV formats.
- Generated `AGENTS.md` protocol files for human and AI agent handoff.
- Plan breakdown: preview and create task drafts from approved implementation plans.
- Agent pickup context for bounded task/issue handoff.

## License

Trailmind is released under the [MIT License](LICENSE).
