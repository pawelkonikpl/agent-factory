#!/usr/bin/env bash
# Grader for eval case flaky-tags. Usage: flaky-tags.sh <checkout-root>.
# Exits 0 when the case is solved.
set -euo pipefail
cd "$1/solve/evals/cases/flaky-tags"
python3 - <<'PY'
import os
import subprocess
import sys

# Hash randomisation changes set order per process, so check under many seeds.
program = """
from tags import normalize_tags
assert normalize_tags("Python, api,python , Web") == ["python", "api", "web"]
assert normalize_tags("b,a,B,c,a") == ["b", "a", "c"]
assert normalize_tags(" , ,") == []
assert normalize_tags("Solo") == ["solo"]
"""
for seed in range(25):
    env = dict(os.environ, PYTHONHASHSEED=str(seed))
    result = subprocess.run([sys.executable, "-c", program], env=env, timeout=30)
    if result.returncode != 0:
        sys.exit(f"flaky-tags: wrong result with PYTHONHASHSEED={seed}")
print("flaky-tags: solved")
PY
