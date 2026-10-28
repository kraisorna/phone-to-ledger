.PHONY: test eval lint

test:
	PYTHONPATH=src:. python3 -m unittest discover -s tests -v

eval:
	python3 -m eval.run_eval --help

lint:
	python3 -m compileall -q src eval tests
