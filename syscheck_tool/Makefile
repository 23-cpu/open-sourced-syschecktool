.PHONY: help run json lint test clean

help:
	@echo "Targets: run, json, lint, test, clean"

run:
	python3 src/syscheck.py

json:
	python3 src/syscheck.py --json out.json && echo "Wrote out.json"

lint:
	python3 -m py_compile src/syscheck.py

test:
	python3 -m unittest -q

clean:
	rm -f out.json
