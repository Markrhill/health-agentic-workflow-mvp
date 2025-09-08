.PHONY: p1_eval validate_schema check_schema
p1_eval: validate_schema
	python -m tools.p1_eval

validate_schema:
	python scripts/validate_schema.py --include-python-deps

check_schema:
	python scripts/validate_schema.py --include-python-deps

