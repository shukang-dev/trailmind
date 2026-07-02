# Contributing to Trailmind

Thanks for your interest in contributing! This guide covers how to add features,
fix bugs, and improve documentation.

## Getting Started

```sh
# Clone the repo
git clone https://github.com/shukang-dev/trailmind.git
cd trailmind

# Set up the virtual environment
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"

# Run tests
python -m pytest -v

# Run the security scan
PYTHONPATH=src python -m trailmind scan
```

## Project Layout

```
src/trailmind/
  cli.py              # Click CLI entry point
  entity_io.py        # Markdown + YAML frontmatter read/write
  errors.py           # User-facing error types
  ids.py              # Entity ID generation and parsing
  paths.py            # Repository path resolution
  resolver.py         # Entity reference resolution (T-xxx, I-xxx)
  roster.py           # Developer registry
  scopes.py           # Project/epic scope resolution
  log.py              # Activity log helpers
  task.py             # Task CRUD and status management
  task_status.py      # Task status state machine
  task_rules.py       # Dependency and deliverable gates
  issue.py            # Issue CRUD and linking
  milestone.py        # Milestone management
  inbox.py            # Inbox item management
  epic.py             # Epic initialization
  project.py          # Project initialization
  agents.py           # AGENTS.md generation
  pickup.py           # Task/issue pickup context
  plan_breakdown.py   # Plan → task breakdown
  plan_artifact.py    # Spec/plan artifact management
  dashboard.py        # HTML dashboard rendering
  serve.py            # Local dashboard server
  security_scan.py    # Release safety scanner
  templates/          # Jinja2 dashboard templates
tests/
  test_*.py           # One test file per module
docs/
  v0.2-project-automation.md
  v0.3-agent-handoff.md
  v0.4-plan-breakdown.md
  v0.4-planning-artifacts.md
examples/
  demo_project/       # Complete demo project
```

## Adding a New Command

1. **Choose the right group**: Commands are organized under `project`, `epic`,
   `task`, `issue`, `milestone`, `inbox`, `plan`, `roster`, or top-level
   (`status`, `sweep`, `scan`, `serve`, `log`).

2. **Follow the pattern**: Look at existing commands in `cli.py`. Use:
   - `@click.pass_context` for context
   - `find_repo_root(_cwd_from_context(ctx))` for repo root
   - `_echo_touched(root, paths)` for created/modified files
   - `--json` flag for structured output when appropriate

3. **Create the module**: Add a new file in `src/trailmind/` or extend an
   existing one. Keep functions focused and testable.

4. **Write tests**: Create or extend `tests/test_<module>.py`. Use
   `CliRunner` for CLI tests. Create temp repos with `_repo_with_epic`.

5. **Update docs**: If the command is user-facing, add it to the relevant
   `docs/v0.x-*.md` file and the README.

## Adding a New Entity Type

If you're adding a new kind of tracked record (not just a new command):

1. **Define frontmatter fields**: Follow existing patterns. Always include
   `id`, `title`, `status`, `created`. Use `filer`/`owner` for human
   assignment. List fields default to `[]`, nullable dates default to `None`.

2. **Choose an ID prefix**: Register in `ids.py` (`ENTITY_PREFIXES`),
   `resolver.py` (`ENTITY_FOLDERS`), `log.py` (`ENTITY_NAMES`), and
   `dashboard.py` if dashboard support is needed.

3. **Create the module**: Follow the pattern in `issue.py` or `task.py`.
   Include `_resolve_epic()`, `_ensure_<entity>s_directory()`, and
   `add_<entity>()`.

4. **Wire the CLI**: Add commands in `cli.py`.

5. **Update `epic init`**: If the entity lives in an epic subdirectory,
   make sure `init_epic()` creates that directory.

## Testing Conventions

- **Test file naming**: `tests/test_<module>.py`
- **Temp repos**: Create with `_repo_with_epic(tmp_path)` pattern
- **CLI tests**: Use `CliRunner().invoke(cli, [...], obj={"cwd": repo})`
- **Assert exit codes**: `0` for success, `1` for user-facing errors,
  `2` for Click usage errors
- **User-facing errors**: Assert `"error:" in result.output` and
  `"Traceback" not in result.output`
- **No private data**: Use `alice@example.com`, `bob@example.com`, demo
  project names. Never include real organization names or internal tools.

## Clean-Room Requirements

Trailmind is a clean-room open-source implementation. Do not add:

- Private code or fixtures
- Organization-specific integrations or references
- Internal service names or proprietary examples
- Non-example email addresses
- Tool-specific branding or workflow names

All public examples must use `example.com` identities and generic project names.

## Submitting a Pull Request

1. Create a feature branch:
   ```sh
   git checkout -b my-feature
   ```

2. Make your changes and commit:
   ```sh
   git add src/ tests/ docs/
   git commit -m "feat: add my feature"
   ```

3. Run validation:
   ```sh
   python -m pytest -v
   PYTHONPATH=src python -m trailmind scan
   git diff --check
   ```

4. Push and create a PR:
   ```sh
   git push -u origin my-feature
   gh pr create
   ```

5. In the PR description, explain:
   - What the change does
   - How you tested it
   - Any design decisions or trade-offs

## Release Checklist

Before tagging a release:

- [ ] All tests pass (`python -m pytest -v`)
- [ ] Security scan passes (`PYTHONPATH=src python -m trailmind scan`)
- [ ] `git diff --check` passes
- [ ] Public docs updated (README, relevant `docs/v0.x-*.md`)
- [ ] Example project updated if schema changed
- [ ] Version bumped in `src/trailmind/__init__.py`
- [ ] Migration notes added if breaking changes exist
- [ ] Branch metadata uses `shukang-dev@users.noreply.github.com`

## Questions?

Open an issue on GitHub or check the existing docs for more context.
