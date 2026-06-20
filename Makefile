# Beginner-friendly shortcuts. Open the macOS "Terminal" app, then:
#   cd /Users/william/Downloads/ravid
# and run e.g.  make run
#
# This is a Python/Django project — there is NO `npm run dev`.

.PHONY: help run stop migrate makemigrations test shell

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /  —  /'

run:  ## Start the API server at http://localhost:8000 (Ctrl+C to stop)
	scripts/dev/run_local.sh .venv/bin/python manage.py runserver 8000

stop:  ## Stop a running server
	-pkill -f "manage.py runserver" 2>/dev/null || true
	@echo "server stopped"

migrate:  ## Create/update the database tables (run once, or after model changes)
	scripts/dev/run_local.sh .venv/bin/python manage.py migrate

makemigrations:  ## Generate new migration files after changing models
	scripts/dev/run_local.sh .venv/bin/python manage.py makemigrations

test:  ## Run the full test suite
	.venv/bin/python -m pytest -q

shell:  ## Open a Django shell (advanced)
	scripts/dev/run_local.sh .venv/bin/python manage.py shell
