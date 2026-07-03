---
title: Task Notifications
status: approved-for-spec
created: '2026-07-02'
scope: mvp
project: taskflow
epic: mvp
linked_plans:
- docs/plans/2026-07-02-task-notifications-implementation.md
---

# Task Notifications

## Purpose

Users should receive notifications when tasks are assigned, completed, or commented on.

## Goals

- In-app notification feed
- Email notifications for important events
- Notification preferences per user

## Non-Goals

- Push notifications (mobile)
- Third-party integrations (Slack, etc.)

## Design

Use a notification service that subscribes to task events. Each user has a
notification preferences record. Email notifications are sent via a pluggable
email backend.

## Open Questions

- Should we batch email notifications or send immediately?
- What notification channels are required for MVP?
