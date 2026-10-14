"""Discovery / deterministic replay CLI with local synthetic evidence."""
import argparse
import json
import os
import re
import uuid
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from .handoff import handoff
from .models import Capability, RunError, RunResult, Step
from .policy import Policy, PolicyError
from .surface import Surface

load_dotenv()
ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "runs"
ARTIFACTS = ROOT / "artifacts"


def dump(path: Path, item):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(item, indent=2, default=str) + "\n")


def fail(result, code, phase, *, exc=None, step=None, expected=None, status="failure"):
    result.status, result.outcome_code = status, code
    result.outputs = {}
    result.message = code.replace("_", " ").capitalize()
    result.error = RunError(
        phase=phase, step=step, expected=expected or {},
        observed={"exception_type": type(exc).__name__} if exc else {"state": code},
    )


def execute(surface, result, member_id, goal, cap, client, model, run_dir, headed, trace):
    outputs, recorded = {}, []
    interventions, consecutive_errors = 0, 0
    params = {"member_id": member_id}
    checkpoint = cap.success_text if cap else "Current Balance"

    def complete():
        # Manual navigation can invalidate earlier extracts. Read them again before success.
        if interventions:
            outputs.clear()
            extracts = [s for s in cap.steps if s.action == "extract"] if cap else [
                Step(action="extract", kind="table_row", name="Current Balance", output_key="balance"),
                Step(action="extract", kind="table_row", name="Status", output_key="account_status"),
            ]
            for extract in extracts:
                surface.perform(extract, params, outputs)
            trace.append({"event": "outputs_revalidated_after_handoff"})
        if not surface.verify_success(outputs, checkpoint):
            raise ValueError("Success checkpoint or outputs missing")
        result.status, result.outcome_code = "success", "BALANCE_FOUND"
        result.outputs, result.error, result.message = dict(outputs), None, ""

    def intervene(reason, number, action=None, resume_step=None):
        nonlocal interventions
        failure_context = result.error.model_dump() if result.error else None
        fail(result, reason, "handoff", step=number, status="needs_human",
             expected={"action": action.action, "target_name": action.name} if action else {})
        if surface.page.is_closed():
            fail(result, "BROWSER_CLOSED", "handoff", step=number)
            return False
        if interventions >= 2:
            fail(result, "HANDOFF_LIMIT_REACHED", "handoff", step=number, status="needs_human")
            return False
        interventions += 1
        directory = run_dir if interventions == 1 else run_dir / "interventions" / str(interventions)
        trace.append({"step": number, "event": "human_handoff_requested", "reason": reason})
        released = handoff(surface.page, directory, headed, reason=reason, context={
            "run_id": result.run_id, "mode": result.mode, "step": number,
            "capability_id": cap.capability_id if cap else "get_savings_balance",
            "current_state": reason, "action": action.action if action else None,
            "target_name": action.name if action else None,
            "failure": failure_context,
        })
        if not released:
            trace.append({"step": number, "event": "human_handoff_ended"})
            return False
        surface.policy.check_url(surface.page.url)
        try:
            if surface.blocking_state():
                raise ValueError("Page is still blocked")
            if resume_step and resume_step.action != "finish" and not surface.business_outcome():
                surface.locator(resume_step).wait_for(state="visible", timeout=6500)
        except PolicyError:
            raise
        except Exception as exc:
            fail(result, "RESUME_NOT_READY", "handoff", exc=exc, step=number, status="needs_human")
            trace.append({"step": number, "event": "resume_rejected"})
            return False
        outputs.clear()
        trace.append({"step": number, "event": "human_handoff_completed"})
        return True

    def perform(step, event):
        if step.action == "finish":
            complete()
            trace.append({**event, "result": "verified"})
            return
        try:
            surface.perform(step, params, outputs)
        except PlaywrightTimeout:
            if step.action not in {"fill", "extract"}:
                raise
            trace.append({**event, "result": "recoverable_timeout", "recovery": "retry_once"})
            surface.page.wait_for_timeout(500)
            surface.perform(step, params, outputs)
        trace.append({**event, "result": "completed"})
        if result.mode == "discovery":
            recorded.append(step)

    for index in range(len(cap.steps) if cap else 16):
        number, step = index + 1, cap.steps[index] if cap else None
        event = {"step": number}
        try:
            surface.policy.check_url(surface.page.url)
            if surface.business_outcome():
                result.status, result.outcome_code = "business_outcome", "MEMBER_NOT_FOUND"
                result.error, result.message = None, ""
                return recorded, interventions
            blocked = surface.blocking_state()
            if blocked == "PERMISSION_DENIED":
                fail(result, blocked, "execution", step=number)
                return recorded, interventions
            if blocked and not intervene(blocked, number, resume_step=step):
                return recorded, interventions
            if blocked and surface.business_outcome():
                result.status, result.outcome_code = "business_outcome", "MEMBER_NOT_FOUND"
                result.error, result.message = None, ""
                return recorded, interventions
            if result.mode == "discovery":
                from .agent import decide
                observation = surface.observe()
                result.llm_decision_calls += 1
                choice = decide(client, model, goal, observation, trace, outputs)
                step = Step.model_validate({**choice.model_dump(), "rationale": ""})
                if member_id in step.name or member_id in step.role or member_id in step.output_key:
                    raise PolicyError("Model-generated locator contains a member identifier")
                event["reason"] = re.sub(r"\d{3,}", "[REDACTED]", choice.rationale)[:150]
            event.update(action=step.action, kind=step.kind, name=step.name,
                         role=step.role, output_key=step.output_key)
            perform(step, event)
            consecutive_errors = 0
            if step.action == "finish":
                return recorded, interventions
        except PolicyError as exc:
            fail(result, "POLICY_BLOCKED", "execution", exc=exc, step=number)
            trace.append({**event, "result": "blocked"})
            return recorded, interventions
        except Exception as exc:
            fail(result, "STEP_FAILED", "execution", exc=exc, step=number,
                 expected={"target_kind": step.kind, "target_name": step.name} if step else {})
            trace.append({**event, "result": "error", **result.error.model_dump()})
            consecutive_errors += 1
            if not cap and consecutive_errors < 2:
                continue
            # A failed click may already have navigated. Only a person may complete it;
            # replay continues from the next declared step after checking its target.
            next_step = cap.steps[index + 1] if cap and step.action == "click" else step
            if not intervene("REPLAY_BLOCKED" if cap else "DISCOVERY_BLOCKED",
                             number, step, next_step if cap else None):
                return recorded, interventions
            if surface.business_outcome():
                result.status, result.outcome_code = "business_outcome", "MEMBER_NOT_FOUND"
                result.error, result.message = None, ""
                return recorded, interventions
            if cap and step.action != "click":
                try:
                    perform(step, event)
                    if step.action == "finish":
                        return recorded, interventions
                except PolicyError:
                    raise
                except Exception as retry_exc:
                    fail(result, "RESUME_STEP_FAILED", "execution", exc=retry_exc, step=number)
                    return recorded, interventions
            consecutive_errors = 0
    if not cap and intervene("DISCOVERY_STEP_LIMIT", 16):
        try:
            complete()
        except PolicyError:
            raise
        except Exception as exc:
            fail(result, "MISSING_CHECKPOINT", "execution", exc=exc, step=16)
    return recorded, interventions


