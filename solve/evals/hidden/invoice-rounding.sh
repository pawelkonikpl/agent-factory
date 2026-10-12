#!/usr/bin/env bash
# Grader for eval case invoice-rounding. Usage: invoice-rounding.sh <checkout-root>.
# Exits 0 when the case is solved.
set -euo pipefail
cd "$1/solve/evals/cases/invoice-rounding"
python3 - <<'PY'
from invoice import invoice_total

# Expected totals: net sum of the invoice, plus VAT, rounded half up to 0.01.
CASES = [
    ([("0.50", 1)], "0.23", "0.62"),
    ([("0.01", 1)], "0.50", "0.02"),
    ([("0.35", 3)], "0.23", "1.29"),
    ([("19.99", 3), ("0.01", 1)], "0.23", "73.78"),
    ([("2.50", 1)], "0.08", "2.70"),
    ([("0.10", 7)], "0.05", "0.74"),
    ([("10.00", 2), ("5.00", 1)], "0.23", "30.75"),
    ([("1234567.89", 1000)], "0.23", "1518518504.70"),
    ([("10.00", 1)], "0.00", "10.00"),
]
for lines, rate, expected in CASES:
    got = invoice_total(lines, rate)
    assert got == expected, f"invoice_total({lines}, {rate!r}) = {got!r}, expected {expected!r}"
print("invoice-rounding: solved")
PY
