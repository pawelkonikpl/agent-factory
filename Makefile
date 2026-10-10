# Dev shortcuts. Run from the repo root. Works with GNU Make 3.81 (macOS).

DASHBOARD_PORT ?= 8000
COMPOSE = docker compose -f keycloak/docker-compose.yml

.PHONY: help dashboard backend docker-up docker-down docker-logs

help: ## List the targets
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-12s %s\n", $$1, $$2}'

dashboard: ## Serve the factory dashboard on 127.0.0.1 (DASHBOARD_PORT, default 8000)
	@echo "Dashboard: http://localhost:$(DASHBOARD_PORT)/dashboard.html"
	python3 -m http.server $(DASHBOARD_PORT) --bind 127.0.0.1 --directory factory

# Both servers run in the background of one shell. When either exits, or on
# Ctrl-C, the shell stops the other one, so no uvicorn is left behind. A server
# that exits on its own is an error, so make reports it.
backend: ## Run the API (port 8001) and the BFF (port 8000); Ctrl-C stops both
	@(cd api && exec uv run uvicorn app.main:create_app --factory --port 8001) & api=$$!; \
	(cd bff && exec uv run uvicorn app.main:create_app --factory --port 8000) & bff=$$!; \
	trap 'kill $$api $$bff 2>/dev/null' INT TERM; \
	while kill -0 $$api 2>/dev/null && kill -0 $$bff 2>/dev/null; do sleep 1; done; \
	kill $$api $$bff 2>/dev/null; wait; exit 1

docker-up: ## Start Keycloak (port 8080) in the background
	$(COMPOSE) up -d

docker-down: ## Stop and remove the Docker services
	$(COMPOSE) down

docker-logs: ## Follow the Docker services' logs until Ctrl-C
	$(COMPOSE) logs -f
