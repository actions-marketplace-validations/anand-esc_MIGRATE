# converted/utils.py
# Python 3 converted implementation. Runs only inside the python:3.12-slim sandbox.


def normalize_name(raw_name):
    """Correctly converted: Python 3 str replaces Python 2 unicode."""
    return str(raw_name).strip().title()


def apply_discount(price, discount_percent):
    """
    INTENTIONAL BUG (left in on purpose as a demo case):
    a naive port kept '//' thinking it preserved Python 2's int-division
    behavior, but the original divided a float subtotal, not two ints.
    This should be caught by the verifier as a 'mismatch' whenever
    price * discount_percent isn't a clean multiple of 100.
    """
    return price - (price * discount_percent / 100)
