# Changelog

All notable changes to Trailmind are documented here.

## [Unreleased]

### Added
- `trailmind init` command for repo scaffolding (roster.yaml, CI, templates)
- `trailmind task list` with `--json` support
- `trailmind issue list` with `--json` support
- `trailmind milestone list` with `--json` support
- `trailmind project list` with `--json` support
- `trailmind epic list` with `--json` support
- `trailmind sweep --json` for structured output
- `trailmind inbox list --json` for structured output
- `trailmind roster list --json` for structured output
- Planning artifact management: `plan spec init/list/show/set-status`
- Planning artifact management: `plan init/list/show/set-status/link-spec`
- `plan status` command showing spec→plan→tasks relationships and gaps
- Epic dashboard now shows Planning section (Specs + Plans tables)
- Project dashboard shows spec/plan counts per epic
- `plan breakdown --write` auto-updates `generated_tasks` on source plan
- Complete demo project at `examples/demo_project/`
- `CONTRIBUTING.md` contribution guide
- `docs/github-workflow.md` GitHub integration guide
- `docs/planning-workflow.md` planning workflow showcase
- `docs/migration-guide.md` upgrade and migration guide
- `docs/release-checklist.md` release process checklist
- GitHub Actions CI workflow reference
- PR and Issue templates

### Changed
- `plan breakdown` now uses `--filer` and `--owner` flags (was positional)

### Fixed
- Sweep report handles tasks with missing frontmatter gracefully
- Inbox resolve rejects non-inbox direct paths

## [v0.4.0] - 2026-06-29

### Added
- `trailmind plan breakdown` — create tasks from implementation plans
- Plan task parser with `### Task N: Title` sections
- File entries extraction (Create/Modify/Test/Note)
- Step extraction from checklists
- Verification command extraction from fenced bash blocks
- Commit message extraction
- `--write` flag to actually create tasks (preview by default)
- `--force` flag to re-create tasks from a plan
- `--filer` and `--owner` options for task assignment
- `--json` output for breakdown report
- `docs/v0.4-plan-breakdown.md` detailed guide

### Changed
- Tasks created by breakdown include `source_plan`, `source_task`, `source_heading` frontmatter

## [v0.3.0] - 2026-06-28

### Added
- `trailmind task pickup` — bounded context for AI agent handoff
- `trailmind issue pickup` — same for issues
- `--json` output for pickup packs
- `--log` flag to record pickup in activity log
- `--max-lines` for code excerpt length control
- `--actor` for pickup log attribution
- Pickup pack includes: summary, dependencies, deliverables, linked issues, recent activity, relevant file excerpts, next actions, warnings
- `docs/v0.3-agent-handoff.md` detailed guide

### Changed
- `trailmind task update` renamed to `trailmind task set-status` (old name kept as alias)

## [v0.2.0] - 2026-06-27

### Added
- Task dependencies: `depends_on` (hard) and `soft_depends_on` (soft)
- Task deliverables: `deliverables` and `completed_deliverables`
- Deliverable management: `task deliverable add/complete`
- Inbox items at project and epic scope: `inbox add/list/resolve`
- `trailmind sweep` — report ready/blocked/stale/missing work
- Task status state machine with validation
- `task normalize-statuses` for legacy status migration
- `task set-status` with actor and note for activity log
- Dependency gates prevent invalid status transitions
- Deliverable gates prevent closing tasks with incomplete deliverables
- `docs/v0.2-project-automation.md` detailed guide

### Changed
- Task statuses now use a formal state machine
- `task update --status` is deprecated, use `task set-status`

## [v0.1.0] - 2026-06-26

### Added
- Project and Epic initialization
- Task, Issue, and Milestone CRUD
- Activity logging on all entities
- YAML frontmatter + Markdown body storage
- HTML dashboard generation (overview, project, epic)
- `trailmind serve` local dashboard server
- `trailmind scan` security and release scan
- `AGENTS.md` generation for AI agent handoff
- `roster.yaml` developer registry
- Git safety helpers
