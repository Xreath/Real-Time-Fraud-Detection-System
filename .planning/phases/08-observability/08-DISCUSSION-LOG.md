# Phase 8: Observability - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-23
**Phase:** 08-observability
**Areas discussed:** Metrics exposure strategy

---

## Metrics Exposure Strategy

### fraud-api metrics

| Option | Description | Selected |
|--------|-------------|----------|
| prometheus_client library | Add prometheus_client to fraud-api, expose /metrics with request count, latency histogram, fraud rate counter | ✓ |
| MLflow built-in metrics only | Rely on MLflow's built-in metrics (if available in 2.12.2) without custom code | |
| You decide | Claude picks best approach | |

**User's choice:** prometheus_client library (Recommended)

### Kafka metrics

| Option | Description | Selected |
|--------|-------------|----------|
| JMX Exporter sidecar | Add JMX Exporter container alongside Kafka, scrapes JMX MBeans, provides consumer lag/throughput/ISR | ✓ |
| kafka-exporter standalone | danielqsj/kafka-exporter, connects to brokers directly, simpler but no broker JMX internals | |
| You decide | Claude picks simplest for portfolio | |

**User's choice:** JMX Exporter sidecar (Recommended)

### Spark metrics

| Option | Description | Selected |
|--------|-------------|----------|
| JMX Exporter on Spark containers | Add JMX agent via SPARK_DAEMON_JAVA_OPTS, requires JMX exporter JAR in Spark image | ✓ |
| Spark PrometheusServlet sink | Built-in metrics.properties sink (Spark 3.5+), exposes /metrics/prometheus on UI port | |
| Skip Spark metrics | Monitor end-to-end via fraud-api latency and Kafka lag instead | |

**User's choice:** JMX Exporter on Spark containers (Recommended)

### Prometheus configuration

| Option | Description | Selected |
|--------|-------------|----------|
| Port 9090, 15s scrape | Standard port, industry default interval | ✓ |
| Port 9090, 30s scrape | Longer interval, less load | |
| You decide | Claude picks based on resource constraints | |

**User's choice:** Port 9090, 15s scrape (Recommended)

## Claude's Discretion

- Dashboard design (layout, panels, single vs multiple dashboards)
- Monitoring DAG behavior (validation data generation, KS/PSI thresholds, concept drift window)
- Alerting channels (Grafana alerting integration with Phase 7 alert files)

## Deferred Ideas

- Slack webhook integration (v2)
- Evidently drift reports (v2)
- SHAP feature importance shift detection (v2)
