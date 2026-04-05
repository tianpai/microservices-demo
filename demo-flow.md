# Demo Flow

## Postman Files

Import these files from the `postman/` folder:
- `Book Order Demo.postman_collection.json`
- `Book Order Demo Local.postman_environment.json`
- `Book Order Demo Kubernetes.postman_environment.json`

## Local Demo Flow

Start the stack:

```bash
docker compose up -d --build
```

In Postman:
1. Select the `Book Order Demo Local` environment.
2. Run the full collection from request `1` to request `11`.

Expected results:
- auth health check returns `200`
- staff registration succeeds
- customer registration succeeds
- both logins return JWTs
- book creation returns `201`
- order creation returns `201`
- order listing succeeds
- Consul returns registered services

## Kubernetes Demo Flow

Deploy the application:

```bash
kubectl apply -k k8s
```

Port-forward the app services:

```bash
# run these in separate terminals
kubectl port-forward -n book-order-demo service/auth-service 8001:8001
kubectl port-forward -n book-order-demo service/book-service 8002:8002
kubectl port-forward -n book-order-demo service/order-service 8003:8003
```

In Postman:
1. Select the `Book Order Demo Kubernetes` environment.
2. Run the collection.

Expected results:
- requests `1` to `10` succeed
- the Consul request is skipped in the Kubernetes environment

## Quick Checks

Local:

```bash
curl http://127.0.0.1:8001/auth/health
curl http://127.0.0.1:8002/books/health
curl http://127.0.0.1:8003/orders/health
```

Kubernetes:

```bash
kubectl get all -n book-order-demo
kubectl get hpa -n book-order-demo
```
