# Metrics Server Setup

Metrics Server is required if the `order-service` HPA should actually receive CPU metrics and scale.

## Why It Is Needed

- the HPA resource exists in `k8s/order-hpa.yaml`
- HPA uses resource metrics
- Kubernetes usually gets those metrics from Metrics Server

Without Metrics Server, the HPA object can be created, but autoscaling will not function.

For the local Kind demo, a fresh `zsh` shell should already have
`KUBECONFIG=/tmp/book-order-demo.kubeconfig` from `~/.zshrc`. If not, point
`kubectl` at the generated kubeconfig manually:

```bash
export KUBECONFIG=/tmp/book-order-demo.kubeconfig
```

## Install

Use the official Metrics Server manifest:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.8.0/components.yaml
```

Then patch it for local demo clusters that commonly need insecure kubelet TLS:

```bash
kubectl patch deployment metrics-server \
  -n kube-system \
  --type=merge \
  --patch-file k8s/metrics-server-patch.yaml
```

## Verify

```bash
kubectl get deployment metrics-server -n kube-system
kubectl top nodes
kubectl top pods -n book-order-demo
kubectl get hpa -n book-order-demo
```

If `kubectl top` works, the `order-service` HPA can use CPU metrics.
