#!/usr/bin/env bash
set -euo pipefail

KIND_BIN="${KIND_BIN:-/tmp/kind}"
KIND_VERSION="${KIND_VERSION:-v0.29.0}"

os_name="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch_name="$(uname -m)"

case "$arch_name" in
  arm64|aarch64)
    arch_name="arm64"
    ;;
  x86_64|amd64)
    arch_name="amd64"
    ;;
  *)
    echo "Unsupported architecture: $arch_name" >&2
    exit 1
    ;;
esac

if [ -x "$KIND_BIN" ] && "$KIND_BIN" version 2>/dev/null | grep -q "$KIND_VERSION"; then
  echo "Kind $KIND_VERSION already available at $KIND_BIN"
  exit 0
fi

echo "Downloading Kind $KIND_VERSION to $KIND_BIN"
curl -Lo "$KIND_BIN" "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-${os_name}-${arch_name}"
chmod +x "$KIND_BIN"
