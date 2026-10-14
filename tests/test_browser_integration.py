"""Opt-in local Chromium checks. Operator actions here are simulated, not human evidence."""
import json
import os
import socket
import threading
import time
from contextlib import contextmanager

import pytest
import uvicorn
from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright

from automator import runner
from automator.handoff import handoff
from automator.surface import Surface
from demo_bank.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BROWSER_TESTS") != "1",
    reason="Set RUN_BROWSER_TESTS=1 to launch local Chromium and a test server.",
)


@pytest.fixture(scope="module")
def bank_url():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        yield url
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive()


@pytest.fixture
def browser_run(bank_url, monkeypatch, tmp_path):
    monkeypatch.setenv("BANK_URL", bank_url)
    monkeypatch.setattr(runner, "EVIDENCE", tmp_path / "runs")

    # The test driver acts as an operator, so even handoff tests can run headlessly.
    @contextmanager
    def playwright():
        with sync_playwright() as p:
            launch = p.chromium.launch
            monkeypatch.setattr(p.chromium, "launch", lambda **kwargs: launch(**{**kwargs, "headless": True}))
            yield p

    monkeypatch.setattr(runner, "sync_playwright", playwright)

    def run(member_id, headed=False):
        return runner.do_run("replay", member_id,
                             artifact=str(runner.ROOT / "artifacts/get_savings_balance_v1.json"),
                             headed=headed)

    return run


def test_real_replay_success(browser_run):
    result = browser_run("84621")
    assert result.status == "success"
    assert result.outputs == {"balance": "7210.38", "currency": "USD", "account_status": "ACTIVE"}
    assert result.llm_decision_calls == 0
    assert (runner.EVIDENCE / result.run_id / "replay_success.png").stat().st_size > 1000


def test_real_member_not_found(browser_run):
    result = browser_run("00000")
    assert result.status == "business_outcome"
    assert result.outcome_code == "MEMBER_NOT_FOUND"


def test_real_headless_gate_has_no_operator_session(browser_run):
    result = browser_run("55555")
    assert result.status == "needs_human"
    request = json.loads((runner.EVIDENCE / result.run_id / "intervention_request.json").read_text())
    assert request["control_owner"] == "none"
    assert request["live_session_available"] is False
    assert request["step"] == 6


def test_real_gate_with_simulated_operator(browser_run, monkeypatch):
    pages = []

    def transfer(page, directory, headed, **kwargs):
        pages.append(page)

        def release(_):
            page.get_by_role("link", name="Approve demo verification").click()
            return ""

        monkeypatch.setattr("builtins.input", release)
        return handoff(page, directory, headed, **kwargs)

    monkeypatch.setattr(runner, "handoff", transfer)
    result = browser_run("55555", headed=True)
    assert result.status == "success"
    assert result.outputs["balance"] == "250.00"
    assert len(pages) == 1
    actions = json.loads((runner.EVIDENCE / result.run_id / "operator_actions.json").read_text())
    assert actions["human_action_count"] == 1
    assert actions["events"][0]["control"] == "Approve demo verification"


def test_real_blocked_click_with_simulated_operator(browser_run, monkeypatch):
    original, attempts, blocked_pages = Surface.perform, [], []

    def perform(surface, step, params, outputs):
        if step.action == "click" and step.name == "Search":
            attempts.append(step)
            blocked_pages.append(surface.page)
            surface.page.evaluate("""() => {
                const dialog = document.createElement('dialog');
                dialog.innerHTML = '<p>Unexpected dialog</p><button>Dismiss dialog</button>';
                dialog.querySelector('button').onclick = () => dialog.remove();
                document.body.append(dialog);
                dialog.showModal();
            }""")
            raise PlaywrightTimeout("Injected blocked click")
        return original(surface, step, params, outputs)

    def transfer(page, directory, headed, **kwargs):
        assert page is blocked_pages[0]

        def release(_):
            page.get_by_role("button", name="Dismiss dialog").click()
            page.get_by_role("button", name="Search", exact=True).click()
            return ""

        monkeypatch.setattr("builtins.input", release)
        return handoff(page, directory, headed, **kwargs)

    monkeypatch.setattr(Surface, "perform", perform)
    monkeypatch.setattr(runner, "handoff", transfer)
    result = browser_run("84621", headed=True)
    assert result.status == "success"
    assert result.llm_decision_calls == 0
    assert len(attempts) == 1
    request = json.loads((runner.EVIDENCE / result.run_id / "intervention_request.json").read_text())
    assert request["reason"] == "REPLAY_BLOCKED"
    actions = json.loads((runner.EVIDENCE / result.run_id / "operator_actions.json").read_text())
    assert actions["human_action_count"] == 2


def test_walkthrough_autoadvances_and_pauses_for_verification(bank_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(bank_url + "/automation")
            page.get_by_label("Member ID").fill("84621")
            page.get_by_role("button", name="Start walkthrough").click()
            page.wait_for_url("**/automation/run?member_id=84621&step=4", timeout=15000)
            assert page.get_by_role("cell", name="USD 7210.38", exact=True).is_visible()
            page.goto(bank_url + "/automation/run?member_id=55555&step=4")
            assert page.get_by_text("Operator verification required", exact=True).is_visible()
            assert page.locator("[data-auto-next]").count() == 0
        finally:
            browser.close()
