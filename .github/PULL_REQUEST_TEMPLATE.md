## Change

Describe the concrete problem and resulting behavior. Keep unrelated cleanup out.

## Validation

- [ ] `python tools/check_repository.py`
- [ ] `python -m unittest discover -s tests -v`
- [ ] `git diff --check`
- [ ] Packaging/migration checks, if applicable
- [ ] Only synthetic data; no personal profiles or credentials

State which host/OS/Python combinations actually ran. Distinguish storage tests
from live Codex/Claude Code/Antigravity behavior; list untested claims explicitly.

## Persistence and compatibility

Describe schema changes, data preservation, scope/ownership changes and any
backup/reversion needs. If there are none, state that briefly.
