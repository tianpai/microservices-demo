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
k8s/
postman/
tests/
docker-compose.yml
requirements.txt
design.md
demo-flow.md
```

Architecture details and Mermaid diagrams are in [design.md](design.md).

## Run Locally

Prerequisites:
- Docker
- Docker Compose
- Python 3.12+

Start the local stack:

```bash
docker compose up -d --build
```

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

Install Python dependencies into the root virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run the pytest suite:

```bash
pytest -q
```

Postman assets:
- `postman/Book Order Demo.postman_collection.json`
- `postman/Book Order Demo Local.postman_environment.json`
- `postman/Book Order Demo Kubernetes.postman_environment.json`

The API walkthrough is in [demo-flow.md](demo-flow.md).

## Kubernetes

Build the service images:

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

## Monitoring

Each service exposes `/metrics`. Prometheus scrapes the application metrics, and Grafana is preconfigured with a basic dashboard for the demo.

## Logging

Fluentd collects Kubernetes container logs from the project namespace, Elasticsearch stores them, and Kibana exposes them on NodePort `30601`.

For local Kind demos, use the commands in [k8s/logging.md](k8s/logging.md) to port-forward Kibana or query Elasticsearch directly.

## CI/CD

GitHub Actions is defined in [.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml). The pipeline runs `pytest`, executes the Docker Compose smoke test with Newman, deploys to a temporary Kind cluster, and reruns the Postman smoke test against Kubernetes.

## Repository

Public repository: <https://github.com/tianpai/microservices-demo>
