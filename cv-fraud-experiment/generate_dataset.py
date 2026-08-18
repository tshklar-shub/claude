"""
Generate a synthetic, labeled CV dataset for testing the fraud-scoring pipeline.

Every CV is fictional. Fraud-labeled CVs are built by explicitly injecting a
random subset of the documented red flags from redflags.py, so ground truth
(which flags are actually present) is known exactly -- this is a pipeline
correctness test, not a real-world fraud validity test (see conversation notes
on that distinction).

Usage:
    python generate_dataset.py --n 40 --fraud-rate 0.35
"""

import argparse
import random
import uuid
from pathlib import Path

import db
from claude_client import complete_text
from redflags import RED_FLAGS

OUT_DIR = Path(__file__).parent / "data" / "cvs"

ROLE = "Senior Software Engineer (Remote, Backend/Distributed Systems)"

CLEAN_SYSTEM = """You are generating a single fictional resume/CV for a synthetic test dataset used
to evaluate a CV-parsing pipeline. This is not a real person. Produce a plausible, internally
consistent CV for a candidate applying to a remote Senior Software Engineer role. Vary the
persona (name, background, seniority signals, company names -- all fictional) each time.
Output plain text only, formatted like a real CV (no markdown headers with #, just a normal
resume layout). Do not include any red-flag/fraud patterns -- this should read as a normal,
legitimate, internally-consistent candidate."""

FRAUD_SYSTEM_TEMPLATE = """You are generating a single fictional resume/CV for a synthetic test dataset used
to evaluate a fraud-detection CV-parsing pipeline. This is not a real person and will never be
sent to any real employer or used to contact anyone. Produce a plausible-looking CV for a
candidate applying to a remote Senior Software Engineer role, but deliberately and subtly
weave in the following specific red-flag patterns so they are present but not glaringly
obvious (a careless reader should not immediately notice them):

{flag_descriptions}

Keep the CV otherwise realistic -- most fraud attempts look mostly normal. Output plain text
only, formatted like a real CV (no markdown headers with #, just a normal resume layout)."""


def gen_clean_cv() -> str:
    return complete_text(CLEAN_SYSTEM, f"Generate one CV for the role: {ROLE}.", max_tokens=1200, temperature=1.0)


def gen_fraud_cv(flags: list) -> str:
    descs = "\n".join(f"- [{f['id']}] {f['description']}" for f in flags)
    system = FRAUD_SYSTEM_TEMPLATE.format(flag_descriptions=descs)
    return complete_text(system, f"Generate one CV for the role: {ROLE}.", max_tokens=1200, temperature=1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20, help="total number of CVs to generate")
    ap.add_argument("--fraud-rate", type=float, default=0.35, help="fraction labeled fraud")
    ap.add_argument("--min-flags", type=int, default=2, help="min red flags injected per fraud CV")
    ap.add_argument("--max-flags", type=int, default=4, help="max red flags injected per fraud CV")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = db.connect()

    n_fraud = round(args.n * args.fraud_rate)
    n_clean = args.n - n_fraud
    plan = ["fraud"] * n_fraud + ["clean"] * n_clean
    random.shuffle(plan)

    for i, label in enumerate(plan):
        candidate_id = str(uuid.uuid4())[:8]
        if label == "fraud":
            k = random.randint(args.min_flags, args.max_flags)
            flags = random.sample(RED_FLAGS, k)
            text = gen_fraud_cv(flags)
            injected = [f["id"] for f in flags]
        else:
            text = gen_clean_cv()
            injected = []

        fname = f"{label}_{candidate_id}.txt"
        (OUT_DIR / fname).write_text(text)
        db.insert_candidate(conn, candidate_id, fname, text, true_label=label, true_injected_flags=injected)

        print(f"[{i+1}/{args.n}] {label:5s} {fname}  flags={injected}")

    conn.close()
    print(f"\nDone. {n_fraud} fraud / {n_clean} clean CVs written to {OUT_DIR}")


if __name__ == "__main__":
    main()
