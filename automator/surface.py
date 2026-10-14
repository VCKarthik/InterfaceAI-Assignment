import re
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.parse import urljoin
from playwright.sync_api import Page
from .models import Step
from .policy import Policy, PolicyError


class Surface:
    """Observe browser pages and execute capability steps through Playwright."""
    def __init__(self, page: Page, policy: Policy):
        self.page = page
        self.policy = policy

    def observe(self) -> dict:
        self.policy.check_url(self.page.url)
        body = self.page.locator("body").inner_text(timeout=5000)
        controls = self.page.locator("input,button,a").evaluate_all('''els => els.map(e => ({
          role: e.tagName === 'A' ? 'link' : e.tagName === 'BUTTON' ? 'button' : 'textbox',
          name: (e.tagName === 'INPUT' ? (document.querySelector('label[for="'+e.id+'"]')?.innerText || e.getAttribute('aria-label') || '') : e.innerText).trim().slice(0,70)
        }))''')
        # Query strings may contain identifiers; send visible text instead of raw HTML.
        return {"path": self.page.url.split("?")[0].replace(self.policy.base_url, ""),
                "visible_text": body[:3500], "controls": controls[:30]}

    def locator(self, step: Step):
        if step.kind == "role":
            return self.page.get_by_role(step.role, name=step.name, exact=True)
        if step.kind == "label":
            return self.page.get_by_label(step.name, exact=True)
        if step.kind == "text":
            return self.page.get_by_text(step.name, exact=True)
        if step.kind == "table_row":
            return self.page.get_by_role("row", name=re.compile(re.escape(step.name)))
        raise ValueError(f"Unsupported locator kind: {step.kind}")

    def perform(self, step: Step, params: dict, outputs: dict):
        self.policy.check_url(self.page.url)
        self.policy.check_step(step.action, step.name)
        if step.action == "finish":
            return
        el = self.locator(step)
        if step.action == "fill":
            if step.value != "{{member_id}}":
                raise PolicyError("Fill must refer to a typed parameter; no literal PII")
            el.fill(params["member_id"], timeout=6500)
        elif step.action == "click":
            if step.kind in {"role", "text"}:
                href = el.get_attribute("href", timeout=6500)
                if href:
                    self.policy.check_url(urljoin(self.page.url, href))
            el.click(timeout=6500)
        elif step.action == "extract":
            if step.kind != "table_row" or step.output_key not in {"balance", "account_status"}:
                raise PolicyError("Extraction must use allowlisted table rows/output keys")
            raw = el.locator("td").first.inner_text(timeout=6500).strip()
            if step.output_key == "balance":
                try:
                    amount = Decimal(raw.replace("$", "").replace(",", ""))
                except InvalidOperation as e:
                    raise ValueError("Invalid balance format") from e
                if not amount.is_finite():
                    raise ValueError("Invalid balance format")
                outputs["balance"] = f"{amount:.2f}"
                outputs["currency"] = "USD" if raw.startswith("$") else "UNKNOWN"
            else:
                outputs["account_status"] = raw
        self.policy.check_url(self.page.url)

    def business_outcome(self) -> Optional[str]:
        if self.page.get_by_text("Member not found", exact=True).count():
            return "MEMBER_NOT_FOUND"
        return None

    def needs_human(self) -> bool:
        return self.blocking_state() in {"OPERATOR_VERIFICATION_REQUIRED", "SESSION_EXPIRED"}

    def blocking_state(self) -> Optional[str]:
        for label, code in (("Operator verification required", "OPERATOR_VERIFICATION_REQUIRED"),
                            ("Session expired", "SESSION_EXPIRED"),
                            ("Permission denied", "PERMISSION_DENIED")):
            if self.page.get_by_text(label, exact=True).count():
                return code
        return None

    def verify_success(self, outputs: dict, success_text: str = "Current Balance") -> bool:
        self.policy.check_url(self.page.url)
        return (self.page.get_by_text(success_text, exact=True).count() > 0
                and {"balance", "currency", "account_status"}.issubset(outputs)
                and outputs["currency"] == "USD"
                and bool(outputs["account_status"]))
