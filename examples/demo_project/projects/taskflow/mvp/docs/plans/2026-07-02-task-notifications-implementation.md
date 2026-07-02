---
title: Task Notifications Implementation
status: in-progress
created: '2026-07-02'
scope: mvp
project: taskflow
epic: mvp
linked_spec: docs/specs/2026-07-02-task-notifications.md
generated_tasks: []
---

# Task Notifications Implementation

## Scope

Implement in-app notification feed and email notifications for task events.

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
- [ ] **Step 3: Add configuration**

## Activity Log

- 2026-07-02: Created plan by maintainer.
