
## Overview

This assignment deploys a **Loan EMI Calculator** web application on Minikube with:
- MongoDB StatefulSet (3-node replica set)
- NGINX Ingress Controller for load balancing
- Horizontal Pod Autoscaler (HPA) for autoscaling
- Load testing and performance benchmarking with Apache Bench

---

## Architecture

```
Client (ab)
    │
    ▼
NGINX Ingress (emi.local)
    │
    ▼
emi-web Service (ClusterIP)
    │  round-robin
    ├──▶ emi-web Pod 1
    ├──▶ emi-web Pod 2  (HPA: min 1, max 5)
    └──▶ emi-web Pod N
              │
              ▼
         MongoDB Service
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
 mongo-0   mongo-1   mongo-2
(PRIMARY) (SECONDARY)(SECONDARY)
```

---

## Prerequisites

- Minikube (with Docker driver)
- kubectl
- Python 3 (`pip install matplotlib`)
- Apache Bench (`ab`)

---

## Quick Start (fresh Minikube cluster)

```bash
minikube start --cpus=4 --memory=4096
minikube addons enable metrics-server ingress

# Deploy everything
kubectl apply -f k8s/

# Wait for all pods to be Running
kubectl get pods -n emi -w

# Initialize MongoDB replica set (one-time)
kubectl exec -it mongo-0 -n emi -- mongosh --eval "
rs.initiate({_id:'rs0',members:[
  {_id:0,host:'mongo-0.mongo.emi.svc.cluster.local:27017'},
  {_id:1,host:'mongo-1.mongo.emi.svc.cluster.local:27017'},
  {_id:2,host:'mongo-2.mongo.emi.svc.cluster.local:27017'}
]})"

# Add Ingress host entry
echo "$(minikube ip) emi.local" | sudo tee -a /etc/hosts
```

> **After Minikube restart**, re-run the `rs.initiate` command above with `rs.reconfig(...)` and `{force:true}`.

---

## Milestone 2: NGINX Ingress + Load Balancing

### Enable Ingress
```bash
minikube addons enable ingress
kubectl apply -f k8s/ingress.yaml
```

### Configure /etc/hosts
```bash
echo "$(minikube ip) emi.local" | sudo tee -a /etc/hosts
```

### Verify
```bash
curl http://emi.local/api/emi \
  -H "Content-Type: application/json" \
  -d '{"principal":500000,"rate":12,"months":60}'
```

---

## Milestone 3: Load Testing & Performance Benchmarking

Run load tests across replica counts (1, 2, 3) and request rates (10–200 req/s):

```bash
chmod +x scripts/load_distribution.sh
./scripts/load_distribution.sh
```

Generate Graph 1 (Response Time vs Request Rate):
```bash
python3 scripts/plot_results.py
```

---

## Milestone 4: HPA Autoscaling

### Deploy HPA
```bash
kubectl apply -f k8s/hpa.yaml
```

HPA configuration: CPU target 50%, min 1 replica, max 5 replicas.

### CPU Profiling — 3 Replicas (Graph 2)
```bash
chmod +x scripts/profile_pods.sh
./scripts/profile_pods.sh
```

Records per-pod CPU every 15s during 5-minute, 100-concurrent load test.


### Autoscale Test — 10 Minutes (Graph 3)
```bash
chmod +x scripts/autoscale_test.sh
./scripts/autoscale_test.sh
```

Test phases:
| Phase | Duration | Concurrency | Purpose |
|-------|----------|-------------|---------|
| Baseline | 2 min | 20 concurrent | Establish baseline, trigger initial scale |
| High Load | 5 min | 100 concurrent | Sustain high CPU, observe scaling |
| Cooldown | 3 min | 20 concurrent | Observe scale-down behavior |



Output files in `results/`:
- `graph1_response_time.png` — Response time vs request rate (3 replica configs)
- `graph2_cpu_per_pod.png` — Per-pod CPU during 100-concurrent load
- `graph3_autoscale.png` — Autoscaling behavior over 10 minutes

---

## Project Structure

```
assignment04/
├── app/                    # Node.js EMI Calculator API
│   ├── index.js
│   └── package.json
├── k8s/                    # Kubernetes manifests
│   ├── namespace.yaml
│   ├── mongo-statefulset.yaml
│   ├── mongo-service.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   └── hpa.yaml
├── scripts/
│   ├── autoscale_test.sh   # 10-min HPA test (phases: 20/100/20 concurrent)
│   ├── profile_pods.sh     # Per-pod CPU profiling (3 replicas, 5 min)
│   ├── load_distribution.sh # Graph 1 load tests
│   └── plot_results.py     # Generate all 3 graphs
├── results/                # Generated after running tests
│   ├── graph1_response_time.png
│   ├── graph2_cpu_per_pod.png
│   ├── graph3_autoscale.png
│   ├── hpa_autoscale.csv
│   └── pod_cpu.csv
└── README.md
```

---

## Key Findings

1. **Horizontal scaling works:** 3 replicas handle 200 req/s at 3ms vs 7.3ms with 1 replica
2. **HPA triggers correctly:** CPU above 50% target caused scale-up from 1→5 replicas in ~90 seconds
3. **Load distribution is uneven:** NGINX round-robin distributes connections, but pod CPU varied 60–93% due to request processing time differences
4. **Scale-down requires cooldown:** HPA did not scale down within the 10-minute test because CPU stayed elevated even during the low-load cooldown phase
