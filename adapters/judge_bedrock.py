# adapters/judge_bedrock.py — SDD §5 / D7 / BUILD_PROMPTS M9
import os
from typing import Protocol
from core.quantize import quantize
from core.types import Requirement, RequirementJudgement, ResumeText


class Judge(Protocol):
    """Protocol for resume judgement providers."""

    def judge(self, resume: ResumeText, req: Requirement) -> RequirementJudgement:
        ...


class BedrockJudge:
    """AWS Bedrock Judge adapter.

    Refuses execution under pytest per Determinism Charter D7.
    Quantizes model's float confidence at the boundary and never returns a float into core.
    """

    def __init__(
        self,
        model_id: str = "anthropic.claude-3-sonnet",
        prompt_version: str = "v1",
    ) -> None:
        if "PYTEST_CURRENT_TEST" in os.environ:
            raise RuntimeError("BedrockJudge is disabled under pytest per Determinism Charter D7")
        self.model_id = model_id
        self.prompt_version = prompt_version

    def judge(self, resume: ResumeText, req: Requirement) -> RequirementJudgement:
        # Live implementation calls AWS Bedrock API
        raise NotImplementedError("Live Bedrock API calls not allowed in test/offline environment")
