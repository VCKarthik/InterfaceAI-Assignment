# Evidence Index

Curated evidence from real local runs against the synthetic bank app.

- `discovery/discovery_success_result.json`: real Gemini discovery run `9f2e595e5353`, 8 LLM decision calls.
- `discovery/discovery_success_trace.json`: sanitized discovery action trace.
- `discovery/discovery_success.png`: final discovery screenshot.
- `artifacts/get_savings_balance_v1.json`: artifact created during the discovery run.
- `replay/replay_success_result.json`: deterministic replay run `28618b655fde` for member `84621`, zero LLM calls.
- `replay/replay_success_trace.json`: replay success trace.
- `replay/replay_member_not_found_result.json`: business outcome replay run `ed9e2efe3123` for member `00000`.
- `intervention/handoff_replay_result.json`: same-session handoff replay run `c5e33624c63b` for member `55555`.
- `intervention/intervention_request.json`: handoff request emitted at the verification gate.
- `intervention/operator_actions.json`: recorded human action summary from the same browser session.

The `runs/` directory contains raw generated local run folders and is ignored by git until intentionally curated.

Additional validation and replay runs after the error-handling changes are indexed in [verification/README.md](verification/README.md). That index distinguishes real CLI run evidence from simulated operator integration tests.
