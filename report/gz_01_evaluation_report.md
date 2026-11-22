# GPT-6 Astra × ROBOTIS AI Worker (`gz_01`) 首次复现与研究评估报告

> **实验代号**：`gz_01` ｜ **自然语言任务**：`"pick up the blue block"` ｜ **模型**：`gpt-6-astra`（`reasoning_effort: low`）  
> **复现时间**：2026-11-22 16:18–16:40 (UTC+8) ｜ **运行平台**：Windows 11 专业版 + WSL 2 (`Ubuntu-24.04`) + Docker Desktop + NVIDIA RTX 5070 Laptop GPU

> **核心结论**：已在 Windows 11 消费级笔记本上端到端跑通 **GPT-6 Astra → Codex App Server → Harness → ROS 2 (Zenoh) / Cyclo → Gazebo** 完整具身闭环。在零深度测距、零物体坐标预编码的纯三路 RGB 条件下，模型自主完成了**低头搜寻 → 降躯干 → 绕桌缘抬臂 → 避碰自救 → 像素视差对准**，在第 57 步触及默认 500 万 Token 上限暂停时，**右臂夹爪已精准跨停在蓝色方块正上方（仅差最后“下降 2 cm → 合爪 → 抬起”3 步）**。  
> **最大工程发现**：全程 20 分 42 秒并非慢在大模型推理——大模型单次多模态视觉思考均值仅 **7.67 秒**（占 33.1%），高达 **56.7%（734.5 秒）** 竟是模型自主检测到 Gazebo 处于 `0.082×` 慢动作仿真后，自发调用了 **26 次 `sleep()`** 主动等待机械臂运动到位。

---

## 1. 完整复现过程视频与关键阶段演进

### 1.1 完整过程评估视频（79.7 秒，1440×810 H.264）

本视频由 `gz_01` 原始全部 **57 次工具调用**（55 组三路同步实拍相机图像 + 2 次安全拦截事件）与实时遥测日志合成，完整同屏展示 **上层大模型低频决策**（工具、参数、模型原始决策理由、自主 `sleep` 时长）与 **底层 100 Hz 机器人运控反馈**（三路相机、右臂侧视 2D 轨迹、关节状态、同步偏差与 Token 进度）：

- **仓储高清视频直达**：[`media/gz_01_full_replay.mp4`](../media/gz_01_full_replay.mp4)（`2.61 MB`，兼容 Windows 媒体播放器 / VLC / PPT 嵌入）
- **交互式逐帧审查面板（本地复现时可用）**：通过 `http://localhost:5500/ffw_codex/run_viewer.html` 输入 `gz_01` 并点击 *Follow run* 逐帧对比决策与执行。

### 1.2 六大关键里程碑双视角演进（头部主摄 + 右腕特写）

![gz_01 关键阶段双视角演进](../assets/gz_01_key_milestones.png)

---

## 2. 系统架构剖析：“大模型低频决策 × 机器人高频运控”

该研究最核心的工程范式，是将**开放世界语义理解与长程视觉规划**和**确定性高频实时运动控制**彻底解耦，中间由 **Harness 校验守卫层** 负责安全边界、坐标契约与传感器时间同步。

![三层解耦闭环架构](../assets/gz_01_architecture_diagram.png)

### 跨 3 个数量级的控制频率分层对照（全部来自本机配置与实测）

| 系统层级 | 核心组件 / 配置文件 | 运行频率 | 等效周期 | 职责边界 |
| :--- | :--- | :--- | :--- | :--- |
| **物理动力学层** | Gazebo Harmonic (`table.sdf`: `max_step_size=0.001`) | **1000 Hz** | `1.0 ms` | 刚体动力学、接触碰撞与摩擦力计算 |
| **关节伺服层** | `ros2_control` `controller_manager` (`update_rate: 100`) | **100 Hz** | `10.0 ms` | 双臂/头部/升降/底盘 6 组控制器闭环追踪 |
| **笛卡尔规划层** | Cyclo MoveL (`control_frequency: 100.0`) | **100 Hz** | `10.0 ms` | 末端直线插补、逆运动学求解与自碰撞防护 |
| **移动底盘层** | `config_gazebo.yaml` (`base.publish_hz: 20.0`) | **20 Hz** | `50.0 ms` | `/cmd_vel` 速度斜坡加减速与停止检测 |
| **多传感器同步** | `observation_guard_gazebo.py`（实测 55 帧） | 同步窗 `≤ 15 ms` | 实测均值 **`2.4 ms`**（最大 `5.0 ms`） | 对齐三路相机、`joint_states` 与 `odom` 时间戳 |
| **大模型决策层（理论 1×）** | GPT-6 Astra 纯视觉思考 (`7.67 s`) + 单步动作 | **~0.12 Hz** | 约 `8.5 s / 步` | 语义理解、视觉定位、避碰策略与长程规划 |
| **大模型决策层（本次实测）** | 含慢仿真自主 `sleep` (`57` 次调用 / `1242.4 s`) | **0.046 Hz**（有效动作 `0.022 Hz`） | `21.8 s / 次`（动作 `46.0 s / 次`） | 较底层 100 Hz 运控低 **~2,200× – 4,600×** |

