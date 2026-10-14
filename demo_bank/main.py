"""Local credit-union demo with synthetic members and balances."""
import json
from html import escape
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Demo Legacy Credit Union")
ROOT = Path(__file__).resolve().parents[1]
DISCOVERED_ARTIFACT = ROOT / "artifacts" / "get_savings_balance_v1.json"
AUTOMATION_DELAY_MS = 1200
MEMBERS = {
    "12345": {"name": "Demo Member Alpha", "balance": "4582.39", "status": "ACTIVE"},
    "84621": {"name": "Demo Member Beta", "balance": "7210.38", "status": "ACTIVE"},
    "55555": {"name": "Demo Member Gamma", "balance": "250.00", "status": "ACTIVE"},
}

# Browser-local events let the runner capture operator actions during handoff.
# Record control labels and change events, not entered values.
TRACKER = """<script>
document.addEventListener('click', function(e) {
  var el = e.target.closest('a,button'); if (!el) return;
  var items = JSON.parse(localStorage.getItem('operator_events') || '[]');
  items.push({kind:'click', control:(el.innerText || el.getAttribute('aria-label') || el.tagName).slice(0,45), at:Date.now()});
  localStorage.setItem('operator_events',JSON.stringify(items.slice(-50)));
}, true);
document.addEventListener('change', function(e) {
  if (!e.target.matches('input,textarea,select')) return;
  var items = JSON.parse(localStorage.getItem('operator_events') || '[]');
  items.push({kind:'field_changed',control:e.target.getAttribute('aria-label') || 'form control',at:Date.now()});
  localStorage.setItem('operator_events',JSON.stringify(items.slice(-50)));
}, true);
</script>"""
STYLE = """<style>
body{font:15px Arial,sans-serif;background:#e5e7eb;margin:38px;color:#1f2937}
main{max-width:760px;margin:auto;background:#fff;border:1px solid #9ca3af;padding:26px}
h1{font-size:24px;margin:0 0 8px;color:#153456}nav{margin:14px 0;background:#eff6ff;padding:12px}
label{display:block;margin:18px 0 8px;font-weight:bold}input{padding:9px;font-size:15px}
button,.btn{display:inline-block;background:#194b75;color:white;border:0;padding:10px 16px;cursor:pointer;text-decoration:none;margin:8px 4px 8px 0}
table{border-collapse:collapse;width:100%;margin:20px 0}th,td{border:1px solid #9ca3af;padding:11px;text-align:left}
.notice{background:#fff3cd;padding:15px;border:1px solid #d8ac44}.error{color:#922}
small{color:#666}
.path-note{margin:8px 0 0;color:#4b5563}
.step-banner{background:#ecfdf5;border:1px solid #10b981;padding:12px;margin:14px 0}
.step-banner strong{display:block;margin-bottom:4px}
</style>"""


def shell(body: str) -> HTMLResponse:
    return HTMLResponse(
        '<!doctype html><html><head><meta charset="utf-8"><title>Demo Credit Union</title>'
        + STYLE + TRACKER + '</head><body><main><h1>Legacy Credit Union</h1>'
        + '<small>SYNTHETIC TEST SYSTEM — NO REAL FINANCIAL DATA</small>'
        + body + '</main></body></html>'
    )


def auto_click_script(selector: str = "[data-auto-next]") -> str:
    return ("<script>setTimeout(function(){"
            f"var el=document.querySelector({json.dumps(selector)});"
            f"if(el){{el.click();}}"
            f"}}, {AUTOMATION_DELAY_MS});</script>")


def step_banner(number: int, label: str) -> str:
    return ('<div class="step-banner">'
            f'<strong>Walkthrough step {number}</strong>'
            f'{escape(label)}</div>')


