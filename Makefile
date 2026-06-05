.PHONY: venv install dev run test lint format clean

VENV_DIR := .venv
PYTHON  := python3

venv:
	$(PYTHON) -m venv $(VENV_DIR)
	@echo "Virtual environment created at $(VENV_DIR)."
	@echo "Activate with: source $(VENV_DIR)/bin/activate"

install: venv
	$(VENV_DIR)/bin/pip install --upgrade pip
	$(VENV_DIR)/bin/pip install -r requirements.txt
	@echo "Dependencies installed."

dev: install
	$(VENV_DIR)/bin/pip install ruff
	@echo "Dev tooling installed (ruff)."

run:
	./run.sh

test:
	$(VENV_DIR)/bin/python tests/test_all.py

lint:
	$(VENV_DIR)/bin/python -m ruff check src tests ui_app.py

format:
	$(VENV_DIR)/bin/python -m ruff format src tests ui_app.py

clean:
	rm -rf $(VENV_DIR)
	rm -rf io/*.xyz io/*.stl io/*.gcode
	rm -rf __pycache__ */__pycache__ .pytest_cache
	@echo "Cleaned."
