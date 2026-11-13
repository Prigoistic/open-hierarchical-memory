UV_RUN = uv run --locked --extra research --extra benchmarks

.PHONY: setup dashboard test verify support-study replay-study
setup:
	uv sync --locked --extra research --extra benchmarks

dashboard:
	$(UV_RUN) python -m research.serve_task_benchmark --port 8792

test:
	$(UV_RUN) python -m pytest -q
	node --test web/visuals/test/*.test.mjs

verify:
	$(UV_RUN) python scripts/verify.py --profile full
	node --test web/visuals/test/*.test.mjs

support-study: OUTPUT ?= experiments/task-support-local
support-study:
	$(UV_RUN) python -m research.task_memory.run_study --output $(OUTPUT)
	$(UV_RUN) python -m scripts.audit_task_support --results $(OUTPUT)

replay-study: OUTPUT ?= experiments/task-replay-local
replay-study:
	$(UV_RUN) python -m research.run_task_replay --output $(OUTPUT)
	$(UV_RUN) python -m scripts.audit_task_replay --results $(OUTPUT)
