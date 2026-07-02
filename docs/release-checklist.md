# Release Checklist

Use this checklist when preparing a new Trailmind release.

## Pre-Release

- [ ] All tests pass: `python -m pytest -v`
- [ ] Security scan passes: `PYTHONPATH=src python -m trailmind scan`
- [ ] `git diff --check` passes (no whitespace errors)
- [ ] Version bumped in `src/trailmind/__init__.py`
- [ ] Changelog updated (if applicable)
- [ ] Public docs updated for new features
- [ ] Example project updated for schema changes
- [ ] Branch metadata uses the project's public noreply email
- [ ] No private data in commits (`git log --format='%ae' main..HEAD`)

## Release Steps

1. **Create release branch**: `git checkout -b release-vX.Y.Z`
2. **Bump version**: Edit `src/trailmind/__init__.py`
3. **Run full validation**:
   ```sh
   python -m pytest -v
   PYTHONPATH=src python -m trailmind scan
   git diff --check
   ```
4. **Commit version bump**: `git commit -am "release: vX.Y.Z"`
5. **Tag**: `git tag vX.Y.Z`
6. **Push**: `git push origin main --tags`
7. **Create GitHub Release**: Use the tag, include changelog

## Post-Release

- [ ] Verify PyPI publish (if configured)
- [ ] Announce in relevant channels
- [ ] Close completed milestones
- [ ] Update trailmind-brain with completed work
