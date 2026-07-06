#!/usr/bin/env python3
"""Bulk-enroll students and their faces from a folder of photos + a CSV.

One-time onboarding tool for ~14k students. Run it against a live API instance.
It does NOT store photos anywhere — each photo is sent to the API, converted to
an embedding server-side, and the local copy is left untouched (delete your
source photos afterward per your retention policy).

CSV format (header required):
    roll_no,full_name,department,photo,consent
    2021CS001,Asha Rao,CSE,2021CS001.jpg,yes

- `photo` is a filename relative to --photos-dir. Leave blank to create the
  student record without a face (enroll the face later).
- `consent` must be yes/true/1 for a face to be enrolled (DPDP requirement).

Usage:
    python bulk_enroll.py --api http://localhost:8000 \
        --admin-email admin@college.edu --admin-password '...' \
        --csv students.csv --photos-dir ./photos
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import json
import uuid

TRUE = {"yes", "true", "1", "y"}


def _http(method: str, url: str, token: str | None = None, data: bytes | None = None,
          content_type: str | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"detail": body.decode(errors="replace")}


def login(api: str, email: str, password: str) -> str:
    data = urllib.parse.urlencode({"username": email, "password": password}).encode()
    status, body = _http("POST", f"{api}/auth/login", data=data,
                          content_type="application/x-www-form-urlencoded")
    if status != 200:
        sys.exit(f"Login failed ({status}): {body}")
    return body["access_token"]


def create_student(api: str, token: str, row: dict) -> int | None:
    consent = row.get("consent", "").strip().lower() in TRUE
    payload = json.dumps({
        "roll_no": row["roll_no"].strip(),
        "full_name": row["full_name"].strip(),
        "department": row.get("department", "").strip(),
        "biometric_consent": consent,
    }).encode()
    status, body = _http("POST", f"{api}/students", token=token, data=payload,
                         content_type="application/json")
    if status == 201:
        return body["id"]
    if status == 409:
        # Already exists — look it up so we can still enroll the face.
        _, students = _http("GET", f"{api}/students?limit=100000", token=token)
        for s in students:
            if s["roll_no"] == row["roll_no"].strip():
                return s["id"]
    print(f"  ! student {row['roll_no']}: {status} {body}", file=sys.stderr)
    return None


def enroll_face(api: str, token: str, student_id: int, photo_path: str) -> bool:
    with open(photo_path, "rb") as fh:
        content = fh.read()
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{os.path.basename(photo_path)}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    status, resp = _http("POST", f"{api}/students/{student_id}/face", token=token,
                         data=body, content_type=f"multipart/form-data; boundary={boundary}")
    if status == 200:
        return True
    print(f"  ! face enroll student {student_id}: {status} {resp}", file=sys.stderr)
    return False


def main() -> None:
    p = argparse.ArgumentParser(description="Bulk-enroll students and faces")
    p.add_argument("--api", required=True)
    p.add_argument("--admin-email", required=True)
    p.add_argument("--admin-password", required=True)
    p.add_argument("--csv", required=True)
    p.add_argument("--photos-dir", default=".")
    args = p.parse_args()

    token = login(args.api, args.admin_email, args.admin_password)
    created = faces = skipped = 0

    with open(args.csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sid = create_student(args.api, token, row)
            if sid is None:
                skipped += 1
                continue
            created += 1
            photo = row.get("photo", "").strip()
            consent = row.get("consent", "").strip().lower() in TRUE
            if photo and consent:
                path = os.path.join(args.photos_dir, photo)
                if not os.path.exists(path):
                    print(f"  ! missing photo {path}", file=sys.stderr)
                elif enroll_face(args.api, token, sid, path):
                    faces += 1
            print(f"  ok {row['roll_no']}")

    print(f"\nDone. students={created} faces_enrolled={faces} skipped={skipped}")


if __name__ == "__main__":
    main()
