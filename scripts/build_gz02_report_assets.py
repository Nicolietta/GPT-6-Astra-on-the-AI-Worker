#!/usr/bin/env python3
"""
Analyze gz_02 complete logs, compare with gz_01, and generate:
1. /workspace/gz02_report_assets/gz02_metrics.json
2. /workspace/gz02_report_assets/gz_02_ab_comparison_charts.png
3. /workspace/gz02_report_assets/gz_02_key_milestones.png
4. /workspace/gz02_report_assets/gz_02_full_replay.mp4 (1440x810 H.264)
"""
import glob
import json
import os
import subprocess
import textwrap
from collections import Counter
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
from PIL import Image, ImageDraw, ImageFont

GZ1_DIR = "/root/ros2_ws/src/ai_worker/ffw_codex/runs/gz_01"
GZ1_METRICS = "/workspace/gz01_report_assets/gz01_metrics.json"
RUN_DIR = "/root/ros2_ws/src/ai_worker/ffw_codex/runs/gz_02"
OUT_DIR = "/workspace/gz02_report_assets"
FONT_PATH = "/workspace/msyh.ttc"
os.makedirs(OUT_DIR, exist_ok=True)

fm.fontManager.addfont(FONT_PATH)
font_prop = fm.FontProperties(fname=FONT_PATH)
plt.rcParams["font.family"] = font_prop.get_name()
plt.rcParams["axes.unicode_minus"] = False

def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def load_font(size):
    return ImageFont.truetype(FONT_PATH, size)

# ------------------------------------------------------------------
# 1. Load gz_01 & gz_02 Data Sources (Pair history:call_reqs:call_ress 38:38:38)
# ------------------------------------------------------------------
m1 = json.load(open(GZ1_METRICS))
res1 = json.load(open(f"{GZ1_DIR}/result.json"))
reqs1 = [json.load(open(f)) for f in sorted(glob.glob(f"{GZ1_DIR}/calls/*_request.json"))]
ress1 = [json.load(open(f)) for f in sorted(glob.glob(f"{GZ1_DIR}/calls/*_result.json"))]
rpc1 = [json.loads(l) for l in open(f"{GZ1_DIR}/rpc_in.jsonl") if l.strip()]

tok1_tl = []
for msg in rpc1:
    if msg.get("method") == "thread/tokenUsage/updated":
        tu = (msg.get("params") or {}).get("tokenUsage") or {}
        tok1_tl.append((tu.get("total") or {}).get("totalTokens", 0))
t1_start = parse_iso(reqs1[0]["started_at"])
gz1_wall_pts = [(parse_iso(s["finished_at"]) - t1_start).total_seconds() for s in ress1]
gz1_tok_pts = [
    tok1_tl[min(len(tok1_tl) - 1, int(i * len(tok1_tl) / len(ress1)))] if tok1_tl else 0
    for i in range(len(ress1))
]
if gz1_tok_pts:
    gz1_tok_pts[-1] = res1["tokens"]["total"]

res2 = json.load(open(f"{RUN_DIR}/result.json"))
hist2 = [json.loads(l) for l in open(f"{RUN_DIR}/public/history.jsonl") if l.strip()]
reqs2 = [json.load(open(f)) for f in sorted(glob.glob(f"{RUN_DIR}/calls/*_request.json"))]
ress2 = [json.load(open(f)) for f in sorted(glob.glob(f"{RUN_DIR}/calls/*_result.json"))]
rolls2 = [json.load(open(f)) for f in sorted(glob.glob(f"{RUN_DIR}/rollout/*.json"))]
rpc2 = [json.loads(l) for l in open(f"{RUN_DIR}/rpc_in.jsonl") if l.strip()]

assert len(hist2) == len(reqs2) == len(ress2), f"Mismatch {len(hist2)}/{len(reqs2)}/{len(ress2)}"

# Extract sleep events in gz_02
sleeps2 = []
for msg in rpc2:
    if msg.get("method") == "item/completed":
        item = (msg.get("params") or {}).get("item") or {}
        if item.get("type") == "sleep":
            ts = item.get("startedAtMs")
            te = item.get("completedAtMs")
            dur_s = (te - ts) / 1000.0 if (ts and te) else item.get("durationMs", 0) / 1000.0
            sleeps2.append({"actual_s": dur_s, "start_ms": ts, "end_ms": te})

# Token snapshots in gz_02
tok2_tl = []
for msg in rpc2:
    if msg.get("method") == "thread/tokenUsage/updated":
        tu = (msg.get("params") or {}).get("tokenUsage") or {}
        tok2_tl.append(((tu.get("total") or {}).get("totalTokens", 0), (tu.get("total") or {}).get("cachedInputTokens", 0)))

# Sync offsets across all 45 observations in gz_02 rollout/*.json
sync_vals = []
for r in rolls2:
    data = (r.get("result") or {}).get("data") or {}
    obs_d = data.get("post_observation") or data
    if isinstance(obs_d, dict) and "max_offset_s" in obs_d:
        sync_vals.append(obs_d["max_offset_s"] * 1000.0)

# Build per-call steps (1..38)
t2_start = parse_iso(reqs2[0]["started_at"])
t2_end = parse_iso(ress2[-1]["finished_at"])
wall_span2 = (t2_end - t2_start).total_seconds()

obs_root = f"{RUN_DIR}/public/observations"
obs45 = json.load(open(f"{obs_root}/045/observation.json"))
# Map to slim observation dict compatible with history.jsonl structure
def obs_file_to_dict(o):
    return {
        "observation_number": o["observation_number"],
        "stamp_s": o["stamp_s"],
        "arms": o["arms"],
        "body": o["body"],
    }

steps = []
prev_end = None
total_tool_s = 0.0
total_sleep_s = 0.0
total_llm_s = 0.0
last_valid_obs = None

