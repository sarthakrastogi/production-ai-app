.PHONY: dev test lint evals evals-offline docker-up docker-down tf-plan tf-apply

# Local dev
dev:
	uvicorn app.main:app --reload --port 8000

# Testing
test:
	pytest tests/ -v

lint:
	ruff check .

# Evals
evals:
	python -m evals.run_evals

evals-offline:
	python -m evals.eval_offline

evals-traces:
	python -m evals.eval_traces

# Update eval baseline from current results
baseline-update:
	python -m evals.run_evals
	cp evals/reports/latest.json evals/baselines/latest.json
	@echo "Baseline updated. Commit evals/baselines/latest.json to lock it in."

# Docker
docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

# Terraform
tf-plan:
	cd terraform && terraform plan

tf-apply:
	cd terraform && terraform apply