---

## 3. 量化实验数据与核心瓶颈诊断

![gz_01 量化遥测与耗时拆解](../assets/gz_01_telemetry_charts.png)

### 3.1 `gz_01` 完整指标总表

| 评估维度 | 实测数值 | 备注与来源 |
| :--- | :--- | :--- |
| **总运行现实耗时** | `1242.4 s`（20 分 42 秒；Call 1–57 跨度 `1296.3 s`） | [`data/gz_01/result.json`](../data/gz_01/result.json) |
| **仿真世界经过时间** | `106.46 s`（`sim_s: 21.22 → 127.68 s`） | 平均实时因子 **`RTF = 0.0821×`**（慢动作约 12 倍） |
| **工具调用构成（共 57 次）** | `robot_observe`: 27 ｜ `robot_move`: 25 ｜ `robot_lift`: 2 ｜ `robot_start`: 1 ｜ `robot_head`: 1 ｜ `robot_base`: 1 | 实际下发动作 **27 次**，同步观测 **55 次** |
| **执行状态构成** | `observed`: 28 ｜ `stopped`: 26 ｜ `rejected`: 2 ｜ `arrived`: 1 | 几乎每次动作都在 4–5 秒后因慢仿真未走完而报 `stopped` |
| **安全守卫拦截（2 次）** | Call #10：`step 0.052 m > 0.05 m`；Call #11：`lift_joint position changed` | Harness 精确拦截，零误动风险 |
| **Token 消耗与成本** | 总计 `5,024,728`（缓存命中 `4,917,760`，**命中率 `98.03%`**；未缓存输入 `98,773`；输出 `8,195`；推理 `1,068`） | 按 API 定价估算约 `$6.315`（本次使用 ChatGPT 订阅授权） |
| **终止状态与任务进展** | `halted:token_limit`（触发默认 `5,000,000` Token 上限） | 右臂最终位置 `(0.444, -0.202, 0.937)`，夹爪正跨于蓝方块上方 |

### 3.2 三元耗时拆解：为什么跑了 20 分钟？

通过精确对齐 `calls/*_request.json`、`calls/*_result.json` 与 `rpc_in.jsonl` 中的全部事件时间戳，揭示了一个极易被表面现象掩盖的关键事实：

1. **模型自主 `sleep` 等待慢仿真：`734.5 s`（占 56.7%，共 26 次）**  
   因为本次 Gazebo 运行在 `0.082×` 慢动作下，一条仿真内需 2–3 秒的机械臂轨迹在现实世界需要约 25–35 秒才能走完。模型在几次试探后自主识别出这一规律，随后每次发完动作都会主动调用 Codex 内置 `sleep(20~30 s)` 等待机械臂挪到位再观测。
2. **大模型纯视觉思考 + 网络 API 往返：`429.3 s`（占 33.1%）**  
   扣除 `sleep` 后，**GPT-6 Astra 处理三路 RGB 图像并输出下一步精确 6D 末端位姿的实际延迟均值仅 `7.67 s`（中位数 `6.50 s`）**。
3. **Harness 校验 + 机器人运控等待：`132.5 s`（占 10.2%）**  
   单次 `robot_observe` 仅需 `0.08 s`，单次动作命令下发与到位检测均值 `4.51 s`。