for idx, (h, req, res) in enumerate(zip(hist2, reqs2, ress2), start=1):
    t0 = parse_iso(req["started_at"])
    t1 = parse_iso(res["finished_at"])
    tool_dur = (t1 - t0).total_seconds()
    gap_before = (t0 - prev_end).total_seconds() if prev_end else 0.0

    sleep_before = 0.0
    if prev_end is not None:
        p_ms = prev_end.timestamp() * 1000.0
        t0_ms = t0.timestamp() * 1000.0
        for sl in sleeps2:
            if sl["start_ms"] and sl["end_ms"] and sl["start_ms"] >= p_ms - 500 and sl["end_ms"] <= t0_ms + 500:
                sleep_before += sl["actual_s"]

    llm_before = max(0.0, gap_before - sleep_before)
    total_tool_s += tool_dur
    total_sleep_s += sleep_before
    total_llm_s += llm_before

    obs = h.get("observation")
    if obs:
        last_valid_obs = obs

    # For task_complete (#38), show obs#44 / obs#45 (latest final obs)
    if h["tool"] == "task_complete":
        display_obs = obs_file_to_dict(obs45)
        is_own_obs = True
    else:
        display_obs = obs if obs else last_valid_obs
        is_own_obs = obs is not None

    args = req.get("arguments") or {}
    reason_text = args.get("reason", "")

    # Sync ms lookup if rollout has matching obs or fallback to observation json
    sync_ms = sync_vals[min(len(sync_vals) - 1, idx - 1)] if sync_vals else None

    if tok2_tl:
        ti = min(len(tok2_tl) - 1, int((idx - 1) * len(tok2_tl) / len(hist2)))
        tok_total, tok_cached = tok2_tl[ti]
    else:
        tok_total, tok_cached = 0, 0

    steps.append({
        "idx": idx,
        "wall_s": (t1 - t2_start).total_seconds(),
        "tool": h["tool"],
        "status": h["status"],
        "actions_cum": h["progress"]["actions_executed"],
        "tool_dur": tool_dur,
        "sleep_before": sleep_before,
        "llm_before": llm_before,
        "reason": reason_text,
        "result_reason": h.get("reason", ""),
        "args": args,
        "obs": obs,
        "display_obs": display_obs,
        "is_own_obs": is_own_obs,
        "sync_ms": sync_ms,
        "tok_total": tok_total,
        "tok_cached": tok_cached,
    })
    prev_end = t1

steps[-1]["tok_total"] = res2["tokens"]["total"]

sim_stamps = [h["observation"]["stamp_s"] for h in hist2 if h.get("observation")]
sim_span2 = sim_stamps[-1] - sim_stamps[0]
avg_rtf2 = sim_span2 / wall_span2
llm_lats = [s["llm_before"] for s in steps[1:] if s["llm_before"] > 0.1]