def do_run(mode: str, member_id: str, *, goal: str = "", artifact: str = "", headed: bool = False):
    result = RunResult(run_id=uuid.uuid4().hex[:12], mode=mode,
                       status="failure", outcome_code="UNFINISHED")
    run_dir = EVIDENCE / result.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    trace, cap, client, model = [], None, None, ""
    phase, page, browser = "validation", None, None
    try:
        if not isinstance(member_id, str) or not re.fullmatch(r"[0-9]{5}", member_id):
            raise ValueError("Demo member_id must contain exactly five ASCII digits")
        phase = "policy"
        base_url = os.getenv("BANK_URL", "http://127.0.0.1:8000").rstrip("/")
        policy = Policy(base_url)
        policy.check_url(base_url + "/servicing")
        if mode == "replay":
            phase = "artifact"
            cap = Capability.model_validate_json(Path(artifact).read_text())
            if (not cap.steps or cap.steps[-1].action != "finish"
                    or any(s.action == "finish" for s in cap.steps[:-1])):
                raise ValueError("Artifact must end at one finish checkpoint")
            if cap.target_app != "demo_legacy_credit_union":
                raise PolicyError("Unexpected target app")
            policy.check_url(base_url + cap.entry_path)
            for step in cap.steps:
                policy.check_step(step.action, step.name)
        else:
            phase = "configuration"
            from .agent import configured_client_and_model
            client, model = configured_client_and_model()
        phase = "browser_start"
        with sync_playwright() as p:
            try:
                browser_kwargs = {"headless": not headed}
                if os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"):
                    browser_kwargs["executable_path"] = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
                browser = p.chromium.launch(**browser_kwargs)
                page = browser.new_page(viewport={"width": 1100, "height": 780})
                phase = "navigation"
                page.goto(base_url + (cap.entry_path if cap else "/servicing"),
                          wait_until="domcontentloaded", timeout=15000)
                phase = "execution"
                recorded, interventions = execute(Surface(page, policy), result, member_id, goal,
                                                  cap, client, model, run_dir, headed, trace)
                if result.status == "success" and mode == "discovery":
                    if interventions:
                        result.outcome_code = "GOAL_COMPLETED_WITH_INTERVENTION"
                        result.message = "Manual actions were needed; no reusable artifact was saved."
                    else:
                        phase = "artifact_save"
                        path = ARTIFACTS / "get_savings_balance_v1.json"
                        dump(path, Capability(steps=recorded + [Step(action="finish")]).model_dump())
                        result.artifact_path = str(path)
            finally:
                if page and not page.is_closed():
                    filename = f"{mode}_success.png" if result.status == "success" else "failure.png"
                    try:
                        policy.check_url(page.url)
                        page.screenshot(path=str(run_dir / filename), timeout=5000)
                    except Exception:
                        trace.append({"event": "screenshot_unavailable"})
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        trace.append({"event": "browser_cleanup_failed"})
    except Exception as exc:
        code = "POLICY_BLOCKED" if isinstance(exc, PolicyError) else {
            "validation": "INVALID_INPUT", "artifact": "INVALID_ARTIFACT",
            "configuration": "CONFIGURATION_ERROR", "browser_start": "BROWSER_START_FAILED",
            "navigation": "NAVIGATION_FAILED", "artifact_save": "ARTIFACT_SAVE_FAILED",
        }.get(phase, "EXECUTION_FAILED")
        fail(result, code, phase, exc=exc,
             expected={"member_id": "five ASCII digits"} if phase == "validation" else {})
        trace.append({"event": "run_failed", **result.error.model_dump()})
    dump(run_dir / "trace.json", trace)
    dump(run_dir / "result.json", result.model_dump())
    print(json.dumps(result.model_dump(), indent=2))
    print(f"Evidence saved at: {run_dir}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Synthetic bank computer-use system")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("discover")
    d.add_argument("--member-id", required=True)
    d.add_argument("--goal", default="Find the member's current savings balance and account status")
    d.add_argument("--headed", action="store_true")
    r = sub.add_parser("replay")
    r.add_argument("--member-id", required=True)
    r.add_argument("--artifact", default="artifacts/get_savings_balance_v1.json")
    r.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    if args.command == "discover":
        result = do_run("discovery", args.member_id, goal=args.goal, headed=args.headed)
    else:
        result = do_run("replay", args.member_id, artifact=args.artifact, headed=args.headed)
    return 0 if result.status in {"success", "business_outcome"} else 2 if result.status == "needs_human" else 1


if __name__ == "__main__":
    raise SystemExit(main())
