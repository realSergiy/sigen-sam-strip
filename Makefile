.PHONY: dev test lint build install clean setup activate download-models

SHELL := /bin/bash

setup:
    @echo "Setting up development environment..."
    @if [ ! -d ".venv" ]; then \
        echo "Creating virtual environment..."; \
        uv venv .venv; \
        echo ""; \
        echo "===================================================="; \
        echo "Virtual environment created! To activate it, run:"; \
        echo "source .venv/bin/activate"; \
        echo "===================================================="; \
        echo ""; \
        echo "Or use our helper command:"; \
        echo "make activate"; \
        echo ""; \
    else \
        echo "Virtual environment already exists."; \
    fi
    @echo "Installing system dependencies..."
    @command -v ffmpeg >/dev/null 2>&1 || { echo "Installing ffmpeg..."; sudo apt install -y ffmpeg libavutil-dev libavcodec-dev libavformat-dev libswscale-dev; }
    @. .venv/bin/activate && $(MAKE) install
    @$(MAKE) download-models
    @echo "Setup complete! You're ready to start developing."

activate:
    @echo "To activate the environment, you need to source it."
    @echo "Run this command manually:"
    @echo ""
    @echo "source .venv/bin/activate"
    @echo ""
    @echo "This cannot be done automatically by make because make runs in a subshell."

dev:
    @echo "Running development server..."
    @cd backend/server && PYTORCH_ENABLE_MPS_FALLBACK=1 \
        APP_ROOT="$(shell pwd)/" \
        APP_URL=http://localhost:7263 \
        MODEL_SIZE=base_plus \
        gunicorn --worker-class gthread app:app --workers 1 --bind 0.0.0.0:7263

install:
    @echo "Installing dependencies..."
    @cd backend && uv pip install -e '.[webapi,dev]'

lint:
    @echo "Running linter..."
    @cd backend && black .
    @cd backend && usort .

test:
    @echo "Running tests..."
    @cd backend && python -m pytest

build:
    @echo "Building package..."
    @cd backend && python setup.py bdist_wheel

download-models:
    @echo "Downloading SAM 2.1 model checkpoints..."
    @chmod +x ./backend/download_ckpts.sh
    @cd $(shell pwd) && ./backend/download_ckpts.sh

check-updates:
    @echo "Checking for outdated dependencies..."
    @cd backend && uv pip list --outdated

update-deps:
    @echo "Updating dependencies..."
    @cd backend && uv pip compile --upgrade-all setup.py -o requirements.lock