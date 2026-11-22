#!/bin/bash
set -e

WORLD="${1:-table}"
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

# Ensure WSLg X11 socket symlink exists
if [ ! -S /tmp/.X11-unix/X0 ] && [ -d /mnt/wslg/.X11-unix ]; then
    rm -rf /tmp/.X11-unix
    ln -s /mnt/wslg/.X11-unix /tmp/.X11-unix
fi

# Clean up any leftover login process
pkill -f "codex login" 2>/dev/null || true

# 1. Zenoh
if ! pgrep -f rmw_zenohd >/dev/null 2>&1; then
    echo "[1/3] Starting Zenoh..."
    nohup ros2 run rmw_zenoh_cpp rmw_zenohd > "$LOG_DIR/1_zenoh.log" 2>&1 < /dev/null &
    sleep 2
else
    echo "[1/3] Zenoh already running."
fi

# 2. Gazebo + Cameras
if ! pgrep -f "ffw_sg2_follower_ai_gazebo" >/dev/null 2>&1; then
    echo "[2/3] Starting Gazebo (world=${WORLD}, use_cam=true, rviz=false)..."
    nohup ros2 launch ffw_bringup ffw_sg2_follower_ai_gazebo.launch.py \
        world:="/root/ros2_ws/src/ai_worker/ffw_bringup/worlds/${WORLD}" \
        use_cam:=true \
        rviz:=false > "$LOG_DIR/2_gazebo.log" 2>&1 < /dev/null &
else
    echo "[2/3] Gazebo already running."
fi

# Wait up to 25s for Gazebo camera topics and joint_states
echo "Waiting for Gazebo topics (/joint_states & /head_camera/image)..."
READY=0
for i in $(seq 1 25); do
    TOPICS=$(ros2 topic list 2>/dev/null || true)
    if echo "$TOPICS" | grep -q "^/joint_states$" && echo "$TOPICS" | grep -q "^/head_camera/image$"; then
        READY=1
        echo "Gazebo topics ready after ${i}s!"
        break
    fi
    sleep 1
done

# 3. Cyclo motion controller
if ! pgrep -f "ai_worker_controller.launch.py" >/dev/null 2>&1; then
    echo "[3/3] Starting Cyclo motion controller (movel)..."
    nohup ros2 launch cyclo_motion_controller_ros ai_worker_controller.launch.py \
        controller_type:=movel > "$LOG_DIR/3_cyclo.log" 2>&1 < /dev/null &
    sleep 4
else
    echo "[3/3] Cyclo already running."
fi

echo "=== Running Processes ==="
ps -ef | grep -E "rmw_zenohd|gz sim|ai_worker_controller" | grep -v grep | head -n 12

echo "=== Key ROS 2 Topics ==="
ros2 topic list 2>/dev/null | grep -E "head_camera/image$|wrist_left_camera/image$|wrist_right_camera/image$|joint_states$|goal_move$|cmd_vel$" || true

echo "=== 2_gazebo.log (tail 15) ==="
tail -n 15 "$LOG_DIR/2_gazebo.log" || true

echo "=== 3_cyclo.log (tail 15) ==="
tail -n 15 "$LOG_DIR/3_cyclo.log" || true
