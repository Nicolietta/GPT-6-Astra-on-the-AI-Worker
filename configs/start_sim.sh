#!/bin/bash
set -e

WORLD="${1:-table}"
GUI="${2:-true}"
RESTART="${3:-false}"
LOG_DIR="/tmp/ai_worker_logs"
mkdir -p "$LOG_DIR"

source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ROS_DOMAIN_ID=30
export DISPLAY=:0
export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir
export QT_X11_NO_MITSHM=1

# Enable WSL2 Mesa D3D12 hardware GPU acceleration on NVIDIA RTX 5070
export LD_LIBRARY_PATH="/usr/lib/wsl/lib:${LD_LIBRARY_PATH:-}"
export GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA

# Ensure WSLg X11 socket symlink exists
if [ ! -S /tmp/.X11-unix/X0 ] && [ -d /mnt/wslg/.X11-unix ]; then
    rm -rf /tmp/.X11-unix
    ln -s /mnt/wslg/.X11-unix /tmp/.X11-unix
fi

# Clean up any leftover login process
pkill -f "codex login" 2>/dev/null || true

if [ "$RESTART" = "restart" ] || [ "$RESTART" = "true" ]; then
    echo "[0/3] Stopping existing ROS 2 / Gazebo / Cyclo / Zenoh processes..."
    pkill -f "gz sim|ffw_sg2_follower|ai_worker_controller|ai_worker_movel|cyclo_teleoperation|parameter_bridge|dual_laser_merger|robot_state_publisher|rmw_zenohd" 2>/dev/null || true
    sleep 2
    rm -f /root/.gz/rendering/ogre2.log 2>/dev/null || true
fi

# 1. Zenoh
if ! pgrep -f rmw_zenohd >/dev/null 2>&1; then
    echo "[1/3] Starting Zenoh..."
    nohup ros2 run rmw_zenoh_cpp rmw_zenohd > "$LOG_DIR/1_zenoh.log" 2>&1 < /dev/null &
    sleep 2
else
    echo "[1/3] Zenoh already running."
fi

# 2. Gazebo + Cameras (GPU accelerated)
WORLD_PATH="$WORLD"
if [[ "$WORLD" != /* ]]; then
    WORLD_PATH="/root/ros2_ws/src/ai_worker/ffw_bringup/worlds/${WORLD}"
fi

if ! pgrep -f "ffw_sg2_follower_ai_gazebo" >/dev/null 2>&1; then
    echo "[2/3] Starting Gazebo (world=${WORLD_PATH}, gui=${GUI}, use_cam=true, rviz=false, GALLIUM_DRIVER=d3d12)..."
    nohup ros2 launch ffw_bringup ffw_sg2_follower_ai_gazebo.launch.py \
        world:="${WORLD_PATH}" \
        gui:="${GUI}" \
        use_cam:=true \
        rviz:=false > "$LOG_DIR/2_gazebo.log" 2>&1 < /dev/null &
else
    echo "[2/3] Gazebo already running."
fi

# Wait up to 30s for Gazebo camera topics and joint_states
echo "Waiting for Gazebo topics (/joint_states & 3 camera image streams)..."
READY=0
for i in $(seq 1 30); do
    TOPICS=$(ros2 topic list 2>/dev/null || true)
    if echo "$TOPICS" | grep -q "^/joint_states$" && \
       echo "$TOPICS" | grep -q "^/head_camera/image$" && \
       echo "$TOPICS" | grep -q "^/wrist_left_camera/image$" && \
       echo "$TOPICS" | grep -q "^/wrist_right_camera/image$"; then
        READY=1
        echo "Gazebo topics ready after ${i}s!"
        break
    fi
    sleep 1
done

if [ "$READY" -ne 1 ]; then
    echo "WARNING: Timed out waiting for Gazebo topics after 30s."
fi

# 3. Cyclo motion controller
if ! pgrep -f "ai_worker_controller.launch.py" >/dev/null 2>&1; then
    echo "[3/3] Starting Cyclo motion controller (movel)..."
    nohup ros2 launch cyclo_motion_controller_ros ai_worker_controller.launch.py \
        controller_type:=movel > "$LOG_DIR/3_cyclo.log" 2>&1 < /dev/null &
    sleep 4
else
    echo "[3/3] Cyclo already running."
fi

echo "=== Ogre2 Renderer Check ==="
grep -E "GL_VENDOR|GL_RENDERER|GL_VERSION|EGL Device" /root/.gz/rendering/ogre2.log 2>/dev/null | tail -n 10 || true

echo "=== Running Processes ==="
ps -eo pid,pcpu,pmem,comm --sort=-pcpu | head -n 10
