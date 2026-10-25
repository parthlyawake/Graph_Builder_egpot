"""Business calculations for the order service."""


def calculate_total(items):
    """Return the sum of product prices in an order."""
    return sum(item["price"] for item in items)
