# Makefile for the Resilient Web Scraper

# --- Variables ---
# Use python3 as the default interpreter
PYTHON = python3
# Define the name of the virtual environment directory
VENV_DIR = venv
# Define the path to the Python executable within the virtual environment
VENV_PYTHON = $(VENV_DIR)/bin/python

# The main script to run
SCRIPT = scraper.py
# The directory where scraped files are saved
OUTPUT_DIR = scraped_pages

# --- Phony Targets ---
# These targets are not files. This prevents 'make' from getting confused if a
# file with the same name as a target exists.
.PHONY: all install run clean help

# --- Default Target ---
# If you just run 'make', it will show the help message.
.DEFAULT_GOAL := help

# --- Targets ---

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: $(VENV_DIR)/bin/activate ## Install dependencies and setup the environment
	@echo "--> Installing Python packages from requirements.txt..."
	$(VENV_PYTHON) -m pip install -r requirements.txt
	@echo "--> Installing Playwright browser binaries (this might take a moment)..."
	$(VENV_PYTHON) -m playwright install --with-deps chromium
	@echo "✅ Installation complete."

run: install ## Run the web scraper
	@echo "--> Running the scraper: $(SCRIPT)..."
	$(VENV_PYTHON) $(SCRIPT)
	@echo "✅ Scraper finished."

clean: ## Clean up the project directory
	@echo "--> Removing virtual environment, output files, and cache..."
	rm -rf $(VENV_DIR)
	rm -rf $(OUTPUT_DIR)
	find . -type d -name "__pycache__" -exec rm -rf {} +
	@echo "✅ Cleanup complete."

# This is an internal target that creates the virtual environment if it doesn't exist.
# The 'install' target depends on this file existing.
$(VENV_DIR)/bin/activate:
	@echo "--> Creating Python virtual environment..."
	$(PYTHON) -m venv $(VENV_DIR)