def render_replay_path(member_id: str, outputs: dict) -> str:
    artifact = json.loads(DISCOVERED_ARTIFACT.read_text())
    labels = {
        "Member ID": "Enter member ID",
        "Search": "Search members",
        "Open Member": "Open selected member profile",
        "Accounts": "Open account list",
        "Open Savings": "Open savings account",
        "Current Balance": "Read savings balance",
        "Status": "Read account status",
    }
    rows = []
    for index, step in enumerate(artifact.get("steps", []), start=1):
        action = step.get("action", "")
        name = step.get("name", "")
        output_key = step.get("output_key", "")
        target = labels.get(name) or ("Verify required outputs" if action == "finish" else name)
        detail = ""
        if action == "fill":
            detail = f"Uses member ID {escape(member_id)}"
        elif action == "click":
            detail = f"Clicks {escape(name)}"
        elif action == "extract":
            value = outputs.get(output_key, "")
            if output_key == "balance" and value:
                value = f'{outputs.get("currency", "USD")} {value}'
            detail = f"{escape(output_key)} = {escape(str(value))}"
        elif action == "finish":
            detail = "Confirms Current Balance was reached"
        rows.append('<tr>'
                    f'<td>{index}</td>'
                    f'<td>{escape(action)}</td>'
                    f'<td>{escape(target)}</td>'
                    f'<td>{detail}</td>'
                    '</tr>')
    return ('<h2>Saved capability reference</h2>'
            '<table><tr><th>#</th><th>Action</th><th>Mapping</th><th>Demo value</th></tr>'
            + ''.join(rows) + '</table>')


@app.get("/servicing", response_class=HTMLResponse)
def servicing():
    return shell('''<nav>Member Servicing Console</nav>
<h2>Find a Member</h2><form action="/members/search" method="get">
<label for="member">Member ID</label><input id="member" name="member_id" autocomplete="off" />
<button type="submit">Search</button></form>''')


@app.get("/automation", response_class=HTMLResponse)
def automation():
    artifact_note = ""
    if not DISCOVERED_ARTIFACT.exists():
        artifact_note = '<div role="alert" class="error">Discovered artifact not found</div>'
    return shell('''<nav>Workflow Walkthrough</nav>
<h2>Savings Balance Walkthrough</h2>'''
                 + artifact_note
                 + '''<form action="/automation/run" method="get">
<label for="automation-member">Member ID</label>
<input id="automation-member" name="member_id" autocomplete="off" pattern="[0-9]{5}" maxlength="5" />
<button type="submit">Start walkthrough</button></form>''')


@app.get("/automation/run", response_class=HTMLResponse)
def automation_run(member_id: str = "", step: int = 0, verified: int = 0):
    if not member_id.isdigit() or len(member_id) != 5:
        return shell('<nav>Automation Runner</nav><div role="alert" class="error">'
                     'Member ID must be exactly five digits</div>'
                     '<a class="btn" href="/automation">Back</a>')
    if not DISCOVERED_ARTIFACT.exists():
        return shell('<nav>Automation Runner</nav><div role="alert" class="error">'
                     'Discovered artifact not found</div>'
                     '<a class="btn" href="/automation">Back</a>')
    if step < 0 or step > 4:
        return shell('<nav>Automation Runner</nav><div role="alert" class="error">'
                     'Unknown automation step</div>'
                     '<a class="btn" href="/automation">Back</a>')

    member_value = escape(member_id)
    if step == 0:
        return shell('<nav>Member Servicing Console</nav>'
                     + step_banner(1, "Member lookup")
                     + '<h2>Find a Member</h2>'
                     '<form action="/automation/run" method="get">'
                     '<input type="hidden" name="step" value="1" />'
                     f'<label for="member">Member ID</label><input id="member" name="member_id" value="{member_value}" autocomplete="off" />'
                     '<button data-auto-next type="submit">Search</button></form>'
                     + auto_click_script())

    if step == 1:
        if member_id not in MEMBERS:
            return shell('<nav>Member Search</nav>'
                         + step_banner(2, "No matching member")
                         + '<div role="alert" class="error">Member not found</div>'
                         '<a class="btn" href="/automation">Run another</a>')
        member = MEMBERS[member_id]
        return shell('<nav>Member Search Results</nav>'
                     + step_banner(2, "Search results")
                     + '<h2>Search results</h2><table>'
                     '<tr><th>Member ID</th><th>Name</th><th>Details</th></tr>'
                     f'<tr><td>{member_value}</td><td>{escape(member["name"])}</td>'
                     f'<td><a data-auto-next href="/automation/run?member_id={member_value}&step=2">Open Member</a></td></tr></table>'
                     + auto_click_script())

    if member_id not in MEMBERS:
        return shell('<nav>Automation Runner</nav><div role="alert" class="error">'
                     'Member not found</div><a class="btn" href="/automation">Run another</a>')

    member = MEMBERS[member_id]
    if step == 2:
        return shell('<nav>Member Profile</nav>'
                     + step_banner(3, "Member profile")
                     + f'<h2>{escape(member["name"])}</h2>'
                     f'<a data-auto-next class="btn" href="/automation/run?member_id={member_value}&step=3">Accounts</a>'
                     + auto_click_script())

    if step == 3:
        return shell('<nav>Member Accounts</nav>'
                     + step_banner(4, "Member accounts")
                     + '<h2>Account list</h2><table>'
                     '<tr><th>Type</th><th>View</th></tr><tr><td>Savings</td>'
                     f'<td><a data-auto-next href="/automation/run?member_id={member_value}&step=4">Open Savings</a></td></tr></table>'
                     + auto_click_script())

    if member_id == "55555" and verified != 1:
        return shell('<nav>Account Details</nav>'
                     + step_banner(5, "Verification pending")
                     + '<div role="alert" class="notice">Operator verification required</div>'
                     f'<a class="btn" href="/automation/run?member_id={member_value}&step=4&verified=1">'
                     'Approve demo verification</a>')

    outputs = {"balance": member["balance"], "currency": "USD", "account_status": member["status"]}
    balance = escape(outputs["balance"])
    status = escape(outputs["account_status"])
    return shell('<nav>Account Details</nav>'
                 + step_banner(5, "Savings account")
                 + '<h2>Savings Account</h2><table>'
                 f'<tr><th scope="row">Member ID</th><td>{member_value}</td></tr>'
                 f'<tr><th scope="row">Current Balance</th><td>USD {balance}</td></tr>'
                 f'<tr><th scope="row">Status</th><td>{status}</td></tr>'
                 '</table>'
                 + render_replay_path(member_id, outputs)
                 + '<a class="btn" href="/automation">Run another</a>')


