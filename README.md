# Computer-Use Automation System

This project retrieves a member's savings balance and account status from a synthetic credit-union servicing app. It implements the interface.ai computer-use automation assignment: model-driven UI discovery, a versioned capability artifact, deterministic replay, safety checks, evidence capture, and same-session human handoff.

## Environment and API keys

Reviewers need their own Gemini API key only to run a new model-driven discovery. Replay with the included `artifacts/get_savings_balance_v1.json`, the web walkthrough, and the automated tests do not require a key or make model calls.

The quick-start commands below copy `.env.example` to `.env` in the project root. For discovery, edit these settings in `.env`:

| Variable | Configuration |
| --- | --- |
| `LLM_PROVIDER` | Keep `gemini` to use the Gemini integration. |
| `GEMINI_API_KEY` | Replace `replace_me` with your own Gemini API key. No working key is included in the repository. |
| `GEMINI_MODEL` | Start with the template value, or select a model available to your API account that supports structured outputs. |
| `BANK_URL` | Keep `http://127.0.0.1:8000` for the local demo server. |

The CLI loads `.env` automatically. Variables already exported in your shell take precedence over `.env`; start a new CLI run after changing settings. If discovery reports a configuration or API error, check the key and model access before retrying.

Keep credentials in `.env`, which is excluded by `.gitignore`. Commit only the placeholder `.env.example`, never a working key. A reviewer can leave `GEMINI_API_KEY=replace_me` when testing replay or the walkthrough without running discovery.

## Quick start (macOS / VS Code)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
cp -n .env.example .env
# Edit .env and set GEMINI_API_KEY using VS Code or a text editor; don't commit it.
```

Start the synthetic bank target in **Terminal 1**:

```bash
source .venv/bin/activate
python -m uvicorn demo_bank.main:app --host 127.0.0.1 --port 8000 --reload
```

Browse `http://127.0.0.1:8000/servicing` and search `12345`.

Run checks in **Terminal 2**:

```bash
source .venv/bin/activate
python -m pytest -q
```

The default suite runs without a browser or model key. To include the local
Chromium integration tests (including simulated operator actions):

```bash
RUN_BROWSER_TESTS=1 python -m pytest -q
```

These tests start an isolated localhost server and do not call the model.

Run model-driven discovery (requires a Gemini API key with access to the configured model):

```bash
python -m automator.runner discover --member-id 12345 --headed
```

A successful, unassisted discovery saves `artifacts/get_savings_balance_v1.json`. Use that generated artifact for replay and submission evidence. If discovery fails, inspect its result and trace before retrying.

Replay **without any LLM calls**:

```bash
python -m automator.runner replay --member-id 84621 --artifact artifacts/get_savings_balance_v1.json --headed
```

Business outcome:

```bash
python -m automator.runner replay --member-id 00000 --artifact artifacts/get_savings_balance_v1.json
```

Same-session human handoff (use headed mode):

```bash
python -m automator.runner replay --member-id 55555 --artifact artifacts/get_savings_balance_v1.json --headed
```

In the visible browser click `Approve demo verification`, return to the terminal, and press Enter to resume. Type `q` to stop. Human clicks and control ownership are captured in `operator_actions.json` for this synthetic site. Resume rechecks the allowed page, the blocked state, and the next target. Final outputs are read again after intervention.

Blocked replay steps, repeated discovery errors, session expiry, and the discovery step limit also request intervention. A failed click is completed manually before continuing to the next saved step; it is never automatically clicked again. Each run allows at most two handoffs. Policy violations and permission denial stop the run. In headless mode, an intervention returns `needs_human` and closes the session; a new headed run is required.

Input, artifact, configuration, and browser startup errors return structured results with a phase and exception type. CLI exit codes are `0` for success/business outcomes, `1` for failure, and `2` for unresolved intervention. For example:

```bash
python -m automator.runner replay --member-id invalid --artifact artifacts/get_savings_balance_v1.json
```

This returns `INVALID_INPUT` without opening a browser. An assisted discovery can complete the goal, but does not save a reusable artifact because manual navigation is not part of the model's recorded steps.

Generated evidence is stored in `evidence/runs/<run-id>/`. Curated submission evidence is copied into stable paths under `evidence/`; see `evidence/README.md`.

## Reviewer web walkthrough

With the included `artifacts/get_savings_balance_v1.json` (or a newly discovered artifact), browse:

```text
http://127.0.0.1:8000/automation
```

Enter a member ID to watch lookup, member profile, accounts, savings, and the final balance/status result. This add-on uses scripted JavaScript clicks and synthetic member data. It displays the saved artifact as a reference, but does not execute that artifact, call the model, or create an automation run trace. Its verification screen is a visual demo; the actual live-session handoff is exercised with the headed CLI command above.

See [FEATURES.md](FEATURES.md) for the add-on's behavior and boundaries. The CLI discovery/replay runs under `evidence/` remain the assignment evidence.

## Boundaries and known limitations

- Browser target only, localhost only, synthetic data only, read-only balance extraction.
- Operator control works in the same headed Playwright browser, not a remote session.
- Errors, schemas, and safety controls are scoped for this take-home, not bank-grade production controls.
- Model-selected actions can fail. Review the saved trace when discovery cannot complete.
- `REPORT.md` describes the actual Gemini discovery, deterministic replay, business outcome, and handoff runs captured in `evidence/`.
- The multi-step capability is produced by model decisions during discovery, then replayed without model calls.
- The `/automation` page is a reviewer walkthrough, not a replacement for the required discovery/replay evidence.

## Submit

Include README.md, REPORT.md (with the seven required headings), source, and recorded run evidence in the public GitHub repository. Keep API keys and sensitive data out of Git. Follow the assignment's submission instructions.

### Optional smoke test before enabling the LLM

A sample artifact lives in `examples/ILLUSTRATIVE_NOT_DISCOVERY_EVIDENCE.json`. Use it to smoke-test Playwright and error handling before discovery:

```bash
python -m automator.runner replay --member-id 84621 \
  --artifact examples/ILLUSTRATIVE_NOT_DISCOVERY_EVIDENCE.json --headed
```

This sample is hand-authored and tests replay only. Submission evidence should use the artifact and logs from a completed model-driven discovery run.

For failures, inspect the result's `error.phase`, `error.step`, `expected`, and `observed` fields, together with `trace.json` and the screenshot under `evidence/runs/<run-id>/`. Exception messages and raw model responses are omitted from saved errors to avoid exposing credentials. Screenshots contain synthetic data; production use would need stronger redaction.
