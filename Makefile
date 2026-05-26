.PHONY: venv install clean

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

clean:
	rm -rf $(VENV_DIR)
	rm -rf io/*.xyz io/*.stl io/*.gcode
	rm -rf __pycache__ */__pycache__ .pytest_cache
	@echo "Cleaned."
