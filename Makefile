SHELL := /bin/bash

KIND_NAME ?= book-order-demo
KIND_BIN ?= /tmp/kind
KUBECONFIG ?= /tmp/book-order-demo.kubeconfig

.PHONY: help kind-install demo-up demo-status demo-forward demo-forward-stop demo-indices demo-logs demo-metrics demo-logging demo-down

help:
	@printf "Available commands:\n"
	@printf "  make demo-up           Create Kind cluster, build/load images, deploy app, metrics, and logging\n"
	@printf "  make demo-status       Show Kubernetes resources for the demo namespace\n"
	@printf "  make demo-forward      Start all required port-forwards in the background\n"
	@printf "  make demo-forward-stop Stop all background port-forwards\n"
	@printf "  make demo-indices      Show Elasticsearch indices for centralized logging\n"
	@printf "  make demo-logs         Show recent centralized request logs from Elasticsearch\n"
	@printf "  make demo-metrics      Install or update Metrics Server only\n"
	@printf "  make demo-logging      Deploy or update Fluentd, Elasticsearch, and Kibana only\n"
	@printf "  make demo-down         Delete the local Kind cluster\n"

kind-install:
	KIND_BIN=$(KIND_BIN) ./scripts/install-kind.sh

demo-up: kind-install
	KIND_BIN=$(KIND_BIN) KIND_NAME=$(KIND_NAME) KUBECONFIG=$(KUBECONFIG) ./scripts/k8s-demo-up.sh all

demo-status:
	KIND_BIN=$(KIND_BIN) KIND_NAME=$(KIND_NAME) KUBECONFIG=$(KUBECONFIG) ./scripts/k8s-demo-up.sh status

demo-forward:
	KUBECONFIG=$(KUBECONFIG) ./scripts/k8s-port-forward.sh start

demo-forward-stop:
	KUBECONFIG=$(KUBECONFIG) ./scripts/k8s-port-forward.sh stop

demo-indices:
	KUBECONFIG=$(KUBECONFIG) ./scripts/k8s-demo-logs.sh indices

demo-logs:
	KUBECONFIG=$(KUBECONFIG) ./scripts/k8s-demo-logs.sh post

demo-metrics:
	KIND_BIN=$(KIND_BIN) KIND_NAME=$(KIND_NAME) KUBECONFIG=$(KUBECONFIG) ./scripts/k8s-demo-up.sh metrics

demo-logging:
	KIND_BIN=$(KIND_BIN) KIND_NAME=$(KIND_NAME) KUBECONFIG=$(KUBECONFIG) ./scripts/k8s-demo-up.sh logging

demo-down:
	KIND_BIN=$(KIND_BIN) KIND_NAME=$(KIND_NAME) KUBECONFIG=$(KUBECONFIG) ./scripts/k8s-demo-up.sh delete-cluster
