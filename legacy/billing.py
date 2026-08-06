# legacy/billing.py
# Python 2 legacy implementation. Runs only inside the python:2.7-slim sandbox.


def calculate_total(items, tax_rate):
    """items: list of dicts like {"price": float, "qty": int}"""
    subtotal = 0
    for item in items:
        subtotal += item["price"] * item["qty"]
    return subtotal * (1 + tax_rate)
