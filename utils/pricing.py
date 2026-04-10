"""
Pricing computation helpers.
All FOB price calculations flow through here so the logic is
defined in one place and reused across the product form, uploads, and exports.
"""


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
) -> dict:
    """
    Run the full pricing chain and return all computed values.
    Returns a dict with keys: net_cost_orig, net_cost_sgd, fob_price_sgd
    """
    net_cost_orig = compute_net_cost_orig(cost_price, discount_pct, cost_additions)
    net_cost_sgd  = compute_net_cost_sgd(net_cost_orig, rate, direction)
    fob_price_sgd = compute_fob_price(net_cost_sgd, margin_pct)
    return {
        "net_cost_orig":  net_cost_orig,
        "net_cost_sgd":   net_cost_sgd,
        "fob_price_sgd":  fob_price_sgd,
    }

