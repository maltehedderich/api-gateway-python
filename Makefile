.PHONY: help build test lint format docker-build docker-push deploy clean

# Variables
IMAGE_NAME ?= api-gateway
IMAGE_TAG ?= latest
REGISTRY ?= docker.io/your-registry
NAMESPACE ?= api-gateway
KUBECONFIG ?= ~/.kube/config

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)API Gateway - Available Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

##@ Development

install: ## Install dependencies
	@echo "$(BLUE)Installing dependencies...$(NC)"
	poetry install

update: ## Update dependencies
	@echo "$(BLUE)Updating dependencies...$(NC)"
	poetry update

test: ## Run tests
	@echo "$(BLUE)Running tests...$(NC)"
	poetry run pytest tests/ -v --cov=src/gateway --cov-report=term-missing

test-unit: ## Run unit tests only
	@echo "$(BLUE)Running unit tests...$(NC)"
	poetry run pytest tests/unit/ -v

test-integration: ## Run integration tests only
	@echo "$(BLUE)Running integration tests...$(NC)"
	poetry run pytest tests/integration/ -v

lint: ## Run linters
	@echo "$(BLUE)Running linters...$(NC)"
	poetry run flake8 src/ tests/
	poetry run mypy src/

format: ## Format code
	@echo "$(BLUE)Formatting code...$(NC)"
	poetry run black src/ tests/
	poetry run isort src/ tests/

format-check: ## Check code formatting
	@echo "$(BLUE)Checking code formatting...$(NC)"
	poetry run black --check src/ tests/
	poetry run isort --check src/ tests/

##@ Docker

docker-build: ## Build Docker image
	@echo "$(BLUE)Building Docker image...$(NC)"
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .
	@echo "$(GREEN)✓ Image built: $(IMAGE_NAME):$(IMAGE_TAG)$(NC)"

docker-build-prod: ## Build production Docker image
	@echo "$(BLUE)Building production Docker image...$(NC)"
	docker build -t $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG) .
	@echo "$(GREEN)✓ Image built: $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)$(NC)"

docker-push: ## Push Docker image to registry
	@echo "$(BLUE)Pushing Docker image...$(NC)"
	docker push $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)
	@echo "$(GREEN)✓ Image pushed: $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)$(NC)"

docker-run: ## Run Docker container locally
	@echo "$(BLUE)Running Docker container...$(NC)"
	docker run -d \
		--name api-gateway-local \
		-p 8080:8080 \
		-p 9090:9090 \
		-e GATEWAY_ENV=development \
		-e GATEWAY_LOG_LEVEL=DEBUG \
		$(IMAGE_NAME):$(IMAGE_TAG)
	@echo "$(GREEN)✓ Container running on http://localhost:8080$(NC)"

docker-stop: ## Stop local Docker container
	@echo "$(BLUE)Stopping Docker container...$(NC)"
	docker stop api-gateway-local || true
	docker rm api-gateway-local || true

docker-logs: ## View Docker container logs
	docker logs -f api-gateway-local

##@ Kubernetes

k8s-namespace: ## Create Kubernetes namespace
	@echo "$(BLUE)Creating namespace...$(NC)"
	kubectl apply -f k8s/namespace.yaml
	@echo "$(GREEN)✓ Namespace created$(NC)"

k8s-secrets: ## Create secrets (requires environment variables)
	@echo "$(BLUE)Creating secrets...$(NC)"
	@if [ -z "$$REDIS_URL" ] || [ -z "$$SESSION_SECRET" ]; then \
		echo "$(YELLOW)Error: REDIS_URL and SESSION_SECRET must be set$(NC)"; \
		exit 1; \
	fi
	kubectl create secret generic api-gateway-secrets \
		--from-literal=redis_url="$$REDIS_URL" \
		--from-literal=session_secret="$$SESSION_SECRET" \
		--namespace=$(NAMESPACE) \
		--dry-run=client -o yaml | kubectl apply -f -
	@echo "$(GREEN)✓ Secrets created$(NC)"

k8s-config: ## Apply ConfigMap
	@echo "$(BLUE)Applying ConfigMap...$(NC)"
	kubectl apply -f k8s/configmap.yaml
	@echo "$(GREEN)✓ ConfigMap applied$(NC)"

k8s-deploy: ## Deploy to Kubernetes
	@echo "$(BLUE)Deploying to Kubernetes...$(NC)"
	kubectl apply -f k8s/deployment.yaml
	kubectl apply -f k8s/service.yaml
	@echo "$(GREEN)✓ Deployment applied$(NC)"

k8s-ingress: ## Deploy Ingress
	@echo "$(BLUE)Deploying Ingress...$(NC)"
	kubectl apply -f k8s/ingress.yaml
	@echo "$(GREEN)✓ Ingress applied$(NC)"

k8s-monitoring: ## Deploy monitoring resources
	@echo "$(BLUE)Deploying monitoring...$(NC)"
	kubectl apply -f monitoring/servicemonitor.yaml
	kubectl apply -f monitoring/alerts.yaml
	kubectl apply -f monitoring/grafana-dashboard-configmap.yaml
	@echo "$(GREEN)✓ Monitoring deployed$(NC)"

deploy-all: k8s-namespace k8s-config k8s-deploy k8s-ingress k8s-monitoring ## Deploy everything to Kubernetes
	@echo "$(GREEN)✓ Full deployment complete$(NC)"