> **慢仿真根因已通过日志实证定位**：实测检查容器内 `/root/.gz/rendering/ogre2.log` 显示 Ogre2 回退使用了 CPU 软渲染 `GL_RENDERER = llvmpipe (LLVM 20.1.2, 256 bits)` 与 `EGL_MESA_device_software`，且 `nvidia-smi` 显示 Gazebo 进程尚未挂载到 RTX 5070（`No running processes found`），导致 `gz sim server`（217% CPU）与 `gz sim gui`（201% CPU）纯靠 CPU 渲染 3 路相机与 GUI；同时 `table.sdf` 中声明了 `<max_step_size>0.001</max_step_size>` 与 `<real_time_update_rate>100</real_time_update_rate>`。若在下一轮排查启用 WSLg GPU 硬件渲染（或 `gui:=false`）并解除更新率限制、恢复接近 `1.0×` 实时运行，省去 26 次冗余 `sleep` 与观察后，推算同类任务耗时可降至 **约 5.5 分钟（~330 s）**。

---

## 4. 具身智能涌现行为深度观察（研究亮点）

抛开仿真速度因素，本次实验日志中记录到了 **6 项极具研究价值的具身涌现行为**（全部未经过任何特定任务的硬编码或微调）：

1. **主动视觉搜索（Active Perception）**：Call #01 初始头部平视仅见白墙，模型立即判断 *"Head view is above the workspace; tilt down to locate the blue block"*，主动下发 `robot_head(0.695 rad)` 低头锁定桌面蓝、黑方块。
2. **全身高度协同（Whole-body Coordination）**：Call #06–#13 自主决定降低躯干升降机构至 `lift_joint = -0.15 m`，扩展手臂在桌面高度的可达工作空间。
3. **物理接触察觉与避碰自救（Collision-aware Recovery）**：Call #45 时，模型结合运控返回的 `stopped .042 m short` 与头部画面判断 *"head shows lower finger close to near tabletop"*，推测手指擦近桌缘受阻，立刻向上抬臂 `3.4 cm`（`z: 0.894 → 0.928 m`），确认手指下方出现清晰间隙后再恢复前伸。
4. **零深度纯 RGB 像素追踪与视差测距（Visual Servoing & Parallax）**：虽然模型没有任何深度图、相机标定矩阵或 OpenCV 检测脚本，但它从 Call #39 蓝方块刚进入右腕画面边缘起，纯靠视觉连续追踪像素坐标 `(280,52) → (227,73) → (183,96) → (150,109)`，并利用相邻帧视差（*Parallax*）反推方块三维坐标约为 `x≈0.50, y≈-0.20`，最终精准将张开的夹爪对齐到方块正上方。
5. **在线系统辨识与持久化工作记忆（Online System ID & Memory）**：在 Codex 沙盒中，模型自发调用终端命令编写并更新了工作笔记 [`data/gz_01/agent/notes/NOTES.md`](../data/gz_01/agent/notes/NOTES.md)，原文摘录如下：
   > *"Most commands report stopped early, settle over ~25s wall; some remain short. Suspected near-table contact at EE z .887; raised to .935 and now head shows gap. Blue cube wrist center (280,52), about 70px wide. Estimated cube x~.50, y~-.20; table height still uncertain likely ~.88-.90. Base attempt no progress; did not repeat."*
6. **失败策略快速止损**：Call #22 曾尝试驱动底盘 `robot_base` 靠近桌子，发现未产生位移且图像无变化后，立刻在笔记中标记 *"Base attempt no progress; did not repeat"*，不再浪费步数死磕底盘，转而继续利用右臂可达空间逼近。

---

## 5. 研究范式综合评估：优势、边界与对比

### 5.1 与主流端到端 VLA（Vision-Language-Action）路线的本质差异

| 评估维度 | 本路线：通用大模型低频决策 + 工具契约 + 高频传统运控 | 端到端 VLA（如 RT-2 / OpenVLA / π0 等） |
| :--- | :--- | :--- |
| **零样本泛化与推理深度** | **极强**（可做多步逻辑推理、写笔记、跨视角视差估计、异常自救） | 依赖遥操作示教数据分布，复杂长程异常恢复较弱 |
| **数据与训练门槛** | **几乎为零**（无需采集海量真机轨迹，只需写清晰的工具契约与安全 Harness） | 需要大规模高质量遥操作数据采集与模型微调 |
| **闭环频率与实时性** | **极低（~0.1–0.2 Hz）**，受限于云端 API 延迟与高分辨率多图推理 | **中高（5–50 Hz）**，本地 GPU 可实现高频连续视觉伺服 |
| **动作安全与可审计性** | **高**（每步有自然语言理由 + 硬限幅校验 + 传统底层控制器保障） | 黑盒神经网络输出动作块，安全边界较难形式化保证 |
| **推理成本** | **较高**（单次长程任务数百万上下文 Token，高度依赖 Prompt Cache 降低成本） | 边际推理成本极低（本地单卡即可持续运行） |
| **最适用场景** | 开放语义、非结构化长程规划、多工具/多部件协调、慢速准静态操作 | 高动态交互、灵巧手精细力控、高速抓取与工业节拍任务 |

