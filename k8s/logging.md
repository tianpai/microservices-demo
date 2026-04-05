# Centralized Logging

This project uses:

- `Fluentd` to collect Kubernetes container logs
- `Elasticsearch` to store logs centrally
- `Kibana` to view logs

These manifests are kept separate from the main `kubectl apply -k k8s` path so the logging stack does not make the CI cluster heavier than necessary.

Kibana is configured with a larger heap and memory limit than the application services because the default lightweight settings were not enough for a local Kind demo cluster.

## Apply the logging stack

```bash
kubectl apply -f k8s/logging-config.yaml -n book-order-demo
kubectl apply -f k8s/logging.yaml -n book-order-demo
```

## Check the logging pods

```bash
kubectl get pods -n book-order-demo -l tier=logging
```

## Access Kibana

Kibana is exposed on NodePort `30601`.

For a local Kind cluster, port-forward is the safer access method:

```bash
kubectl port-forward -n book-order-demo service/kibana 5601:5601
```

## View application logs

1. Open Kibana.
2. Create a data view for `book-order-demo-*`.
3. Open `Discover`.
4. Generate some requests against the application.
5. Search by `log_file` to find logs for a specific service, for example:
   - `auth-service`
   - `book-service`
   - `order-service`

Fluentd tails files matching `/var/log/containers/*_book-order-demo_*.log`, so it collects logs from the project namespace and sends them to Elasticsearch.

## Quick Local Proof

You can also query Elasticsearch directly without opening Kibana:

```bash
kubectl exec -n book-order-demo deploy/elasticsearch -- \
  curl -s 'http://127.0.0.1:9200/_cat/indices/book-order-demo-*?v'
```

To show recent request logs:

```bash
kubectl exec -n book-order-demo deploy/elasticsearch -- \
  curl -s 'http://127.0.0.1:9200/book-order-demo-*/_search?q=POST&size=20&sort=@timestamp:desc'
```

That query returns request logs such as:
- `POST /auth/register`
- `POST /auth/login`
- `POST /books`
- `POST /orders`