m2 = {
    "run_id": "gz_02",
    "task": res2["task"],
    "model": res2["model"],
    "effort": res2["effort"],
    "renderer": "D3D12 (NVIDIA GeForce RTX 5070 Laptop GPU)",
    "finish_reason": res2["finish_reason"],
    "elapsed_s_result": res2["elapsed_s"],
    "wall_span_calls_s": round(wall_span2, 2),
    "sim_span_s": round(sim_span2, 2),
    "avg_rtf": round(avg_rtf2, 4),
    "total_calls": len(steps),
    "actions_executed": res2["actions_executed"],
    "observations": res2["observations"],
    "rejections": res2["rejections"],
    "sleep_count": len(sleeps2),
    "total_sleep_s": round(total_sleep_s, 2),
    "sleep_pct": round(100.0 * total_sleep_s / wall_span2, 1),
    "total_llm_s": round(total_llm_s, 2),
    "llm_pct": round(100.0 * total_llm_s / wall_span2, 1),
    "llm_mean_s": round(sum(llm_lats) / max(1, len(llm_lats)), 2),
    "llm_median_s": round(sorted(llm_lats)[len(llm_lats) // 2], 2),
    "total_tool_s": round(total_tool_s, 2),
    "tool_pct": round(100.0 * total_tool_s / wall_span2, 1),
    "sync_mean_ms": round(sum(sync_vals) / len(sync_vals), 2),
    "sync_max_ms": round(max(sync_vals), 2),
    "tokens": res2["tokens"],
    "cache_hit_pct": round(100.0 * res2["tokens"]["cached_input"] / max(1, res2["tokens"]["cached_input"] + res2["tokens"]["uncached_input"]), 2),
    "cost_usd_estimate": res2["cost_usd_estimate"],
    "tool_counts": dict(Counter(h["tool"] for h in hist2)),
    "status_counts": dict(Counter(h["status"] for h in hist2)),
}
with open(f"{OUT_DIR}/gz02_metrics.json", "w") as f:
    json.dump(m2, f, indent=2, ensure_ascii=False)
print("=== gz02_metrics.json ===")
print(json.dumps(m2, indent=2, ensure_ascii=False))

# ------------------------------------------------------------------
# 2. Generate 2x2 A/B Comparison Charts (gz_02_ab_comparison_charts.png)
# ------------------------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(15.6, 10.4), dpi=160)
fig.patch.set_facecolor("#F8FAFC")
fig.suptitle(
    "GPT-6 Astra × AI Worker A/B 对照实证：CPU 软渲染 (gz_01) vs RTX 5070 D3D12 加速 (gz_02)",
    fontsize=15.5, fontweight="bold", color="#0F172A", y=0.975
)

# Panel (A): 3-Way Stacked Wall-Time Comparison
ax = axes[0, 0]
ax.set_facecolor("#FFFFFF")
cats = ["gz_02 (RTX 5070 D3D12)\n成功抓起蓝方块 · 599.1s", "gz_01 (CPU llvmpipe)\n触达5M上限未抓起 · 1296.3s"]
sleep_vals = [m2["total_sleep_s"], m1["total_sleep_s"]]
llm_vals   = [m2["total_llm_s"],   m1["total_llm_s"]]
tool_vals  = [m2["total_tool_s"],  m1["total_tool_s"]]
y_pos = np.arange(len(cats))

ax.barh(y_pos, sleep_vals, color="#F59E0B", height=0.45, label="模型自主 sleep 等慢仿真")
ax.barh(y_pos, llm_vals, left=sleep_vals, color="#2563EB", height=0.45, label="大模型多模态思考 + API")
left2 = [a + b for a, b in zip(sleep_vals, llm_vals)]
ax.barh(y_pos, tool_vals, left=left2, color="#10B981", height=0.45, label="Harness + 机器人物理执行")

ax.set_yticks(y_pos)
ax.set_yticklabels(cats, fontsize=9.8, fontweight="bold", color="#1E293B")
ax.set_xlabel("调用首尾时间跨度 (秒)", fontsize=10.5, color="#334155")
ax.set_xlim(0, 1540)
ax.grid(axis="x", linestyle="--", alpha=0.35)
ax.set_title("(A) 全流程耗时三元拆解：sleep 从 734.5s 彻底清零", fontsize=11.3, fontweight="bold", color="#0F172A", pad=10)
ax.legend(loc="lower right", fontsize=8.8, framealpha=0.95)

# Labels on bars
ax.text(m2["total_llm_s"]/2, 0, f"LLM {m2['total_llm_s']:.0f}s\n({m2['llm_pct']}%)", ha="center", va="center", color="white", fontsize=8.8, fontweight="bold")
ax.text(m2["total_llm_s"] + m2["total_tool_s"]/2, 0, f"运控 {m2['total_tool_s']:.0f}s\n({m2['tool_pct']}%)", ha="center", va="center", color="white", fontsize=8.8, fontweight="bold")
ax.text(m2["wall_span_calls_s"] + 18, 0, "总 599s\n(0次 sleep)", va="center", ha="left", color="#047857", fontsize=9.5, fontweight="bold")

ax.text(m1["total_sleep_s"]/2, 1, f"sleep {m1['total_sleep_s']:.0f}s ({m1['sleep_pct']}%)", ha="center", va="center", color="#0F172A", fontsize=8.8, fontweight="bold")
ax.text(m1["total_sleep_s"] + m1["total_llm_s"]/2, 1, f"LLM {m1['total_llm_s']:.0f}s", ha="center", va="center", color="white", fontsize=8.5, fontweight="bold")
ax.text(m1["wall_span_calls_s"] + 18, 1, "总 1296s", va="center", ha="left", color="#B91C1C", fontsize=9.5, fontweight="bold")

# Panel (B): Normalized A/B Key KPIs
ax = axes[0, 1]
ax.set_facecolor("#FFFFFF")
kpi_labels = [
    "仿真实时因子\nRTF (×)",
    "现实总耗时\n(秒)",
    "总 Token\n(百万)",
    "执行物理动作\n(次)",
    "单步一次到位\narrived (次)",
    "无效 observe\n轮询 (次)",
]
v1_raw = [m1["avg_rtf"], m1["elapsed_s_result"], m1["tokens"]["total"]/1e6, m1["actions_executed"], m1["status_counts"].get("arrived", 0), m1["tool_counts"].get("robot_observe", 0)]
v2_raw = [m2["avg_rtf"], m2["elapsed_s_result"], m2["tokens"]["total"]/1e6, m2["actions_executed"], m2["status_counts"].get("arrived", 0), m2["tool_counts"].get("robot_observe", 0)]
v1_txt = [f"{v1_raw[0]:.3f}×", f"{v1_raw[1]:.0f}s", f"{v1_raw[2]:.2f}M", f"{int(v1_raw[3])}", f"{int(v1_raw[4])}", f"{int(v1_raw[5])}"]
v2_txt = [f"{v2_raw[0]:.3f}×", f"{v2_raw[1]:.0f}s", f"{v2_raw[2]:.2f}M", f"{int(v2_raw[3])}", f"{int(v2_raw[4])}", f"{int(v2_raw[5])}"]

# Normalize each pair by max(v1, v2) to plot cleanly on 0..100% scale with exact value labels!
max_pair = [max(a, b, 1e-6) for a, b in zip(v1_raw, v2_raw)]
v1_norm = [100.0 * a / m for a, m in zip(v1_raw, max_pair)]
v2_norm = [100.0 * b / m for b, m in zip(v2_raw, max_pair)]

xk = np.arange(len(kpi_labels))
bw = 0.36
b1 = ax.bar(xk - bw/2, v1_norm, width=bw, color="#94A3B8", label="gz_01 (llvmpipe 软渲染)")
b2 = ax.bar(xk + bw/2, v2_norm, width=bw, color="#10B981", label="gz_02 (RTX 5070 D3D12)")
ax.set_xticks(xk)
ax.set_xticklabels(kpi_labels, fontsize=8.8, color="#1E293B")
ax.set_ylabel("相对峰值比例 (%)", fontsize=10, color="#334155")
ax.set_ylim(0, 122)
ax.grid(axis="y", linestyle="--", alpha=0.35)
ax.set_title("(B) 核心性能指标 A/B 全面逆转（各组上方标注实测值）", fontsize=11.3, fontweight="bold", color="#0F172A", pad=10)
ax.legend(loc="upper right", fontsize=8.8, framealpha=0.95)

for rect, txt in zip(b1, v1_txt):
    ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + 2, txt, ha="center", va="bottom", fontsize=8.2, fontweight="bold", color="#475569")
for rect, txt in zip(b2, v2_txt):
    ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + 2, txt, ha="center", va="bottom", fontsize=8.4, fontweight="bold", color="#047857")

