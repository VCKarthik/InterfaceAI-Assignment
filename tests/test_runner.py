import json
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from automator import agent, runner
from automator.models import AgentChoice, Capability, Step
from automator.policy import Policy
from automator.surface import Surface


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("BANK_URL", "http://127.0.0.1:8000")
    monkeypatch.setattr(runner, "EVIDENCE", tmp_path / "runs")
    monkeypatch.setattr(runner, "ARTIFACTS", tmp_path / "artifacts")
    manager = MagicMock()
    monkeypatch.setattr(runner, "sync_playwright", lambda: manager)
    browser = manager.__enter__.return_value.chromium.launch.return_value
    page = browser.new_page.return_value
    page.is_closed.return_value = False
    page.url = "http://127.0.0.1:8000/servicing"
    surface = MagicMock(spec=Surface)
    surface.page, surface.policy = page, Policy("http://127.0.0.1:8000")
    surface.business_outcome.return_value = None
    surface.blocking_state.return_value = None

    def perform(step, params, outputs):
        if step.action == "extract":
            outputs[step.output_key] = "7210.38" if step.output_key == "balance" else "ACTIVE"
            outputs["currency"] = "USD"

    surface.perform.side_effect = perform
    surface.verify_success.side_effect = lambda outputs, checkpoint: (
        {"balance", "currency", "account_status"}.issubset(outputs)
        and checkpoint == "Current Balance"
    )
    monkeypatch.setattr(runner, "Surface", lambda *args: surface)
    capability = Capability(steps=[
        Step(action="fill", kind="label", name="Member ID", value="{{member_id}}"),
        Step(action="click", kind="role", role="button", name="Search"),
        Step(action="extract", kind="table_row", name="Current Balance", output_key="balance"),
        Step(action="extract", kind="table_row", name="Status", output_key="account_status"),
        Step(action="finish"),
    ])
    artifact = tmp_path / "capability.json"
    artifact.write_text(capability.model_dump_json())
    handoff = MagicMock(return_value=False)
    monkeypatch.setattr(runner, "handoff", handoff)
    return manager, browser, surface, artifact, handoff


@pytest.mark.parametrize("member_id", ["", "123", "123456", "abcde", "１２３４５", None, 12345])
def test_invalid_input_is_structured_without_browser(runtime, member_id):
    manager, _, _, artifact, _ = runtime
    result = runner.do_run("replay", member_id, artifact=str(artifact))
    assert result.status == "failure"
    assert result.outcome_code == "INVALID_INPUT"
    assert result.error.phase == "validation"
    manager.__enter__.assert_not_called()
    saved = json.loads((runner.EVIDENCE / result.run_id / "result.json").read_text())
    assert saved["error"]["expected"] == {"member_id": "five ASCII digits"}


@pytest.mark.parametrize("content", ["{", "{}", '{"steps": []}'])
def test_invalid_artifact_is_structured(runtime, content):
    manager, _, _, artifact, _ = runtime
    artifact.write_text(content)
    result = runner.do_run("replay", "84621", artifact=str(artifact))
    assert result.outcome_code == "INVALID_ARTIFACT"
    manager.__enter__.assert_not_called()


def test_missing_artifact_is_structured(runtime):
    manager, _, _, artifact, _ = runtime
    result = runner.do_run("replay", "84621", artifact=str(artifact.parent / "missing.json"))
    assert result.outcome_code == "INVALID_ARTIFACT"
    manager.__enter__.assert_not_called()


def test_disallowed_artifact_entry_never_opens_browser(runtime):
    manager, _, _, artifact, _ = runtime
    cap = Capability.model_validate_json(artifact.read_text())
    cap.entry_path = "/not-allowed"
    artifact.write_text(cap.model_dump_json())
    result = runner.do_run("replay", "84621", artifact=str(artifact))
    assert result.outcome_code == "POLICY_BLOCKED"
    manager.__enter__.assert_not_called()


def test_browser_launch_error_is_saved_without_exception_text(runtime):
    manager, _, _, artifact, _ = runtime
    manager.__enter__.return_value.chromium.launch.side_effect = RuntimeError("sensitive-diagnostic")
    result = runner.do_run("replay", "84621", artifact=str(artifact))
    assert result.outcome_code == "BROWSER_START_FAILED"
    assert result.error.observed == {"exception_type": "RuntimeError"}
    assert "sensitive-diagnostic" not in (runner.EVIDENCE / result.run_id / "result.json").read_text()


def test_navigation_error_closes_browser_and_saves_result(runtime):
    _, browser, surface, artifact, _ = runtime
    surface.page.goto.side_effect = PlaywrightTimeout("connection timed out")
    result = runner.do_run("replay", "84621", artifact=str(artifact))
    assert result.outcome_code == "NAVIGATION_FAILED"
    browser.close.assert_called_once()
    surface.page.screenshot.assert_called_once()