### 5.2 本次复现暴露的 4 项关键研究局限

1. **单步限幅过细导致“步数碎片化”与上下文膨胀**：默认 `limits.max_step_m = 0.05 m` 让机器人从身侧伸到桌前 45 cm 处至少需要十余次独立 `robot_move`，每步附带 3 张高清图片迅速推高上下文长度至 500 万 Token（尽管缓存命中率达 98.03%，但上下文窗口与总预算压力依然显著）；且本次模型未充分利用 `robot_execute_plan` 在开阔空间内打包连续 3–5 步移动。
2. **动作执行期“盲区”风险**：从发令到轨迹执行完毕期间大模型无法实时看图（开环执行），若环境动态变化或发生未预期碰撞，完全依赖底层控制器限力/避障与急停。
3. **无深度/无力觉导致 Z 轴高度估计依赖保守试探**：正如模型在 `NOTES.md` 中所写 *"table height still uncertain likely ~.88-.90"*，纯 RGB 很难精确判断桌面与方块高度，导致前期在桌缘附近花费大量步数小心试探。
4. **对仿真器/硬件时序一致性高度敏感**：当底层执行时间超过 Harness 固定墙上时间超时窗口时，极易产生大量 `stopped` 假停顿，诱发额外观察轮次，放大时间与 Token 成本。

---

## 6. 下一轮实验建议（`gz_02` 提速与完整抓起验证）

1. **解除 Gazebo 软渲染与慢仿真瓶颈（最优先）**：排查启用容器内 WSLg D3D12/NVIDIA 硬件渲染（或采用 `gui:=false` 无头渲染配合网页 Live Viewer），同时调整 `table.sdf` 中的 `<real_time_update_rate>`，将 RTF 恢复至接近 `1.0×` 实时后重跑 `gz_02`。
2. **适度放宽自由空间步幅或引导使用多步计划**：在纯仿真评估中对比 `max_step_m: 0.05` vs `0.08–0.10`，观察完成同一抓取任务的耗时与 Token 降幅。
3. **横向评测复杂官方世界**：在提速后依次测试 `articulated_cabinet`（开抽屉取物）与 `pick_and_deliver`（底盘移动 + 跨房间抓放），全面评估长程任务成功率。

---

## 7. 复现环境与原始数据索引

- **宿主机与硬件**：Windows 11 Pro (`10.0.26200`) ｜ Intel Core i9-14900HX (24C/32T) ｜ 32 GB RAM ｜ NVIDIA RTX 5070 Laptop GPU (8 GB, Driver 582.05)
- **容器与适配配置**：`robotis/ai-worker:2.3.1`（ROS 2 Jazzy + Gazebo Harmonic + Cyclo）｜ [`configs/docker-compose.wsl.yml`](../configs/docker-compose.wsl.yml) ｜ [`configs/.wslconfig.example`](../configs/.wslconfig.example) ｜ [`configs/start_sim.sh`](../configs/start_sim.sh)
- **Codex 环境**：`codex-cli 0.171.0` ｜ 隔离目录 `/root/.codex_robot` ｜ ChatGPT OAuth 授权
- **原始实验档案**：
  - 汇总结果：[`data/gz_01/result.json`](../data/gz_01/result.json)
  - 遥测统计：[`data/gz_01/gz01_metrics.json`](../data/gz_01/gz01_metrics.json)
  - 完整时序历史：[`data/gz_01/public/history.jsonl`](../data/gz_01/public/history.jsonl)
  - 模型自建工作记忆：[`data/gz_01/agent/notes/NOTES.md`](../data/gz_01/agent/notes/NOTES.md)
  - 完整回放视频：[`media/gz_01_full_replay.mp4`](../media/gz_01_full_replay.mp4)
