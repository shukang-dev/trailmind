---
title: Dashboard Improvements
status: approved
created: '2026-07-02'
scope: mvp
project: taskflow
epic: mvp
linked_spec: null
generated_tasks: []
---

# Dashboard Improvements

## Scope

Improve the project dashboard with better task summaries and filtering.

## Architecture

Add summary cards at the top of the dashboard. Implement client-side
filtering with URL query params.

### Task 1: Summary Cards

**Files:**
- Modify: `src/views/dashboard.py`

- [ ] **Step 1: Add task count by status**
- [ ] **Step 2: Add overdue task count**

### Task 2: Client-side Filtering

**Files:**
- Modify: `src/static/dashboard.js`

- [ ] **Step 1: Add filter UI**
- [ ] **Step 2: Wire URL params**
