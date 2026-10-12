#!/usr/bin/env bash
# Grader for eval case email-redos. Usage: email-redos.sh <checkout-root>.
# Exits 0 when the case is solved.
set -euo pipefail
cd "$1/solve/evals/cases/email-redos"
python3 - <<'PY'
import subprocess
import sys

VALID = [
    "jan.kowalski@example.com",
    "a@b.co",
    "x_1-y.z@sub.example.org",
    "UPPER@EXAMPLE.COM",
    "a1@x-y.example.io",
]
INVALID = [
    "plain",
    "a@b",
    "a..b@example.com",
    ".a@example.com",
    "a b@example.com",
    "a@example.c",
    "a@example..com",
    "a@@example.com",
]
ATTACKS = ["a" * 40 + "!", "a." * 25 + "!", "a-" * 25 + "@", "a_1" * 20 + "@x"]

# Correctness and speed run in a child process, so a hang ends at the timeout.
program = f"""
from validator import is_valid_email
for address in {VALID!r}:
    assert is_valid_email(address), "rejects valid " + address
for address in {INVALID!r}:
    assert not is_valid_email(address), "accepts invalid " + address
for address in {ATTACKS!r}:
    assert not is_valid_email(address), "accepts invalid " + address
"""
try:
    result = subprocess.run([sys.executable, "-c", program], timeout=5)
except subprocess.TimeoutExpired:
    sys.exit("email-redos: validation took longer than 5 s on crafted input")
if result.returncode != 0:
    sys.exit("email-redos: wrong accept/reject result")
print("email-redos: solved")
PY
