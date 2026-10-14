import json
from unittest.mock import MagicMock

import pytest

from automator.handoff import handoff


@pytest.fixture
def page():
    page = MagicMock()
    page.is_closed.return_value = False
    page.evaluate.return_value = [{"kind": "click", "control": "Approve demo verification"}]
    return page


def test_headless_request_does_not_claim_live_human_control(page, tmp_path, monkeypatch):
    prompt = MagicMock()
    monkeypatch.setattr("builtins.input", prompt)
    assert handoff(page, tmp_path, False) is False
    request = json.loads((tmp_path / "intervention_request.json").read_text())
    assert request["live_session_available"] is False
    assert request["control_owner"] == "none"
    prompt.assert_not_called()


@pytest.mark.parametrize("answer", ["q", "stop"])
def test_operator_can_end_run(page, tmp_path, monkeypatch, answer):
    monkeypatch.setattr("builtins.input", lambda _: answer)
    assert handoff(page, tmp_path, True) is False
    record = json.loads((tmp_path / "operator_actions.json").read_text())
    assert record["decision"] == "stopped"
    assert record["control_owner"] == "none"


def test_disconnected_terminal_is_recorded(page, tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=EOFError))
    assert handoff(page, tmp_path, True) is False
    record = json.loads((tmp_path / "operator_actions.json").read_text())
    assert record["decision"] == "operator_disconnected"


def test_resume_records_actions_and_ownership(page, tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert handoff(page, tmp_path, True, reason="REPLAY_BLOCKED",
                   context={"step": 3, "capability_id": "get_savings_balance"}) is True
    request = json.loads((tmp_path / "intervention_request.json").read_text())
    record = json.loads((tmp_path / "operator_actions.json").read_text())
    assert request["step"] == 3
    assert record["human_action_count"] == 1
    assert [item["owner"] for item in record["ownership"]] == ["automation", "human", "automation"]


def test_screenshot_failure_preserves_intervention_request(page, tmp_path, monkeypatch):
    page.screenshot.side_effect = RuntimeError("screenshot failed")
    monkeypatch.setattr("builtins.input", lambda _: "q")
    assert handoff(page, tmp_path, True) is False
    request = json.loads((tmp_path / "intervention_request.json").read_text())
    assert request["screenshot"] is None


def test_closed_page_during_handoff_cannot_resume(page, tmp_path, monkeypatch):
    def close(_):
        page.is_closed.return_value = True
        return ""

    monkeypatch.setattr("builtins.input", close)
    assert handoff(page, tmp_path, True) is False
    record = json.loads((tmp_path / "operator_actions.json").read_text())
    assert record["decision"] == "session_closed"
