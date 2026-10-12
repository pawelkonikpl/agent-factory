#!/usr/bin/env bash
# Fresh-checkout setup from AGENTS.md, run once when the dev container is created.
# Keeps existing .env files, and installs from the lockfiles without rewriting them.
set -euo pipefail

for dir in bff api; do
  if [ ! -e "$dir/.env" ]; then
    cp "$dir/.env.example" "$dir/.env"
  fi
  (cd "$dir" && uv sync --frozen)
done

(cd web && npm ci)
