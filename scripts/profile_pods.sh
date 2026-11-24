#!/bin/bash
HOST="emi.local"
PORT=80
mkdir -p results

cat > /tmp/emi_post.json <<'EOF'
{"principal":500000,"rate":12,"months":60}
EOF

# Set exactly 3 replicas
kubectl scale deployment emi-web --replicas=3 -n emi
kubectl rollout status deployment/emi-web -n emi

echo "timestamp,pod,cpu" > results/pod_cpu.csv

# Record CPU per pod every 15s while running load
record_pods() {
  while true; do
    TS=$(date -Iseconds)
    kubectl top pods -n emi --no-headers 2>/dev/null | grep emi-web | while read line; do
      POD=$(echo "$line" | awk '{print $1}')
      CPU=$(echo "$line" | awk '{print $2}')
      echo "$TS,$POD,$CPU" >> results/pod_cpu.csv
    done
    sleep 15
  done
}

record_pods &
RECORDER_PID=$!
echo "Pod CPU recorder started (PID $RECORDER_PID)"

echo "=== Running 100 req/s load for 5 minutes ==="
ab -t 300 -n 999999 -c 100 \
   -p /tmp/emi_post.json -T "application/json" \
   -H "Host: emi.local" \
   http://${HOST}:${PORT}/api/emi 2>&1 | tee results/profile_100rps.txt

kill $RECORDER_PID 2>/dev/null
echo "=== Done ==="
echo "Samples collected: $(wc -l < results/pod_cpu.csv)"
