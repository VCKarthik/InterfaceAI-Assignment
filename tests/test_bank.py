from fastapi.testclient import TestClient
from demo_bank.main import app, render_replay_path

client = TestClient(app)


def test_search_and_balance():
    assert "Open Member" in client.get("/members/search?member_id=12345").text
    assert "$4582.39" in client.get("/members/12345/accounts/savings").text


def test_not_found():
    assert "Member not found" in client.get("/members/search?member_id=00000").text


def test_verification_gate():
    assert "Operator verification required" in client.get("/members/55555/accounts/savings").text
    assert "$250.00" in client.get("/members/55555/accounts/savings?verified=1").text


def test_automation_page():
    response = client.get("/automation")
    assert response.status_code == 200
    assert "Savings Balance Walkthrough" in response.text
    assert "Member ID" in response.text


def test_visible_automation_steps():
    first = client.get("/automation/run?member_id=84621")
    assert "Walkthrough step 1" in first.text
    assert "data-auto-next" in first.text

    account_list = client.get("/automation/run?member_id=84621&step=3")
    assert "Walkthrough step 4" in account_list.text
    assert "Open Savings" in account_list.text

    final = client.get("/automation/run?member_id=84621&step=4")
    assert "Current Balance" in final.text
    assert "USD 7210.38" in final.text
    assert "Saved capability reference" in final.text


def test_replay_path_shows_mapping():
    html = render_replay_path("84621", {
        "balance": "7210.38",
        "currency": "USD",
        "account_status": "ACTIVE",
    })
    assert "Open account list" in html
    assert "Open savings account" in html
    assert "Read savings balance" in html
    assert "balance = USD 7210.38" in html
