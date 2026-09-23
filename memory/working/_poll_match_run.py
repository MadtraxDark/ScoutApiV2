"""Poll MatchRun status until terminal."""

from __future__ import annotations

import json
import sys
import time
import urllib.request

RUN = sys.argv[1] if len(sys.argv) > 1 else ""
if not RUN:
    raise SystemExit("usage: poll_match_run.py <run_id>")

url = f"http://localhost:8000/match-runs/{RUN}"
prev = None
stall = 0
t0 = time.time()

while True:
    with urllib.request.urlopen(url, timeout=15) as response:
        data = json.loads(response.read().decode())
    status = data["status"]
    key = (
        status,
        data.get("stores_completed"),
        data.get("matches_found"),
        data.get("errors"),
        data.get("last_activity_at"),
    )
    elapsed = int(time.time() - t0)
    if key != prev:
        print(
            f"[{elapsed}s] status={status} "
            f"stores={data.get('stores_completed')}/{data.get('stores_total')} "
            f"matches={data.get('matches_found')} no={data.get('no_matches')} "
            f"err={data.get('errors')} activity={data.get('last_activity_at')}",
            flush=True,
        )
        prev = key
        stall = 0
    else:
        stall += 1
    if status in ("completed", "failed", "cancelled"):
        print(json.dumps(data, indent=2, default=str))
        break
    if elapsed > 1200:
        print("TIMEOUT_1200s", json.dumps(data, default=str))
        break
    if stall >= 12 and status == "running":
        print("STALL_WARNING", json.dumps(data, default=str))
        break
    time.sleep(30)
