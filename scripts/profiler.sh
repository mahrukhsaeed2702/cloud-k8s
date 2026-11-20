#!/bin/bash
# Records pod CPU/memory every 15s to CSV
# Run in a separate terminal during load tests
# Usage: ./profiler.sh <label>
# Example: ./profiler.sh r3_rps100

LABEL=${1:-test}
RESULTS_DIR="results"
mkdir -p "$RESULTS_DIR"
OUTFILE="$RESULTS_DIR/profile_${LABEL}.csv"

echo "timestamp,pod,cpu,memory" > "$OUTFILE"
echo "Profiling started → $OUTFILE (Ctrl+C to stop)"

while true; do
  TS=$(date +"%Y-%m-%dT%H:%M:%S")
  kubectl top pods -n emi --no-headers 2>/dev/null | grep emi-web | while read line; do
    POD=$(echo $line | awk '{print $1}')
    CPU=$(echo $line | awk '{print $2}')
    MEM=$(echo $line | awk '{print $3}')
    echo "$TS,$POD,$CPU,$MEM" >> "$OUTFILE"
    echo "$TS | $POD | CPU:$CPU | MEM:$MEM"
  done
  sleep 15
done
