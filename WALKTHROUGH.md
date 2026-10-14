# Local Setup and Verification (macOS / VS Code)

This guide walks through the local setup and verification flow for the Interface.ai computer-use automation assignment. `README.md`, `REPORT.md`, and the curated `evidence/` directory are the primary submission materials.

## Project layout

* `demo_bank/main.py`: synthetic, read-only legacy-style member servicing web UI plus the reviewer walkthrough.
* `automator/agent.py`: model client that chooses one discovery action at a time.
* `automator/surface.py`: Playwright browser observation, semantic locators, typing/clicking/extraction.
* `automator/models.py`: typed Pydantic action/capability/result data contracts.
* `automator/policy.py`: localhost/route/action allowlist.
* `automator/runner.py`: entry point with discover and replay modes.
* `automator/handoff.py`: same-browser manual verification handoff.
* `artifacts/`: capability saved after unassisted model-driven discovery succeeds.
* `evidence/runs/`: automatically saved machine-readable logs and screenshots; keep out of git until curated.
* `examples/ILLUSTRATIVE_NOT_DISCOVERY_EVIDENCE.json`: hand-authored sample for testing replay, not discovery evidence.

## 1. Open the project in VS Code

Open the repository folder in Terminal:

```bash
cd /path/to/InterfaceAI_Automation
code .
```

If `code` is missing, in VS Code command palette run `Shell Command: Install 'code' command in PATH`, or use File → Open Folder.

## 2. Check Python and create a virtual environment

```bash
python3 --version              # aim for Python 3.11+
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

In VS Code: Cmd+Shift+P → `Python: Select Interpreter` → `.venv/bin/python`.

## 3. Configure model access

```bash
cp -n .env.example .env
```

Edit `.env` and replace `replace_me` with a Gemini API key that has access to the configured model. Keep credentials in `.env`, which is ignored by Git. Set `GEMINI_MODEL` to a model available to your API account that supports structured outputs.

No model key is needed for the synthetic bank, unit tests, or example replay.

## 4. Terminal 1: start the synthetic bank

```bash
source .venv/bin/activate
python -m uvicorn demo_bank.main:app --host 127.0.0.1 --port 8000 --reload
```

Keep this terminal running. Browse http://127.0.0.1:8000/servicing. Try synthetic IDs `12345`, `84621`, `00000` and `55555`. For matching members, follow the links to Savings. Member `55555` opens the demo verification screen.

Once discovery has created `artifacts/get_savings_balance_v1.json`, browse http://127.0.0.1:8000/automation to enter a member ID and watch the reviewer walkthrough move through search, member profile, accounts, savings, and the final balance/status result.

This add-on uses scripted clicks and fixture balances; it only displays the artifact for reference. It does not execute the artifact or create run evidence. See `FEATURES.md`. Use the CLI below to exercise actual discovery and replay.

## 5. Terminal 2: run local checks

```bash
source .venv/bin/activate
python -m pytest -q
```

To check replay without making model calls, use the hand-authored sample artifact:

```bash
python -m automator.runner replay --member-id 84621 --artifact examples/ILLUSTRATIVE_NOT_DISCOVERY_EVIDENCE.json --headed
```

Expected: `status=success`, `balance="7210.38"`, `currency="USD"`, `account_status="ACTIVE"`, `llm_decision_calls=0`. This checks replay only; discovery evidence comes from the next step.

## 6. Model-driven discovery

```bash
python -m automator.runner discover --member-id 12345 --headed
```

The agent sees the page text and labeled controls, chooses one structured action, acts via Playwright and repeats. A successful, unassisted run saves `artifacts/get_savings_balance_v1.json`. Check that the member ID is parameterized as `{{member_id}}`. The JSON steps should include search, member, accounts, savings, extracts, and a finish checkpoint. The console reports the number of model decision calls.

If it fails, inspect `evidence/runs/<run-id>/result.json`, `trace.json`, and the screenshot. Structured errors include the phase, step, and exception type. Diagnose the failure, update the relevant code or configuration, and rerun discovery to capture a new trace.

## 7. Deterministic replay using discovered artifact

```bash
python -m automator.runner replay --member-id 84621 --artifact artifacts/get_savings_balance_v1.json --headed
```

Success requires output values and a verified balance checkpoint; `llm_decision_calls` should be `0`.

## 8. Business outcome

```bash
python -m automator.runner replay --member-id 00000 --artifact artifacts/get_savings_balance_v1.json
```

This should return `status=business_outcome, outcome_code=MEMBER_NOT_FOUND`, not an exception.

## 9. Same-session human handoff

```bash
python -m automator.runner replay --member-id 55555 --artifact artifacts/get_savings_balance_v1.json --headed
```

After verification appears, the automation pauses while **that same browser window** remains open. The operator clicks `Approve demo verification` in the browser, returns to the terminal, and presses Enter. Inspect `intervention_request.json`, `operator_actions.json`, and the final result. No new browser should be opened for human approval.

Blocked actions and repeated discovery failures can request the same handoff. Follow the terminal's pending-action message, then press Enter to release control or type `q` to stop. Resume checks the page again. Headless runs end with `needs_human`; rerunning headed creates a new session. Assisted discovery does not save a reusable artifact.

## 10. Review evidence and report

```bash
find evidence/runs -type f | sort
cat artifacts/get_savings_balance_v1.json
```

Review logs and screenshots before copying selected runs into the top-level `evidence/` directory. Keep only synthetic or redacted data. Check that `REPORT.md` matches the included runs and describes their behavior and trade-offs, retaining the seven required headings.

## 11. Git and submission

```bash
git init
git add .
git status         # Check that .env and API keys are not staged.
git commit -m "Add computer-use automation and demo bank"
git branch -M main
# Create an empty public GitHub repository in the browser first.
git remote add origin https://github.com/YOUR_USERNAME/computer-use-automation.git
git push -u origin main
```

Include `/README.md`, `/REPORT.md`, and `/evidence/` with the recorded discovery and replay runs in the public repo. Follow the PDF submission instructions.

## Troubleshooting

* `ModuleNotFoundError`: check `source .venv/bin/activate`; install requirements in that interpreter.
* `Executable doesn't exist`: run `python -m playwright install chromium`.
* `Connection refused`: keep Terminal 1 (uvicorn) running at port 8000.
* `GEMINI_API_KEY`: configure `.env`; a consumer subscription is not an API key.
* `Unknown model / access denied`: choose an enabled model in `GEMINI_MODEL`.
* Model produces wrong action: inspect the trace, observed controls, and prompt to identify the cause, then rerun discovery after correcting it.
* Headless browser cannot do a human takeover: use `--headed`.
* This is a local prototype, not production banking automation. It lacks production authentication, durable approval workflows, and full sensitive-data redaction.
