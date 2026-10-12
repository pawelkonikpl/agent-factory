#!/usr/bin/env bash
# Grader for eval case shared-cart. Usage: shared-cart.sh <checkout-root>.
# Exits 0 when the case is solved.
set -euo pipefail
cd "$1/solve/evals/cases/shared-cart"
python3 - <<'PY'
from cart import Cart

alice = Cart("alice")
alice.add("tea", 2)
bob = Cart("bob")
assert bob.items == [], f"a new cart starts with {bob.items}"
assert bob.total_quantity() == 0
bob.add("tea")
assert alice.total_quantity() == 2, "adding to one cart changed another"
assert bob.total_quantity() == 1
carol = Cart("carol", [("cup", 1)])
assert carol.total_quantity() == 1, "a cart created with items lost them"
carol.add("cup")
assert carol.items == [("cup", 2)]
assert Cart("dave").items == [], "a cart created after others is not empty"
print("shared-cart: solved")
PY
