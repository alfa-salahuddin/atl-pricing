"""
Pricing computation helpers — Alfa Tradelinks Pte Ltd

Margin convention: MARKUP ON COST
  FOB price = net_cost_sgd × (1 + margin_pct / 100)
  e.g. cost SGD 11.50, margin 14% → 11.50 × 1.14 = SGD 13.11

Rounding: always round UP to nearest 0.10
  e.g. 13.11 → 13.20,  13.20 → 13.20,  13.21 → 13.30
"""

import math

BASE_CURRENCY = "SGD"


def round_up_to_10_cents(value: float) -> float:
    """Always round up to the nearest 0.10."""
    return math.ceil(round(value * 10, 8)) / 10


def resolve_rate(cost_currency: str, rate_obj) -> tuple[float, str]:
    """Return (rate, direction). SGD always returns (1.0, multiply)."""
    if cost_currency and cost_currency.upper() == BASE_CURRENCY:
        return 1.0, "multiply"
    if rate_obj:
        return rate_obj.rate, rate_obj.direction
    return 1.0, "multiply"


def compute_net_cost_orig(cost_price: float, discount_pct: float, cost_additions: float) -> float:
    """Net cost in the original supplier currency."""
    discounted = cost_price * (1 - discount_pct / 100)
    return round(discounted + cost_additions, 6)


def compute_net_cost_sgd(net_cost_orig: float, rate: float, direction: str) -> float:
    """Convert net cost to SGD using the exchange rate."""
    if direction == "multiply":
        return round(net_cost_orig * rate, 6)
    elif direction == "divide":
        if rate == 0:
            return 0.0
        return round(net_cost_orig / rate, 6)
    return net_cost_orig


def compute_fob_price(net_cost_sgd: float, margin_pct: float) -> float:
    """
    FOB price = net_cost_sgd × (1 + margin_pct / 100)
    Always rounded UP to the nearest 0.10.
    """
    raw = net_cost_sgd * (1 + margin_pct / 100)
    return round_up_to_10_cents(raw)


def compute_all(
    cost_price:    float,
    discount_pct:  float,
    cost_additions:float,
    rate:          float,
    direction:     str,
    margin_pct:    float,
    cost_currency: str = "",
) -> dict:
    """
    Full pricing chain. Returns dict with all computed values.
    If cost_currency is SGD, rate is auto-set to 1.0 multiply.
    """
    if cost_currency and cost_currency.upper() == BASE_CURRENCY:
        rate      = 1.0
        direction = "multiply"

    net_cost_orig = compute_net_cost_orig(cost_price, discount_pct, cost_additions)
    net_cost_sgd  = compute_net_cost_sgd(net_cost_orig, rate, direction)
    fob_price_sgd = compute_fob_price(net_cost_sgd, margin_pct)

    return {
        "net_cost_orig":  net_cost_orig,
        "net_cost_sgd":   net_cost_sgd,
        "fob_price_sgd":  fob_price_sgd,
        "rate_used":      rate,
        "direction_used": direction,
    }
