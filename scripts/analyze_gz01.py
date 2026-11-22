#!/usr/bin/env python3
import glob
import json
import math
import os
from datetime import datetime
from collections import Counter

RUN_DIR = "/root/ros2_ws/src/ai_worker/ffw_codex/runs/gz_01"

def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

result = json.load(open(f"{RUN_DIR}/result.json"))
run_meta = json.load(open(f"{RUN_DIR}/run.json"))
host_meta = json.load(open(f"{RUN_DIR}/host.json"))

history = [json.loads(line) for line in open(f"{RUN_DIR}/public/history.jsonl") if line.strip()]
rollout_files = sorted(glob.glob(f"{RUN_DIR}/rollout/*.json"))
rollouts = [json.load(open(f)) for f in rollout_files]

# Also check agent_events for LLM latency vs tool execution latency
events = [json.loads(line) for line in open(f"{RUN_DIR}/agent_events.jsonl") if line.strip()]

print("=== RUN / HOST META ===")
print("run.json:", json.dumps(run_meta, indent=2))
print("host.json keys:", list(host_meta.keys()))
print("result.json:", json.dumps(result, indent=2))

print("\n=== TOOL & STATUS BREAKDOWN ===")
tool_counts = Counter(r["tool"] for r in rollouts)
status_counts = Counter(r["result"].get("status") for r in rollouts)
tool_status = Counter((r["tool"], r["result"].get("status")) for r in rollouts)
print("Tool counts:", dict(tool_counts))
print("Status counts:", dict(status_counts))
print("Tool x Status:", {f"{k[0]}:{k[1]}": v for k, v in tool_status.items()})

print("\n=== TIMING & RTF ANALYSIS ===")
t0 = parse_iso(history[0]["at"])
t_end = parse_iso(history[-1]["at"])
sim0 = history[0]["observation"]["stamp_s"]
sim_end = [h["observation"]["stamp_s"] for h in history if h.get("observation")][-1]
wall_span = (t_end - t0).total_seconds()
sim_span = sim_end - sim0
print(f"First call: {history[0]['at']} (sim_s={sim0:.3f})")
print(f"Last call : {history[-1]['at']} (sim_s={sim_end:.3f})")
print(f"Wall span (call 1..{len(history)}): {wall_span:.2f}s | Sim span: {sim_span:.2f}s | Avg RTF: {sim_span/wall_span:.4f}")

# Inter-call intervals & action intervals
intervals = []
action_exec_elapsed = []
sync_offsets = []
for i in range(1, len(history)):
    dt = (parse_iso(history[i]["at"]) - parse_iso(history[i-1]["at"])).total_seconds()
    intervals.append(dt)

for r in rollouts:
    res = r.get("result", {})
    data = res.get("data") or {}
    arr = data.get("arrival") or {}
    if "elapsed_s" in arr:
        action_exec_elapsed.append((r["tool"], res.get("status"), arr["elapsed_s"]))
    obs = data.get("post_observation") or data
    if isinstance(obs, dict) and "max_offset_s" in obs:
        sync_offsets.append(obs["max_offset_s"])

print(f"Inter-call wall interval (N={len(intervals)}): mean={sum(intervals)/len(intervals):.2f}s, median={sorted(intervals)[len(intervals)//2]:.2f}s, min={min(intervals):.2f}s, max={max(intervals):.2f}s")
print(f"Effective decision rate (all calls): {len(history)/result['elapsed_s']:.4f} Hz ({result['elapsed_s']/len(history):.2f} s/call)")
print(f"Effective action rate (executed actions): {result['actions_executed']/result['elapsed_s']:.4f} Hz ({result['elapsed_s']/result['actions_executed']:.2f} s/action)")
print(f"Action-only wait elapsed_s (N={len(action_exec_elapsed)}): mean={sum(x[2] for x in action_exec_elapsed)/max(1,len(action_exec_elapsed)):.2f}s")
if sync_offsets:
    print(f"Multi-sensor sync max_offset_s (N={len(sync_offsets)}): mean={sum(sync_offsets)/len(sync_offsets)*1000:.2f}ms, max={max(sync_offsets)*1000:.2f}ms")

# Estimate LLM thinking+network latency vs Robot execution time from call files
call_reqs = sorted(glob.glob(f"{RUN_DIR}/calls/*_request.json"))
call_ress = sorted(glob.glob(f"{RUN_DIR}/calls/*_result.json"))
print(f"calls/ requests: {len(call_reqs)}, results: {len(call_ress)}")
tool_durations = []
llm_gaps = []
prev_res_t = None
for req_f, res_f in zip(call_reqs, call_ress):
    req = json.load(open(req_f))
    res = json.load(open(res_f))
    t_req = parse_iso(req["started_at"])
    t_res = parse_iso(res["finished_at"])
    tool_durations.append((t_res - t_req).total_seconds())
    if prev_res_t is not None:
        llm_gaps.append((t_req - prev_res_t).total_seconds())
    prev_res_t = t_res

if tool_durations:
    print(f"Harness+Robot tool duration (N={len(tool_durations)}): total={sum(tool_durations):.1f}s, mean={sum(tool_durations)/len(tool_durations):.2f}s, min={min(tool_durations):.2f}s, max={max(tool_durations):.2f}s")
if llm_gaps:
    print(f"LLM think+API gap between calls (N={len(llm_gaps)}): total={sum(llm_gaps):.1f}s, mean={sum(llm_gaps)/len(llm_gaps):.2f}s, median={sorted(llm_gaps)[len(llm_gaps)//2]:.2f}s, min={min(llm_gaps):.2f}s, max={max(llm_gaps):.2f}s")

print("\n=== PHASE-BY-PHASE CALL LOG ===")
for i, (h, r) in enumerate(zip(history, rollouts), 1):
    obs = h.get("observation")
    pos_str = ""
    if obs:
        rx, ry, rz = obs["arms"]["right"]["xyz"]
        hd = obs["body"]["head_joint1"]
        lf = obs["body"]["lift_joint"]
        grp = obs["arms"]["right"]["gripper"]
        pos_str = f"R_EE=({rx:.3f},{ry:.3f},{rz:.3f}) head={hd:.2f} lift={lf:.3f} grp={grp:.2f} sim={obs['stamp_s']:.1f}s"
    reason = (r.get("arguments") or {}).get("reason", "")
    reason_short = (reason[:90] + "...") if len(reason) > 90 else reason
    dt_from_start = (parse_iso(h["at"]) - t0).total_seconds()
    print(f"#{i:02d} +{dt_from_start:6.1f}s | {h['tool']:13s} | {h['status']:8s} | {pos_str} | {reason_short}")