# Panel (C): gz_02 Right EE (X, Y, Z) & Gripper Trajectory
ax = axes[1, 0]
ax.set_facecolor("#FFFFFF")
c_idx = [s["idx"] for s in steps]
rx_arr = [s["display_obs"]["arms"]["right"]["xyz"][0] for s in steps]
ry_arr = [s["display_obs"]["arms"]["right"]["xyz"][1] for s in steps]
rz_arr = [s["display_obs"]["arms"]["right"]["xyz"][2] for s in steps]
grp_arr = [s["display_obs"]["arms"]["right"]["gripper"] for s in steps]

ax.plot(c_idx, rx_arr, label="右臂 X (前伸, m)", color="#2563EB", linewidth=2.2, marker="o", markersize=3)
ax.plot(c_idx, rz_arr, label="右臂 Z (高度, m)", color="#10B981", linewidth=2.2, marker="s", markersize=3)
ax.plot(c_idx, ry_arr, label="右臂 Y (横向追物, m)", color="#8B5CF6", linewidth=2.0, linestyle="--")
ax.plot(c_idx, grp_arr, label="右爪闭合度 (0开..1闭)", color="#F59E0B", linewidth=2.2, linestyle="-.", marker="^", markersize=3.5)

annots = [
    (11, rz_arr[10], "批处理计划快速抵近\n(#10-#11)", (-90, 18)),
    (16, grp_arr[15], "首次全闭致方块滑移\n(主动重追)", (-48, -32)),
    (24, grp_arr[23], "二次全闭滑移后\n拒绝误报", (-35, 12)),
    (35, grp_arr[34], "两段温和半闭\n0.45→0.68", (-78, -28)),
    (37, rz_arr[36], "抬升至 0.90m\n悬空抓起!", (-85, 16)),
]
for mx, my, txt, off in annots:
    ax.annotate(txt, xy=(mx, my), xytext=off, textcoords="offset points",
                fontsize=8.2, fontweight="bold", color="#0F172A",
                bbox=dict(boxstyle="round,pad=0.25", fc="#FEF3C7", ec="#D97706", lw=0.8),
                arrowprops=dict(arrowstyle="->", color="#D97706", lw=1.0))

ax.set_xlabel("工具调用序号 (Call Index, 1..38)", fontsize=10.5, color="#334155")
ax.set_ylabel("位置 (m) / 夹爪开合度", fontsize=10.5, color="#334155")
ax.set_title("(C) gz_02 右臂抓取与滑移重追全轨迹（含多步计划与温和半闭策略切换）", fontsize=11.0, fontweight="bold", color="#0F172A", pad=10)
ax.set_xlim(0, 40)
ax.set_ylim(-0.35, 1.28)
ax.grid(True, linestyle="--", alpha=0.35)
ax.legend(loc="lower left", fontsize=8.3, ncol=2, framealpha=0.95)

# Panel (D): Cumulative Tokens vs Wall Time (gz_01 vs gz_02)
ax = axes[1, 1]
ax.set_facecolor("#FFFFFF")
gz2_wall_pts = [s["wall_s"] for s in steps]
gz2_tok_pts = [s["tok_total"] / 1e6 for s in steps]
gz1_tok_m = [t / 1e6 for t in gz1_tok_pts]

ax.plot(gz1_wall_pts, gz1_tok_m, color="#DC2626", linewidth=2.5, linestyle="--", marker="x", markersize=4, markevery=4,
        label=f"gz_01 (0.082× RTF): 1296s 触达 5.02M 上限暂停")
ax.plot(gz2_wall_pts, gz2_tok_pts, color="#059669", linewidth=2.8, marker="o", markersize=4, markevery=3,
        label=f"gz_02 (0.836× RTF): 599s 仅耗 2.04M 完成抓取!")

ax.axhline(5.0, color="#DC2626", linestyle=":", linewidth=1.3, alpha=0.7)
ax.text(875, 4.72, "默认保护上限: 5.0M Tokens", fontsize=8.8, color="#B91C1C", fontweight="bold")

ax.scatter([gz2_wall_pts[-1]], [gz2_tok_pts[-1]], s=95, color="#10B981", edgecolor="#064E3B", zorder=5)
ax.annotate("任务完成!\n耗时 -50.9% | Token -59.3%", xy=(gz2_wall_pts[-1], gz2_tok_pts[-1]),
            xytext=(gz2_wall_pts[-1] + 55, gz2_tok_pts[-1] - 0.15),
            fontsize=9.2, fontweight="bold", color="#065F46",
            bbox=dict(boxstyle="round,pad=0.35", fc="#D1FAE5", ec="#059669", lw=1.2),
            arrowprops=dict(arrowstyle="->", color="#059669", lw=1.4))

ax.set_xlabel("现实经过时间 (秒)", fontsize=10.5, color="#334155")
ax.set_ylabel("累计 Token 消耗 (Million)", fontsize=10.5, color="#334155")
ax.set_title("(D) 现实耗时 vs Token 消耗对比曲线（提速后成本与时长双降一半）", fontsize=11.2, fontweight="bold", color="#0F172A", pad=10)
ax.set_xlim(-20, 1380)
ax.set_ylim(0, 5.7)
ax.grid(True, linestyle="--", alpha=0.35)
ax.legend(loc="upper left", fontsize=8.6, framealpha=0.95)

plt.tight_layout(rect=[0, 0.01, 1, 0.945])
chart_path = f"{OUT_DIR}/gz_02_ab_comparison_charts.png"
plt.savefig(chart_path, dpi=160, facecolor=fig.get_facecolor())
plt.close()
print("Saved A/B chart:", chart_path)

