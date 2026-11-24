#!/bin/bash
# combined_test.sh
# Single 10-minute experiment that records EVERYTHING simultaneously:
#   - per-pod CPU (kubectl top pods) every 15s
#   - HPA replica count + aggregate CPU (kubectl get hpa) every 15s
#   - ab response time per phase (phase1/2/3 output files)
#
# Phases: 2min @c=20 | 5min @c=100 | 3min @c=20

HOST="emi.local"
PORT=80
mkdir -p results

cat > /tmp/emi_post.json <<'EOF'
{"principal":500000,"rate":12,"months":60}
EOF

# Confirm current state
echo "=== Current state ==="
kubectl get hpa emi-web -n emi
kubectl get pods -n emi | grep emi-web
sleep 2

# CSV headers
echo "timestamp,pod,cpu_millicores" > results/combined_pod_cpu.csv
echo "timestamp,replicas,hpa_cpu_percent" > results/combined_hpa.csv

START_TIME=$(date +%s)

# Background recorder — runs every 15s, records both sources
record_all() {
  while true; do
    TS=$(date -Iseconds)
    ELAPSED=$(( $(date +%s) - START_TIME ))

    # Record per-pod CPU
    kubectl top pods -n emi --no-headers 2>/dev/null | grep emi-web | while read line; do
      POD=$(echo "$line" | awk '{print $1}')
      CPU=$(echo "$line" | awk '{print $2}')
      echo "$TS,$POD,$CPU" >> results/combined_pod_cpu.csv
    done

    # Record HPA replica count + aggregate CPU
    REPLICAS=$(kubectl get hpa emi-web -n emi \
      -o jsonpath='{.status.currentReplicas}' 2>/dev/null)
    HPA_CPU=$(kubectl get hpa emi-web -n emi \
      -o jsonpath='{.status.currentMetrics[0].resource.current.averageUtilization}' 2>/dev/null)
    echo "$TS,${REPLICAS:-0},${HPA_CPU:-0}" >> results/combined_hpa.csv

    echo "[${ELAPSED}s] replicas=${REPLICAS} hpa_cpu=${HPA_CPU}%"
    sleep 15
  done
}

record_all &
RECORDER_PID=$!
echo "Recorder started (PID $RECORDER_PID)"

# ── Phase 1: Baseline — 2 minutes at c=20 ────────────────────────────────────
echo ""
echo "=== Phase 1: Baseline (c=20, 2 min) ==="
ab -t 120 -n 999999 -c 20 \
   -p /tmp/emi_post.json -T "application/json" \
   -H "Host: emi.local" \
   http://${HOST}:${PORT}/api/emi 2>&1 | tee results/combined_phase1.txt

# ── Phase 2: High Load — 5 minutes at c=100 ──────────────────────────────────
echo ""
echo "=== Phase 2: High Load (c=100, 5 min) ==="
ab -t 300 -n 999999 -c 100 \
   -p /tmp/emi_post.json -T "application/json" \
   -H "Host: emi.local" \
   http://${HOST}:${PORT}/api/emi 2>&1 | tee results/combined_phase2.txt

# ── Phase 3: Cooldown — 3 minutes at c=20 ────────────────────────────────────
echo ""
echo "=== Phase 3: Cooldown (c=20, 3 min) ==="
ab -t 180 -n 999999 -c 20 \
   -p /tmp/emi_post.json -T "application/json" \
   -H "Host: emi.local" \
   http://${HOST}:${PORT}/api/emi 2>&1 | tee results/combined_phase3.txt

# Stop recorder
kill $RECORDER_PID 2>/dev/null
echo ""
echo "=== Done ==="
echo "Pod CPU samples : $(wc -l < results/combined_pod_cpu.csv)"
echo "HPA samples     : $(wc -l < results/combined_hpa.csv)"
echo ""
echo "Response times:"
for i in 1 2 3; do
  RT=$(grep "Time per request" results/combined_phase${i}.txt | head -1 | awk '{print $4}')
  echo "  Phase $i: ${RT} ms (mean)"
done
