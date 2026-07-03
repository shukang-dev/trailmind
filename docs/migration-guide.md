# Migration Guide

How to upgrade Trailmind and adapt to schema changes.

## v0.4 → v0.5

No breaking schema changes. New features are additive:

- `trailmind init` for repo scaffolding
- `trailmind task list`, `issue list`, `milestone list`, `project list`, `epic list` commands
- `--json` output on `sweep`, `inbox list`, `roster list`
- Planning artifacts (specs and plans) in `docs/specs/` and `docs/plans/`

## v0.3 → v0.4

### Plan Breakdown

New `trailmind plan breakdown` command creates tasks from implementation plans.

**To use:**
1. Write a plan Markdown file with `### Task N: Title` sections
2. Run `trailmind plan breakdown path/to/plan.md --epic projects/myapp/mvp --filer alice@example.com --owner alice@example.com`
3. Preview first (read-only), then add `--write` to create tasks

### Task Frontmatter Additions

New optional fields on tasks:
- `source_plan` — path to the plan that generated this task
- `source_task` — task number in the plan
- `source_heading` — task title from the plan

These are set automatically by `plan breakdown --write`.

## v0.2 → v0.3

### Agent Handoff

New `trailmind task pickup` and `trailmind issue pickup` commands generate bounded context for AI agents.

**New files:**
- `src/trailmind/pickup.py` — pickup pack builder
- `docs/v0.3-agent-handoff.md` — detailed guide

### Task Status Normalization

`trailmind task normalize-statuses` normalizes legacy status values:
- `open` → `created`
- `in progress` → `in_progress`
- `closed` → `done`

Run `trailmind task normalize-statuses --write` to update all tasks.

## v0.1 → v0.2

### Project Automation

New workflow helpers:
- Task dependencies (`depends_on`, `soft_depends_on`)
- Task deliverables (`deliverables`, `completed_deliverables`)
- Inbox items (`projects/*/inbox/`, `projects/*/*/inbox/`)
- Sweep report (`trailmind sweep`)
- Task status state machine (`created → ready → in_progress → done`)

### Task Frontmatter Changes

New required fields default to empty when missing:
- `depends_on: []`
- `soft_depends_on: []`
- `deliverables: []`
- `completed_deliverables: []`
- `known_issues: []`

No migration needed — `task add` and `task update` handle defaults.

### New Directories

Epic creation now creates these subdirectories:
```
projects/<project>/<epic>/
  inbox/          # inbox items
  tasks/          # tasks
  issues/         # issues
  milestones/     # milestones
  docs/
    specs/        # design specs
    plans/        # implementation plans
```

Existing epics don't need these directories — they're created on demand.

## General Upgrade Steps

1. **Install the new version:**
   ```sh
   pip install --upgrade trailmind
   # or
   git pull && pip install -e ".[dev]"
   ```

2. **Run the security scan:**
   ```sh
   trailmind scan
   ```

3. **Run tests (if you have a test suite):**
   ```sh
   python -m pytest -v
   ```

4. **Normalize task statuses (v0.2 → v0.3):**
   ```sh
   trailmind task normalize-statuses --write
   ```

5. **Regenerate dashboards:**
   ```sh
   trailmind status --overview
   ```

6. **Check for stale/blocked work:**
   ```sh
   trailmind sweep
   ```

## Getting Help

If you encounter issues during migration:
1. Check the relevant `docs/v0.X-*.md` file
2. Run `trailmind scan` to catch common problems
3. File an issue on GitHub with the error output
