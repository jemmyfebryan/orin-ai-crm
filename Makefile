# Makefile for FastAPI project (with optional Docker or PM2)

# ----------------------------
# Variables
# ----------------------------
IMAGE_NAME=orinai-crm-app
PORT=8090
CONTAINER_NAME=orinai-crm-container
USE_DOCKER ?= false
APP_NAME=orinai-crm-app

# Python virtual environment settings (for non-Docker runs)
VENV_DIR=.venv
PYTHON=$(VENV_DIR)/bin/python
PIP=$(VENV_DIR)/bin/pip

.PHONY: build run stop remove logs shell rebuild restart test clean venv

# ----------------------------
# Docker targets
# ----------------------------

docker-build:
	docker build -t $(IMAGE_NAME) .

docker-run:
	docker run -d -p $(PORT):$(PORT) --name $(CONTAINER_NAME) $(IMAGE_NAME)

docker-stop:
	docker stop $(CONTAINER_NAME)

docker-remove:
	docker rm $(CONTAINER_NAME)

docker-logs:
	docker logs -f $(CONTAINER_NAME)

docker-shell:
	docker exec -it $(CONTAINER_NAME) /bin/sh

# ----------------------------
# Local (non-Docker) targets
# ----------------------------

venv:
	python3 -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

# Run app in foreground
local-run:
	$(PYTHON) -m uvicorn app:app --host 0.0.0.0 --port $(PORT) --reload

# Run app in background using PM2
pm2-run:
	pm2 start $(PYTHON) --name $(APP_NAME) -- -m uvicorn app:app --host 0.0.0.0 --port $(PORT)
	pm2 save

pm2-stop:
	pm2 stop $(APP_NAME) || true
	pm2 delete $(APP_NAME) || true

pm2-logs:
	pm2 logs $(APP_NAME)

pm2-restart:
	pm2 restart $(APP_NAME)

local-test:
	$(PYTHON) -m pytest tests/

clean:
	rm -rf $(VENV_DIR) __pycache__ .pytest_cache

# ----------------------------
# Conditional (Unified) targets
# ----------------------------

build:
ifeq ($(USE_DOCKER),true)
	$(MAKE) docker-build
else
	$(MAKE) venv
endif

run:
ifeq ($(USE_DOCKER),true)
	$(MAKE) docker-run
else
	$(MAKE) pm2-run
endif

stop:
ifeq ($(USE_DOCKER),true)
	$(MAKE) docker-stop
else
	$(MAKE) pm2-stop
endif

remove:
ifeq ($(USE_DOCKER),true)
	$(MAKE) docker-remove
endif

logs:
ifeq ($(USE_DOCKER),true)
	$(MAKE) docker-logs
else
	$(MAKE) pm2-logs
endif

shell:
ifeq ($(USE_DOCKER),true)
	$(MAKE) docker-shell
endif

rebuild:
	$(MAKE) stop
	$(MAKE) remove
	$(MAKE) build
	$(MAKE) run

restart:
ifeq ($(USE_DOCKER),true)
	$(MAKE) docker-stop
	$(MAKE) docker-remove
	$(MAKE) docker-run
else
	$(MAKE) pm2-restart
endif

test:
ifeq ($(USE_DOCKER),true)
	docker exec -it $(CONTAINER_NAME) pytest tests/
else
	$(MAKE) local-test
endif
