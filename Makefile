PY ?= python

.PHONY: install run report dashboard test lint fmt lineage clean

install:
	$(PY) -m pip install -e ".[dev]"

run:
	$(PY) -m pipeline run

report:
	$(PY) -m pipeline report

dashboard:
	streamlit run dashboard/app.py

test:
	$(PY) -m pytest

lint:
	ruff check . && ruff format --check .

fmt:
	ruff check --fix . && ruff format .

lineage:
	$(PY) -m pipeline lineage

clean:
	rm -rf data .pytest_cache .ruff_cache
