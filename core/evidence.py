# core/evidence.py — SDD §3 / D8 / BUILD_PROMPTS M7
from dataclasses import replace
from core.types import RequirementJudgement, ResumeText


def validate_evidence(
    j: RequirementJudgement,
    r: ResumeText,
) -> RequirementJudgement:
    """Validate evidence span against resume text (SDD §3 / D8).

    Returns j unchanged if r.text[j.evidence.start:j.evidence.end] == j.evidence.text.
    Otherwise returns a copy with met=False, evidence=None.

    Strictly checks character offsets, never a loose substring check.
    """
    if j.evidence is None:
        if not j.met:
            return j
        # met=True without evidence is invalid
        return replace(j, met=False, evidence=None)

    start = j.evidence.start
    end = j.evidence.end

    if start < 0 or end > len(r.text) or start > end:
        return replace(j, met=False, evidence=None)

    actual_slice = r.text[start:end]
    if actual_slice == j.evidence.text and j.met:
        return j

    return replace(j, met=False, evidence=None)