@app.get("/members/search", response_class=HTMLResponse)
def search(member_id: str = ""):
    if member_id not in MEMBERS:
        return shell('<nav>Member Search</nav><div role="alert" class="error">Member not found</div>'
                     '<a href="/servicing">Back to search</a>')
    return shell(f'<nav>Member Search Results</nav><h2>Search results</h2>'
                 f'<table><tr><th>Member ID</th><th>Name</th><th>Details</th></tr>'
                 f'<tr><td>{escape(member_id)}</td><td>{MEMBERS[member_id]["name"]}</td>'
                 f'<td><a href="/members/{escape(member_id)}">Open Member</a></td></tr></table>')


@app.get("/members/{member_id}", response_class=HTMLResponse)
def member(member_id: str):
    if member_id not in MEMBERS:
        return shell('<div role="alert">Member not found</div>')
    return shell(f'<nav>Member Profile</nav><h2>{MEMBERS[member_id]["name"]}</h2>'
                 f'<a class="btn" href="/members/{escape(member_id)}/accounts">Accounts</a>')


@app.get("/members/{member_id}/accounts", response_class=HTMLResponse)
def accounts(member_id: str):
    if member_id not in MEMBERS:
        return shell('<div role="alert">Member not found</div>')
    return shell(f'<nav>Member Accounts</nav><h2>Account list</h2><table>'
                 f'<tr><th>Type</th><th>View</th></tr><tr><td>Savings</td>'
                 f'<td><a href="/members/{escape(member_id)}/accounts/savings">Open Savings</a></td></tr></table>')


@app.get("/members/{member_id}/accounts/savings", response_class=HTMLResponse)
def savings(member_id: str, verified: int = 0):
    if member_id not in MEMBERS:
        return shell('<div role="alert">Member not found</div>')
    if member_id == "55555" and verified != 1:
        return shell('<nav>Account Details</nav><div role="alert" class="notice">'
                     'Operator verification required</div>'
                     f'<a class="btn" href="/members/{member_id}/accounts/savings?verified=1">'
                     'Approve demo verification</a>')
    item = MEMBERS[member_id]
    return shell('<nav>Account Details</nav><h2>Savings Account</h2><table>'
                 f'<tr><th scope="row">Current Balance</th><td>${item["balance"]}</td></tr>'
                 f'<tr><th scope="row">Status</th><td>{item["status"]}</td></tr>'
                 '</table>')


@app.get("/", response_class=HTMLResponse)
def root():
    return shell('<a class="btn" href="/servicing">Open Member Servicing</a>'
                 '<a class="btn" href="/automation">Workflow Walkthrough</a>')
