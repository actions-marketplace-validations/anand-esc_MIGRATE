# legacy/utils.py
# Python 2 legacy implementation. Runs only inside the python:2.7-slim sandbox.


def normalize_name(raw_name):
    """Returns a cleaned-up unicode name (Python 2 unicode type)."""
    return unicode(raw_name).strip().title()  # noqa: F821 (unicode is Py2-only, intentional)


def apply_discount(price, discount_percent):
    """Python 2: '/' on two ints does floor division."""
    return price - (price * discount_percent / 100)
