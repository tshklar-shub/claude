"""
Find the optimal OLLAMA_NUM_PARALLEL setting for the machine this is run on,
empirically: for each candidate parallelism level, restart Ollama configured
for exactly that level, fire that many concurrent extraction requests against
a realistic-length CV, and measure actual throughput (candidates/sec). Ramps
up while throughput keeps improving, then confirms the peak by testing one
level past it.

Why restart Ollama per level rather than just varying client-side concurrency
against one server: OLLAMA_NUM_PARALLEL controls how the server divides
KV-cache memory into slots at startup, so a server configured for N=8 behaves
differently even at 1 concurrent request than one configured for N=1 -- the
level being tested needs to actually be the server's real configuration to
get a result that means anything.

This machine's numbers won't transfer to a different machine (verified: the
"more parallelism = more throughput" assumption already broke between two
model sizes on the same M1 in manual testing). Run this on whatever machine
will actually process the real batch, not just once here.

Usage:
    python3 tune_parallelism.py --model qwen3:4b --levels 1,2,3,4,6,8
"""

import argparse
import json
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

OLLAMA_BIN = "/Applications/Ollama.app/Contents/Resources/ollama"
HOST = "http://localhost:11434"

# A realistic-length test payload matters -- this project's own synthetic CVs
# average ~100 words, real resumes average ~700. Using a short payload would
# understate memory/KV-cache pressure and give an optimistic, wrong answer.
SAMPLE_CV = """Jordan Ellis
jordan.ellis@example.com | (555) 019-2231 | Denver, CO

SUMMARY
Operations manager with 9 years of experience leading cross-functional teams across logistics,
procurement, and vendor management. Proven track record of reducing costs while improving
service-level outcomes in fast-paced distribution environments.

EXPERIENCE
Senior Operations Manager, Meridian Distribution Group -- Mar 2021 to Present
Oversee daily operations for a 300,000 sq ft distribution center serving the western region.
Led implementation of a new warehouse management system that reduced order-fulfillment errors
by 22% within the first two quarters. Manage a team of 45 across three shifts, responsible for
staffing, scheduling, and performance reviews. Negotiated contracts with six regional carriers,
saving approximately $180,000 annually in freight costs. Partnered with IT to roll out barcode
scanning across all inbound receiving docks.

Operations Manager, Northgate Logistics -- Jan 2018 to Feb 2021
Managed inventory accuracy program that improved cycle-count accuracy from 91% to 98.5%.
Supervised a team of 22 warehouse associates and 4 shift leads. Coordinated with procurement to
implement just-in-time ordering for high-turnover SKUs, reducing carrying costs by 15%.
Conducted root-cause analysis on shipping delays and implemented corrective action plans.

Warehouse Supervisor, Northgate Logistics -- Jun 2015 to Dec 2017
Supervised receiving and put-away operations for a mid-size regional warehouse. Trained new
hires on safety protocols and equipment operation. Maintained OSHA compliance records and led
monthly safety audits. Assisted in transition to a new WMS platform.

EDUCATION
B.S. Business Administration, University of Colorado Denver, 2015

CERTIFICATIONS
Certified Supply Chain Professional (CSCP), APICS, 2019
OSHA 30-Hour General Industry Certification, 2017

REFERENCES
Available upon request. Former director at Northgate Logistics can be reached through the
company's main office line."""


def restart_ollama(num_parallel: int):
    # `ollama serve` spawns a *child* llama-server process that actually holds the model
    # in memory -- killing only the parent (as an earlier version of this script did)
    # leaves that child running, competing for GPU/memory with the next restart's fresh
    # instance. Verified in practice: this caused a supposedly-restarted server to be
    # 5x+ slower than a genuinely clean instance, produced nonsense timing results, and
    # left a zombie process that had eaten 46 minutes of CPU time by the time it was
    # found. Kill both, and confirm nothing is left before starting the next instance.
    subprocess.run(["pkill", "-9", "-f", "llama-server"], capture_output=True)
    subprocess.run(["pkill", "-9", "-f", "ollama serve"], capture_output=True)
    time.sleep(2)
    leftover = subprocess.run(["pgrep", "-f", "llama-server|ollama serve"],
                               capture_output=True, text=True).stdout.strip()
    if leftover:
        raise RuntimeError(f"Ollama/llama-server processes still running after kill "
                            f"(PIDs: {leftover.splitlines()}) -- refusing to start a new "
                            f"instance on top of them. Kill manually and re-run.")

    env = {"OLLAMA_NUM_PARALLEL": str(num_parallel)}
    import os
    full_env = os.environ.copy()
    full_env.update(env)
    log = open(f"/tmp/ollama_tune_{num_parallel}.log", "w")
    subprocess.Popen([OLLAMA_BIN, "serve"], env=full_env, stdout=log, stderr=log,
                      start_new_session=True)
    # wait for the server to actually be up
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{HOST}/api/version", timeout=2)
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"Ollama didn't come up after restart with NUM_PARALLEL={num_parallel}")


