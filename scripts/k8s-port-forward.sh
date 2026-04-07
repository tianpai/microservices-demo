#!/usr/bin/env bash
set -euo pipefail

KUBECONFIG_PATH="${KUBECONFIG:-/tmp/book-order-demo.kubeconfig}"
NAMESPACE="${NAMESPACE:-book-order-demo}"
STATE_DIR="${STATE_DIR:-/tmp/book-order-demo-port-forward}"

mkdir -p "$STATE_DIR"

SERVICES=(
  "auth-service:8001:8001"
  "book-service:8002:8002"
  "order-service:8003:8003"
  "prometheus:9090:9090"
  "grafana:3000:3000"
  "elasticsearch:9200:9200"
  "kibana:5601:5601"
)

is_running() {
  local pid_file="$1"
  [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

start_forward() {
  local service_name="$1"
  local local_port="$2"
  local remote_port="$3"
  local pid_file="$STATE_DIR/${service_name}.pid"
  local log_file="$STATE_DIR/${service_name}.log"

  if is_running "$pid_file"; then
    echo "$service_name already running on localhost:$local_port"
    return
  fi

  nohup kubectl --kubeconfig "$KUBECONFIG_PATH" port-forward -n "$NAMESPACE" \
    "service/${service_name}" "${local_port}:${remote_port}" >"$log_file" 2>&1 &

  echo "$!" >"$pid_file"
}

stop_forward() {
  local service_name="$1"
  local pid_file="$STATE_DIR/${service_name}.pid"

  if is_running "$pid_file"; then
    kill "$(cat "$pid_file")"
  fi

  rm -f "$pid_file"
}

show_status() {
  local service_name pid_file log_file

  for spec in "${SERVICES[@]}"; do
    IFS=":" read -r service_name _ _ <<<"$spec"
    pid_file="$STATE_DIR/${service_name}.pid"
    log_file="$STATE_DIR/${service_name}.log"

    if is_running "$pid_file"; then
      echo "$service_name: running"
    else
      echo "$service_name: stopped"
    fi

    if [ -f "$log_file" ]; then
      echo "  log: $log_file"
    fi
  done

  cat <<'EOF'

Metrics:
  Prometheus: http://localhost:9090
  Grafana: http://localhost:3000

Logging:
  Elasticsearch: http://localhost:9200
  Kibana: http://localhost:5601
EOF
}

usage() {
  cat <<'EOF'
Usage: ./scripts/k8s-port-forward.sh <start|stop|status>
EOF
}

command="${1:-status}"

case "$command" in
  start)
    for spec in "${SERVICES[@]}"; do
      IFS=":" read -r service_name local_port remote_port <<<"$spec"
      start_forward "$service_name" "$local_port" "$remote_port"
    done
    sleep 5
    show_status
    ;;
  stop)
    for spec in "${SERVICES[@]}"; do
      IFS=":" read -r service_name _ _ <<<"$spec"
      stop_forward "$service_name"
    done
    ;;
  status)
    show_status
    ;;
  *)
    usage
    exit 1
    ;;
esac
