#!/bin/bash

# Get the number of iterations from the first argument, default to 1 if not provided
iterations=${1:-1}

for ((i=1; i<=iterations; i++))
do
  echo "Iteration $i"
  python3 generate_test_payload.py
  curl -X POST -H "Content-Type: application/json" \
       -d @test_payload.json \
       http://localhost:8990/receive_json
done
