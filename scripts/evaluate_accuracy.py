#!/usr/bin/env python3
"""Accuracy / bias validation harness for the face-recognition pipeline.

Runs the SAME production code path (InsightFace engine + cosine threshold from
app settings) over a labeled evaluation set and reports:

  * Verification: true-accept rate (TAR) on genuine pairs and false-accept
    rate (FAR) on impostor pairs at the production threshold.
  * Identification: rank-1 accuracy against the full enrolled gallery
    (the "who is this face" question the attendance matcher answers).
  * Per-group breakdown (skin tone, lighting, gender, ... — any grouping you
    provide) with a bias flag when a group's TAR deviates from the overall
    TAR by more than --bias-tolerance percentage points.

Dataset layout (photos never leave this machine):
    dataset/
      <person_label>/
        enroll.jpg      # or any file; alphabetically-first image = enrollment
        probe1.jpg
        probe2.jpg
      <person_label_2>/
        ...

Optional groups CSV (header required) for the bias breakdown:
    label,group
    2021CS001,skin_tone_dark
    2021CS002,skin_tone_light

Multiple group files can be passed (e.g. one for skin tone, one for lighting);
each produces its own breakdown table.

Usage:
    cd backend && pip install -r requirements.txt   # once
    python scripts/evaluate_accuracy.py --dataset ./eval_photos \
        --groups skin_tone.csv --groups lighting.csv --json report.json

Interpreting results: NIST FRVT documents measurable demographic differentials
in most face-recognition models. If a group is flagged here, do NOT deploy
auto-marking for affected cohorts without lowering the threshold impact (the
human-review step already catches false absents, but systematic differences
must be surfaced to the operator, not hidden).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

# Make the backend app importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def load_dataset(root: Path) -> dict[str, list[Path]]:
    """Return {person_label: [image paths, alphabetically sorted]}."""
    people: dict[str, list[Path]] = {}
    for person_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        images = sorted(
            f for f in person_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS
        )
        if len(images) >= 2:
            people[person_dir.name] = images
        else:
            print(f"  ! skipping {person_dir.name}: needs >=2 images "
                  f"(1 enrollment + >=1 probe), found {len(images)}")
    return people


def embed(path: Path):
    """Embed one face via the production engine; None if unusable."""
    from app.face.engine import embed_single_face

    try:
        return embed_single_face(path.read_bytes())
    except ValueError as e:
        print(f"  ! {path}: {e}")
        return None


def load_groups(csv_path: Path) -> dict[str, str]:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if not {"label", "group"} <= set(reader.fieldnames or []):
            raise SystemExit(f"{csv_path}: needs 'label,group' header")
        return {row["label"].strip(): row["group"].strip() for row in reader}


def rate(hits: int, total: int) -> float | None:
    return hits / total if total else None


def fmt(x: float | None) -> str:
    return "  n/a " if x is None else f"{100 * x:5.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True, type=Path,
                    help="root dir: one subdir per person, >=2 images each")
    ap.add_argument("--groups", action="append", default=[], type=Path,
                    help="CSV (label,group) for a per-group breakdown; repeatable")
    ap.add_argument("--threshold", type=float, default=None,
                    help="override the production cosine threshold")
    ap.add_argument("--bias-tolerance", type=float, default=5.0,
                    help="flag groups whose TAR deviates from overall by more "
                         "than this many percentage points (default 5)")
    ap.add_argument("--json", type=Path, default=None,
                    help="also write the full report to this JSON file")
    args = ap.parse_args()

    from app.config import settings

    threshold = args.threshold if args.threshold is not None else settings.face_match_threshold
    print(f"Model pack: {settings.face_model_pack}   threshold: {threshold}")

    people = load_dataset(args.dataset)
    if len(people) < 2:
        raise SystemExit("Need at least 2 people to measure false accepts.")

    # ── Embed everything (first image = enrollment/gallery, rest = probes) ──
    print(f"Embedding {sum(len(v) for v in people.values())} images "
          f"for {len(people)} people ...")
    gallery: dict[str, np.ndarray] = {}
    probes: dict[str, list[np.ndarray]] = defaultdict(list)
    skipped = 0
    for label, images in people.items():
        g = embed(images[0])
        if g is None:
            skipped += len(images)
            continue
        gallery[label] = g
        for img in images[1:]:
            p = embed(img)
            if p is None:
                skipped += 1
            else:
                probes[label].append(p)

    labels = [lb for lb in gallery if probes[lb]]
    if len(labels) < 2:
        raise SystemExit("Too few usable people after embedding failures.")
    gallery_mat = np.vstack([gallery[lb] for lb in labels])   # (P, 512)

    # ── Verification + rank-1 identification ────────────────────────────────
    genuine_hit = genuine_total = 0
    impostor_hit = impostor_total = 0
    rank1_hit = rank1_total = 0
    per_person: dict[str, dict] = {}

    for i, lb in enumerate(labels):
        p_gen_hit = p_gen_tot = p_r1_hit = 0
        for probe in probes[lb]:
            sims = gallery_mat @ probe                        # cosine (normalized)
            # verification vs own enrollment
            genuine_total += 1
            p_gen_tot += 1
            if sims[i] >= threshold:
                genuine_hit += 1
                p_gen_hit += 1
            # verification vs every other enrollment (impostor pairs)
            for j in range(len(labels)):
                if j != i:
                    impostor_total += 1
                    if sims[j] >= threshold:
                        impostor_hit += 1
            # rank-1 identification over the whole gallery
            rank1_total += 1
            if int(np.argmax(sims)) == i and sims[i] >= threshold:
                rank1_hit += 1
                p_r1_hit += 1
        per_person[lb] = {
            "probes": p_gen_tot,
            "tar": rate(p_gen_hit, p_gen_tot),
            "rank1": rate(p_r1_hit, p_gen_tot),
        }

    overall = {
        "people": len(labels),
        "probes": genuine_total,
        "skipped_images": skipped,
        "threshold": threshold,
        "tar": rate(genuine_hit, genuine_total),
        "far": rate(impostor_hit, impostor_total),
        "rank1": rate(rank1_hit, rank1_total),
    }

    print("\n== Overall ==")
    print(f"  people: {overall['people']}   probes: {overall['probes']}   "
          f"skipped images: {skipped}")
    print(f"  TAR (true accept)  : {fmt(overall['tar'])}")
    print(f"  FAR (false accept) : {fmt(overall['far'])}  "
          f"({impostor_hit}/{impostor_total} impostor pairs)")
    print(f"  Rank-1 identification: {fmt(overall['rank1'])}")

    # ── Per-group bias breakdown ─────────────────────────────────────────────
    report = {"overall": overall, "per_person": per_person, "groups": {}}
    flagged: list[str] = []
    for groups_csv in args.groups:
        mapping = load_groups(groups_csv)
        buckets: dict[str, list[str]] = defaultdict(list)
        for lb in labels:
            buckets[mapping.get(lb, "<unlabeled>")].append(lb)

        print(f"\n== Breakdown: {groups_csv.name} ==")
        print(f"  {'group':24s} {'people':>6s} {'probes':>6s} {'TAR':>7s} {'rank1':>7s}")
        table = {}
        for group, members in sorted(buckets.items()):
            g_tot = sum(per_person[lb]["probes"] for lb in members)
            g_tar_hits = sum(
                (per_person[lb]["tar"] or 0) * per_person[lb]["probes"] for lb in members
            )
            g_r1_hits = sum(
                (per_person[lb]["rank1"] or 0) * per_person[lb]["probes"] for lb in members
            )
            g_tar = rate(round(g_tar_hits), g_tot)
            g_r1 = rate(round(g_r1_hits), g_tot)
            table[group] = {"people": len(members), "probes": g_tot,
                            "tar": g_tar, "rank1": g_r1}
            marker = ""
            if (g_tar is not None and overall["tar"] is not None
                    and abs(g_tar - overall["tar"]) * 100 > args.bias_tolerance
                    and group != "<unlabeled>"):
                marker = "  <-- BIAS FLAG"
                flagged.append(f"{groups_csv.name}:{group}")
            print(f"  {group:24s} {len(members):6d} {g_tot:6d} "
                  f"{fmt(g_tar)} {fmt(g_r1)}{marker}")
        report["groups"][groups_csv.name] = table

    if flagged:
        print(f"\n!! Groups outside +/-{args.bias_tolerance}pp of overall TAR: "
              f"{', '.join(flagged)}")
        print("!! Review threshold/enrollment quality for these cohorts before "
              "relying on auto-marking. The human-review step is mandatory.")

    if args.json:
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nFull report written to {args.json}")

    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
