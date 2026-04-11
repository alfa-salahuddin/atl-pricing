"""
Pricing computation helpers.
All FOB price calculations flow through here so the logic is
defined in one place and reused across the product form, uploads, and exports.

Rule: if cost_currency == SGD (or any same-currency scenario),
      exchange rate defaults to 1.00 multiply automatically.
"""

# The base/reporting currency for Alfa Tradelinks
BASE_CURRENCY = "SGD"


def resolve_rate(cost_currency: str, rate_obj) -> tuple[float, str]:
    """
    Returns (rate, direction) to use for conversion.
    If cost_currency matches BASE_CURRENCY, returns (1.0, 'multiply')
    regardless of whether a rate_obj is provided.
    """
    if cost_currency and cost_currency.upper() == BASE_CURRENCY:
        return 1.0, "multiply"
    if rate_obj:
        return rate_obj.rate, rate_obj.direction
    # Fallback — no rate available, return 1.0 (will be flagged elsewhere)
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
    """FOB price in SGD after applying margin."""
    if margin_pct >= 100:
        return 0.0
    return round(net_cost_sgd / (1 - margin_pct / 100), 4)


def compute_all(
    cost_price: float,
    discount_pct: float,
    cost_additions: float,
    rate: float,
    direction: str,
    margin_pct: float,
    cost_currency: str = "",
) -> dict:
    """
    Run the full pricing chain and return all computed values.
    If cost_currency is SGD, overrides rate to 1.0 multiply automatically.
    Returns a dict with keys: net_cost_orig, net_cost_sgd, fob_price_sgd, rate_used, direction_used
    """
    # Auto-apply SGD rule
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
