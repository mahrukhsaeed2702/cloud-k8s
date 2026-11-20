#!/bin/bash
HOST="emi.local"
PORT=80
mkdir -p results

cat > /tmp/emi_post.json <<'EOF'
{"principal":500000,"rate":12,"months":60}
EOF

# Record HPA every 15s
record_hpa() {
  echo "timestamp,replicas,cpu_current,cpu_target" > results/hpa_autoscale.csv
  while true; do
    TS=$(date -Iseconds)
    LINE=$(kubectl get hpa emi-web -n emi --no-headers 2>/dev/null)
    REPLICAS=$(echo "$LINE" | awk '{print $6}')
    CPU_RAW=$(kubectl get hpa emi-web -n emi \
      -o jsonpath='{.status.currentMetrics[0].resource.current.averageUtilization}' 2>/dev/null)
    echo "$TS,$REPLICAS,cpu:,${CPU_RAW}%/50%" >> results/hpa_autoscale.csv
    sleep 15
  done
}

kubectl scale deployment emi-web --replicas=1 -n emi
kubectl rollout status deployment/emi-web -n emi

record_hpa &
RECORDER_PID=$!
echo "HPA recorder started (PID $RECORDER_PID)"

echo "=== Phase 1: low load (10 concurrent, 3 min) ==="
# -t 180 = run for 180 seconds
ab -t 180 -c 10 \
   -p /tmp/emi_post.json -T "application/json" \
   -H "Host: emi.local" \
   http://${HOST}:${PORT}/api/emi 2>&1 | tee results/autoscale_phase1.txt

echo "=== Phase 2: high load (30 concurrent, 6 min) ==="
ab -t 360 -c 30 \
   -p /tmp/emi_post.json -T "application/json" \
   -H "Host: emi.local" \
   http://${HOST}:${PORT}/api/emi 2>&1 | tee results/autoscale_phase2.txt

echo "=== Phase 3: cooldown (5 concurrent, 3 min) ==="
ab -t 180 -c 5 \
   -p /tmp/emi_post.json -T "application/json" \
   -H "Host: emi.local" \
   http://${HOST}:${PORT}/api/emi 2>&1 | tee results/autoscale_phase3.txt

kill $RECORDER_PID 2>/dev/null
echo "=== Autoscale test complete ==="
echo "HPA samples collected: $(wc -l < results/hpa_autoscale.csv)"
