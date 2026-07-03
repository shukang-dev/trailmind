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

| Task | Epic | Status | Notes |
|------|------|--------|-------|
| Build Task List View | MVP | `ready` | Ready to start, design reviewed |
| Implement Task Create API | MVP | `done` | All deliverables completed |
| Add Task Detail Page | MVP | `created` | Assigned to Bob |
| Wire Up Task Editing | MVP | `blocked` | Depends on API (done), soft-depends on detail page |
| User Registration | Auth | `created` | Has activity log note |
| Login Session | Auth | `created` | Depends on User Registration |

### Issues

| Issue | Epic | Severity | Status |
|-------|------|----------|--------|
| Task list crashes on empty | MVP | high | `done` (linked to task, fixed) |
| Create button disabled state unclear | MVP | low | `open` (carried to Auth epic) |

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

# Sweep for blocked/stale/ready work
trailmind sweep --epic projects/taskflow/mvp
trailmind sweep --project taskflow

# List tasks, issues, milestones
trailmind task pickup T-123456-001
trailmind issue pickup I-123456-001

# Inbox
trailmind inbox list --project taskflow
trailmind inbox list --epic projects/taskflow/mvp

# Plan breakdown (preview)
trailmind plan breakdown projects/taskflow/mvp/docs/plans/2026-07-02-task-notifications-implementation.md \
  --epic projects/taskflow/mvp \
  --filer alice@example.com \
  --owner alice@example.com

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
