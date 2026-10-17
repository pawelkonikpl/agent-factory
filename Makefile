# Dev shortcuts. Run from the repo root. Works with GNU Make 3.81 (macOS).

DASHBOARD_PORT ?= 8005
CONTAINER_ENGINE ?= podman
COMPOSE = $(CONTAINER_ENGINE) compose -f keycloak/docker-compose.yml
SANDBOX = $(CONTAINER_ENGINE) compose -f compose.yaml

.PHONY: help dashboard backend web web-build docker-up docker-down docker-logs sandbox-up sandbox-down sandbox-logs

help: ## List the targets
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-12s %s\n", $$1, $$2}'

dashboard: ## Serve the factory dashboard (Approve / Rework buttons) on 127.0.0.1 (DASHBOARD_PORT, default 8000)
	python3 factory/serve.py --port $(DASHBOARD_PORT)

# Both servers run in the background of one shell. When either exits, or on
# Ctrl-C, the shell stops the other one, so no uvicorn is left behind. A server
# that exits on its own is an error, so make reports it.
backend: ## Run the API (port 8001) and the BFF (port 8000); Ctrl-C stops both
	@(cd api && exec uv run uvicorn app.main:create_app --factory --port 8001 --reload --reload-dir app) & api=$$!; \
	(cd bff && exec uv run uvicorn app.main:create_app --factory --port 8000 --reload --reload-dir app) & bff=$$!; \
	trap 'kill $$api $$bff 2>/dev/null' INT TERM; \
	while kill -0 $$api 2>/dev/null && kill -0 $$bff 2>/dev/null; do sleep 1; done; \
	kill $$api $$bff 2>/dev/null; wait; exit 1

web: ## Start the web dev server on port 5173 until Ctrl-C
	cd web && bun run dev

web-build: ## Build the web app (type check plus production build into web/dist/)
	cd web && bun run build

docker-up: ## Start Keycloak (port 8080), PostgreSQL (port 5432) and smtp4dev (ports 2525 and 5080) in the background (CONTAINER_ENGINE, default podman)
	$(COMPOSE) up -d

docker-down: ## Stop and remove Keycloak, PostgreSQL (port 5432) and smtp4dev (ports 2525 and 5080) (CONTAINER_ENGINE, default podman)
	$(COMPOSE) down

docker-logs: ## Follow the logs of Keycloak, PostgreSQL (port 5432) and smtp4dev (ports 2525 and 5080) until Ctrl-C (CONTAINER_ENGINE, default podman)
	$(COMPOSE) logs -f

sandbox-up: ## Build and start the full stack in containers (compose.yaml), web on port 5173
	$(SANDBOX) up -d --build
	@echo "Sandbox: http://localhost:5173"

sandbox-down: ## Stop and remove the sandbox containers
	$(SANDBOX) down

sandbox-logs: ## Follow the sandbox services' logs until Ctrl-C
	$(SANDBOX) logs -f