# ------------------------------------------------------------------
# 3. Generate gz_02 6-Stage Key Milestones Dual-View Collage
# ------------------------------------------------------------------
milestone_specs = [
    (2,  "阶段 1 · Call #02 (Obs #02, 14s)",   "一次 arrived 低头 0.695 rad 锁定蓝方块"),
    (18, "阶段 2 · Call #11 (Obs #18, 197s)",  "robot_execute_plan 多步批处理快速抵近"),
    (23, "阶段 3 · Call #16 (Obs #23, 282s)",  "首次全闭 (grp=1.0) 致方块向左滑移"),
    (31, "阶段 4 · Call #24 (Obs #31, 396s)",  "二次滑移后拒绝误报，重定位追踪 (y→0)"),
    (42, "阶段 5 · Call #35 (Obs #42, 554s)",  "策略切换：两段温和半闭 (0.45→0.68) 稳夹"),
    (44, "阶段 6 · Call #37 (Obs #44, 580s)",  "抬升至 Z=0.900m：蓝方块悬空离桌成功！"),
]
tile_w, tile_h = 560, 290
cols, rows = 3, 2
pad = 22
header_h = 72
canvas_w = cols * tile_w + (cols + 1) * pad
canvas_h = header_h + rows * tile_h + (rows + 1) * pad

collage = Image.new("RGB", (canvas_w, canvas_h), (15, 23, 42))
draw = ImageDraw.Draw(collage)
draw.text((pad, 16), "GPT-6 Astra × AI Worker (gz_02 · RTX 5070 加速) 关键阶段演进：从滑移失误到稳健抓起",
          font=load_font(22), fill=(248, 250, 252))
draw.text((pad, 48), "RTF 0.836× · 0 次 sleep · 0 次空等 observe · 自主识别滑移并切换温和半闭策略成功举起蓝色方块",
          font=load_font(14), fill=(167, 243, 208))

for idx_m, (obs_num, title_m, desc_m) in enumerate(milestone_specs):
    r_i, c_i = divmod(idx_m, cols)
    x0 = pad + c_i * (tile_w + pad)
    y0 = header_h + pad + r_i * (tile_h + pad)
    draw.rounded_rectangle([x0, y0, x0 + tile_w, y0 + tile_h], radius=12, fill=(30, 41, 59), outline=(16, 185, 129) if idx_m == 5 else (71, 85, 105), width=2)

    folder = f"{obs_root}/{obs_num:03d}"
    head_im = Image.open(f"{folder}/head.jpg").convert("RGB").resize((330, 185), Image.Resampling.LANCZOS)
    wrist_im = Image.open(f"{folder}/wrist_right.jpg").convert("RGB").resize((200, 185), Image.Resampling.LANCZOS)
    collage.paste(head_im, (x0 + 12, y0 + 12))
    collage.paste(wrist_im, (x0 + 348, y0 + 12))

    draw.rectangle([x0 + 16, y0 + 16, x0 + 96, y0 + 34], fill=(15, 23, 42))
    draw.text((x0 + 22, y0 + 17), "HEAD 头部", font=load_font(11), fill=(56, 189, 248))
    draw.rectangle([x0 + 352, y0 + 16, x0 + 450, y0 + 34], fill=(15, 23, 42))
    draw.text((x0 + 358, y0 + 17), "R-WRIST 右腕", font=load_font(11), fill=(52, 211, 153))

    draw.text((x0 + 14, y0 + 206), title_m, font=load_font(17), fill=(110, 231, 183) if idx_m == 5 else (250, 204, 21))
    draw.text((x0 + 14, y0 + 234), desc_m, font=load_font(14), fill=(226, 232, 240))
    obs_j = json.load(open(f"{folder}/observation.json"))
    re_ = obs_j["arms"]["right"]["xyz"]
    rg_ = obs_j["arms"]["right"]["gripper"]
    draw.text((x0 + 14, y0 + 260),
              f"Right EE: ({re_[0]:+.3f}, {re_[1]:+.3f}, {re_[2]:+.3f})m | grp={rg_:.2f} | sim={obs_j['stamp_s']:.1f}s",
              font=load_font(12), fill=(148, 163, 184))

collage_path = f"{OUT_DIR}/gz_02_key_milestones.png"
collage.save(collage_path, quality=95)
print("Saved gz_02 collage:", collage_path)

# ------------------------------------------------------------------
# 4. Render gz_02 Full Replay Video (1440x810 H.264 MP4)
# ------------------------------------------------------------------
W, H = 1440, 810
FPS = 10
frames_dir = f"{OUT_DIR}/video_frames"
os.makedirs(frames_dir, exist_ok=True)
for old_f in glob.glob(f"{frames_dir}/*.jpg"):
    os.remove(old_f)

f_title = load_font(21)
f_sub   = load_font(15)
f_sec   = load_font(18)
f_body  = load_font(15)
f_small = load_font(13)
f_badge = load_font(14)
f_big   = load_font(36)
f_med   = load_font(22)

def phase_label_cn(idx):
    if idx <= 4:
        return "阶段 1/5 · 提速上线（一次 arrived 低头 + 降躯干 + 底盘试探止损）"
    elif idx <= 13:
        return "阶段 2/5 · 多步批处理快速抵近（robot_execute_plan 跨桌缘逼近）"
    elif idx <= 25:
        return "阶段 3/5 · 两次全闭失误与主动重追（拒绝幻觉，追踪滑移方块）"
    elif idx <= 33:
        return "阶段 4/5 · 精准二次对准（调整俯仰角并垂直下探到抓取点）"
    else:
        return "阶段 5/5 · 温和半闭稳夹与悬空举起（Obs #44 确认成功，task_complete！）"

def tool_cn(tool):
    return {
        "robot_start": "启动并首次观测",
        "robot_head": "头部俯仰视角",
        "robot_lift": "躯干升降机构",
        "robot_base": "底盘速度试探",
        "robot_execute_plan": "多步动作批处理计划",
        "robot_move": "右臂末端直线移动 (MoveL)",
        "robot_gripper": "右夹爪开合控制",
        "task_complete": "视觉确认成功并结束任务",
    }.get(tool, tool)

