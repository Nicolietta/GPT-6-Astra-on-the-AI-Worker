#!/usr/bin/env python3
"""Render a crisp 3-layer architecture diagram for the gz_01 Word report."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

FONT_PATH = "/workspace/msyh.ttc"
OUT_PATH = "/workspace/gz01_report_assets/gz_01_architecture_diagram.png"

fm.fontManager.addfont(FONT_PATH)
fp = fm.FontProperties(fname=FONT_PATH)
plt.rcParams["font.family"] = fp.get_name()

fig, ax = plt.subplots(figsize=(14.5, 7.6), dpi=200)
fig.patch.set_facecolor("#F8FAFC")
ax.set_facecolor("#F8FAFC")
ax.set_xlim(0, 100)
ax.set_ylim(0, 62)
ax.axis("off")

# Title
ax.text(50, 59.2, "“大模型低频决策 × 机器人高频运控”三层解耦闭环架构（gz_01 实测参数标注）",
        ha="center", va="center", fontsize=16, fontweight="bold", color="#0F172A")
ax.text(50, 56.2, "GPT-6 Astra (Codex App Server)  →  Harness 校验守卫层  →  ROS 2 (Zenoh) / Cyclo / Gazebo Harmonic",
        ha="center", va="center", fontsize=11, color="#475569")

def draw_box(x, y, w, h, fc, ec, lw=2.0, radius=1.6):
    box = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.3,rounding_size={radius}",
                         facecolor=fc, edgecolor=ec, linewidth=lw)
    ax.add_patch(box)

def draw_arrow(x1, y1, x2, y2, color="#2563EB", lw=2.2, ls="-", rad=0.0):
    arr = FancyArrowPatch((x1, y1), (x2, y2),
                          connectionstyle=f"arc3,rad={rad}",
                          arrowstyle="-|>,head_length=7,head_width=4.5",
                          color=color, linewidth=lw, linestyle=ls)
    ax.add_patch(arr)

# --- Layer 1 Container (Left: 2.0 .. 29.0) ---
draw_box(2.0, 19.5, 27.0, 33.5, "#EFF6FF", "#2563EB", lw=2.2)
ax.text(15.5, 50.8, "① 上层：大模型低频决策层", ha="center", va="center", fontsize=12.5, fontweight="bold", color="#1D4ED8")
ax.text(15.5, 48.2, "实测 0.046 Hz (理论 1× 约 0.12 Hz)", ha="center", va="center", fontsize=9.8, fontweight="bold", color="#1E40AF")

draw_box(3.5, 32.5, 24.0, 13.5, "#FFFFFF", "#60A5FA", lw=1.5, radius=1.2)
ax.text(15.5, 43.8, "GPT-6 Astra / Codex App Server", ha="center", va="center", fontsize=11, fontweight="bold", color="#0F172A")
l1_lines = [
    "• 纯三路 RGB + 关节状态输入（零深度）",
    "• 多模态纯推理均值: 7.67 s / 次 (33.1%)",
    "• Prompt Cache 命中率: 98.03%",
    "• 输出: 工具名 + 绝对坐标 + 决策理由",
]
for i, t in enumerate(l1_lines):
    ax.text(4.3, 40.8 - i * 2.15, t, ha="left", va="center", fontsize=8.5, color="#334155")

draw_box(3.5, 21.2, 24.0, 9.5, "#DBEAFE", "#3B82F6", lw=1.3, radius=1.2)
ax.text(15.5, 28.9, "沙盒记忆与自适应节奏", ha="center", va="center", fontsize=10.5, fontweight="bold", color="#1E3A8A")
l1_sub = [
    "• 自主维护 notes/NOTES.md 在线笔记",
    "• 自主调用 26 次 sleep() 等慢仿真",
    "  (共 734.5 s，占全流程耗时 56.7%)",
]
for i, t in enumerate(l1_sub):
    ax.text(4.3, 26.5 - i * 1.9, t, ha="left", va="center", fontsize=8.4, color="#1E293B")

# --- Layer 2 Container (Middle: 36.2 .. 63.0) ---
draw_box(36.2, 19.5, 26.8, 33.5, "#ECFDF5", "#059669", lw=2.2)
ax.text(49.6, 50.8, "② 中间层：Harness 校验守卫层", ha="center", va="center", fontsize=12.5, fontweight="bold", color="#047857")
ax.text(49.6, 48.2, "安全边界 · 坐标契约 · 硬件时间同步", ha="center", va="center", fontsize=9.8, fontweight="bold", color="#065F46")

draw_box(37.7, 33.0, 23.8, 13.0, "#FFFFFF", "#34D399", lw=1.5, radius=1.2)
ax.text(49.6, 43.8, "动作安全与状态新鲜度校验", ha="center", va="center", fontsize=10.8, fontweight="bold", color="#0F172A")
l2_lines = [
    "• 单步硬限幅: ≤ 0.05 m / ≤ 0.35 rad",
    "• request_id 绑定最新观测 (防滞后误动)",
    "• gz_01 精确拦截 2 次异常调用 (Rejected):",
    "  #10 步幅 0.052m 超限 | #11 lift 漂移",
]
for i, t in enumerate(l2_lines):
    ax.text(38.5, 40.8 - i * 2.15, t, ha="left", va="center", fontsize=8.4, color="#334155")

draw_box(37.7, 21.2, 23.8, 9.8, "#D1FAE5", "#10B981", lw=1.3, radius=1.2)
ax.text(49.6, 28.9, "多传感器同步与到位检测", ha="center", va="center", fontsize=10.5, fontweight="bold", color="#065F46")
l2_sub = [
    "• 同步采集 3路相机 + /joint_states + /odom",
    "• 同步偏差: 均值 2.4 ms (最大 5.0 ms)",
    "• 9大工具映射为 ROS 2 Topic (占时 10.2%)",
]
for i, t in enumerate(l2_sub):
    ax.text(38.5, 26.5 - i * 1.9, t, ha="left", va="center", fontsize=8.4, color="#1E293B")

# --- Layer 3 Container (Right: 70.2 .. 98.0) ---
draw_box(70.2, 19.5, 27.8, 33.5, "#FFFBEB", "#D97706", lw=2.2)
ax.text(84.1, 50.8, "③ 底层：机器人高频实时运控层", ha="center", va="center", fontsize=12.5, fontweight="bold", color="#B45309")
ax.text(84.1, 48.2, "20 Hz ~ 1000 Hz（快出决策层 3 个数量级）", ha="center", va="center", fontsize=9.8, fontweight="bold", color="#92400E")

draw_box(71.7, 36.2, 24.8, 9.8, "#FFFFFF", "#FBBF24", lw=1.5, radius=1.2)
ax.text(84.1, 44.0, "Cyclo MoveL 笛卡尔控制器 (100 Hz)", ha="center", va="center", fontsize=10.5, fontweight="bold", color="#0F172A")
ax.text(72.5, 41.2, "• 订阅 /l_goal_move、/r_goal_move (MoveL)", ha="left", va="center", fontsize=8.4, color="#334155")
ax.text(72.5, 39.1, "• 直线插补 + IK 逆解 + 基础自碰撞防护", ha="left", va="center", fontsize=8.4, color="#334155")
ax.text(72.5, 37.2, "• 独立于大模型运行，不依赖 LLM 伺服", ha="left", va="center", fontsize=8.4, color="#334155")

draw_box(71.7, 21.2, 24.8, 13.2, "#FEF3C7", "#F59E0B", lw=1.3, radius=1.2)
ax.text(84.1, 32.4, "ROS 2 (Zenoh) + Gazebo Harmonic", ha="center", va="center", fontsize=10.5, fontweight="bold", color="#78350F")
l3_sub = [
    "• 关节伺服环 update_rate: 100 Hz (6组)",
    "• 底盘速度控制 /cmd_vel: 20 Hz",
    "• Gazebo 物理积分步进: 1000 Hz (1 ms)",
    "• 3路相机: 头 672×376 + 双腕 424×240",
    "• 当前瓶颈: CPU 软渲染下 RTF = 0.0821×",
]
for i, t in enumerate(l3_sub):
    ax.text(72.5, 29.8 - i * 1.95, t, ha="left", va="center", fontsize=8.3, color="#1E293B")

# --- Bottom Feedback Loop Box ---
draw_box(10.0, 4.0, 80.0, 10.5, "#F1F5F9", "#64748B", lw=1.8, radius=1.4)
ax.text(50.0, 12.1, "观测与执行状态闭环反馈通道（第 57 步终止前共完成 55 次同步观测、27 次物理动作）",
        ha="center", va="center", fontsize=11, fontweight="bold", color="#0F172A")
ax.text(50.0, 9.0, "数据流：3路 RGB 图像 (Base64) + base_link 6D 末端位姿 + 关节/升降/夹爪状态 + 运控到位判定 (arrived / stopped / rejected)",
        ha="center", va="center", fontsize=9.4, color="#334155")
ax.text(50.0, 6.1, "物理世界状态（非高频连续视觉伺服）：每步执行期间机械臂开环走完插补轨迹，完成后再采样下一帧触发大模型决策",
        ha="center", va="center", fontsize=9.1, color="#475569")

# --- Arrows connecting the 3 layers ---
# L1 -> L2 (gap 29.3 .. 35.9, center 32.6)
draw_arrow(29.3, 40.0, 35.9, 40.0, color="#2563EB", lw=2.6)
ax.text(32.6, 42.6, "tool call\n+位姿参数", ha="center", va="center", fontsize=8.3, fontweight="bold", color="#1D4ED8",
        bbox=dict(boxstyle="round,pad=0.2", fc="#F8FAFC", ec="none"))

# L2 -> L1 rejection dashed
draw_arrow(35.9, 34.0, 29.3, 34.0, color="#DC2626", lw=2.0, ls="--")
ax.text(32.6, 31.3, "Rejected\n(2次拦截)", ha="center", va="center", fontsize=8.2, fontweight="bold", color="#DC2626",
        bbox=dict(boxstyle="round,pad=0.2", fc="#F8FAFC", ec="none"))

# L2 -> L3 (gap 63.3 .. 69.9, center 66.6)
draw_arrow(63.3, 40.0, 69.9, 40.0, color="#059669", lw=2.6)
ax.text(66.6, 42.6, "ROS 2\nTopic指令", ha="center", va="center", fontsize=8.3, fontweight="bold", color="#047857",
        bbox=dict(boxstyle="round,pad=0.2", fc="#F8FAFC", ec="none"))

# L3 -> Bottom Feedback -> L1
draw_arrow(84.1, 19.2, 84.1, 15.0, color="#D97706", lw=2.4)
draw_arrow(15.5, 15.0, 15.5, 19.2, color="#2563EB", lw=2.4)
draw_arrow(49.6, 19.2, 49.6, 15.0, color="#059669", lw=2.0, ls=":")

plt.tight_layout(pad=0.3)
plt.savefig(OUT_PATH, dpi=200, facecolor=fig.get_facecolor())
plt.close()
print("Saved architecture diagram:", OUT_PATH)
