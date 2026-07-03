---
id: I-123456-001
title: Task list crashes on empty
filer: alice
status: done
severity: high
created: '2026-07-02'
linked_tasks:
- T-123456-001
carried_into: []
---
# Task list crashes on empty

## Description

When there are no tasks, the list view throws an IndexError.

## Resolution

TBD

## Activity Log

- 2026-07-02: Filed by alice.
- 2026-07-02: Closed as done by alice. Fixed by adding empty state check.