REQUEST_TIMEOUT = 420  # generous -- under contention a single request can legitimately
                        # take several minutes; better to wait than to record a bogus failure


def one_extraction(model: str, results: list, idx: int, timeout: int = REQUEST_TIMEOUT):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Extract the candidate's full name and every "
             "company name mentioned. Output JSON: {\"full_name\": string, "
             "\"companies\": [string]}"},
            {"role": "user", "content": SAMPLE_CV},
        ],
        "stream": False,
        "think": False,
        "options": {"num_predict": 500},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{HOST}/api/chat", data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        results[idx] = time.time() - t0
    except Exception as e:
        results[idx] = None
        print(f"    request {idx} failed: {e}")


def warm_up(model: str):
    """Send one request and wait for it to fully complete before timing anything --
    without this, the timed batch's first requests race the model's cold-start load
    time (reading weights off disk into GPU memory), which produced spurious full-length
    timeouts on every level >=2 in initial testing here even though the server was
    technically 'up' per /api/version."""
    print("    warming up (loading model into memory, untimed)...")
    placeholder = [None]
    one_extraction(model, placeholder, 0, timeout=REQUEST_TIMEOUT)
    if placeholder[0] is None:
        raise RuntimeError("Warm-up request itself failed -- check Ollama is healthy before tuning.")
    print(f"    warm-up done ({placeholder[0]:.1f}s)")


def test_level(model: str, level: int) -> dict:
    print(f"\n--- Testing OLLAMA_NUM_PARALLEL={level} ---")
    restart_ollama(level)
    warm_up(model)

    results = [None] * level
    t0 = time.time()
    threads = [threading.Thread(target=one_extraction, args=(model, results, i)) for i in range(level)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall_clock = time.time() - t0

    ok = [r for r in results if r is not None]
    if len(ok) < level:
        print(f"    {len(ok)}/{level} succeeded -- INVALID result, excluding this level from comparison")
        return {"level": level, "wall_clock": wall_clock, "succeeded": len(ok), "throughput": None}

    throughput = level / wall_clock if wall_clock > 0 else 0
    print(f"    {len(ok)}/{level} succeeded, wall_clock={wall_clock:.1f}s, "
          f"throughput={throughput:.3f} candidates/sec ({1/throughput:.1f}s/candidate effective)")
    return {"level": level, "wall_clock": wall_clock, "succeeded": len(ok),
             "throughput": throughput}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, default="qwen3:4b")
    ap.add_argument("--levels", type=str, default="1,2,3,4,6,8",
                     help="comma-separated OLLAMA_NUM_PARALLEL values to test, in order")
    args = ap.parse_args()

    levels = [int(x) for x in args.levels.split(",")]
    results = []
    best = None

    try:
        for level in levels:
            r = test_level(args.model, level)
            results.append(r)
            if r["throughput"] is None:
                continue  # invalid result (some requests failed) -- don't let it influence best/stop logic
            if best is None or r["throughput"] > best["throughput"]:
                best = r
            elif r["throughput"] < best["throughput"] * 0.95:
                # throughput dropped meaningfully below the best seen -- confirmed past the peak
                print(f"\nThroughput declined at level={level} vs best so far (level={best['level']}). "
                      f"Stopping the ramp -- peak found.")
                break
    finally:
        # Don't leave a server running after this script exits -- it's already caused
        # one confusing zombie-process bug this session.
        subprocess.run(["pkill", "-9", "-f", "llama-server"], capture_output=True)
        subprocess.run(["pkill", "-9", "-f", "ollama serve"], capture_output=True)

    print("\n=== Results ===")
    print(f"{'Level':<8}{'Wall clock':<14}{'Throughput (cand/s)':<22}{'Effective s/candidate'}")
    for r in results:
        if r["throughput"] is None:
            print(f"{r['level']:<8}{r['wall_clock']:<14.1f}{'INVALID (' + str(r['succeeded']) + '/' + str(r['level']) + ' ok)':<22}-")
        else:
            print(f"{r['level']:<8}{r['wall_clock']:<14.1f}{r['throughput']:<22.3f}{1/r['throughput']:.1f}")

    if best is None:
        print("\nNo level produced a valid result -- every tested level had failures. "
              "Something is wrong beyond parallelism tuning (check Ollama health, model pull, "
              "available memory) before trying again.")
        sys.exit(1)

    print(f"\nRecommended OLLAMA_NUM_PARALLEL for this machine + model ({args.model}): {best['level']}")
    print(f"  (throughput {best['throughput']:.3f} candidates/sec = {1/best['throughput']:.1f}s/candidate effective)")
    print(f"\nSet it with: OLLAMA_NUM_PARALLEL={best['level']} ollama serve")
    print("This result is specific to this machine and this model -- re-run if either changes.")


if __name__ == "__main__":
    main()