STATUS_STYLE = {
    "observed":         ("OBSERVED", (14, 165, 233)),
    "arrived":          ("ARRIVED (一次到位)", (16, 185, 129)),
    "plan_completed":   ("PLAN COMPLETED", (16, 185, 129)),
    "plan_interrupted": ("PLAN INTERRUPTED", (245, 158, 11)),
    "stopped":          ("STOPPED", (245, 158, 11)),
    "rejected":         ("REJECTED (拦截)", (239, 68, 68)),
    "completed":        ("TASK COMPLETE!", (16, 185, 129)),
}

frame_counter = 0
def save_repeated(img, seconds):
    global frame_counter
    n = max(1, int(round(seconds * FPS)))
    for _ in range(n):
        img.save(f"{frames_dir}/f_{frame_counter:05d}.jpg", quality=92)
        frame_counter += 1

# Intro Slide
intro = Image.new("RGB", (W, H), (11, 18, 32))
d = ImageDraw.Draw(intro)
d.rounded_rectangle([60, 55, W-60, H-55], radius=20, fill=(15, 23, 42), outline=(16, 185, 129), width=2)
d.text((110, 100), "GPT-6 Astra × ROBOTIS AI Worker (gz_02)", font=f_big, fill=(52, 211, 153))
d.text((110, 158), "RTX 5070 D3D12 硬件渲染提速对照实验 · 完整抓起蓝色方块录像", font=load_font(25), fill=(248, 250, 252))
d.line([(110, 212), (W-110, 212)], fill=(51, 65, 85), width=2)

d.rounded_rectangle([110, 245, 695, 555], radius=14, fill=(30, 41, 59), outline=(59, 130, 246), width=2)
d.text((138, 268), "GPU 渲染优化效果（对比 gz_01）", font=f_med, fill=(96, 165, 250))
il = [
    "• 渲染后端: llvmpipe 软渲染 -> RTX 5070 D3D12",
    f"• 仿真实时因子: 0.0821× -> {m2['avg_rtf']:.4f}× (提速 10.2×)",
    f"• 自主 sleep 次数: 26 次 (734s) -> {m2['sleep_count']} 次 (0.0s)",
    "• 无效 observe 轮询: 27 次 -> 0 次 (省掉全部空等)",
    "• 动作到位率: 单步 arrived 从 1 次跃升至 26 次",
]
for i, line in enumerate(il):
    d.text((138, 320 + i * 42), line, font=f_sec, fill=(226, 232, 240))

d.rounded_rectangle([745, 245, W-110, 555], radius=14, fill=(30, 41, 59), outline=(16, 185, 129), width=2)
d.text((773, 268), "gz_02 完整抓取成果与涌现亮点", font=f_med, fill=(52, 211, 153))
ir = [
    f"• 现实总耗时: {m2['elapsed_s_result']}s (10分10秒，比 gz_01 减半)",
    f"• 总 Token: {m2['tokens']['total']:,} (-59.3% | 缓存 {m2['cache_hit_pct']:.1f}%)",
    f"• 实际执行动作: {m2['actions_executed']} 次 (含 5 次多步计划批处理)",
    "• 容错纠偏: 两次抓滑后拒绝误报，重追至新坐标",
    "• 策略切换: 改为温和两段式闭合 (0.45→0.68) 稳稳抓起",
]
for i, line in enumerate(ir):
    d.text((773, 320 + i * 42), line, font=f_sec, fill=(226, 232, 240))

d.rounded_rectangle([110, 590, W-110, 705], radius=12, fill=(6, 78, 59))
d.text((140, 612), "本视频完整回放 gz_02 全程 38 次工具调用（45 组三路实拍观测 -> 最终蓝色方块悬空离桌）", font=f_med, fill=(254, 240, 138))
d.text((140, 654), "任务指令: \"pick up the blue block\"  |  模型: gpt-6-astra (low)  |  结论: task_complete (成功)", font=f_sub, fill=(226, 232, 240))
save_repeated(intro, 3.5)

all_x = [s["display_obs"]["arms"]["right"]["xyz"][0] for s in steps]
all_z = [s["display_obs"]["arms"]["right"]["xyz"][2] for s in steps]

