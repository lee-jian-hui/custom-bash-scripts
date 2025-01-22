# Makefile for GitLab Repository Batch Update Script

# Variables
PYTHON := python3
SCRIPT := gitlab_batch_update.py  # Replace with your actual script name
VENV := venv
# ACTIVATE := source $(VENV)/bin/activate

# Default target
.PHONY: all
all: help

# Create a virtual environment
.PHONY: venv
venv:
	@echo "Creating virtual environment..."
	$(PYTHON) -m venv $(VENV)
	@echo "Virtual environment created at .$(VENV)/"

# Install dependencies
.PHONY: install
install: venv
	@echo "Activating virtual environment and installing dependencies..."
	$(ACTIVATE) && \
	pip install --upgrade pip && \
	pip install -r requirements.txt

# Run the script
.PHONY: run
run:
	@echo "Running the script..."
	$(PYTHON) $(SCRIPT)

# Run the script with environment variables loaded from .env
.PHONY: run-env
run-env: install
	@echo "Running the script with environment variables from .env..."
	$(ACTIVATE) && \
	$(PYTHON) $(SCRIPT)

# Clean up virtual environment and temporary files
.PHONY: clean
clean:
	@echo "Cleaning up..."
	@rm -rf $(VENV) __pycache__ *.pyc script.log summary_report.txt
	@echo "Cleanup completed."

# Display help
.PHONY: help
help:
	@echo "Available targets:"
	@echo "  make venv          - Create a Python virtual environment"
	@echo "  make install       - Install Python dependencies"
	@echo "  make run           - Run the script"
	@echo "  make run-env       - Run the script with .env variables"
	@echo "  make clean         - Remove virtual environment and temporary files"
	@echo "  make help          - Display this help message"

