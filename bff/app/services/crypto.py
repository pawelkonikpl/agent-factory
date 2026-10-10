"""Random values and comparisons used by the login flow."""

import base64
import hashlib
import hmac
import secrets

RANDOM_BYTES = 32


def random_token() -> str:
    """URL-safe random string with 256 bits of entropy (43 characters)."""
    return secrets.token_urlsafe(RANDOM_BYTES)


def generate_code_verifier() -> str:
    # 43 characters from [A-Za-z0-9_-], within the 43-128 range PKCE requires.
    return random_token()


def code_challenge_s256(code_verifier: str) -> str:
    """PKCE S256: BASE64URL(SHA256(code_verifier)) without padding."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())
