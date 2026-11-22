# GPT-6 Astra × ROBOTIS AI Worker — Windows 11 (WSL 2 + Docker) 复现与 GPU 提速 A/B 研究评估

> 基于 ROBOTIS 官方开源项目 [`ROBOTIS-GIT/ai_worker`](https://github.com/ROBOTIS-GIT/ai_worker/tree/feature-codex)（`feature-codex` 分支）及技术文章 [*GPT-6 Astra on the AI Worker*](https://docs.robotis.com/technical-story/ai-worker-codex/) 在 **Windows 11 消费级笔记本** 上的完整工程复现、RTX 5070 硬件渲染提速改造与 `gz_01` vs `gz_02` 严格 A/B 对照评估。

---

## 核心成果总览（`gz_01` 基线 → `gz_02` 加速成功抓取）

- **全链路跑通**：在 Windows 11 + WSL 2 (`Ubuntu-24.04`) + Docker Desktop 环境下成功打通 **GPT-6 Astra (Codex App Server) → Harness 校验守卫 → ROS 2 (`rmw_zenoh_cpp`) / Cyclo MoveL → Gazebo Harmonic** 完整具身闭环。
- **定位并根治慢仿真瓶颈**：基线 `gz_01` 因容器内 Ogre2 回退为 CPU 软渲染（`llvmpipe`），RTF 仅 `0.0821×`，导致模型被迫调用 26 次 `sleep()`，在耗时 `1242.4 s` / `5.02M` Tokens 后于方块正上方暂停。通过注入 **WSL 2 Mesa D3D12** 环境变量启用 RTX 5070 硬件渲染，RTF 跃升至 **`0.8359×`（10.2× 加速）**！
- **完整抓起蓝色方块（`task_complete`）**：加速后的对照组 `gz_02` 在完全保持相同模型配置与步幅限制下，**`sleep()` 与冗余 `robot_observe` 均降至 0 次**，总耗时腰斩至 **`610.1 s`（-50.9%）**，Token 耗费直降 **`2,044,902`（-59.3%）**，并在经历两次全闭滑移后主动切换为**两段式温和半闭策略（`0.45 → 0.68`）**稳稳抓起蓝色方块并举离桌面！

### `gz_01` vs `gz_02` 核心 A/B 指标一览

| 评估指标 | `gz_01`（CPU `llvmpipe` 软渲染） | `gz_02`（RTX 5070 `D3D12` 加速） | 对比变化 |
| :--- | :--- | :--- | :--- |
| **任务最终结局** | `halted:token_limit`（未抓起） | **`task_complete`（成功抓起并悬空举起）** | **0% → 100% 闭环** |
| **平均实时因子 (RTF)** | `0.0821×` | **`0.8359×`** | **+10.2× 提速** |
| **现实总耗时 (`elapsed_s`)** | `1242.4 s`（20 分 42 秒） | **`610.1 s`（10 分 10 秒）** | **-50.9%** |
| **自主 `sleep()` / 冗余 `observe`** | `26` 次（`734.5 s`） / `27` 次 | **`0` 次（`0.0 s`） / `0` 次** | **彻底清零** |
| **单步一次到位 (`arrived`)** | `1` 次 | **`26` 次**（另有 `2` 次多步计划完成） | **26× 提升** |
| **调用次数 / 物理动作数** | `57` 次调用 / `27` 次动作 | **`38` 次调用 / `43` 次动作**（含 `5` 次批处理） | 少 33% 调用，多做 59% 动作 |
| **Token 总消耗 / 估算成本** | `5,024,728` / `$6.315` | **`2,044,902` / `$3.124`** | **-59.3% / -50.5%** |

---

## 仓库目录结构

| 目录 / 文件 | 内容说明 |
| :--- | :--- |
| [`report/gz_01_evaluation_report.md`](report/gz_01_evaluation_report.md) | **v2.0 完整 Markdown 评估报告**（涵盖 `gz_01` vs `gz_02` A/B 对照、D3D12 提速方法、涌现行为与 VLA 对比） |
| [`report/gz_01_evaluation_report.docx`](report/gz_01_evaluation_report.docx) | **v2.0 排版完整的 Word 评估报告**（含 5 张高清图表、11 张数据表及双实验实测轨迹附录） |
| [`media/gz_02_full_replay.mp4`](media/gz_02_full_replay.mp4) | **`gz_02` 加速成功抓起全过程视频**（61.6 s · 1440×810 H.264，1.76 MB） |
| [`media/gz_01_full_replay.mp4`](media/gz_01_full_replay.mp4) | **`gz_01` 基线慢仿真对比视频**（79.7 s · 1440×810 H.264，2.61 MB） |
| [`assets/`](assets/) | A/B 对照四联图、`gz_02`/`gz_01` 六阶段演进拼图、三层解耦架构图及基线遥测图 |
| [`configs/`](configs/) | Windows 11 WSL 2 适配配置（`.wslconfig.example`、`docker-compose.wsl.yml`、含 **RTX 5070 D3D12 加速** 的 `start_sim.sh`） |
| [`scripts/`](scripts/) | `gz_01`/`gz_02` 遥测分析、图表与视频合成、Word 报告自动生成 Python 脚本 |
| [`data/gz_02/`](data/gz_02/) & [`data/gz_01/`](data/gz_01/) | 脱敏后的双实验核心档案（`result.json`、`metrics.json`、`NOTES.md`、`rollout/` 及全部三路 RGB 同步观测图像） |

---

## 可视化预览

### 1. `gz_01` vs `gz_02` A/B 对照实证四联图

![gz_01 vs gz_02 A/B 对照四联图](assets/gz_02_ab_comparison_charts.png)

### 2. `gz_02`（RTX 5070 加速）关键阶段演进：从抓滑失误到稳健抓起

![gz_02 关键阶段演进](assets/gz_02_key_milestones.png)

### 3. “大模型低频决策 × 机器人高频运控”三层解耦架构

![三层解耦架构图](assets/gz_01_architecture_diagram.png)

---

## Windows 11 + RTX GPU 快速复现指南

### 1. 基础环境（Windows 宿主机）
- 安装 **WSL 2 (`Ubuntu-24.04`)** 与 **Docker Desktop**（开启 *WSL 2 backend*、*Ubuntu-24.04 WSL Integration* 与 *Enable host networking*）。
- 参考 [`configs/.wslconfig.example`](configs/.wslconfig.example) 配置 `%USERPROFILE%\.wslconfig` 后执行 `wsl --shutdown` 生效（开启 `WSLg`、`mirrored` 网络与 `autoProxy`）。

### 2. 在 WSL 2 中拉取仓库并启动适配容器
```bash
mkdir -p ~/workspace && cd ~/workspace
git clone -b feature-codex https://github.com/ROBOTIS-GIT/ai_worker.git
# 将本仓库 configs/docker-compose.wsl.yml 与 configs/start_sim.sh 放到 ~/workspace/ai_worker/docker/
cd ~/workspace/ai_worker/docker && mkdir -p workspace
docker compose -f docker-compose.wsl.yml up -d
```

### 3. 容器内安装与登录 Codex CLI
```bash
docker exec -it ai_worker bash
mkdir -p /root/.codex_robot && chmod 700 /root/.codex_robot
curl -fsSL https://chatgpt.com/codex/install.sh -o /tmp/codex-install.sh
CODEX_HOME=/root/.codex_robot CODEX_INSTALL_DIR=/usr/local/bin sh /tmp/codex-install.sh
CODEX_HOME=/root/.codex_robot codex login
```

### 4. 启动 RTX GPU 加速仿真并下达自然语言任务
```bash
# 容器内一键启动 Zenoh + Gazebo (开启 D3D12 GPU 加速) + Cyclo MoveL
/root/ros2_ws/src/ai_worker/docker/start_sim.sh table true restart

# 可选确认 Ogre2 是否已命中 NVIDIA D3D12 硬件加速：
grep GL_RENDERER /root/.gz/rendering/ogre2.log

# 提交自然语言抓取任务
source /opt/ros/jazzy/setup.bash && source /root/ros2_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_zenoh_cpp ROS_DOMAIN_ID=30
cd /root/ros2_ws/src/ai_worker/ffw_codex
python3 run_codex_gazebo.py --task "pick up the blue block" --run-id gz_02
```

---

## 致谢与版权说明
- 上游机器人仿真与 Harness 接口源码归属于 [`ROBOTIS-GIT/ai_worker`](https://github.com/ROBOTIS-GIT/ai_worker/tree/feature-codex)（Apache-2.0 License）。
- 本仓库仅归档 Windows 11 / WSL 2 适配配置、量化遥测分析脚本、评估报告及 `gz_01` / `gz_02` 复现实验轨迹数据（不含任何账号凭证或敏感认证文件）。
