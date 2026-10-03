# Unix/Git-Bash convenience targets. Windows users can run the same python commands directly.
PY ?= $(shell [ -x .venv/Scripts/python ] && echo .venv/Scripts/python || echo .venv/bin/python)

.PHONY: setup data seed calibrate validate history train impact web demo test smoke camera-accuracy

setup:
	python -m venv .venv
	$(PY) -m pip install -r requirements.txt
	cd web && npm ci
data:
	$(PY) data/fetch_data.py
seed:
	$(PY) -m db.seed
calibrate:
	$(PY) -m twin.calibrate
validate:
	$(PY) -m twin.validate
history:
	$(PY) -m twin.generate --days 90 --verify
train:
	$(PY) -m predictor.evaluate
impact:
	$(PY) -m advisory.impact
web:
	cd web && npm run build
demo:
	$(PY) scripts/demo.py
test:
	$(PY) -m pytest -q
smoke:
	bash scripts/smoke.sh
camera-accuracy:
	$(PY) -m camera.accuracy --synthetic