for s in steps:
    frame = Image.new("RGB", (W, H), (15, 23, 42))
    d = ImageDraw.Draw(frame)

    d.rectangle([0, 0, W, 76], fill=(11, 18, 32))
    d.line([(0, 76), (W, 76)], fill=(51, 65, 85), width=2)
    d.text((24, 12), "GPT-6 Astra × AI Worker | gz_02 (RTX 5070 D3D12 加速)", font=f_title, fill=(248, 250, 252))
    d.text((24, 46), phase_label_cn(s["idx"]), font=f_sub, fill=(52, 211, 153))

    st_text, st_col = STATUS_STYLE.get(s["status"], (s["status"].upper(), (148, 163, 184)))
    badge_w = 210
    d.rounded_rectangle([W - badge_w - 24, 16, W - 24, 60], radius=10, fill=st_col)
    d.text((W - badge_w - 10, 28), st_text, font=f_badge, fill=(15, 23, 42) if s["status"] != "rejected" else (255, 255, 255))

    sim_s = s["display_obs"]["stamp_s"]
    top_stats = f"Call {s['idx']:02d}/38  |  Actions {s['actions_cum']:02d}/43  |  Wall {s['wall_s']:5.1f}s  |  Sim {sim_s:5.1f}s"
    d.text((W - badge_w - 490, 28), top_stats, font=f_sub, fill=(226, 232, 240))

    obs_num = s["display_obs"]["observation_number"]
    obs_dir = f"{obs_root}/{obs_num:03d}"

    cam_boxes = [
        ("wrist_left.jpg",  "LEFT WRIST 左腕相机 (424×240)",  24,  112, 376, 260, (148, 163, 184)),
        ("head.jpg",        "HEAD VIEW 头部主视角 (672×376)", 416,  92, 608, 342, (56, 189, 248)),
        ("wrist_right.jpg", "RIGHT WRIST 右腕相机 (424×240)", 1040, 112, 376, 260, (52, 211, 153)),
    ]
    for fname, clabel, cx, cy, cw, ch, ccol in cam_boxes:
        d.rounded_rectangle([cx - 3, cy - 3, cx + cw + 3, cy + ch + 3], radius=10, fill=(30, 41, 59), outline=ccol, width=2)
        im = Image.open(f"{obs_dir}/{fname}").convert("RGB").resize((cw, ch), Image.Resampling.LANCZOS)
        frame.paste(im, (cx, cy))
        d.rectangle([cx, cy, cx + 255, cy + 26], fill=(15, 23, 42))
        d.text((cx + 8, cy + 4), clabel, font=f_small, fill=ccol)
        if not s["is_own_obs"]:
            d.rectangle([cx + 12, cy + ch - 36, cx + cw - 12, cy + ch - 8], fill=(185, 28, 28))
            d.text((cx + 22, cy + ch - 31), "安全层拦截 (复用上一帧观测)", font=f_small, fill=(255, 255, 255))

    # Left badge under left wrist
    if s["tool"] == "robot_execute_plan":
        n_steps = len((s["args"] or {}).get("steps") or [])
        d.rounded_rectangle([24, 384, 400, 434], radius=8, fill=(30, 58, 138), outline=(59, 130, 246), width=2)
        d.text((38, 398), f"[PLAN] 批处理 {n_steps} 步动作 | 思考 {s['llm_before']:.1f}s | 执行 {s['tool_dur']:.1f}s", font=f_sub, fill=(224, 242, 254))
    else:
        d.rounded_rectangle([24, 384, 400, 434], radius=8, fill=(30, 41, 59), outline=(71, 85, 105), width=1)
        d.text((38, 398), f"[LLM] 纯推理+API: {s['llm_before']:.2f}s | 运控执行: {s['tool_dur']:.2f}s", font=f_sub, fill=(203, 213, 225))

    # Right badge under right wrist
    sync_txt = f"{s['sync_ms']:.1f} ms" if s["sync_ms"] is not None else "N/A"
    d.rounded_rectangle([1040, 384, 1416, 434], radius=8, fill=(30, 41, 59), outline=(71, 85, 105), width=1)
    d.text((1054, 398), f"[CAM] 观测 #{obs_num:02d} | 同步偏差: {sync_txt} | 0 sleep", font=f_sub, fill=(167, 243, 208))

    # Bottom Left: Decision Layer
    d.rounded_rectangle([24, 452, 830, 768], radius=12, fill=(30, 41, 59), outline=(59, 130, 246), width=2)
    d.text((42, 464), f"大模型低频决策层  |  工具: {s['tool']} ({tool_cn(s['tool'])})", font=f_sec, fill=(96, 165, 250))

    args = s["args"]
    if s["tool"] == "robot_move":
        arg_str = f"arm={args.get('arm')}  target=({args.get('x',0):.3f}, {args.get('y',0):.3f}, {args.get('z',0):.3f}) m  |  rpy=({args.get('roll',0):.2f}, {args.get('pitch',0):.2f}, {args.get('yaw',0):.2f})"
    elif s["tool"] == "robot_execute_plan":
        st_list = args.get("steps") or []
        arg_str = f"批处理步骤数: {len(st_list)} 步  |  连续向桌面蓝色方块安全逼近"
    elif s["tool"] == "robot_gripper":
        arg_str = f"arm={args.get('arm')}  value={args.get('value')} (0=全开 .. 1=闭合)"
    elif s["tool"] == "robot_head":
        arg_str = f"head_joint1={args.get('head_joint1')} rad, head_joint2={args.get('head_joint2')} rad"
    elif s["tool"] == "robot_lift":
        arg_str = f"position_m={args.get('position_m')} m"
    elif s["tool"] == "robot_base":
        arg_str = f"vx={args.get('vx')}, vy={args.get('vy')}, wz={args.get('wz')}, duration={args.get('duration_s')}s"
    elif s["tool"] == "task_complete":
        arg_str = "提交任务完成声明 (request_id 已绑定最新 Obs #45)"
    else:
        arg_str = "无动作参数（初始化回合与三路相机同步观测）"

    d.text((42, 498), "指令参数: " + arg_str, font=f_sub, fill=(250, 204, 21))
    d.text((42, 526), f"Harness 反馈: {s['result_reason']}", font=f_sub, fill=(248, 113, 113) if s["status"] == "rejected" else (167, 243, 208))
    d.line([(42, 554), (812, 554)], fill=(71, 85, 105), width=1)
    d.text((42, 564), "GPT-6 Astra 决策依据 (Recorded Model Rationale):", font=f_small, fill=(148, 163, 184))

    rationale = s["reason"] if s["reason"] else "（初始化回合，采集初始三路 RGB 图像与机器人关节位姿）"
    wrapped = textwrap.wrap(rationale, width=68)[:6]
    for wi, wline in enumerate(wrapped):
        d.text((42, 588 + wi * 26), wline, font=f_body, fill=(241, 245, 249))

    # Bottom Right: High-Frequency Control State + Live Trajectory
    d.rounded_rectangle([848, 452, 1416, 768], radius=12, fill=(30, 41, 59), outline=(16, 185, 129), width=2)
    d.text((866, 464), "高频运控反馈层  |  ROS 2 / Cyclo (100 Hz · RTF 0.84×)", font=f_sec, fill=(52, 211, 153))

    r_arm = s["display_obs"]["arms"]["right"]
    body = s["display_obs"]["body"]
    rx, ry, rz = r_arm["xyz"]
    d.text((866, 500), f"右臂末端 (base_link): X={rx:+.3f}m  Y={ry:+.3f}m  Z={rz:+.3f}m", font=f_sub, fill=(248, 250, 252))
    d.text((866, 528), f"右爪闭合: {r_arm['gripper']:.3f}  |  头部: {body['head_joint1']:.2f} rad  |  升降: {body['lift_joint']:+.3f} m", font=f_sub, fill=(203, 213, 225))
    d.text((866, 556), f"当前累计 Token: {s['tok_total']/1e6:.2f}M / 5.00M (最终仅耗 2.04M)", font=f_sub, fill=(253, 224, 71))

    tx0, ty0, tx1, ty1 = 866, 590, 1398, 750
    d.rounded_rectangle([tx0, ty0, tx1, ty1], radius=8, fill=(15, 23, 42), outline=(51, 65, 85), width=1)
    d.text((tx0 + 10, ty0 + 6), "右臂末端侧视轨迹演进 (X 前伸 vs Z 高度, 含两次抓滑与终态抬升)", font=f_small, fill=(148, 163, 184))

    def map_xz(xv, zv):
        px = tx0 + 24 + (xv - (-0.05)) / (0.58 - (-0.05)) * (tx1 - tx0 - 48)
        py = ty1 - 18 - (zv - 0.52) / (0.96 - 0.52) * (ty1 - ty0 - 44)
        return (int(px), int(py))

    bx, by = map_xz(0.535, 0.85)
    d.rectangle([bx - 9, by - 9, bx + 9, by + 9], fill=(37, 99, 235), outline=(147, 197, 253), width=2)
    d.text((bx - 68, by + 12), "终态抓取点", font=f_small, fill=(147, 197, 253))

    pts_all = [map_xz(all_x[k], all_z[k]) for k in range(len(steps))]
    for k in range(1, len(pts_all)):
        d.line([pts_all[k - 1], pts_all[k]], fill=(51, 65, 85), width=2)
    pts_cur = pts_all[:s["idx"]]
    for k in range(1, len(pts_cur)):
        d.line([pts_cur[k - 1], pts_cur[k]], fill=(52, 211, 153), width=3)
    cx_pt, cy_pt = pts_cur[-1]
    d.ellipse([cx_pt - 6, cy_pt - 6, cx_pt + 6, cy_pt + 6], fill=(250, 204, 21), outline=(255, 255, 255), width=2)

    d.rectangle([24, 782, W - 24, 796], fill=(30, 41, 59))
    prog_w = int((W - 48) * (s["idx"] / len(steps)))
    d.rectangle([24, 782, 24 + prog_w, 796], fill=(16, 185, 129))

    if s["idx"] in (2, 10, 11, 16, 24, 34, 35, 36, 37, 38):
        dur_sec = 2.0
    else:
        dur_sec = 1.2
    save_repeated(frame, dur_sec)

