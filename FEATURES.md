# Workflow Walkthrough

The browser walkthrough is an optional addition to the computer-use engine. It gives a reviewer a quick view of the member servicing workflow without starting a model session or using the CLI.

## Run it

Start the app with the command in README.md and open http://127.0.0.1:8000/automation.
Enter a five-digit member ID and choose **Start walkthrough**.

The pages advance about every 1.2 seconds:

`Member lookup -> Search results -> Member profile -> Accounts -> Savings`

| Member ID | Result |
| --- | --- |
| `12345` | USD 4582.39, ACTIVE |
| `84621` | USD 7210.38, ACTIVE |
| `00000` | Member not found |
| `55555` | Pauses for demo verification, then shows USD 250.00 |

## Implementation

The walkthrough is a scripted presentation in `demo_bank/main.py`. JavaScript clicks links on a fixed sequence of pages, and the result comes directly from the synthetic fixture data. The final table loads the saved capability JSON for reference. Changing the artifact does not change the walkthrough's navigation.

The walkthrough does not run Playwright, make model calls, emit a RunResult, or write discovery/replay evidence. The verification link demonstrates the screen flow; it does not exercise the engine's ownership transfer or operator action evidence.

The CLI is the executable capability interface. Use `automator.runner discover` to obtain an artifact through model decisions, and `automator.runner replay` to execute its steps with Playwright. Use `--headed` to watch that real browser session and handle intervention.

## Possible Extension

A future control page could launch the actual runner and display its live progress. It would need run isolation, explicit ownership and resume controls, and progress events from the engine. Those are not implemented by the current walkthrough.
