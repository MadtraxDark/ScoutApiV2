import json
import re
from pathlib import Path

h = Path("data/kabum_q1.html").read_text(encoding="utf-8", errors="replace")
m = re.search(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    h,
    re.S,
)
assert m
rows = json.loads(m.group(1))["props"]["pageProps"]["data"]["catalogServer"]["data"]
print("keys", sorted(rows[0].keys()))
for k in sorted(rows[0].keys()):
    v = rows[0][k]
    if isinstance(v, (str, int, float, bool)) or v is None:
        print(f"  {k}={v!r}"[:160])
    else:
        print(f"  {k}=<{type(v).__name__}>")
