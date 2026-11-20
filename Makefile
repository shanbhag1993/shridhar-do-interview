# Build, test, and release targets. Works with GNU Make 3.81 (the macOS default).
# Run `make help` for the list.

# --- Python: one project-level virtualenv -----------------------------------

# Interpreter used only to create the venv. Must be Python 3.11+.
PYTHON   ?= python3
VENV     := .venv
VENV_BIN := $(CURDIR)/$(VENV)/bin
PY       := $(VENV_BIN)/python
DEPS     := $(VENV)/.deps-installed

# Recipes call $(PY) by path. These exports give any script a recipe starts the
# same environment as a shell after `source .venv/bin/activate`.
export VIRTUAL_ENV := $(CURDIR)/$(VENV)
export PATH := $(VENV_BIN):$(PATH)

# --- Container image ---------------------------------------------------------

REGISTRY      ?= registry.digitalocean.com/shridhar-job-queue
IMAGE_NAME    ?= job-queue
IMAGE         := $(REGISTRY)/$(IMAGE_NAME)
REGISTRY_HOST := $(firstword $(subst /, ,$(REGISTRY)))

# The Droplet is amd64. Building on an Apple Silicon Mac without this would
# produce an arm64 image that cannot start there.
PLATFORM ?= linux/amd64

# Immutable tag: git short SHA, with -dirty when there are uncommitted changes.
GIT_SHA   := $(shell git rev-parse --short HEAD 2>/dev/null || echo nogit)
GIT_DIRTY := $(shell [ -n "$$(git status --porcelain 2>/dev/null)" ] && echo -dirty)
TAG       ?= $(GIT_SHA)$(GIT_DIRTY)

.DEFAULT_GOAL := help
.PHONY: help venv compile test run build smoke login push release clean

help: ## List the targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-z-]+:.*## / {printf "  make %-9s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "  image: $(IMAGE):$(TAG)  ($(PLATFORM))"

# --- Python targets ----------------------------------------------------------

$(PY):
	@$(PYTHON) -c 'import sys; v = sys.version_info[:2]; sys.exit(0 if v >= (3, 11) else "Python 3.11+ is required, but `$(PYTHON)` is %d.%d. Run: make venv PYTHON=/path/to/python3.11+" % v)'
	$(PYTHON) -m venv $(VENV)

# Reinstall only when the dependency list changes.
$(DEPS): pyproject.toml | $(PY)
	$(PY) -m pip install --quiet --editable ".[dev]"
	@touch $(DEPS)

venv: $(DEPS) ## Create .venv and install the project with dev dependencies

compile: venv ## Byte-compile src and tests; fails on any syntax error
	$(PY) -m compileall -q src tests

test: venv ## Run the unit tests (extra pytest flags: make test ARGS="-v -k cancel")
	$(PY) -m pytest $(ARGS)

run: venv ## Run the service locally on port 8000
	$(PY) -m job_queue.main

# --- Image targets -----------------------------------------------------------

build: ## Build the image, tagged with the git SHA and latest
	docker build --platform $(PLATFORM) -t $(IMAGE):$(TAG) -t $(IMAGE):latest .

smoke: build ## Run the end-to-end smoke test against the built image
	SMOKE_PLATFORM=$(PLATFORM) ops/scripts/smoke-test.sh $(IMAGE):$(TAG)

login: ## Log Docker in to the registry using DIGITALOCEAN_TOKEN
	@[ -n "$$DIGITALOCEAN_TOKEN" ] || { echo "DIGITALOCEAN_TOKEN is not set. Export a DigitalOcean API token with registry write access."; exit 1; }
	@printf '%s' "$$DIGITALOCEAN_TOKEN" | docker login $(REGISTRY_HOST) --username "$$DIGITALOCEAN_TOKEN" --password-stdin

push: build login ## Build the image, log in, and push both tags to the registry
	docker push $(IMAGE):$(TAG)
	docker push $(IMAGE):latest
	@echo "pushed $(IMAGE):$(TAG) and $(IMAGE):latest"

release: compile test smoke push ## Compile, test, build, smoke-test, then push; stops at the first failure

# --- Housekeeping ------------------------------------------------------------

clean: ## Remove .venv and caches
	rm -rf $(VENV) .pytest_cache build dist src/*.egg-info
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
