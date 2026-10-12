#!/usr/bin/env bash
# Checks the eval graders themselves: for every case in solve/evals/cases/, the
# grader in solve/evals/hidden/ must fail on the case as committed and pass once
# the case's reference patch is applied. Run it after adding or editing a case.
set -euo pipefail

repo="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
hidden="$repo/solve/evals/hidden"
status=0

for case_dir in "$repo"/solve/evals/cases/*/; do
  id="$(basename "$case_dir")"
  tmp="$(mktemp -d)"
  mkdir -p "$tmp/solve/evals/cases"
  cp -R "$case_dir" "$tmp/solve/evals/cases/$id"

  if [[ ! -f "$hidden/$id.sh" || ! -f "$hidden/$id.patch" ]]; then
    echo "FAIL $id: missing $id.sh or $id.patch in solve/evals/hidden/"
    status=1
  elif bash "$hidden/$id.sh" "$tmp" >/dev/null 2>&1; then
    echo "FAIL $id: the grader passes on the unfixed case"
    status=1
  elif ! (cd "$tmp" && git apply "$hidden/$id.patch"); then
    echo "FAIL $id: the reference patch does not apply"
    status=1
  elif ! output="$(bash "$hidden/$id.sh" "$tmp" 2>&1)"; then
    echo "FAIL $id: the grader fails with the reference fix"
    echo "$output" | sed 's/^/     /'
    status=1
  else
    echo "ok   $id"
  fi
  rm -rf "$tmp"
done

exit "$status"
