#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIND_BIN="${KIND_BIN:-/tmp/kind}"
KIND_NAME="${KIND_NAME:-book-order-demo}"
KUBECONFIG_PATH="${KUBECONFIG:-/tmp/book-order-demo.kubeconfig}"
NAMESPACE="${NAMESPACE:-book-order-demo}"
METRICS_SERVER_URL="${METRICS_SERVER_URL:-https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml}"

export KUBECONFIG="$KUBECONFIG_PATH"

log_step() {
  printf "\n[%s] %s\n" "STEP" "$1"
}

cluster_exists() {
  "$KIND_BIN" get clusters 2>/dev/null | grep -Fxq "$KIND_NAME"
}

create_cluster() {
  if cluster_exists; then
    log_step "Kind cluster '$KIND_NAME' already exists"
    return
  fi

  log_step "Creating Kind cluster"
  "$KIND_BIN" create cluster --name "$KIND_NAME" --wait 120s --kubeconfig "$KUBECONFIG_PATH"
}

build_images() {
  log_step "Building service images"
  docker build -t finalproject-auth-service:latest -f "$ROOT_DIR/services/auth-service/Dockerfile" "$ROOT_DIR"
  docker build -t finalproject-book-service:latest -f "$ROOT_DIR/services/book-service/Dockerfile" "$ROOT_DIR"
  docker build -t finalproject-order-service:latest -f "$ROOT_DIR/services/order-service/Dockerfile" "$ROOT_DIR"
}

load_images() {
  log_step "Loading images into Kind"
  "$KIND_BIN" load docker-image finalproject-auth-service:latest --name "$KIND_NAME"
  "$KIND_BIN" load docker-image finalproject-book-service:latest --name "$KIND_NAME"
  "$KIND_BIN" load docker-image finalproject-order-service:latest --name "$KIND_NAME"
}

deploy_base() {
  log_step "Applying base Kubernetes manifests"
  kubectl apply -k "$ROOT_DIR/k8s"

  log_step "Waiting for databases"
  kubectl rollout status deployment/auth-db -n "$NAMESPACE" --timeout=240s
  kubectl rollout status deployment/book-db -n "$NAMESPACE" --timeout=240s
  kubectl rollout status deployment/order-db -n "$NAMESPACE" --timeout=240s

  log_step "Waiting for application services"
  kubectl rollout status deployment/auth-service -n "$NAMESPACE" --timeout=240s
  kubectl rollout status deployment/book-service -n "$NAMESPACE" --timeout=240s
  kubectl rollout status deployment/order-service -n "$NAMESPACE" --timeout=240s

  log_step "Waiting for monitoring services"
  kubectl rollout status deployment/prometheus -n "$NAMESPACE" --timeout=240s
  kubectl rollout status deployment/grafana -n "$NAMESPACE" --timeout=240s
}

install_metrics_server() {
  log_step "Installing Metrics Server"
  kubectl apply -f "$METRICS_SERVER_URL"

  if ! kubectl get deployment metrics-server -n kube-system -o jsonpath='{.spec.template.spec.containers[0].args}' | grep -q -- '--kubelet-insecure-tls'; then
    kubectl patch deployment metrics-server -n kube-system --type='json' \
      -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
  fi

  kubectl rollout status deployment/metrics-server -n kube-system --timeout=240s
}

deploy_logging() {
  log_step "Applying centralized logging manifests"
  kubectl apply -f "$ROOT_DIR/k8s/logging-config.yaml" -n "$NAMESPACE"
  kubectl apply -f "$ROOT_DIR/k8s/logging.yaml" -n "$NAMESPACE"

  kubectl rollout status deployment/elasticsearch -n "$NAMESPACE" --timeout=360s
  kubectl rollout status deployment/kibana -n "$NAMESPACE" --timeout=360s
  kubectl rollout status daemonset/fluentd -n "$NAMESPACE" --timeout=360s
}

show_status() {
  log_step "Namespace resources"
  kubectl get all -n "$NAMESPACE"

  log_step "HPA"
  kubectl get hpa -n "$NAMESPACE" || true

  log_step "Logging pods"
  kubectl get pods -n "$NAMESPACE" -l tier=logging || true
}

delete_cluster() {
  if cluster_exists; then
    log_step "Deleting Kind cluster '$KIND_NAME'"
    "$KIND_BIN" delete cluster --name "$KIND_NAME"
  fi

  rm -f "$KUBECONFIG_PATH"
}

usage() {
  cat <<'EOF'
Usage: ./scripts/k8s-demo-up.sh <command>

Commands:
  create-cluster  Create the local Kind cluster if it does not exist
  build           Build the three service images
  load            Load the images into Kind
  deploy          Apply the base Kubernetes manifests
  metrics         Install or update Metrics Server
  logging         Apply the centralized logging manifests
  status          Show key Kubernetes resources for the demo
  all             Run the full local Kubernetes demo setup
  delete-cluster  Delete the local Kind cluster
EOF
}

command="${1:-all}"

case "$command" in
  create-cluster)
    create_cluster
    ;;
  build)
    build_images
    ;;
  load)
    load_images
    ;;
  deploy)
    deploy_base
    ;;
  metrics)
    install_metrics_server
    ;;
  logging)
    deploy_logging
    ;;
  status)
    show_status
    ;;
  all)
    create_cluster
    build_images
    load_images
    deploy_base
    install_metrics_server
    deploy_logging
    show_status
    ;;
  delete-cluster)
    delete_cluster
    ;;
  *)
    usage
    exit 1
    ;;
esac
