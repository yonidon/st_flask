#!/bin/bash

python3 generate_test_payload.py
curl -X POST -H "Content-Type: application/json" \
-d @test_payload.json \
http://localhost:8999/receive_json
