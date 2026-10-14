from typing import Literal, Optional
from pydantic import BaseModel, Field

Action = Literal["fill", "click", "extract", "finish"]
Kind = Literal["role", "label", "text", "table_row", "none"]


class Step(BaseModel):
    action: Action
    kind: Kind = "none"
    name: str = ""
    role: str = ""
    value: str = ""
    output_key: str = ""
    rationale: str = ""


class AgentChoice(Step):
    """A model-selected action validated against the supported step schema."""
    pass


class Capability(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    capability_id: str = "get_savings_balance"
    capability_version: str = "1.0.0"
    target_app: str = "demo_legacy_credit_union"
    entry_path: str = "/servicing"
    inputs: dict = Field(default_factory=lambda: {"member_id": {"type": "string", "required": True}})
    outputs: dict = Field(default_factory=lambda: {
        "balance": {"type": "decimal_string"}, "currency": {"type": "string"},
        "account_status": {"type": "string"}})
    success_text: str = "Current Balance"
    steps: list[Step]


class RunError(BaseModel):
    phase: str
    step: Optional[int] = None
    expected: dict = Field(default_factory=dict)
    observed: dict = Field(default_factory=dict)


class RunResult(BaseModel):
    run_id: str
    mode: Literal["discovery", "replay"]
    status: Literal["success", "business_outcome", "needs_human", "failure"]
    outcome_code: str
    outputs: dict = Field(default_factory=dict)
    artifact_path: Optional[str] = None
    llm_decision_calls: int = 0
    message: str = ""
    error: Optional[RunError] = None
