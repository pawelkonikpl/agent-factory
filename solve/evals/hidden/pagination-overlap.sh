#!/usr/bin/env bash
# Grader for eval case pagination-overlap. Usage: pagination-overlap.sh <checkout-root>.
# Exits 0 when the case is solved.
set -euo pipefail
cd "$1/solve/evals/cases/pagination-overlap"
python3 - <<'PY'
from pager import page, page_count

items = list(range(23))
for size in (1, 2, 4, 5, 7, 23, 30):
    count = page_count(len(items), size)
    pages = [page(items, number, size) for number in range(1, count + 1)]
    assert sum(pages, []) == items, f"size {size}: pages {pages} do not tile the items"
    assert all(len(p) == size for p in pages[:-1]), f"size {size}: a page before the last is short"
    assert page(items, count + 1, size) == [], f"size {size}: page past the end is not empty"
assert page([], 1, 3) == [], "an empty list has an empty first page"
try:
    page(items, 0, 3)
except ValueError:
    pass
else:
    raise AssertionError("page 0 must still raise ValueError")
print("pagination-overlap: solved")
PY
