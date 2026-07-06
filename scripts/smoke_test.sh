#!/usr/bin/env bash
# End-to-end smoke test against a running stack (docker compose up).
# Verifies auth, student+course+roster creation, and session lifecycle.
# It does NOT exercise face recognition (needs real photos) — it checks the
# API wiring so you know the deployment is sound.
#
# Usage: API=http://localhost:8000 ADMIN_EMAIL=admin@college.edu ADMIN_PW='...' ./smoke_test.sh
set -euo pipefail

API="${API:-http://localhost:8000}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@college.edu}"
ADMIN_PW="${ADMIN_PW:-change-me-too}"

echo "1. health"
curl -fsS "$API/health" | grep -q '"ok"' && echo "   ok"

echo "2. login"
TOKEN=$(curl -fsS -X POST "$API/auth/login" \
  -d "username=$ADMIN_EMAIL&password=$ADMIN_PW" | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
auth=(-H "Authorization: Bearer $TOKEN")
echo "   ok"

echo "3. create student"
curl -fsS -X POST "$API/students" "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{"roll_no":"SMOKE001","full_name":"Smoke Test","department":"CSE","biometric_consent":true}' >/dev/null \
  && echo "   ok" || echo "   (already exists, continuing)"

echo "4. create course"
curl -fsS -X POST "$API/courses" "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{"code":"SMOKE101","name":"Smoke Course","department":"CSE"}' >/dev/null \
  && echo "   ok" || echo "   (already exists, continuing)"

CID=$(curl -fsS "$API/courses" "${auth[@]}" | python3 -c 'import sys,json;print([c["id"] for c in json.load(sys.stdin) if c["code"]=="SMOKE101"][0])')

echo "5. add to roster"
curl -fsS -X POST "$API/courses/$CID/roster" "${auth[@]}" -H 'Content-Type: application/json' \
  -d '{"roll_nos":["SMOKE001"]}' >/dev/null && echo "   ok"

echo "6. create session"
SID=$(curl -fsS -X POST "$API/sessions" "${auth[@]}" -H 'Content-Type: application/json' \
  -d "{\"course_id\":$CID}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "   session #$SID"

echo "7. read session"
curl -fsS "$API/sessions/$SID" "${auth[@]}" | grep -q '"state"' && echo "   ok"

echo
echo "SMOKE TEST PASSED ✅  (upload a real group photo to test face matching)"
