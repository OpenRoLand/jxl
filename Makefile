MODULE_NAME ?= openroland_jxl
PACKAGE_NAME ?= openroland-jxl
ifeq ($(OS),Windows_NT)
    detected_OS := Windows
else
    detected_OS := $(shell uname)
endif
ifeq ($(OS),Windows_NT)
	RMRF = rmdir /s /q
else
	RMRF = rm -rf
endif

# Local virtual environment. `init` creates it automatically if missing;
# delete the `venv/` directory to force a rebuild.
ifeq ($(OS),Windows_NT)
    VENV_PYTHON := venv/Scripts/python.exe
    VENV_CREATE := py -3.14 -m venv venv
else
    VENV_PYTHON := venv/bin/python
    VENV_CREATE := python3.14 -m venv venv
endif

venv/pyvenv.cfg:
	$(VENV_CREATE)

venv: venv/pyvenv.cfg
	$(VENV_PYTHON) -m pip install --upgrade pip


init: venv
	$(VENV_PYTHON) -m pip install -e .[dev]
	$(VENV_PYTHON) -m pip install pre-commit
	$(VENV_PYTHON) -m pre_commit install


all: test build-dist


sdist:
	$(RMRF) dist || echo "dist not found, skipping"
	$(RMRF) build || echo "build not found, skipping"
	$(RMRF) $(MODULE_NAME).egg-info || echo "egg-info not found, skipping"
	$(VENV_PYTHON) -m build
	$(VENV_PYTHON) -m twine check dist/*


lint:
	$(VENV_PYTHON) -m isort --check $(MODULE_NAME) tests
	$(VENV_PYTHON) -m black --check --quiet --workers=1 $(MODULE_NAME) tests
	$(VENV_PYTHON) -m pflake8 $(MODULE_NAME) tests


delint:
	$(VENV_PYTHON) -m isort $(MODULE_NAME)
	$(VENV_PYTHON) -m black $(MODULE_NAME) tests --line-length 80 --workers=1


typecheck:
	$(VENV_PYTHON) -m mypy $(MODULE_NAME) tests


test: lint typecheck
	$(VENV_PYTHON) -m pytest \
		--cov-report term \
		--cov-report html \
		--cov=$(MODULE_NAME) tests/


build-dist:
	$(VENV_PYTHON) -m build