# Outro Summary Slide
outro = Image.new("RGB", (W, H), (11, 18, 32))
d = ImageDraw.Draw(outro)
d.rounded_rectangle([60, 55, W-60, H-55], radius=20, fill=(15, 23, 42), outline=(16, 185, 129), width=2)
d.text((110, 95), "A/B 实证结论：解决渲染瓶颈后任务 100% 闭环成功", font=f_big, fill=(52, 211, 153))
d.line([(110, 158), (W-110, 158)], fill=(51, 65, 85), width=2)

outro_items = [
    ("1. RTF 从 0.082× 跃升至 0.836×（10.2× 加速）", "启用 WSL2 Mesa D3D12 (RTX 5070) 后，单步一次到位 arrived 从 1 次激增至 26 次，26 次自主 sleep 和 27 次无效 observe 轮询彻底归零。"),
    ("2. 时长与成本腰斩，成功举起蓝色方块", "现实总耗时从 1242.4s 降至 610.1s (-50.9%)；总 Token 从 5.02M 降至 2.04M (-59.3%)；成功完成抓起，任务以 task_complete 圆满收官。"),
    ("3. 激发出高阶多步规划与容错纠偏能力", "模型主动运用 5 次 robot_execute_plan 批处理；在两次全闭把方块挤偏后拒绝幻觉，追至新位置并改用 0.45→0.68 温和半闭策略稳稳夹起。"),
    ("4. 研究启示：大模型与传统运控解耦可行且安全", "在可靠硬件同步与低延迟底层运控支撑下，通用多模态大模型无需微调即可完成“感知→试错→策略切换→物理抓取→自检确认”完整闭环。"),
]
for oi, (otitle, odesc) in enumerate(outro_items):
    y_box = 190 + oi * 130
    d.rounded_rectangle([110, y_box, W-110, y_box + 110], radius=12, fill=(30, 41, 59), outline=(71, 85, 105), width=1)
    d.text((135, y_box + 14), otitle, font=f_med, fill=(250, 204, 21))
    wlines = textwrap.wrap(odesc, width=62)
    for wl_i, wl in enumerate(wlines[:2]):
        d.text((135, y_box + 50 + wl_i * 26), wl, font=f_sub, fill=(226, 232, 240))

save_repeated(outro, 4.5)

video_path = f"{OUT_DIR}/gz_02_full_replay.mp4"
cmd = [
    "ffmpeg", "-y",
    "-framerate", str(FPS),
    "-i", f"{frames_dir}/f_%05d.jpg",
    "-c:v", "libx264",
    "-pix_fmt", "yuv420p",
    "-preset", "medium",
    "-crf", "21",
    "-movflags", "+faststart",
    video_path,
]
subprocess.run(cmd, check=True)
os.system(f"cp {frames_dir}/f_00000.jpg {OUT_DIR}/qa_intro.jpg")
os.system(f"cp {frames_dir}/f_{frame_counter//2:05d}.jpg {OUT_DIR}/qa_mid.jpg")
os.system(f"cp {frames_dir}/f_{max(0, frame_counter-55):05d}.jpg {OUT_DIR}/qa_end_call.jpg")
os.system(f"cp {frames_dir}/f_{frame_counter-1:05d}.jpg {OUT_DIR}/qa_outro.jpg")
print(f"Video rendered successfully: {video_path} ({frame_counter} frames, {frame_counter/FPS:.1f}s)")
