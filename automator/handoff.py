"""Pause browser automation for operator intervention and record the handoff."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page


def handoff(page: Page, run_dir: Path, headed: bool, *,
            reason: str = "OPERATOR_VERIFICATION_REQUIRED",
            context: Optional[dict] = None) -> bool:
    """Return True when the operator requests resume; the runner rechecks the page."""
    run_dir.mkdir(parents=True, exist_ok=True)
    live = headed and not page.is_closed()
    owner = "human" if live else "none"
    screenshot = None
    try:
        page.screenshot(path=str(run_dir / "handoff.png"), timeout=5000)
        screenshot = "handoff.png"
    except Exception:
        pass
    request = {
        **(context or {}), "reason": reason, "control_owner": owner,
        "live_session_available": live, "screenshot": screenshot,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    (run_dir / "intervention_request.json").write_text(json.dumps(request, indent=2) + "\n")
    events, resumed, decision = [], False, "unavailable"
    ownership = [{"owner": "automation"}, {"owner": owner}]
    try:
        if not live:
            print("Human needed. This run has no interactive browser; use --headed for a new run.")
            return False
        page.evaluate("localStorage.setItem('operator_events', '[]')")
        print("\nPAUSED: the operator controls the existing browser window.")
        print(f"Reason: {reason}. Resolve the blocked state in that window.")
        if (context or {}).get("action") == "click":
            print("Complete the blocked click manually. Resume continues with the next saved step.")
        else:
            print("Resume rechecks the page before continuing the pending step.")
        answer = input("Press ENTER to resume, or type q to end this run: ").strip().lower()
        resumed = answer == ""
        decision = "resume_requested" if resumed else "stopped"
    except (EOFError, KeyboardInterrupt):
        decision = "operator_disconnected"
    except Exception:
        decision = "session_unavailable"
    finally:
        if live and not page.is_closed():
            try:
                events = page.evaluate("JSON.parse(localStorage.getItem('operator_events') || '[]')")
            except Exception:
                resumed, decision = False, "session_unavailable"
        elif live:
            resumed, decision = False, "session_closed"
        ownership.append({"owner": "automation" if resumed else "none"})
        (run_dir / "operator_actions.json").write_text(json.dumps({
            "control_owner": ownership[-1]["owner"], "decision": decision,
            "events": events, "human_action_count": len(events),
            "ownership": ownership, "released_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2) + "\n")
    return resumed
