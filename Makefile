PROJECT_DIR := $(shell pwd)
ADMIN_UI_DIR := $(PROJECT_DIR)/admin-ui
VENV_DIR := $(ADMIN_UI_DIR)/venv

# Default Pi hostname (override: make deploy PI=192.168.1.50)
PI ?= harbouros.local

.PHONY: build dev test clean setup-dev deploy install-remote migrate-plex

# Build the HarbourOS image using pi-gen + Docker
build:
	@echo "Building HarbourOS image..."
	@bash "$(PROJECT_DIR)/build.sh"

# Set up local development environment
setup-dev:
	@echo "Setting up development environment..."
	python3 -m venv "$(VENV_DIR)"
	"$(VENV_DIR)/bin/pip" install -r "$(ADMIN_UI_DIR)/requirements.txt"
	@echo "Done. Activate with: source \"$(VENV_DIR)/bin/activate\""

# Run Flask dev server locally
dev: setup-dev
	@echo "Starting HarbourOS Admin UI dev server on http://localhost:8080..."
	cd "$(ADMIN_UI_DIR)" && FLASK_ENV=development HARBOUROS_DEV=1 "$(VENV_DIR)/bin/python" -m flask --app harbouros_admin.app run --host 0.0.0.0 --port 8080 --debug

# Run tests
test:
	@echo "Running tests..."
	cd "$(ADMIN_UI_DIR)" && "$(VENV_DIR)/bin/python" -m pytest tests/ -v

# Deploy to a running Pi
deploy:
	@bash "$(PROJECT_DIR)/deploy.sh" "$(PI)"

# Install HarbourOS on a Pi remotely via SSH
install-remote:
	@bash "$(PROJECT_DIR)/install-remote.sh" "$(PI)"

# Migrate Docker Plex to native Plex on the Pi
migrate-plex:
	@echo "Migrating Docker Plex to native on $(PI)..."
	scp "$(PROJECT_DIR)/scripts/migrate-docker-plex.sh" "$(PI):/tmp/migrate-docker-plex.sh"
	ssh -t "$(PI)" "sudo bash /tmp/migrate-docker-plex.sh"

# Clean build artifacts
clean:
	rm -rf pi-gen-build/
	rm -rf output/*.img output/*.img.xz
	rm -rf "$(VENV_DIR)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned."
