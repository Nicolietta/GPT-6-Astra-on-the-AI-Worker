#!/usr/bin/env python3
import glob, json
from collections import Counter
from datetime import datetime

def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

RUN_DIR = "/root/ros2_ws/src/ai_worker/ffw_codex/runs/gz_02"
res = json.load(open(f"{RUN_DIR}/result.json"))
hist = [json.loads(l) for l in open(f"{RUN_DIR}/public/history.jsonl") if l.strip()]
reqs = [json.load(open(f)) for f in sorted(glob.glob(f"{RUN_DIR}/calls/*_request.json"))]
ress = [json.load(open(f)) for f in sorted(glob.glob(f"{RUN_DIR}/calls/*_result.json"))]
rpc_in = [json.loads(l) for l in open(f"{RUN_DIR}/rpc_in.jsonl") if l.strip()]

sleeps = []
for m in rpc_in:
    if m.get("method") == "item/completed":
        it = (m.get("params") or {}).get("item") or {}
        if it.get("type") == "sleep":
            dur = (it["completedAtMs"] - it["startedAtMs"]) / 1000.0 if it.get("startedAtMs") and it.get("completedAtMs") else it.get("durationMs", 0) / 1000.0
            sleeps.append(dur)

t_start = parse_iso(reqs[0]["started_at"])
t_end = parse_iso(ress[-1]["finished_at"])
wall_span = (t_end - t_start).total_seconds()
sim_stamps = [h["observation"]["stamp_s"] for h in hist if h.get("observation")]
sim_span = sim_stamps[-1] - sim_stamps[0]

tool_s = sum((parse_iso(s["finished_at"]) - parse_iso(r["started_at"])).total_seconds() for r, s in zip(reqs, ress))
sleep_s = sum(sleeps)
llm_s = wall_span - tool_s - sleep_s

print("=== gz_02 EXACT TELEMETRY ===")
print(f"Wall span (call 1..{len(hist)}): {wall_span:.2f}s | elapsed_s (result.json): {res['elapsed_s']}s")
print(f"Sim span: {sim_stamps[0]:.2f} -> {sim_stamps[-1]:.2f} = {sim_span:.2f}s | Avg RTF: {sim_span / wall_span:.4f}x")
print(f"Sleeps: count={len(sleeps)}, total={sleep_s:.2f}s ({100 * sleep_s / wall_span:.1f}%)")
print(f"LLM+API: total={llm_s:.2f}s ({100 * llm_s / wall_span:.1f}%), mean={llm_s / max(1, len(hist) - 1):.2f}s")
print(f"Tool+Robot: total={tool_s:.2f}s ({100 * tool_s / wall_span:.1f}%)")
print("Tool counts:", dict(Counter(h["tool"] for h in hist)))
print("Status counts:", dict(Counter(h["status"] for h in hist)))
print("Actions executed:", res["actions_executed"], "| Observations:", res["observations"], "| Calls:", res["robot_tool_calls"])
tok = res["tokens"]
hit = 100.0 * tok["cached_input"] / max(1, tok["cached_input"] + tok["uncached_input"])
print(f"Tokens: total={tok['total']:,}, cached={tok['cached_input']:,} ({hit:.2f}%), output={tok['output']:,}, reasoning={tok['reasoning']:,}, cost=${res['cost_usd_estimate']}")
print("\n=== Last 12 calls ===")
for h in hist[-12:]:
    obs = h.get("observation")
    p = ""
    if obs:
        x, y, z = obs["arms"]["right"]["xyz"]
        g = obs["arms"]["right"]["gripper"]
        p = f"R_EE=({x:+.3f},{y:+.3f},{z:+.3f}) grp={g:.3f} sim={obs['stamp_s']:.1f}s"
    print(f"#{h['progress']['call_index']:02d} {h['tool']:18s} {h['status']:8s} | {p} | {h['reason']}")
