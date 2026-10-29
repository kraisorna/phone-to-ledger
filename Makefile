.PHONY: test eval lint

test:
	PYTHONPATH=src:. python3 -m unittest discover -s tests -v

eval:
	PYTHONPATH=src python3 -m ptl.eval.run_eval --help

lint:
	python3 -m compileall -q src tests
