# Recovery and Validation Checks

These are additional local runs captured on October 14, 2026, after the runner's error and handoff changes. The original discovery artifact and original human-operated handoff evidence remain in their existing directories.

| Directory | Run ID | Result | CLI exit |
| --- | --- | --- | --- |
| `invalid_input/` | `bd0a73528f48` | `failure / INVALID_INPUT`, no browser opened | 1 |
| `replay_success/` | `82a8d99e8959` | `success / BALANCE_FOUND`, USD 7210.38, ACTIVE | 0 |
| `headless_handoff/` | `e5186015ba68` | `needs_human / OPERATOR_VERIFICATION_REQUIRED` | 2 |

All three recorded zero model calls. The headless handoff has no operator and no retained interactive session; its request records `live_session_available=false` and `control_owner=none`.

## Reproduce

Start the local bank using README.md, then run:

```bash
python -m automator.runner replay --member-id invalid --artifact artifacts/get_savings_balance_v1.json
python -m automator.runner replay --member-id 84621 --artifact artifacts/get_savings_balance_v1.json
python -m automator.runner replay --member-id 55555 --artifact artifacts/get_savings_balance_v1.json
```

## Automated Checks

```bash
RUN_BROWSER_TESTS=1 python -m pytest -q
```

The full suite passed with 54 tests. Two dependency deprecation warnings came from Uvicorn's WebSocket imports. The six Chromium tests include actual browser navigation, a blocked-click recovery, and verification approval performed by a **simulated operator**. Those test interactions are not presented as human intervention evidence. The default suite runs 48 tests and skips the six opt-in browser checks.

No fresh model discovery was requested during these checks. The existing discovery evidence and its artifact were preserved.
