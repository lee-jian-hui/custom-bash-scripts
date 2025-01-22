# Variables
PYTHON := python3
SCRIPT := copy_s3_files.py
ENV1 := dev
ENV2 := uat

# Load variables from .env file
ifneq (,$(wildcard .env))
    include .env
    export $(shell sed 's/=.*//' .env)
endif


# Default target
.PHONY: all
all: run

# Install dependencies
.PHONY: install
install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

# Run with environment arguments
.PHONY: run
run:
	$(PYTHON) $(SCRIPT)

# Clean up any temporary files or artifacts
.PHONY: clean
clean:
	rm -rf __pycache__

# Help menu
.PHONY: help
help:
	@echo "Usage:"
	@echo "  make install        - Install dependencies"
	@echo "  make run            - Run the script interactively"
	@echo "  make run-with-env   - Run the script with predefined ENV1 and ENV2"
	@echo "  make clean          - Clean up temporary files"