def test_replay_never_configures_or_calls_model(runtime, monkeypatch):
    _, _, _, artifact, _ = runtime
    configure, decide = MagicMock(), MagicMock()
    monkeypatch.setattr(agent, "configured_client_and_model", configure)
    monkeypatch.setattr(agent, "decide", decide)
    result = runner.do_run("replay", "84621", artifact=str(artifact))
    assert result.status == "success"
    assert result.outputs["balance"] == "7210.38"
    assert result.llm_decision_calls == 0
    configure.assert_not_called()
    decide.assert_not_called()


def test_checkpoint_from_artifact_is_enforced(runtime):
    _, _, _, artifact, handoff = runtime
    cap = Capability.model_validate_json(artifact.read_text())
    cap.success_text = "Different checkpoint"
    artifact.write_text(cap.model_dump_json())
    result = runner.do_run("replay", "84621", artifact=str(artifact))
    assert result.status == "needs_human"
    assert result.outputs == {}
    handoff.assert_called_once()


def test_known_business_outcome_does_not_escalate(runtime):
    _, _, surface, artifact, handoff = runtime
    surface.business_outcome.return_value = "MEMBER_NOT_FOUND"
    result = runner.do_run("replay", "00000", artifact=str(artifact))
    assert result.status == "business_outcome"
    assert result.error is None
    handoff.assert_not_called()


def test_permission_denied_stops_without_operator_bypass(runtime):
    _, _, surface, artifact, handoff = runtime
    surface.blocking_state.return_value = "PERMISSION_DENIED"
    result = runner.do_run("replay", "84621", artifact=str(artifact), headed=True)
    assert result.outcome_code == "PERMISSION_DENIED"
    surface.perform.assert_not_called()
    handoff.assert_not_called()


def test_transient_fill_is_retried_once(runtime):
    _, _, surface, artifact, handoff = runtime
    perform, attempts = surface.perform.side_effect, []

    def transient(step, params, outputs):
        if step.action == "fill":
            attempts.append(step)
            if len(attempts) == 1:
                raise PlaywrightTimeout("delayed")
        perform(step, params, outputs)

    surface.perform.side_effect = transient
    result = runner.do_run("replay", "84621", artifact=str(artifact))
    assert result.status == "success"
    assert len(attempts) == 2
    handoff.assert_not_called()


def test_failed_click_requests_handoff_without_reclicking(runtime):
    _, _, surface, artifact, handoff = runtime
    perform, clicks = surface.perform.side_effect, []

    def blocked(step, params, outputs):
        if step.action == "click":
            clicks.append(step)
            raise PlaywrightTimeout("blocked")
        perform(step, params, outputs)

    surface.perform.side_effect = blocked
    result = runner.do_run("replay", "84621", artifact=str(artifact))
    assert result.status == "needs_human"
    assert result.outcome_code == "REPLAY_BLOCKED"
    assert result.error.step == 2
    assert len(clicks) == 1
    assert handoff.call_args.args[0] is surface.page
    assert handoff.call_args.kwargs["context"]["target_name"] == "Search"


def test_manual_click_completion_resumes_next_step_and_refreshes_outputs(runtime):
    _, _, surface, artifact, handoff = runtime
    perform, clicks = surface.perform.side_effect, []

    def blocked(step, params, outputs):
        if step.action == "click":
            clicks.append(step)
            raise PlaywrightTimeout("blocked")
        perform(step, params, outputs)

    surface.perform.side_effect = blocked
    handoff.return_value = True
    result = runner.do_run("replay", "84621", artifact=str(artifact), headed=True)
    assert result.status == "success"
    assert len(clicks) == 1
    surface.locator.return_value.wait_for.assert_called_once()
    extracts = [c.args[0] for c in surface.perform.call_args_list if c.args[0].action == "extract"]
    assert len(extracts) == 4


def test_unresolved_gate_cannot_resume(runtime):
    _, _, surface, artifact, handoff = runtime
    surface.blocking_state.return_value = "OPERATOR_VERIFICATION_REQUIRED"
    handoff.return_value = True
    result = runner.do_run("replay", "55555", artifact=str(artifact), headed=True)
    assert result.outcome_code == "RESUME_NOT_READY"
    assert result.outputs == {}
    surface.perform.assert_not_called()


def test_resume_cannot_leave_allowlist(runtime):
    _, _, surface, artifact, handoff = runtime
    surface.blocking_state.return_value = "SESSION_EXPIRED"

    def outside(*args, **kwargs):
        surface.page.url = "https://outside.invalid"
        return True

    handoff.side_effect = outside
    result = runner.do_run("replay", "84621", artifact=str(artifact), headed=True)
    assert result.outcome_code == "POLICY_BLOCKED"
    surface.perform.assert_not_called()


