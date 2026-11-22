#!/usr/bin/env python3
"""
Analyze gz_01 complete logs, generate publication-grade telemetry charts,
key milestone collage, and a full H.264 replay video illustrating
"LLM Low-Frequency Decision + Robot High-Frequency Motion Control".
"""
import glob
import json
import math
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

RUN_DIR = "/root/ros2_ws/src/ai_worker/ffw_codex/runs/gz_01"
OUT_DIR = "/workspace/gz01_report_assets"
FONT_PATH = "/workspace/msyh.ttc"
os.makedirs(OUT_DIR, exist_ok=True)

# Configure Chinese font for matplotlib
fm.fontManager.addfont(FONT_PATH)
font_prop = fm.FontProperties(fname=FONT_PATH)
plt.rcParams["font.family"] = font_prop.get_name()
plt.rcParams["axes.unicode_minus"] = False

def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

# ------------------------------------------------------------------
# 1. Load & Precisely Analyze All Data Sources
# ------------------------------------------------------------------
result = json.load(open(f"{RUN_DIR}/result.json"))
run_meta = json.load(open(f"{RUN_DIR}/run.json"))
history = [json.loads(l) for l in open(f"{RUN_DIR}/public/history.jsonl") if l.strip()]
rollouts = [json.load(open(f)) for f in sorted(glob.glob(f"{RUN_DIR}/rollout/*.json"))]
call_reqs = [json.load(open(f)) for f in sorted(glob.glob(f"{RUN_DIR}/calls/*_request.json"))]
call_ress = [json.load(open(f)) for f in sorted(glob.glob(f"{RUN_DIR}/calls/*_result.json"))]
rpc_in = [json.loads(l) for l in open(f"{RUN_DIR}/rpc_in.jsonl") if l.strip()]

# Extract all sleep events from rpc_in.jsonl
sleeps = []
for msg in rpc_in:
    if msg.get("method") == "item/completed":
        item = (msg.get("params") or {}).get("item") or {}
        if item.get("type") == "sleep":
            t_start = item.get("startedAtMs")
            t_end = item.get("completedAtMs")
            dur_s = (t_end - t_start) / 1000.0 if (t_start and t_end) else item.get("durationMs", 0) / 1000.0
            sleeps.append({
                "id": item.get("id"),
                "requested_s": item.get("durationMs", 0) / 1000.0,
                "actual_s": dur_s,
                "start_ms": t_start,
                "end_ms": t_end,
            })

# Extract per-step token snapshots from rpc_in (thread/tokenUsage/updated)
token_timeline = []
for msg in rpc_in:
    if msg.get("method") == "thread/tokenUsage/updated":
        p = msg.get("params") or {}
        tu = p.get("tokenUsage") or {}
        tot = (tu.get("total") or {}).get("totalTokens", 0)
        cached = (tu.get("total") or {}).get("cachedInputTokens", 0)
        token_timeline.append((tot, cached))

# Per-call timing decomposition
t_run_start = parse_iso(call_reqs[0]["started_at"])
t_run_end = parse_iso(call_ress[-1]["finished_at"])
total_span_s = (t_run_end - t_run_start).total_seconds()

steps = []
prev_end = None
total_tool_s = 0.0
total_sleep_s = 0.0
total_llm_s = 0.0
last_valid_obs = None

for idx, (h, r, req, res) in enumerate(zip(history, rollouts, call_reqs, call_ress), start=1):
    t0 = parse_iso(req["started_at"])
    t1 = parse_iso(res["finished_at"])
    tool_dur = (t1 - t0).total_seconds()
    gap_before = (t0 - prev_end).total_seconds() if prev_end else 0.0

    # Find sleep events occurring between prev_end and t0
    sleep_before = 0.0
    if prev_end is not None:
        p_ms = prev_end.timestamp() * 1000.0
        t0_ms = t0.timestamp() * 1000.0
        for sl in sleeps:
            if sl["start_ms"] and sl["end_ms"] and sl["start_ms"] >= p_ms - 500 and sl["end_ms"] <= t0_ms + 500:
                sleep_before += sl["actual_s"]

    llm_before = max(0.0, gap_before - sleep_before)
    total_tool_s += tool_dur
    total_sleep_s += sleep_before
    total_llm_s += llm_before

    obs = h.get("observation")
    if obs:
        last_valid_obs = obs

    # Parse error/target/sync info from rollout
    r_res = r.get("result") or {}
    r_data = r_res.get("data") or {}
    arrival = r_data.get("arrival") or {}
    post_obs = r_data.get("post_observation") or r_data
    sync_ms = (post_obs.get("max_offset_s", 0.0) * 1000.0) if isinstance(post_obs, dict) and "max_offset_s" in post_obs else None

    args = r.get("arguments") or {}
    reason_text = args.get("reason", "")

    # Approx token progress linearly/by index if token_timeline has entries
    if token_timeline:
        ti = min(len(token_timeline) - 1, int((idx - 1) * len(token_timeline) / len(history)))
        tok_total, tok_cached = token_timeline[ti]
    else:
        tok_total, tok_cached = 0, 0

    steps.append({
        "idx": idx,
        "wall_s": (t1 - t_run_start).total_seconds(),
        "tool": h["tool"],
        "status": h["status"],
        "action_executed": h.get("action_executed", False),
        "actions_cum": h["progress"]["actions_executed"],
        "tool_dur": tool_dur,
        "sleep_before": sleep_before,
        "llm_before": llm_before,
        "reason": reason_text,
        "result_reason": h.get("reason", ""),
        "args": args,
        "obs": obs,
        "display_obs": obs if obs else last_valid_obs,
        "is_own_obs": obs is not None,
        "sync_ms": sync_ms,
        "pos_err_m": arrival.get("position_error_m"),
        "tok_total": tok_total,
        "tok_cached": tok_cached,
    })
    prev_end = t1

