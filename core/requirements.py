# core/requirements.py — SDD §3 / BUILD_PROMPTS M7
import re
from core.ids import content_id
from core.normalize import normalize_ws
from core.types import Bp, Requirement, RequirementId, Sha256


def build_requirements(
    raw: tuple[dict, ...],
    jd_sha: Sha256,
) -> tuple[Requirement, ...]:
    """Build Requirement objects from raw extracted requirements dicts.

    Asserts that weights sum to exactly 10000 basis points.
    If input weights do not sum to 10000, normalizes them using integer arithmetic
    and assigns any remainder to the highest-weight requirement.
    Ensures deterministic output sorted by Requirement.id (D4).

    Raises:
        ValueError: if raw is empty, has negative weights, or non-positive total weight.
        TypeError: if any weight is a float or bool.
    """
    if not raw:
        raise ValueError("Requirements list cannot be empty")

    raw_weights: list[int] = []
    norm_texts: list[str] = []
    req_ids: list[RequirementId] = []
    tokens_list: list[tuple[str, ...]] = []

    for d in raw:
        w = d.get("weight_bp", d.get("weight"))
        if isinstance(w, bool) or not isinstance(w, int):
            raise TypeError(f"Weight must be an integer Bp, got {type(w).__name__}")
        if w < 0:
            raise ValueError(f"Weight cannot be negative: {w}")
        raw_weights.append(w)

        text = d.get("text", "")
        norm_text = normalize_ws(text)
        norm_texts.append(norm_text)

        if "id" in d and d["id"]:
            req_id = RequirementId(str(d["id"]))
        else:
            req_id = RequirementId(content_id(str(jd_sha), norm_text))
        req_ids.append(req_id)

        if "tokens" in d and d["tokens"] is not None:
            tokens = tuple(sorted(set(str(t).lower() for t in d["tokens"])))
        else:
            tokens = tuple(sorted(set(re.findall(r"\b[a-zA-Z0-9]+\b", norm_text.lower()))))
        tokens_list.append(tokens)

    total_weight = sum(raw_weights)
    if total_weight <= 0:
        raise ValueError("Total requirement weight must be positive")

    if total_weight == 10000:
        final_weights = [Bp(w) for w in raw_weights]
    else:
        # Integer normalization: scaled = (w * 10000) // total
        scaled_weights = [(w * 10000) // total_weight for w in raw_weights]
        remainder = 10000 - sum(scaled_weights)

        # Assign remainder to highest-weight requirement.
        # Tie-break deterministically by req_id so shuffled input produces identical result (D4).
        highest_idx = max(
            range(len(raw)),
            key=lambda i: (raw_weights[i], req_ids[i]),
        )
        scaled_weights[highest_idx] += remainder
        final_weights = [Bp(w) for w in scaled_weights]

    assert sum(final_weights) == 10000, f"Weights must sum to exactly 10000, got {sum(final_weights)}"

    reqs: list[Requirement] = []
    for i in range(len(raw)):
        req = Requirement(
            id=req_ids[i],
            text=norm_texts[i],
            tokens=tokens_list[i],
            weight_bp=final_weights[i],
        )
        reqs.append(req)

    return tuple(sorted(reqs, key=lambda r: r.id))
