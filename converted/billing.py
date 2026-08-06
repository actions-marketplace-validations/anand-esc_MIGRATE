# converted/billing.py
# Python 3 converted implementation. Runs only inside the python:3.12-slim sandbox.


def calculate_total(items, tax_rate):
    subtotal = sum(item["price"] * item["qty"] for item in items)
    return subtotal * (1 + tax_rate)
