# Contributing to Meal Magic

Use [issues](https://github.com/alexneverland/meal-magic/issues) for reproducible
bugs and scoped feature proposals. Read [SECURITY.md](SECURITY.md) before reporting
anything involving credentials or private profiles. Examples must be synthetic.

## Local setup

Use Python 3.10+ with `sqlite3` and Git. There are no pip dependencies. From a
checkout of the implementation branch:

```text
python tools/check_repository.py
python -m unittest discover -s tests -v
python tools/build_package.py
git diff --check
```

On macOS/Linux, use `python3` if `python` is not available. All storage tests use
temporary directories. Do not configure tests to use the default personal data
directory or install the skill into your real agent profile for an automated test.

## Pull requests

1. Branch from current `main` after the initial implementation is merged. While
   the first PR is under review, base changes on that implementation branch.
2. Make one focused change. Add behavioral tests for changed persistence, scoping,
   migration, idempotency or lifecycle behavior.
3. Run the checks above. Stage only the intended files, inspect the diff, and
   push your branch or fork. Propose a PR to `main` with the supplied template.
4. Wait for the required checks, review and conversation resolution. Do not push
   directly to `main`, bypass protection, or force-push as a routine fix.

The CI workflow runs the tests and repository checks on Windows, Linux and macOS,
using Python 3.10 and 3.14. A single `Required checks` job gates the full matrix.
Actions are pinned to commit SHAs, the workflow token is read-only, no secrets
are supplied, and fork code is not run through `pull_request_target`.

For a solo-maintainer repository, PRs and passing checks are required but no
second human approval is mandatory. Codex review is an additional reviewer, not
a substitute for tests or a guarantee that every bug is detected. Maintainers
must review and resolve findings before merging. A merge/release is a separate
decision; this initial setup does not enable auto-merge or auto-publication.

## Architectural boundaries

- The host model interprets language and generates recipes. The helper receives
  structured JSON, validates it, and persists/retrieves local records.
- Keep runtime dependencies in the Python standard library. Calendar verification
  uses optional existing host tools or user-provided dates, not a bundled service.
- Store user data outside the installation. A new schema must preserve existing
  IDs/content/history, have migration/rollback tests, and document backup/reversion.
- Maintain a single shared skill; don't add a separate implementation per agent.
- Do not add user phrases or regex lists to classify conversational intent.

Live agent checks should follow [the scenario protocol](tests/agent-scenarios.md)
in isolated profiles. Record the actual host/model/version and observed results.
Installation-path tests are not evidence of successful model behavior.
