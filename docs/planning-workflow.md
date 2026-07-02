# Planning Workflow Showcase

This document walks through a complete Trailmind planning workflow, from
idea to tracked tasks.

## Overview

Trailmind supports a full planning lifecycle:

```
Idea → Spec → Plan → Tasks → Status → Done
```

Each step produces a Markdown artifact with YAML frontmatter. Links between
artifacts are recorded in frontmatter for traceability.

## Step 1: Create a Project and Epic

```sh
trailmind project init \
  --slug taskflow \
  --title "TaskFlow" \
  --goal "Build a collaborative task management app." \
  --owners alice@example.com \
  --tags demo,webapp

trailmind epic init \
  --project taskflow \
  --slug mvp \
  --title "MVP Release" \
  --goal "First usable release with core task management" \
  --start 2026-07-01 \
  --target 2026-07-31 \
  --roster alice,bob \
  --repos taskflow
```

## Step 2: Write a Design Spec

Create a spec file at `projects/taskflow/mvp/docs/specs/`:

```markdown
---
title: Task Notifications
status: draft-for-review
created: '2026-07-02'
scope: mvp
project: taskflow
epic: mvp
linked_plans: []
---

# Task Notifications

## Purpose

Users should receive notifications when tasks are assigned, completed,
or commented on.

## Goals

- In-app notification feed
- Email notifications for important events

## Non-Goals

- Push notifications (mobile)
- Third-party integrations

## Design

Use a notification service that subscribes to task events. Each user has a
notification preferences record.
```

### Spec Statuses

| Status | When to use |
| --- | --- |
| `draft-for-review` | Initial draft, seeking review |
| `approved-for-spec` | Spec approved; plan can be written |
| `approved-for-implementation` | Spec and plan approved; implementation can begin |
| `superseded` | Replaced by a newer spec |

## Step 3: Write an Implementation Plan

Create a plan file at `projects/taskflow/mvp/docs/plans/`:

```markdown
---
title: Task Notifications Implementation
status: draft
created: '2026-07-02'
scope: mvp
project: taskflow
epic: mvp
linked_spec: docs/specs/2026-07-02-task-notifications.md
generated_tasks: []
---

# Task Notifications Implementation

## Scope

Implement in-app notification feed and email notifications.

## Architecture

- `NotificationService` class with event handlers
- `NotificationPreference` model per user
- Email backend interface with SMTP implementation

### Task 1: Notification Model and Storage

**Files:**
- Create: `src/models/notification.py`
- Create: `src/services/notification_service.py`
- Test: `tests/test_notification.py`

- [ ] **Step 1: Define notification types and model**
- [ ] **Step 2: Implement in-memory storage**
- [ ] **Step 3: Write service tests**

### Task 2: Email Backend

**Files:**
- Create: `src/email/smtp_backend.py`
- Test: `tests/test_email.py`

- [ ] **Step 1: Define EmailBackend interface**
- [ ] **Step 2: Implement SMTP backend**
```

### Plan Statuses

| Status | When to use |
| --- | --- |
| `draft` | Initial draft |
| `approved` | Reviewed and approved for execution |
| `in-progress` | Implementation underway |
| `completed` | All generated tasks done |
| `superseded` | Replaced by a newer plan |

## Step 4: Break Down the Plan into Tasks

Preview first (read-only):

```sh
trailmind plan breakdown projects/taskflow/mvp/docs/plans/2026-07-02-task-notifications-implementation.md \
  --epic projects/taskflow/mvp \
  --filer alice@example.com \
  --owner alice@example.com
```

Then write tasks:

```sh
trailmind plan breakdown projects/taskflow/mvp/docs/plans/2026-07-02-task-notifications-implementation.md \
  --epic projects/taskflow/mvp \
  --filer alice@example.com \
  --owner alice@example.com \
  --write
```

This creates task files in `projects/taskflow/mvp/tasks/` with:
- `source_plan` pointing to the plan
- `source_task` matching the task number in the plan
- `source_heading` for the task title
- Code paths and deliverables derived from the plan

The source plan's `generated_tasks` frontmatter is automatically updated
with the created task IDs.

## Step 5: Track Task Progress

```sh
# Pick up a task for implementation
trailmind task pickup T-123456-001

# Mark ready to start
trailmind task set-status T-123456-001 ready --actor alice --note "Design reviewed."

# Start work
trailmind task set-status T-123456-001 in_progress --actor alice

# Log progress
trailmind task log T-123456-001 --author alice --note "Implemented model and storage."

# Complete a deliverable
trailmind task deliverable complete T-123456-001 --item "tests pass" --actor alice

# Close the task
trailmind task close T-123456-001 --closer alice --note "All deliverables complete."
```

## Step 6: Review Planning Status

```sh
trailmind plan status --epic projects/taskflow/mvp
```

This shows:
- All specs with their statuses and linked plans
- All plans with their statuses, linked specs, and generated task counts
- Gaps: specs without plans, plans without linked specs

## Step 7: View the Dashboard

```sh
trailmind status --epic projects/taskflow/mvp
```

The epic dashboard includes a Planning section with Specs and Plans tables,
plus the usual Tasks, Issues, and Milestones.

## Traceability Chain

The full chain from spec to implementation is traceable through frontmatter:

```
Spec (linked_plans) → Plan (linked_spec, generated_tasks) → Task (source_plan)
```

- **Spec → Plan**: `spec.linked_plans` and `plan.linked_spec`
- **Plan → Tasks**: `plan.generated_tasks` (list of task IDs)
- **Task → Plan**: `task.source_plan` (path to the plan)

This makes it easy to answer:
- Which tasks came from this plan?
- Which spec does this plan implement?
- What specs don't have implementation plans yet?

## Tips

- **Review specs before writing plans**: A spec should be approved before
  detailed planning begins.
- **Keep plans focused**: Each plan should have 3-10 tasks. If you need more,
  consider splitting into multiple plans.
- **Use `--write` carefully**: Breakdown is idempotent — running it again
  won't create duplicate tasks (unless `--force` is used).
- **Update plan status**: Move plans to `in-progress` when implementation
  starts, and `completed` when all tasks are done.
- **Link specs and plans**: Use `trailmind plan link-spec` to connect a
  plan to its spec if you didn't do it at creation time.
