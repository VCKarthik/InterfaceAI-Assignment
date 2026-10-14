import pytest
from automator.models import Capability, Step
from automator.policy import Policy, PolicyError


def test_artifact_contract():
    artifact = Capability(steps=[Step(action="fill", kind="label", name="Member ID", value="{{member_id}}")])
    recovered = Capability.model_validate_json(artifact.model_dump_json())
    assert recovered.inputs["member_id"]["required"] is True


def test_policy():
    p = Policy("http://127.0.0.1:8000")
    p.check_url("http://127.0.0.1:8000/servicing")
    with pytest.raises(PolicyError):
        p.check_url("https://evil.example/servicing")
    with pytest.raises(PolicyError):
        p.check_step("click", "Delete Account")
