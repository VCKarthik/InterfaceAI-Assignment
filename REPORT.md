# Architecture

The project retrieves savings balances and account status through a local, synthetic credit-union servicing app. During discovery, Playwright observes the page and Gemini (`gemini-3.8-flash`) chooses one structured action. The runner validates that action with Pydantic, checks it against the policy, executes it, and repeats until the balance/status checkpoint is verified. The successful discovery run was `9f2e595e5353`, with 8 LLM decision calls and output `balance=4582.39`, `currency=USD`, `account_status=ACTIVE`.

Replay is a separate deterministic path. It loads the saved artifact, validates typed inputs, executes the recorded steps with Playwright semantic locators, extracts outputs, and reports `llm_decision_calls=0`. The target app runs locally with synthetic data, and the workflow reads account information without changing it.

The FastAPI app also includes `/automation`, an optional scripted walkthrough through lookup, member profile, accounts, savings, and balance/status. Its timed JavaScript clicks and fixture values demonstrate the workflow. It displays the saved artifact for reference but does not execute it or generate run evidence. The CLI runs exercise the actual discovery and replay engine.

# Artifact schema

The capability artifact is stored at `artifacts/get_savings_balance_v1.json` and copied to `evidence/artifacts/get_savings_balance_v1.json`. It is a Pydantic `Capability` with schema/version IDs, target app, entry path, typed input/output descriptors, ordered `Step` actions, and a success text checkpoint.

The member ID is parameterized as `{{member_id}}`, not stored as the discovered value. Steps use semantic locator kinds (`label`, `role`, `table_row`, `none`) rather than raw coordinates or absolute XPath. The artifact contains the steps needed for review and replay without the raw model transcript.

# Determinism & error handling

Replay uses the artifact steps exactly as saved and does not instantiate a model client. Replay run `28618b655fde` used member `84621`, returned `balance=7210.38`, and recorded `llm_decision_calls=0`.

The runner distinguishes success, business outcomes, needs-human, and failures. Replay run `ed9e2efe3123` used member `00000` and returned `status=business_outcome`, `outcome_code=MEMBER_NOT_FOUND`, not a crash. Playwright auto-waits on locators, and the runner retries a small class of timeout-prone fill/extract actions once. Failures save JSON traces and screenshots under `evidence/runs/<run_id>/`.

Validation, artifact loading, model configuration, browser startup, and navigation failures also return structured results. Error details contain the phase, step when known, expected target, and exception type without raw exception text. Permission denial and policy violations terminate execution. Session expiry and blocked actions request intervention. CLI exit codes distinguish success/business outcomes (0), failure (1), and unresolved intervention (2).

The runner passed 54 tests, including six local Chromium integration checks. Success, invalid-input, and headless-intervention runs are saved under `evidence/verification/`. Integration tests simulate operator actions; the separately curated handoff records a human-operated run.

# Heterogeneity & multi-tenant

The `Surface` adapter handles browser interaction for the recorded flow. It observes visible text and controls and performs Playwright actions. Supporting legacy frames, accessibility trees, screenshot/coordinate control, or desktop automation would require additional adapters and validation for those targets.

For multi-tenant reuse, the artifact would become a vendor baseline plus tenant/version metadata and overrideable locator bundles. Drift detection would compare checkpoints, route patterns, and locator uniqueness before allowing unattended replay. This project documents that direction but does not implement tenant catalogs or drift management.

# Escalation & handoff

The synthetic member `55555` triggers an operator verification gate. Replay pauses, writes an `intervention_request.json`, cedes control of the same headed Playwright browser to the human, records the operator click from browser-local instrumentation, and resumes only after terminal confirmation.

The verified handoff run was `c5e33624c63b`: the operator clicked `Approve demo verification`, replay resumed in the same session, returned `balance=250.00`, and still recorded `llm_decision_calls=0`. The curated evidence is under `evidence/intervention/`.

Handoff also covers blocked replay steps, repeated discovery errors, and the discovery step limit, with at most two interventions per run. Each request includes its run, capability, step, reason, and screenshot where available. Enter releases control; `q`, EOF, or a closed browser ends the intervention. Resume checks policy and page readiness. Failed clicks are completed manually, then replay continues at the next saved step; read/fill operations may be retried after explicit release. Outputs are refreshed before success. Headless runs return `needs_human` and close rather than retaining an inaccessible session. Assisted discovery does not save an artifact containing unrecorded human actions. The curated handoff demonstrates the verification gate; automated recovery tests are separate from that human evidence.

# Safety

The policy guard allows only the configured localhost bank URL/routes and conservative action types. It blocks financial-changing labels such as transfer or close account. Artifacts and curated logs use synthetic data only, and the generated artifact does not contain the discovery member ID or API key. `.env` is ignored; `.env.example` contains placeholders only.

This is not production-grade privacy enforcement. Screenshot redaction, authenticated operator controls, durable audit storage, and real PII controls are left as production work.

# Cuts

The implementation focuses on one read-only capability, from discovery through replay and human handoff. It does not include production authentication, a remote operator console, desktop automation, tenant catalogs, artifact approval workflows, broad retry/fallback policies, or a production dashboard. The `/automation` walkthrough helps reviewers inspect the workflow, but does not replace the CLI engine. Broader deployment would need those operational controls and validation against additional targets.
