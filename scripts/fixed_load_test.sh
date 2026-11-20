#!/bin/bash
REPLICAS=$1
RATE=$2
DURATION=${3:-60}
HOST="emi.local"
PORT=80
RESULTS_DIR="results"
mkdir -p "$RESULTS_DIR"
OUTFILE="$RESULTS_DIR/run_r${REPLICAS}_rps${RATE}.txt"

echo "=== Run: replicas=$REPLICAS rate=$RATE rps duration=${DURATION}s ===" | tee "$OUTFILE"
kubectl scale deployment emi-web --replicas=$REPLICAS -n emi
kubectl rollout status deployment/emi-web -n emi

TOTAL=$((RATE * DURATION))
httperf --server "$HOST" --port $PORT --uri=/ --rate $RATE --num-conns $TOTAL --num-calls 1 2>&1 | tee -a "$OUTFILE"
echo "Done. Saved to $OUTFILE"
