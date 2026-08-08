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


init:
	python -m pip install --upgrade pip
	python -m pip install -e .[dev]
	pre-commit install


all: test build-dist


sdist:
	$(RMRF) dist || echo "dist not found, skipping"
	$(RMRF) build || echo "build not found, skipping"
	$(RMRF) $(MODULE_NAME).egg-info || echo "egg-info not found, skipping"
	python -m build
	python -m twine check dist/*


lint:
	@python -m isort --check $(MODULE_NAME)  ||  echo "isort:   FAILED!"
	@python -m black --check --quiet $(MODULE_NAME) || echo "black:   FAILED!"
	@python -m pflake8 $(MODULE_NAME)  || echo "flake8:  FAILED!"


delint:
	python -m isort $(MODULE_NAME)
	python -m black $(MODULE_NAME) --line-length 80


typecheck:
	python -m mypy $(MODULE_NAME)


test: lint typecheck
	python -m pytest \
		--cov-report term \
		--cov-report html \
		--cov=$(MODULE_NAME) tests/


build-dist:
	python -m build
