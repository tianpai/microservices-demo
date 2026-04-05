# Book Order Demo

Book Order Demo is a small microservices project built for a course final project. It uses three FastAPI services with separate PostgreSQL databases, JWT-based access control, local service discovery with Consul, and Kubernetes manifests for cluster deployment.

## Services

| Service | Responsibility | Database |
| --- | --- | --- |
| `auth-service` | Register users, log in users, issue JWTs | `auth-db` |
| `book-service` | List and manage books | `book-db` |
| `order-service` | Create and list orders, verify books through `book-service` | `order-db` |

## Project Structure

```text
services/
  auth-service/
  book-service/
  order-service/
scripts/
k8s/
postman/
tests/
Makefile
docker-compose.yml
requirements.txt
design.md
demo-flow.md
```

Architecture details and Mermaid diagrams are in [design.md](design.md).

## Python Setup

Use Python `3.12` for local development. The CI workflow and the service Docker images use Python `3.12`.

Create and activate the root virtual environment:

```bash
python3.12 -m venv venv
source venv/bin/activate
python --version
pip install -r requirements.txt
```

If `python3.12` is not available on your machine, use the Python command that points to version `3.12`.

## Run Locally

Prerequisites:
- Docker
- Docker Compose
- Python 3.12

Start the local stack:

```bash
docker compose up -d --build
```

This path is useful for local API checks with Consul. The full rubric demo path is the Kubernetes setup below.

Local endpoints:
- `auth-service`: `http://127.0.0.1:8001`
- `book-service`: `http://127.0.0.1:8002`
- `order-service`: `http://127.0.0.1:8003`
- `Consul`: `http://127.0.0.1:8500`

Stop the local stack:

```bash
docker compose down -v
```

## Testing

Run the pytest suite:

```bash
venv/bin/pytest -q
```

Postman assets:
- `postman/Book Order Demo.postman_collection.json`
- `postman/Book Order Demo Local.postman_environment.json`
- `postman/Book Order Demo Kubernetes.postman_environment.json`

The API walkthrough is in [demo-flow.md](demo-flow.md).

## Kubernetes

Docker Desktop must be running before the Kubernetes demo setup, because the local Kind workflow builds Docker images and loads them into the cluster.

Recommended local demo path:

```bash
make demo-up
make demo-forward
```

Then run the Postman collection with:
- `postman/Book Order Demo.postman_collection.json`
- `postman/Book Order Demo Kubernetes.postman_environment.json`

Direct log proof:

```bash
make demo-logs
```

Cleanup:

```bash
make demo-forward-stop
make demo-down
```

Manual setup is still available if needed.

Build the service images manually:

```bash
docker build -t finalproject-auth-service:latest -f services/auth-service/Dockerfile .
docker build -t finalproject-book-service:latest -f services/book-service/Dockerfile .
docker build -t finalproject-order-service:latest -f services/order-service/Dockerfile .
```

Then apply the Kubernetes manifests:

```bash
kubectl apply -k k8s
```

Included Kubernetes resources:
- Deployments and Services for all apps and databases
- ConfigMap and Secret
- RBAC
- NetworkPolicy
- Horizontal Pod Autoscaler for `order-service`
- Prometheus and Grafana manifests

NodePorts:
- `auth-service`: `30081`
- `book-service`: `30082`
- `order-service`: `30083`
- `Prometheus`: `30090`
- `Grafana`: `30300`

Metrics Server setup for HPA is documented in [k8s/metrics-server.md](k8s/metrics-server.md).

Centralized logging is provided as a separate add-on:

```bash
kubectl apply -f k8s/logging-config.yaml -n book-order-demo
kubectl apply -f k8s/logging.yaml -n book-order-demo
```

Logging details are in [k8s/logging.md](k8s/logging.md).

Local demo shortcuts:

```bash
make demo-up
make demo-status
make demo-forward
make demo-indices
make demo-logs
make demo-forward-stop
make demo-down
```

## Monitoring

Each service exposes `/metrics`. Prometheus scrapes the application metrics, and Grafana is preconfigured with a basic dashboard for the demo.

## Logging

Fluentd collects Kubernetes container logs from the project namespace, Elasticsearch stores them, and Kibana exposes them on NodePort `30601`.

For local Kind demos, use the commands in [k8s/logging.md](k8s/logging.md) to port-forward Kibana or query Elasticsearch directly.

In Kibana:
- create a data view for `book-order-demo-*`
- use `@timestamp` as the time field
- open `Discover`
- search `POST`

## CI/CD

GitHub Actions is defined in [.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml). The pipeline runs `pytest`, executes the Docker Compose smoke test with Newman, deploys to a temporary Kind cluster, and reruns the Postman smoke test against Kubernetes.

## Repository

Public repository: <https://github.com/tianpai/microservices-demo>