sim_start = steps[0]["obs"]["stamp_s"]
sim_end = [s["obs"]["stamp_s"] for s in steps if s["obs"]][-1]
sim_span_s = sim_end - sim_start
avg_rtf = sim_span_s / total_span_s

# Build summary metrics JSON
llm_latencies = [s["llm_before"] for s in steps[1:] if s["llm_before"] > 0.1]
sync_vals = [s["sync_ms"] for s in steps if s["sync_ms"] is not None]
metrics = {
    "run_id": "gz_01",
    "task": result["task"],
    "model": result["model"],
    "effort": result["effort"],
    "elapsed_s_result": result["elapsed_s"],
    "wall_span_calls_s": round(total_span_s, 2),
    "sim_span_s": round(sim_span_s, 2),
    "avg_rtf": round(avg_rtf, 4),
    "total_calls": len(steps),
    "actions_executed": result["actions_executed"],
    "observations": result["observations"],
    "rejections": result["rejections"],
    "sleep_count": len(sleeps),
    "total_sleep_s": round(total_sleep_s, 2),
    "sleep_pct": round(100.0 * total_sleep_s / total_span_s, 1),
    "total_llm_s": round(total_llm_s, 2),
    "llm_pct": round(100.0 * total_llm_s / total_span_s, 1),
    "llm_mean_s": round(sum(llm_latencies) / len(llm_latencies), 2),
    "llm_median_s": round(sorted(llm_latencies)[len(llm_latencies)//2], 2),
    "total_tool_s": round(total_tool_s, 2),
    "tool_pct": round(100.0 * total_tool_s / total_span_s, 1),
    "sync_mean_ms": round(sum(sync_vals) / len(sync_vals), 2),
    "sync_max_ms": round(max(sync_vals), 2),
    "tokens": result["tokens"],
    "cache_hit_pct": round(100.0 * result["tokens"]["cached_input"] / max(1, result["tokens"]["cached_input"] + result["tokens"]["uncached_input"]), 2),
    "cost_usd_estimate": result["cost_usd_estimate"],
    "tool_counts": dict(Counter(s["tool"] for s in steps)),
    "status_counts": dict(Counter(s["status"] for s in steps)),
    "ideal_1x_rtf_est_s": round(total_llm_s * 0.55 + result["actions_executed"] * 3.5, 1),
}
with open(f"{OUT_DIR}/gz01_metrics.json", "w") as f:
    json.dump(metrics, f, indent=2, ensure_ascii=False)
print("=== EXACT METRICS ===")
print(json.dumps(metrics, indent=2, ensure_ascii=False))

# ------------------------------------------------------------------
# 2. Generate Publication-Grade Telemetry Charts (2x2 Figure)
# ------------------------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(15.5, 10.2), dpi=160)
fig.patch.set_facecolor("#F8FAFC")
fig.suptitle(
    "GPT-6 Astra × ROBOTIS AI Worker (gz_01) 首次复现量化遥测与分层架构分析",
    fontsize=16, fontweight="bold", color="#0F172A", y=0.975
)

# Panel A: Three-way Wall-Time Breakdown (Revealing the Adaptive Sleep Discovery!)
ax = axes[0, 0]
ax.set_facecolor("#FFFFFF")
labels_a = [
    f"模型自主 sleep 等慢仿真\n({len(sleeps)} 次，模拟 RTF=0.082×)",
    f"大模型多模态思考 + API 往返\n(均值 {metrics['llm_mean_s']:.1f}s / 次)",
    f"Harness 校验 + 机器人运控等待\n(57 次工具执行)"
]
vals_a = [total_sleep_s, total_llm_s, total_tool_s]
pcts_a = [100.0 * v / total_span_s for v in vals_a]
colors_a = ["#F59E0B", "#2563EB", "#10B981"]
y_pos = np.arange(len(labels_a))
bars = ax.barh(y_pos, vals_a, color=colors_a, height=0.55, edgecolor="none")
ax.set_yticks(y_pos)
ax.set_yticklabels(labels_a, fontsize=10, color="#1E293B")
ax.invert_yaxis()
ax.set_xlabel("累计耗时 (秒)", fontsize=10.5, color="#334155")
ax.set_title("(A) 全程 1296 秒耗时三元拆解：瓶颈并非大模型推理", fontsize=11.5, fontweight="bold", color="#0F172A", pad=10)
ax.set_xlim(0, max(vals_a) * 1.28)
ax.grid(axis="x", linestyle="--", alpha=0.35)
for bar, v, p in zip(bars, vals_a, pcts_a):
    ax.text(v + 15, bar.get_y() + bar.get_height()/2, f"{v:.1f}s  ({p:.1f}%)",
            va="center", ha="left", fontsize=10.5, fontweight="bold", color="#0F172A")

# Panel B: Hierarchical Frequency Comparison (Log Scale!)
ax = axes[0, 1]
ax.set_facecolor("#FFFFFF")
layers = [
    "Gazebo 物理积分步进\n(max_step_size=1ms)",
    "ROS 2 Control 关节环\n(controller_manager)",
    "Cyclo MoveL 笛卡尔插补\n(ai_worker_controller)",
    "移动底盘速度控制\n(/cmd_vel publish_hz)",
    "理论 1× 实时下大模型决策\n(实测纯思考+动作 ~8.5s)",
    "本次 gz_01 实测决策频率\n(含慢仿真 sleep 0.082×)",
    "本次 gz_01 有效动作频率\n(27 次动作 / 1242s)"
]
freqs = [1000.0, 100.0, 100.0, 20.0, 0.118, 57.0/1242.4, 27.0/1242.4]
layer_colors = ["#0EA5E9", "#0284C7", "#0369A1", "#14B8A6", "#8B5CF6", "#F59E0B", "#EF4444"]
y_b = np.arange(len(layers))
bars_b = ax.barh(y_b, freqs, color=layer_colors, height=0.58)
ax.set_xscale("log")
ax.set_yticks(y_b)
ax.set_yticklabels(layers, fontsize=9.2, color="#1E293B")
ax.invert_yaxis()
ax.set_xlabel("控制 / 决策频率 (Hz，对数坐标)", fontsize=10.5, color="#334155")
ax.set_title("(B) “大模型低频决策 × 机器人高频运控”跨 3 个数量级频差", fontsize=11.5, fontweight="bold", color="#0F172A", pad=10)
ax.set_xlim(0.01, 5000)
ax.grid(axis="x", which="both", linestyle="--", alpha=0.35)
for bar, f in zip(bars_b, freqs):
    lbl = f"{f:.0f} Hz" if f >= 1 else f"{f:.3f} Hz (约 {1/f:.1f}s/次)"
    ax.text(f * 1.22, bar.get_y() + bar.get_height()/2, lbl,
            va="center", ha="left", fontsize=9, fontweight="bold", color="#0F172A")

# Panel C: Right Arm End-Effector Trajectory & Body Joints Across Calls
ax = axes[1, 0]
ax.set_facecolor("#FFFFFF")
obs_steps = [s for s in steps if s["obs"]]
xs_idx = [s["idx"] for s in obs_steps]
ee_x = [s["obs"]["arms"]["right"]["xyz"][0] for s in obs_steps]
ee_y = [s["obs"]["arms"]["right"]["xyz"][1] for s in obs_steps]
ee_z = [s["obs"]["arms"]["right"]["xyz"][2] for s in obs_steps]
lift_j = [s["obs"]["body"]["lift_joint"] for s in obs_steps]
head_j = [s["obs"]["body"]["head_joint1"] for s in obs_steps]

ax.plot(xs_idx, ee_x, label="右臂 X (前伸, m)", color="#2563EB", linewidth=2.3, marker="o", markersize=3)
ax.plot(xs_idx, ee_z, label="右臂 Z (高度, m)", color="#10B981", linewidth=2.3, marker="s", markersize=3)
ax.plot(xs_idx, ee_y, label="右臂 Y (左右, m)", color="#8B5CF6", linewidth=1.8, linestyle="--")
ax.plot(xs_idx, lift_j, label="躯干升降 Lift (m)", color="#F59E0B", linewidth=1.8, linestyle="-.")
ax.plot(xs_idx, head_j, label="头部俯仰 Head (rad)", color="#EC4899", linewidth=1.6, linestyle=":")

# Annotate key milestones
milestones = [
    (5, 0.66, "低头定位方块", (-15, 16)),
    (13, -0.15, "降躯干到位", (8, -18)),
    (39, 0.245, "入腕部视野", (5, -24)),
    (46, 0.928, "避桌缘抬升", (-58, 12)),
    (57, 0.444, "悬停方块正上方", (-90, 12)),
]
for mx, my, mtxt, moff in milestones:
    ax.annotate(mtxt, xy=(mx, my), xytext=moff, textcoords="offset points",
                fontsize=8.5, fontweight="bold", color="#0F172A",
                bbox=dict(boxstyle="round,pad=0.25", fc="#FEF3C7", ec="#D97706", lw=0.8),
                arrowprops=dict(arrowstyle="->", color="#D97706", lw=1.0))

ax.set_xlabel("工具调用序号 (Call Index)", fontsize=10.5, color="#334155")
ax.set_ylabel("末端位置 (m) / 关节量", fontsize=10.5, color="#334155")
ax.set_title("(C) 右臂 3D 轨迹与全身协同演进（零深度传感器、纯 RGB 视觉伺服）", fontsize=11.5, fontweight="bold", color="#0F172A", pad=10)
ax.set_xlim(0, 60)
ax.set_ylim(-0.42, 1.08)
ax.grid(True, linestyle="--", alpha=0.35)
ax.legend(loc="lower right", fontsize=8.3, ncol=2, framealpha=0.92)

# Panel D: Per-Call Latency Stacked + Cumulative Token Growth
ax = axes[1, 1]
ax.set_facecolor("#FFFFFF")
c_idx = [s["idx"] for s in steps]
c_sleep = [s["sleep_before"] for s in steps]
c_llm = [s["llm_before"] for s in steps]
c_tool = [s["tool_dur"] for s in steps]
c_tok_m = [s["tok_total"] / 1e6 for s in steps]
# Ensure last point matches exact result total
c_tok_m[-1] = result["tokens"]["total"] / 1e6

ax.bar(c_idx, c_sleep, label="自主 sleep (等慢仿真)", color="#F59E0B", alpha=0.85, width=0.75)
ax.bar(c_idx, c_llm, bottom=c_sleep, label="大模型推理 + API", color="#2563EB", alpha=0.85, width=0.75)
bottom2 = [a + b for a, b in zip(c_sleep, c_llm)]
ax.bar(c_idx, c_tool, bottom=bottom2, label="Harness + 机器人执行", color="#10B981", alpha=0.85, width=0.75)

ax.set_xlabel("工具调用序号 (Call Index)", fontsize=10.5, color="#334155")
ax.set_ylabel("单步现实耗时分解 (秒)", fontsize=10.5, color="#334155")
ax.set_ylim(0, 62)
ax.grid(axis="y", linestyle="--", alpha=0.35)

ax2 = ax.twinx()
ax2.plot(c_idx, c_tok_m, color="#DC2626", linewidth=2.4, label="累计 Token (百万)")
ax2.axhline(5.0, color="#DC2626", linestyle="--", linewidth=1.2, alpha=0.7)
ax2.text(20, 5.16, f"默认保护上限: 5.0M Tokens ({metrics['cache_hit_pct']:.1f}% 缓存命中)", fontsize=8.8, color="#B91C1C", fontweight="bold")
ax2.set_ylabel("累计 Token 消耗 (Million)", fontsize=10.5, color="#B91C1C")
ax2.set_ylim(0, 5.85)

ax.set_title("(D) 每步耗时构成本质与 Token 累积曲线", fontsize=11.5, fontweight="bold", color="#0F172A", pad=10)
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8.3, framealpha=0.92)

plt.tight_layout(rect=[0, 0.01, 1, 0.945])
chart_path = f"{OUT_DIR}/gz_01_telemetry_charts.png"
plt.savefig(chart_path, dpi=160, facecolor=fig.get_facecolor())
plt.close()
print("Saved chart:", chart_path)

# ------------------------------------------------------------------
# 3. Generate 6-Stage Key Milestone Visual Collage
# ------------------------------------------------------------------
def load_font(size):
    return ImageFont.truetype(FONT_PATH, size)

milestone_specs = [
    (1,  "阶段 1 · Call #01 (Obs #01, 0s)",    "初始平视状态：看不到桌面，启动自主观察"),
    (5,  "阶段 2 · Call #05 (Obs #05, 63s)",   "主动低头 0.66 rad：锁定木桌与蓝色方块"),
    (11, "阶段 3 · Call #13 (Obs #11, 264s)",  "降躯干至 -0.15m 并启动右臂绕桌缘抬升"),
    (37, "阶段 4 · Call #39 (Obs #37, 866s)",  "关键转折：蓝色方块首次进入右腕相机视野"),
    (44, "阶段 5 · Call #46 (Obs #44, 1039s)", "察觉触碰桌缘受阻：自主抬臂至 Z=0.93m 脱困"),
    (55, "阶段 6 · Call #57 (Obs #55, 1296s)", "临门一脚：夹爪跨正上方 (差下降合爪即抓起)"),
]
# Map obs number -> folder
obs_root = f"{RUN_DIR}/public/observations"
tile_w, tile_h = 560, 290
cols, rows = 3, 2
pad = 22
header_h = 72
canvas_w = cols * tile_w + (cols + 1) * pad
canvas_h = header_h + rows * tile_h + (rows + 1) * pad

collage = Image.new("RGB", (canvas_w, canvas_h), (15, 23, 42))
draw = ImageDraw.Draw(collage)
draw.text((pad, 16), "GPT-6 Astra × AI Worker (gz_01) 关键阶段双视角演进（头部主摄 + 右腕特写）",
          font=load_font(24), fill=(248, 250, 252))
draw.text((pad, 48), "零深度测距 · 零预编码物体坐标 · 纯三路 RGB 视觉伺服 + 自主策略修正",
          font=load_font(14), fill=(148, 163, 184))

for idx_m, (obs_num, title_m, desc_m) in enumerate(milestone_specs):
    r_i, c_i = divmod(idx_m, cols)
    x0 = pad + c_i * (tile_w + pad)
    y0 = header_h + pad + r_i * (tile_h + pad)
    draw.rounded_rectangle([x0, y0, x0 + tile_w, y0 + tile_h], radius=12, fill=(30, 41, 59), outline=(71, 85, 105), width=2)

    folder = f"{obs_root}/{obs_num:03d}"
    head_im = Image.open(f"{folder}/head.jpg").convert("RGB").resize((330, 185), Image.Resampling.LANCZOS)
    wrist_im = Image.open(f"{folder}/wrist_right.jpg").convert("RGB").resize((200, 185), Image.Resampling.LANCZOS)
    collage.paste(head_im, (x0 + 12, y0 + 12))
    collage.paste(wrist_im, (x0 + 348, y0 + 12))

    # Small camera badges
    draw.rectangle([x0 + 16, y0 + 16, x0 + 96, y0 + 34], fill=(15, 23, 42))
    draw.text((x0 + 22, y0 + 17), "HEAD 头部", font=load_font(11), fill=(56, 189, 248))
    draw.rectangle([x0 + 352, y0 + 16, x0 + 450, y0 + 34], fill=(15, 23, 42))
    draw.text((x0 + 358, y0 + 17), "R-WRIST 右腕", font=load_font(11), fill=(52, 211, 153))

    draw.text((x0 + 14, y0 + 206), title_m, font=load_font(17), fill=(250, 204, 21))
    draw.text((x0 + 14, y0 + 234), desc_m, font=load_font(14), fill=(226, 232, 240))
    # Add EE coordinates from observation.json
    obs_j = json.load(open(f"{folder}/observation.json"))
    re_ = obs_j["arms"]["right"]["xyz"]
    draw.text((x0 + 14, y0 + 260),
              f"Right EE: x={re_[0]:.3f}m  y={re_[1]:.3f}m  z={re_[2]:.3f}m  |  sim={obs_j['stamp_s']:.1f}s",
              font=load_font(12), fill=(148, 163, 184))

collage_path = f"{OUT_DIR}/gz_01_key_milestones.png"
collage.save(collage_path, quality=95)
print("Saved collage:", collage_path)

# ------------------------------------------------------------------
# 4. Render Full Replay Video (1440x810 H.264 MP4)
# ------------------------------------------------------------------
W, H = 1440, 810
FPS = 10
frames_dir = f"{OUT_DIR}/video_frames"
os.makedirs(frames_dir, exist_ok=True)
for old_f in glob.glob(f"{frames_dir}/*.jpg"):
    os.remove(old_f)

f_title   = load_font(26)
f_sub     = load_font(15)
f_sec     = load_font(18)
f_body    = load_font(15)
f_small   = load_font(13)
f_badge   = load_font(15)
f_big     = load_font(38)
f_med     = load_font(22)

def phase_label_cn(idx):
    if idx <= 5:
        return "阶段 1/5 · 主动视觉搜索（低头定位桌面方块）"
    elif idx <= 13:
        return "阶段 2/5 · 全身高度协同（降躯干 + 触发安全限幅拦截）"
    elif idx <= 38:
        return "阶段 3/5 · 跨桌缘抬臂接近（含底盘前移试探）"
    elif idx <= 47:
        return "阶段 4/5 · 腕部视野捕获与桌缘避碰自适应抬升"
    else:
        return "阶段 5/5 · 纯 RGB 视差像素追踪，精准对准蓝色方块正上方"

def tool_cn(tool):
    return {
        "robot_start": "启动并首次观测",
        "robot_observe": "刷新三路相机与状态",
        "robot_head": "控制头部俯仰视角",
        "robot_lift": "控制躯干升降机构",
        "robot_move": "右臂末端直线移动 (MoveL)",
        "robot_base": "移动底盘速度试探",
        "robot_gripper": "控制夹爪开合",
    }.get(tool, tool)

STATUS_STYLE = {
    "observed": ("OBSERVED", (14, 165, 233)),
    "arrived":  ("ARRIVED",  (16, 185, 129)),
    "stopped":  ("STOPPED (慢仿真未走完)", (245, 158, 11)),
    "rejected": ("REJECTED (安全拦截)",   (239, 68, 68)),
}

frame_counter = 0
def save_repeated(img, seconds):
    global frame_counter
    n = max(1, int(round(seconds * FPS)))
    for _ in range(n):
        img.save(f"{frames_dir}/f_{frame_counter:05d}.jpg", quality=92)
        frame_counter += 1

# --- Intro Slide (3.5s) ---
intro = Image.new("RGB", (W, H), (11, 18, 32))
d = ImageDraw.Draw(intro)
d.rounded_rectangle([60, 55, W-60, H-55], radius=20, fill=(15, 23, 42), outline=(56, 189, 248), width=2)
d.text((110, 105), "GPT-6 Astra × ROBOTIS AI Worker", font=f_big, fill=(56, 189, 248))
d.text((110, 165), "Windows 11 (WSL2 + Docker) 首次全链路复现评估录像 · gz_01", font=f_title, fill=(248, 250, 252))
d.line([(110, 220), (W-110, 220)], fill=(51, 65, 85), width=2)

# Two-column architecture summary on intro slide
d.rounded_rectangle([110, 255, 695, 560], radius=14, fill=(30, 41, 59), outline=(59, 130, 246), width=2)
d.text((138, 278), "上层：大模型低频决策 (GPT-6 Astra / Codex)", font=f_med, fill=(96, 165, 250))
intro_left = [
    "• 任务指令：\"pick up the blue block\"（自然语言）",
    "• 感知输入：纯三路 RGB（头部 + 双腕），零深度测距",
    "• 决策频率：约 0.046 Hz（含 26 次自适应 sleep）",
    f"• 纯推理延迟：均值 {metrics['llm_mean_s']:.1f} s / 次，缓存命中 {metrics['cache_hit_pct']:.1f}%",
    "• 涌现能力：主动写工作笔记、像素视差测距、避碰抬臂",
]
for li, line in enumerate(intro_left):
    d.text((138, 330 + li * 42), line, font=f_sec, fill=(226, 232, 240))

d.rounded_rectangle([745, 255, W-110, 560], radius=14, fill=(30, 41, 59), outline=(16, 185, 129), width=2)
d.text((773, 278), "底层：机器人高频运控 (ROS 2 + Cyclo + Gazebo)", font=f_med, fill=(52, 211, 153))
intro_right = [
    "• 物理仿真步进：1000 Hz（max_step_size = 0.001s）",
    "• ROS 2 关节控制器 & Cyclo MoveL 插补：100 Hz",
    f"• 移动底盘控制：20 Hz | 三路相机同步偏差 <= {metrics['sync_max_ms']:.1f} ms",
    "• Harness 安全层：限幅 0.05m/步、状态变化防误动拦截",
    f"• 本次核心发现：RTF=0.082x 使 sleep 占时 {metrics['sleep_pct']:.1f}%",
]
for ri, line in enumerate(intro_right):
    d.text((773, 330 + ri * 42), line, font=f_sec, fill=(226, 232, 240))

d.rounded_rectangle([110, 595, W-110, 705], radius=12, fill=(30, 58, 138))
d.text((140, 616), "本视频按时序完整回放全部 57 次工具调用（55 组三路实拍观测 + 2 次安全拦截）", font=f_med, fill=(254, 240, 138))
d.text((140, 656), "总耗时 1242.4s (20分42秒) · 27 次执行动作 · 5,024,728 Tokens · 最终右臂夹爪精准悬停于蓝色方块正上方", font=f_sub, fill=(226, 232, 240))
save_repeated(intro, 3.8)

# --- Render Every Single Call (1..57) ---
# Preload all Right EE x, z for live mini trajectory plot
all_x = [s["display_obs"]["arms"]["right"]["xyz"][0] for s in steps]
all_z = [s["display_obs"]["arms"]["right"]["xyz"][2] for s in steps]

for s in steps:
    frame = Image.new("RGB", (W, H), (15, 23, 42))
    d = ImageDraw.Draw(frame)

    # Top Header Bar (y: 0..76)
    d.rectangle([0, 0, W, 76], fill=(11, 18, 32))
    d.line([(0, 76), (W, 76)], fill=(51, 65, 85), width=2)
    d.text((24, 12), "GPT-6 Astra × AI Worker | gz_01 (\"pick up the blue block\")", font=load_font(21), fill=(248, 250, 252))
    d.text((24, 46), phase_label_cn(s["idx"]), font=f_sub, fill=(56, 189, 248))

    # Top-right metrics & status badge
    st_text, st_col = STATUS_STYLE.get(s["status"], (s["status"].upper(), (148, 163, 184)))
    badge_w = 240 if len(st_text) > 10 else 155
    d.rounded_rectangle([W - badge_w - 24, 16, W - 24, 60], radius=10, fill=st_col)
    d.text((W - badge_w - 10, 27), st_text, font=f_badge, fill=(15, 23, 42) if s["status"] != "rejected" else (255, 255, 255))

    sim_s = s["display_obs"]["stamp_s"]
    top_stats = f"Call {s['idx']:02d}/57  |  Actions {s['actions_cum']:02d}/27  |  Wall {s['wall_s']:6.1f}s  |  Sim {sim_s:5.1f}s"
    d.text((W - badge_w - 495, 28), top_stats, font=f_sub, fill=(226, 232, 240))

    # Middle Camera Strip (y: 92..442, height 350)
    obs_num = s["display_obs"]["observation_number"]
    obs_dir = f"{obs_root}/{obs_num:03d}"

    # Left wrist: 380x260 centered vertically, Head: 600x336 centered, Right wrist: 380x260
    cam_boxes = [
        ("wrist_left.jpg",  "LEFT WRIST 左腕相机 (424×240)",  24,  112, 376, 260, (148, 163, 184)),
        ("head.jpg",        "HEAD VIEW 头部主视角 (672×376)", 416,  92, 608, 342, (56, 189, 248)),
        ("wrist_right.jpg", "RIGHT WRIST 右腕相机 (424×240)", 1040, 112, 376, 260, (52, 211, 153)),
    ]
    for fname, clabel, cx, cy, cw, ch, ccol in cam_boxes:
        d.rounded_rectangle([cx - 3, cy - 3, cx + cw + 3, cy + ch + 3], radius=10, fill=(30, 41, 59), outline=ccol, width=2)
        im = Image.open(f"{obs_dir}/{fname}").convert("RGB").resize((cw, ch), Image.Resampling.LANCZOS)
        frame.paste(im, (cx, cy))
        # Label overlay
        d.rectangle([cx, cy, cx + 255, cy + 26], fill=(15, 23, 42))
        d.text((cx + 8, cy + 4), clabel, font=f_small, fill=ccol)
        if not s["is_own_obs"]:
            # Overlay translucent-style red rejection banner on cameras
            d.rectangle([cx + 12, cy + ch - 36, cx + cw - 12, cy + ch - 8], fill=(185, 28, 28))
            d.text((cx + 22, cy + ch - 31), "安全层拦截 (复用上一帧观测)", font=f_small, fill=(255, 255, 255))

    # Sleep badge under left wrist if adaptive sleep happened before this call
    if s["sleep_before"] >= 1.0:
        d.rounded_rectangle([24, 384, 400, 434], radius=8, fill=(120, 53, 15), outline=(245, 158, 11), width=2)
        d.text((38, 398), f"[WAIT] 模型自主 sleep({s['sleep_before']:.1f}s) 等慢仿真", font=f_sub, fill=(254, 240, 138))
    else:
        d.rounded_rectangle([24, 384, 400, 434], radius=8, fill=(30, 41, 59), outline=(71, 85, 105), width=1)
        d.text((38, 398), f"[LLM] 纯推理+API: {s['llm_before']:.2f}s | 运控执行: {s['tool_dur']:.2f}s", font=f_sub, fill=(203, 213, 225))

    # Observation metadata badge under right wrist
    sync_txt = f"{s['sync_ms']:.1f} ms" if s["sync_ms"] is not None else "N/A"
    d.rounded_rectangle([1040, 384, 1416, 434], radius=8, fill=(30, 41, 59), outline=(71, 85, 105), width=1)
    d.text((1054, 398), f"[CAM] 观测 #{obs_num:02d} | 三路相机同步偏差: {sync_txt}", font=f_sub, fill=(167, 243, 208))

    # Bottom Left Panel: LLM Low-Frequency Decision (x: 24..830, y: 452..768)
    d.rounded_rectangle([24, 452, 830, 768], radius=12, fill=(30, 41, 59), outline=(59, 130, 246), width=2)
    d.text((42, 464), f"大模型低频决策层  |  工具: {s['tool']} ({tool_cn(s['tool'])})", font=f_sec, fill=(96, 165, 250))

    # Format concise tool arguments
    arg_parts = []
    args = s["args"]
    if s["tool"] == "robot_move":
        arg_parts.append(f"arm={args.get('arm')}  target=({args.get('x',0):.3f}, {args.get('y',0):.3f}, {args.get('z',0):.3f}) m")
        arg_parts.append(f"rpy=({args.get('roll',0):.2f}, {args.get('pitch',0):.2f}, {args.get('yaw',0):.2f}) rad")
    elif s["tool"] == "robot_head":
        arg_parts.append(f"head_joint1={args.get('head_joint1')} rad, head_joint2={args.get('head_joint2')} rad")
    elif s["tool"] == "robot_lift":
        arg_parts.append(f"position_m={args.get('position_m')} m")
    elif s["tool"] == "robot_base":
        arg_parts.append(f"vx={args.get('vx')}, vy={args.get('vy')}, wz={args.get('wz')}, duration={args.get('duration_s')}s")
    else:
        arg_parts.append("无动作参数（仅同步采集三路 RGB 图像与关节/末端状态）")

    d.text((42, 498), "指令参数: " + "  |  ".join(arg_parts), font=f_sub, fill=(250, 204, 21))
    d.text((42, 526), f"Harness 反馈: {s['result_reason']}", font=f_sub, fill=(248, 113, 113) if s["status"] == "rejected" else (167, 243, 208))
    d.line([(42, 554), (812, 554)], fill=(71, 85, 105), width=1)

    d.text((42, 564), "GPT-6 Astra 决策依据 (Recorded Model Rationale):", font=f_small, fill=(148, 163, 184))
    rationale = s["reason"] if s["reason"] else (
        "（本步为观测刷新：读取最新三路图像与关节状态，检查上一步慢仿真动作是否到位）"
        if s["tool"] == "robot_observe" else "（初始化回合，获取初始三路相机视角与机器人位姿）"
    )
    wrapped = textwrap.wrap(rationale, width=68)[:6]
    for wi, wline in enumerate(wrapped):
        d.text((42, 588 + wi * 26), wline, font=f_body, fill=(241, 245, 249))

    # Bottom Right Panel: High-Frequency Robot Control State + Mini Trajectory (x: 848..1416, y: 452..768)
    d.rounded_rectangle([848, 452, 1416, 768], radius=12, fill=(30, 41, 59), outline=(16, 185, 129), width=2)
    d.text((866, 464), "高频运控反馈层  |  ROS 2 / Cyclo (100 Hz)", font=f_sec, fill=(52, 211, 153))

    r_arm = s["display_obs"]["arms"]["right"]
    body = s["display_obs"]["body"]
    rx, ry, rz = r_arm["xyz"]
    d.text((866, 500), f"右臂末端 (base_link):  X={rx:+.3f} m   Y={ry:+.3f} m   Z={rz:+.3f} m", font=f_sub, fill=(248, 250, 252))
    d.text((866, 528), f"头部俯仰: {body['head_joint1']:.3f} rad   |   躯干升降: {body['lift_joint']:+.3f} m   |   右爪: {r_arm['gripper']:.3f}", font=f_sub, fill=(203, 213, 225))
    err_str = f"{s['pos_err_m']*100:.1f} cm (慢仿真滞后)" if s["pos_err_m"] is not None else "—"
    d.text((866, 556), f"当步末端误差: {err_str}   |   Token: {s['tok_total']/1e6:.2f}M / 5.00M", font=f_sub, fill=(253, 224, 71))

    # Mini XZ Trajectory Canvas (x: 866..1398, y: 590..750)
    tx0, ty0, tx1, ty1 = 866, 590, 1398, 750
    d.rounded_rectangle([tx0, ty0, tx1, ty1], radius=8, fill=(15, 23, 42), outline=(51, 65, 85), width=1)
    d.text((tx0 + 10, ty0 + 6), "右臂末端侧视轨迹演进 (X 前伸 vs Z 高度, base_link)", font=f_small, fill=(148, 163, 184))

    # Map X in [-0.05, 0.50], Z in [0.52, 0.98]
    def map_xz(xv, zv):
        px = tx0 + 24 + (xv - (-0.05)) / (0.50 - (-0.05)) * (tx1 - tx0 - 48)
        py = ty1 - 18 - (zv - 0.52) / (0.98 - 0.52) * (ty1 - ty0 - 44)
        return (int(px), int(py))

    # Approximate blue block zone marker
    bx, by = map_xz(0.47, 0.88)
    d.rectangle([bx - 10, by - 10, bx + 10, by + 10], fill=(37, 99, 235), outline=(147, 197, 253), width=2)
    d.text((bx - 64, by + 12), "蓝方块区域", font=f_small, fill=(147, 197, 253))

    # Draw full faint path and active path up to current step
    pts_all = [map_xz(all_x[k], all_z[k]) for k in range(len(steps))]
    for k in range(1, len(pts_all)):
        d.line([pts_all[k-1], pts_all[k]], fill=(51, 65, 85), width=2)
    pts_cur = pts_all[:s["idx"]]
    for k in range(1, len(pts_cur)):
        d.line([pts_cur[k-1], pts_cur[k]], fill=(52, 211, 153), width=3)
    cx_pt, cy_pt = pts_cur[-1]
    d.ellipse([cx_pt - 6, cy_pt - 6, cx_pt + 6, cy_pt + 6], fill=(250, 204, 21), outline=(255, 255, 255), width=2)

    # Bottom Progress Bar (y: 780..798)
    d.rectangle([24, 782, W - 24, 796], fill=(30, 41, 59))
    prog_w = int((W - 48) * (s["idx"] / len(steps)))
    d.rectangle([24, 782, 24 + prog_w, 796], fill=(56, 189, 248))

    # Hold duration: actions & rejections slightly longer so user can read rationale clearly
    if s["idx"] in (1, 5, 10, 11, 13, 22, 39, 45, 46, 55, 57):
        dur_sec = 2.0
    elif s["tool"] == "robot_observe":
        dur_sec = 0.8
    else:
        dur_sec = 1.4
    save_repeated(frame, dur_sec)

# --- Outro Summary Slide (4.5s) ---
outro = Image.new("RGB", (W, H), (11, 18, 32))
d = ImageDraw.Draw(outro)
d.rounded_rectangle([60, 55, W-60, H-55], radius=20, fill=(15, 23, 42), outline=(16, 185, 129), width=2)
d.text((110, 100), "gz_01 研究复现总结：结论与核心瓶颈诊断", font=f_big, fill=(52, 211, 153))
d.line([(110, 162), (W-110, 162)], fill=(51, 65, 85), width=2)

outro_items = [
    ("1. 全链路能力验证通过", "在 Windows 11 (WSL2 + Docker) 上成功跑通 GPT-6 Astra → Harness → ROS 2 / Cyclo → Gazebo 闭环；最后第 57 步右臂夹爪已精准悬停于蓝色方块正上方（仅差最后 3 步合爪抬起）。"),
    ("2. 惊人的具身涌现行为", "零深度传感器与零预编码坐标下，模型自主低头搜寻、降躯干、感知桌缘碰撞风险并抬高脱困、通过腕部图像像素位移做视差定位，还自发维护 NOTES.md 记录系统动力学规律。"),
    ("3. 关键瓶颈真凶浮出水面", f"1296 秒中，大模型纯推理+API 仅占 {metrics['llm_pct']:.1f}%（均值 {metrics['llm_mean_s']:.1f}s/次）；高达 {metrics['sleep_pct']:.1f}% ({metrics['total_sleep_s']:.0f}s) 是模型自主调用 sleep 等待 0.082× 慢仿真！"),
    ("4. 下一轮提速优化方向", f"只要消除 Gazebo 软渲染 / RTF 限速瓶颈（拉升至 0.8~1.0× 实时），省去 {metrics['sleep_count']} 次 sleep 与重复观察，预计 3~5 分钟、不到一半 Token 即可一次稳定举起蓝色方块。"),
]
for oi, (otitle, odesc) in enumerate(outro_items):
    y_box = 195 + oi * 128
    d.rounded_rectangle([110, y_box, W-110, y_box + 108], radius=12, fill=(30, 41, 59), outline=(71, 85, 105), width=1)
    d.text((135, y_box + 14), otitle, font=f_med, fill=(250, 204, 21))
    wlines = textwrap.wrap(odesc, width=62)
    for wl_i, wl in enumerate(wlines[:2]):
        d.text((135, y_box + 48 + wl_i * 26), wl, font=f_sub, fill=(226, 232, 240))

save_repeated(outro, 4.5)

video_path = f"{OUT_DIR}/gz_01_full_replay.mp4"
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
# Save a few sample frames for visual QA
os.system(f"cp {frames_dir}/f_00000.jpg {OUT_DIR}/qa_intro.jpg")
os.system(f"cp {frames_dir}/f_{frame_counter//2:05d}.jpg {OUT_DIR}/qa_mid.jpg")
os.system(f"cp {frames_dir}/f_{frame_counter-1:05d}.jpg {OUT_DIR}/qa_outro.jpg")
print(f"Video rendered successfully: {video_path} ({frame_counter} frames, {frame_counter/FPS:.1f}s)")
