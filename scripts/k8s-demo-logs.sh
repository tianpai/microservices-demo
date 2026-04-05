#!/usr/bin/env bash
set -euo pipefail

KUBECONFIG_PATH="${KUBECONFIG:-/tmp/book-order-demo.kubeconfig}"
NAMESPACE="${NAMESPACE:-book-order-demo}"

show_indices() {
  kubectl --kubeconfig "$KUBECONFIG_PATH" exec -n "$NAMESPACE" deploy/elasticsearch -- \
    curl -s 'http://127.0.0.1:9200/_cat/indices/book-order-demo-*?v'
}

show_post_logs() {
  kubectl --kubeconfig "$KUBECONFIG_PATH" exec -n "$NAMESPACE" deploy/elasticsearch -- \
    curl -s 'http://127.0.0.1:9200/book-order-demo-*/_search?q=POST&size=20&sort=@timestamp:desc'
}

usage() {
  cat <<'EOF'
Usage: ./scripts/k8s-demo-logs.sh <indices|post>
EOF
}

command="${1:-post}"

case "$command" in
  indices)
    show_indices
    ;;
  post)
    show_post_logs
    ;;
  *)
    usage
    exit 1
    ;;
esac
