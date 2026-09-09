# eval/checks.py — SDD §2 / D13 Pre-declared Threshold Checker
import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

DEFAULT_THRESHOLDS_PATH = Path("eval/thresholds.json")


class UndeclaredThreshold(Exception):
    """Raised when check() is invoked with an undeclared threshold key (D13)."""
    pass


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    target: float | int
    comparator: str
    measured: float | int
    passed: bool
    description: str


def load_thresholds(path: Path | str = DEFAULT_THRESHOLDS_PATH) -> dict[str, dict]:
    """Load pre-declared thresholds from JSON file. Read-only."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Thresholds file not found at {p}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


_LOADED_THRESHOLDS = load_thresholds()


def check(name: str, measured: float | int | Fraction) -> CheckResult:
    """Evaluate a measured metric against pre-declared thresholds.

    Raises UndeclaredThreshold if name is not declared in thresholds.json (D13).
    Never writes or mutates thresholds.json.
    """
    if name not in _LOADED_THRESHOLDS:
        raise UndeclaredThreshold(
            f"Undeclared threshold comparison '{name}' (D13 violation): threshold must be declared in thresholds.json"
        )

    meta = _LOADED_THRESHOLDS[name]
    target = meta["target"]
    comparator = meta["comparator"]
    description = meta.get("description", "")

    # Normalize measured value for comparison
    val = float(measured) if isinstance(measured, Fraction) else measured

    if comparator == ">=":
        passed = bool(val >= target)
    elif comparator == "<=":
        passed = bool(val <= target)
    elif comparator == ">":
        passed = bool(val > target)
    elif comparator == "<":
        passed = bool(val < target)
    elif comparator == "==":
        passed = bool(val == target)
    else:
        raise ValueError(f"Unsupported comparator '{comparator}' for threshold '{name}'")

    return CheckResult(
        name=name,
        target=target,
        comparator=comparator,
        measured=val,
        passed=passed,
        description=description,
    )


# Declared call sites for each threshold in thresholds.json (AST-scanned for completeness)
def check_t1_parse_success(measured: float | int | Fraction) -> CheckResult:
    return check("t1_parse_success", measured)


def check_t2_evidence_validity(measured: float | int | Fraction) -> CheckResult:
    return check("t2_evidence_validity", measured)


def check_t3_self_consistency_jaccard(measured: float | int | Fraction) -> CheckResult:
    return check("t3_self_consistency_jaccard", measured)


def check_t4_bias_score_delta(measured: float | int | Fraction) -> CheckResult:
    return check("t4_bias_score_delta", measured)


def check_t4_bias_rank_shift(measured: float | int | Fraction) -> CheckResult:
    return check("t4_bias_rank_shift", measured)


def check_t5_win_claim_lift(measured: float | int | Fraction) -> CheckResult:
    return check("t5_win_claim_lift", measured)


def check_t6_latency_wall_clock(measured: float | int | Fraction) -> CheckResult:
    return check("t6_latency_wall_clock", measured)


def check_t7_cost_max_usd(measured: float | int | Fraction) -> CheckResult:
    return check("t7_cost_max_usd", measured)


def check_t8_label_agreement_kappa(measured: float | int | Fraction) -> CheckResult:
    return check("t8_label_agreement_kappa", measured)
