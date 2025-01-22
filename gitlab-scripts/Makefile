# Makefile for GitLab Repository Batch Update Script

# Variables
PYTHON := python3
PIP := pip3
SCRIPT ?=  # Default script name; can be overridden
ARGS ?= # Default to empty; can be overridden

# Default target
.PHONY: all
all: help

# Install dependencies
.PHONY: install
install:
	@echo "Installing dependencies..."
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

# Run the script
.PHONY: run
run: install
	@echo "Script: $(SCRIPT), Args: $(ARGS)"
	@if [ -f $(SCRIPT) ]; then \
		$(PYTHON) $(SCRIPT) $(ARGS); \
	else \
		echo "Error: Script $(SCRIPT) does not exist."; \
		exit 1; \
	fi

# Run the script with environment variables loaded from .env
.PHONY: run-env
run-env: install
	@echo "Running the script with environment variables from .env: $(SCRIPT) with arguments: $(ARGS)"
	@if [ -f $(SCRIPT) ]; then \
		$(PYTHON) $(SCRIPT) $(ARGS); \
	else \
		echo "Error: Script $(SCRIPT) does not exist."; \
		exit 1; \
	fi

# Clean up temporary files
.PHONY: clean
clean:
	@echo "Cleaning up..."
	@rm -rf __pycache__ *.pyc script.log summary_report.txt
	@echo "Cleanup completed."

# List available Python scripts
.PHONY: list-scripts
list-scripts:
	@echo "Available Python scripts:"
	@ls *.py

# Display help
.PHONY: help
help:
	@echo "Available targets:"
	@echo "  make install       - Install Python dependencies"
	@echo "  make run [SCRIPT=your_script.py ARGS='-b branch']           - Run the specified script with optional arguments (default: $(SCRIPT))"
	@echo "  make run-env [SCRIPT=your_script.py ARGS='-b branch']       - Run the script with .env variables and optional arguments (default: $(SCRIPT))"
	@echo "  make clean         - Remove temporary files"
	@echo "  make list-scripts  - List available Python scripts"
	@echo "  make help          - Display this help message"
