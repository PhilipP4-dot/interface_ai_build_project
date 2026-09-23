"""Small, validated capability contract for the first browser slice."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Step(Contract):
    action: Literal["fill", "click", "read"]
    role: Literal["textbox", "button", "link", "status"]
    name: str = Field(min_length=1)
    parameter: Literal["member_id", "new_balance"] | None = None
    output: Literal["balance"] | None = None


class RecoveryRule(Contract):
    trigger: Literal["operator_review", "session_expired"]
    action: Literal["continue_review", "restore_session"]

    @model_validator(mode="after")
    def validate_pair(self) -> Self:
        expected = {"operator_review": "continue_review", "session_expired": "restore_session"}
        if self.action != expected[self.trigger]:
            raise ValueError("Recovery action does not match trigger")
        return self


class Capability(Contract):
    schema_version: Literal["1.0", "1.1", "1.2"]
    name: Literal["savings_balance", "update_savings_balance"]
    provenance: Literal[
        "hand_authored_fixture",
        "llm_discovery",
        "llm_discovery_recovered",
        "offline_test",
        "human_assisted_discovery",
    ]
    input_type: Literal[
        "member_id: five-digit string",
        "member_id: five-digit string; new_balance: USD decimal string",
    ]
    output_type: Literal["balance: USD decimal string"]
    steps: list[Step] = Field(min_length=1, max_length=20)
    checkpoint: str = Field(min_length=1)
    recoveries: list[RecoveryRule] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        updates = [i for i, step in enumerate(self.steps) if step.name == "Update savings balance"]
        amounts = [i for i, step in enumerate(self.steps) if step.parameter == "new_balance"]
        if self.name == "update_savings_balance":
            if (
                self.schema_version != "1.2"
                or len(updates) != 1
                or not amounts
                or amounts[-1] >= updates[0]
            ):
                raise ValueError(
                    "Update workflow requires version 1.2, amount entry, and one update"
                )
            if not any(step.output == "balance" for step in self.steps[updates[0] + 1 :]):
                raise ValueError("Update workflow must read back its result")
            if self.input_type != "member_id: five-digit string; new_balance: USD decimal string":
                raise ValueError("Update workflow requires both inputs")
        elif updates or amounts:
            raise ValueError("Lookup workflow cannot update a balance")
        return self


class Inputs(Contract):
    member_id: str = Field(pattern=r"^[0-9]{5}$")
    new_balance: str | None = Field(
        default=None, pattern=r"^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,2})?$"
    )


class Result(Contract):
    status: Literal["success", "business_outcome", "failure"]
    code: str
    outputs: dict[str, str] = Field(default_factory=dict)
    step: int | None = None
    expected: str | None = None
    observed: str | None = None

    def with_details(self, step: int = 0) -> "Result":
        """Fill safe diagnostic defaults without incorporating page text or inputs."""
        if self.status == "success":
            return self
        details = {
            "target_blocked": ("Target permitted by policy", "Target rejected by allowlist"),
            "action_blocked": ("Action permitted by policy", "Action rejected by allowlist"),
            "output_missing": ("Declared balance extracted", "Balance output absent"),
            "output_invalid": ("USD decimal balance", "Balance format invalid"),
            "operator_required": ("Available human operator", "Review requires a visible session"),
            "resume_state_invalid": (
                "Original member and recognized results or details",
                "Resume checks failed",
            ),
            "human_owns_session": ("Automation owns session", "Human owns session"),
            "step_limit": ("Completion within step limit", "Step limit reached"),
            "browser_unavailable": ("Browser session available", "Browser launch failed"),
        }
        expected, observed = details.get(
            self.code, ("Operation completes within configured constraints", "Operation stopped")
        )
        return self.model_copy(
            update={
                "step": self.step if self.step is not None else step,
                "expected": self.expected or expected,
                "observed": self.observed or observed,
            }
        )
