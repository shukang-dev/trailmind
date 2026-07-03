---
title: Task Search
status: approved-for-spec
created: '2026-07-02'
scope: mvp
project: taskflow
epic: mvp
linked_plans: []
---

# Task Search

## Purpose

Users need to search and filter tasks by title, status, assignee, and creation date.

## Goals

- Full-text search on task titles
- Filter by status, assignee, date range
- Sort by creation date or priority

## Non-Goals

- Advanced query language
- Saved search views (deferred)

## Design

Use SQLite FTS5 for full-text search. Build a query builder that composes
filters. Results are paginated with cursor-based pagination.
