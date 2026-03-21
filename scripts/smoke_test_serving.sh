#!/bin/bash
# Smoke test for fraud-api serving endpoint
# Usage: bash scripts/smoke_test_serving.sh
set -e

BASE_URL="http://localhost:5002"
PASS=0
FAIL=0

echo "============================================"
echo "Fraud API Smoke Test"
echo "============================================"

# Test 1: Health check (SERV-02)
echo -n "[1/3] Health check... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
if [ "$HTTP_CODE" = "200" ]; then
    echo "PASS (HTTP $HTTP_CODE)"
    PASS=$((PASS + 1))
else
    echo "FAIL (HTTP $HTTP_CODE)"
    FAIL=$((FAIL + 1))
fi

# Test 2: Single transaction scoring (SERV-01)
echo -n "[2/3] Invocations (single transaction)... "
RESPONSE=$(curl -s -X POST "$BASE_URL/invocations" \
    -H "Content-Type: application/json" \
    -d '{
        "dataframe_records": [{
            "amount": 150.75,
            "merchant_category": "grocery",
            "card_type": "visa",
            "country": "TR",
            "latitude": 41.01,
            "longitude": 28.97,
            "is_weekend": 0,
            "is_night": 0,
            "is_foreign": 0,
            "hour_of_day": 14,
            "day_of_week": 1,
            "amount_log": 5.02,
            "is_high_amount": 0,
            "is_round_amount": 0,
            "distance_km": 0.0,
            "time_diff_hours": 0.0,
            "speed_kmh": 0.0
        }]
    }')
if echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'predictions' in d; assert 'fraud_score' in d['predictions'][0]; print('PASS (fraud_score=' + str(round(d['predictions'][0]['fraud_score'],4)) + ')')"; then
    PASS=$((PASS + 1))
else
    echo "FAIL (response: $RESPONSE)"
    FAIL=$((FAIL + 1))
fi

# Test 3: High-risk transaction (should score higher)
echo -n "[3/3] Invocations (high-risk transaction)... "
RESPONSE=$(curl -s -X POST "$BASE_URL/invocations" \
    -H "Content-Type: application/json" \
    -d '{
        "dataframe_records": [{
            "amount": 9999.99,
            "merchant_category": "electronics",
            "card_type": "mastercard",
            "country": "US",
            "latitude": 40.71,
            "longitude": -74.01,
            "is_weekend": 1,
            "is_night": 1,
            "is_foreign": 1,
            "hour_of_day": 3,
            "day_of_week": 6,
            "amount_log": 9.21,
            "is_high_amount": 1,
            "is_round_amount": 0,
            "distance_km": 8000.0,
            "time_diff_hours": 1.0,
            "speed_kmh": 8000.0
        }]
    }')
if echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'predictions' in d; assert 'fraud_score' in d['predictions'][0]; print('PASS (fraud_score=' + str(round(d['predictions'][0]['fraud_score'],4)) + ')')"; then
    PASS=$((PASS + 1))
else
    echo "FAIL (response: $RESPONSE)"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "============================================"
echo "Results: $PASS passed, $FAIL failed"
echo "============================================"

if [ $FAIL -gt 0 ]; then
    exit 1
fi