def test_eof_or_cancel_ends_gate_without_continuing(runtime):
    _, browser, surface, artifact, handoff = runtime
    surface.blocking_state.return_value = "SESSION_EXPIRED"
    result = runner.do_run("replay", "84621", artifact=str(artifact), headed=True)
    assert result.status == "needs_human"
    handoff.assert_called_once()
    surface.perform.assert_not_called()
    browser.close.assert_called_once()


def test_repeated_discovery_errors_request_intervention(runtime, monkeypatch):
    _, _, _, _, handoff = runtime
    monkeypatch.setattr(agent, "configured_client_and_model", lambda: (None, "test"))
    monkeypatch.setattr(agent, "decide", MagicMock(side_effect=RuntimeError("model failed")))
    result = runner.do_run("discovery", "12345", headed=True)
    assert result.status == "needs_human"
    assert result.outcome_code == "DISCOVERY_BLOCKED"
    assert result.llm_decision_calls == 2
    assert result.artifact_path is None
    handoff.assert_called_once()


def test_assisted_discovery_does_not_publish_incomplete_artifact(runtime, monkeypatch):
    _, _, _, _, handoff = runtime
    handoff.return_value = True
    monkeypatch.setattr(agent, "configured_client_and_model", lambda: (None, "test"))
    monkeypatch.setattr(agent, "decide", lambda *args: AgentChoice(action="finish"))
    result = runner.do_run("discovery", "12345", headed=True)
    assert result.status == "success"
    assert result.outcome_code == "GOAL_COMPLETED_WITH_INTERVENTION"
    assert result.artifact_path is None
    assert not runner.ARTIFACTS.exists()


def test_cli_failure_exit_code(runtime, monkeypatch):
    monkeypatch.setattr("sys.argv", ["runner", "replay", "--member-id", "invalid"])
    assert runner.main() == 1


def test_model_configuration_failure_is_structured(runtime, monkeypatch):
    manager, _, _, _, _ = runtime
    monkeypatch.setattr(agent, "configured_client_and_model", MagicMock(side_effect=RuntimeError("key missing")))
    result = runner.do_run("discovery", "12345")
    assert result.outcome_code == "CONFIGURATION_ERROR"
    manager.__enter__.assert_not_called()


def test_discovery_interventions_are_bounded(runtime, monkeypatch):
    _, _, _, _, handoff = runtime
    handoff.return_value = True
    monkeypatch.setattr(agent, "configured_client_and_model", lambda: (None, "test"))
    monkeypatch.setattr(agent, "decide", MagicMock(side_effect=RuntimeError("blocked")))
    result = runner.do_run("discovery", "12345", headed=True)
    assert result.outcome_code == "HANDOFF_LIMIT_REACHED"
    assert handoff.call_count == 2
    assert result.llm_decision_calls == 6


def test_discovery_limit_routes_to_operator(runtime, monkeypatch):
    _, _, _, _, handoff = runtime
    monkeypatch.setattr(agent, "configured_client_and_model", lambda: (None, "test"))
    monkeypatch.setattr(agent, "decide", lambda *args: AgentChoice(
        action="fill", kind="label", name="Member ID", value="{{member_id}}"))
    result = runner.do_run("discovery", "12345", headed=True)
    assert result.outcome_code == "DISCOVERY_STEP_LIMIT"
    assert result.llm_decision_calls == 16
    handoff.assert_called_once()


def test_unassisted_discovery_saves_parameterized_artifact(runtime, monkeypatch):
    _, _, _, artifact, _ = runtime
    choices = iter(Capability.model_validate_json(artifact.read_text()).steps)
    monkeypatch.setattr(agent, "configured_client_and_model", lambda: (None, "test"))
    monkeypatch.setattr(agent, "decide", lambda *args: AgentChoice(**next(choices).model_dump()))
    result = runner.do_run("discovery", "12345")
    assert result.status == "success"
    saved = (runner.ARTIFACTS / "get_savings_balance_v1.json").read_text()
    assert "12345" not in saved
    assert "{{member_id}}" in saved
    assert len(Capability.model_validate_json(saved).steps) == 5


def test_handoff_can_resolve_to_business_outcome(runtime):
    _, _, surface, artifact, handoff = runtime
    surface.blocking_state.return_value = "SESSION_EXPIRED"

    def not_found(*args, **kwargs):
        surface.blocking_state.return_value = None
        surface.business_outcome.return_value = "MEMBER_NOT_FOUND"
        return True

    handoff.side_effect = not_found
    result = runner.do_run("replay", "00000", artifact=str(artifact), headed=True)
    assert result.status == "business_outcome"
    surface.perform.assert_not_called()