k8s-status: ## Check deployment status
	@echo "$(BLUE)Deployment Status:$(NC)"
	kubectl get all -n $(NAMESPACE)
	@echo ""
	@echo "$(BLUE)ConfigMaps and Secrets:$(NC)"
	kubectl get configmap,secret -n $(NAMESPACE)
	@echo ""
	@echo "$(BLUE)Ingress:$(NC)"
	kubectl get ingress -n $(NAMESPACE)

k8s-logs: ## Tail gateway logs
	kubectl logs -f deployment/api-gateway -n $(NAMESPACE)

k8s-logs-previous: ## View previous pod logs
	kubectl logs deployment/api-gateway -n $(NAMESPACE) --previous

k8s-describe: ## Describe gateway deployment
	kubectl describe deployment/api-gateway -n $(NAMESPACE)

k8s-exec: ## Execute shell in gateway pod
	kubectl exec -it deployment/api-gateway -n $(NAMESPACE) -- /bin/bash

k8s-port-forward: ## Port forward to gateway
	@echo "$(BLUE)Port forwarding to gateway...$(NC)"
	@echo "$(GREEN)Gateway: http://localhost:8080$(NC)"
	@echo "$(GREEN)Metrics: http://localhost:9090/metrics$(NC)"
	kubectl port-forward -n $(NAMESPACE) svc/api-gateway 8080:80 9090:9090

k8s-restart: ## Restart gateway deployment
	@echo "$(BLUE)Restarting deployment...$(NC)"
	kubectl rollout restart deployment/api-gateway -n $(NAMESPACE)
	kubectl rollout status deployment/api-gateway -n $(NAMESPACE)
	@echo "$(GREEN)✓ Deployment restarted$(NC)"

k8s-rollback: ## Rollback deployment
	@echo "$(BLUE)Rolling back deployment...$(NC)"
	kubectl rollout undo deployment/api-gateway -n $(NAMESPACE)
	kubectl rollout status deployment/api-gateway -n $(NAMESPACE)
	@echo "$(GREEN)✓ Deployment rolled back$(NC)"

k8s-scale: ## Scale deployment (use REPLICAS=N)
	@echo "$(BLUE)Scaling deployment to $(REPLICAS) replicas...$(NC)"
	kubectl scale deployment/api-gateway --replicas=$(REPLICAS) -n $(NAMESPACE)
	@echo "$(GREEN)✓ Deployment scaled$(NC)"

k8s-delete: ## Delete all resources
	@echo "$(YELLOW)⚠ This will delete all gateway resources!$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		kubectl delete -f k8s/ingress.yaml; \
		kubectl delete -f k8s/service.yaml; \
		kubectl delete -f k8s/deployment.yaml; \
		kubectl delete -f k8s/configmap.yaml; \
		kubectl delete namespace $(NAMESPACE); \
		echo "$(GREEN)✓ Resources deleted$(NC)"; \
	fi

##@ Local Development

run-local: ## Run locally with Poetry
	@echo "$(BLUE)Running gateway locally...$(NC)"
	poetry run python -m gateway

dev: ## Run in development mode with auto-reload
	@echo "$(BLUE)Running in development mode...$(NC)"
	GATEWAY_ENV=development GATEWAY_LOG_LEVEL=DEBUG poetry run python -m gateway

redis-local: ## Start local Redis for development
	@echo "$(BLUE)Starting local Redis...$(NC)"
	docker run -d --name redis-local -p 6379:6379 redis:7-alpine
	@echo "$(GREEN)✓ Redis running on localhost:6379$(NC)"

redis-stop: ## Stop local Redis
	@echo "$(BLUE)Stopping local Redis...$(NC)"
	docker stop redis-local || true
	docker rm redis-local || true

##@ Testing

load-test: ## Run load tests with Locust
	@echo "$(BLUE)Running load tests...$(NC)"
	poetry run locust -f tests/performance/locustfile.py

##@ Utilities

clean: ## Clean up generated files
	@echo "$(BLUE)Cleaning up...$(NC)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf dist/ build/ *.egg-info htmlcov/ .coverage
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

version: ## Show version info
	@echo "$(BLUE)Version Information:$(NC)"
	@poetry version
	@echo "Python: $$(poetry run python --version)"
	@echo "Poetry: $$(poetry --version)"
	@echo "Docker: $$(docker --version)"
	@echo "Kubectl: $$(kubectl version --client --short 2>/dev/null || echo 'not installed')"

health-check: ## Check local gateway health
	@echo "$(BLUE)Checking gateway health...$(NC)"
	@curl -s http://localhost:8080/health | jq . || echo "$(YELLOW)Gateway not reachable$(NC)"

metrics: ## View current metrics
	@echo "$(BLUE)Current Metrics:$(NC)"
	@curl -s http://localhost:9090/metrics | grep -E "http_requests_total|http_request_duration_seconds" || echo "$(YELLOW)Metrics not reachable$(NC)"

##@ CI/CD

ci-test: lint test ## Run CI tests
	@echo "$(GREEN)✓ CI tests passed$(NC)"

ci-build: docker-build-prod docker-push ## Build and push for CI
	@echo "$(GREEN)✓ CI build complete$(NC)"

##@ Documentation

docs-serve: ## Serve documentation locally (requires mkdocs)
	@echo "$(BLUE)Serving documentation...$(NC)"
	@echo "Documentation available in docs/ directory"
	@ls -la docs/

.DEFAULT_GOAL := help
