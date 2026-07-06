# TaskFlow — Trailmind Demo Project

This directory contains a complete example Trailmind project called **TaskFlow**,
a fictional collaborative task management app. It demonstrates all Trailmind
features with realistic data.

## Project Structure

```
projects/taskflow/
  PROJECT.md          # Project definition
  AGENTS.md           # Agent handoff instructions
  inbox/              # Project-level inbox items
  mvp/                # Epic: MVP Release
    EPIC.md
    tasks/            # Tasks with dependencies, deliverables, statuses
    issues/           # Issues with severities and linked tasks
    milestones/       # Milestones with dates
    inbox/            # Epic-level inbox items
    docs/
      specs/          # Design specs (with and without plans)
      plans/          # Implementation plans (with and without linked specs)
  auth/               # Epic: Authentication & Users
    EPIC.md
    tasks/            # Tasks with cross-epic dependencies
    issues/           # Carried issues from MVP
    milestones/
    inbox/
```

## What This Demo Shows

### Projects and Epics

- **TaskFlow** project with two epics: **MVP Release** and **Authentication & Users**
- Each epic has `AGENTS.md` with agent handoff instructions

### Tasks

| Task | Epic | Status | Priority | Due | Notes |
|------|------|--------|----------|-----|-------|
| Build Task List View | MVP | `ready` | high | 2026-07-10 | Design reviewed |
| Implement Task Create API | MVP | `done` | medium | 2026-07-08 | All deliverables completed |
| Add Task Detail Page | MVP | `created` | low | 2026-07-20 | Assigned to Alice |
| Wire Up Task Editing | MVP | `blocked` | medium | 2026-07-12 | Depends on API (done) |
| User Registration | Auth | `created` | critical | 2026-07-05 | Has activity log note |
| Login Session | Auth | `created` | high | 2026-07-08 | Depends on User Registration |

### Issues

| Issue | Epic | Severity | Owner | Status |
|-------|------|----------|-------|--------|
| Task list crashes on empty | MVP | high | alice | `done` (linked to task, fixed) |
| Create button disabled state unclear | MVP | low | bob | `open` (carried to Auth epic) |

### Milestones

- **Alpha** (2026-07-15) — MVP epic
- **Beta** (2026-07-25) — MVP epic
- **Auth Alpha** (2026-08-15) — Auth epic

### Inbox Items

- Project-level: "Evaluate deployment options"
- MVP epic-level: "Review accessibility" (resolved)
- Auth epic-level: "OAuth provider selection"

### Planning Artifacts

**Specs:**
- `task-notifications` — approved-for-spec, linked to implementation plan
- `task-search` — approved-for-spec, **no plan yet** (gap!)

**Plans:**
- `task-list-implementation` — completed, 3 generated tasks (1 done)
- `task-notifications-implementation` — in-progress, linked to spec
- `dashboard-improvements` — approved, **no linked spec** (gap!)

### Cross-Epic Features

- Issue "Create button disabled state unclear" was **carried** from MVP to Auth epic
- Task "Login Session" depends on "User Registration" (same epic)

## Try It Out

```sh
cd examples/demo_project

# View status
trailmind status --overview
trailmind status --project taskflow
trailmind status --epic projects/taskflow/mvp

# Repository statistics
trailmind stats
trailmind stats --json

# Sweep for blocked/stale/ready work
trailmind sweep --epic projects/taskflow/mvp
trailmind sweep --project taskflow

# List tasks with filters
trailmind task list
trailmind task list --status in_progress
trailmind task list --owner alice
trailmind task list --priority high
trailmind task list --overdue
trailmind task list --epic projects/taskflow/mvp --json

# Task workflow shortcuts
trailmind task start T-123456-001 --actor alice
trailmind task done T-123456-002 --actor alice

# Task management
trailmind task show T-123456-001
trailmind task set-priority T-654321-001 high --actor alice
trailmind task due T-123456-003 2026-07-15 --actor alice
trailmind task assign T-123456-003 bob --actor alice

# Issue management
trailmind issue list
trailmind issue show I-123456-001
trailmind issue assign I-654321-001 alice --actor bob
trailmind issue set-severity I-654321-001 medium --actor bob

# Pickup context for AI agents
trailmind task pickup T-123456-001
trailmind issue pickup I-123456-001

# Inbox
trailmind inbox list --project taskflow
trailmind inbox list --epic projects/taskflow/mvp
trailmind inbox show IN-20260702-001

# Planning artifacts
trailmind plan spec list --epic projects/taskflow/mvp
trailmind plan list --epic projects/taskflow/mvp
trailmind plan show projects/taskflow/mvp/docs/plans/2026-07-02-dashboard-improvements.md

# Plan breakdown (preview)
trailmind plan breakdown projects/taskflow/mvp/docs/plans/2026-07-02-task-notifications-implementation.md \
  --epic projects/taskflow/mvp \
  --filer alice@example.com \
  --owner alice@example.com

# Project/Epic state management
trailmind project set-status taskflow paused --actor alice
trailmind epic set-status projects/taskflow/mvp completed --actor alice

# Export/Import
trailmind export -o backup.json
trailmind import backup.json

# Diagnostics
trailmind doctor
trailmind doctor --json

# Security scan
trailmind scan

# Serve dashboard
trailmind serve --port 8888
```

## Roster

| Name | Email | Shortname | UID |
|------|-------|-----------|-----|
| Alice Example | alice@example.com | alice | 123456 |
| Bob Example | bob@example.com | bob | 654321 |
