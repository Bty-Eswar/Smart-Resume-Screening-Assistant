# core/quantize.py — SDD §0 C2 / D1
from decimal import Decimal, ROUND_HALF_EVEN
from core.types import Bp


def quantize(x: float) -> Bp:
    """Quantize float score in [0.0, 1.0] to basis points (0..10000) via round-half-even.

    Uses Decimal(str(x)) rather than Decimal(x) to prevent binary float representation noise.
    Raises ValueError if x is outside [0.0, 1.0].
    """
    if not (0.0 <= x <= 1.0):
        raise ValueError(f"Score {x} outside [0.0, 1.0]")
    # Scale to basis points, then round to nearest integer using round-half-even
    d = Decimal(str(x)) * Decimal("10000")
    rounded = d.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
    return Bp(int(rounded))
