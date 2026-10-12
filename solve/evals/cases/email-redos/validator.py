"""Input validation for the signup form."""

import re

EMAIL = re.compile(r"^([A-Za-z0-9]+[._-]?)+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}$")


def is_valid_email(address):
    """True when `address` looks like name@domain.tld.

    The local part is letters and digits, optionally separated by single dots,
    underscores or hyphens. The domain is dot-separated labels of letters,
    digits and hyphens, ending in a top-level domain of two or more letters.
    """
    return EMAIL.match(address) is not None
