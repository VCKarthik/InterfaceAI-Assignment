from pathlib import Path
from automator.models import Capability


def test_illustrative_example_contract():
    root = Path(__file__).resolve().parents[1]
    cap = Capability.model_validate_json((root / "examples/ILLUSTRATIVE_NOT_DISCOVERY_EVIDENCE.json").read_text())
    assert [step.action for step in cap.steps][-1] == "finish"
    assert cap.capability_id == "get_savings_balance"
    assert {step.output_key for step in cap.steps if step.action == "extract"} == {"balance", "account_status"}
