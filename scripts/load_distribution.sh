#!/bin/bash
# Sends 30 POST requests to /api/emi and counts which pod served each one

URL="http://emi.local/api/emi"
TOTAL=30

echo "Sending $TOTAL requests to $URL ..."
declare -A counts

for i in $(seq 1 $TOTAL); do
  SERVED=$(curl -s -X POST "$URL" \
    -H "Content-Type: application/json" \
    -d "{\"principal\":$((RANDOM % 900000 + 100000)),\"rate\":$((RANDOM % 15 + 5)),\"months\":$((RANDOM % 48 + 12))}" \
    | grep -o '"servedBy":"[^"]*"' | cut -d'"' -f4)

  echo "Request $i → $SERVED"
  counts[$SERVED]=$((${counts[$SERVED]:-0} + 1))
done

echo ""
echo "=== Distribution ==="
for pod in "${!counts[@]}"; do
  echo "$pod: ${counts[$pod]} requests"
done
