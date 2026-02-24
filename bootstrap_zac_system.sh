#!/bin/bash
set -euo pipefail

# --- Config ---
LITTLEZAC_USER="littlezac"
ACTIONS_USER="actions"
REPO_URL="https://github.com/robtandy/zac.git"
REPO_BRANCH="main"
LITTLEZAC_REPO_DIR="/home/$LITTLEZAC_USER/zac-mono"
ACTIONS_REPO_DIR="/home/$ACTIONS_USER/zac-mono"
ACTION_SYSTEM_PORT=8000
GATEWAY_PORT=8001

# --- Idempotent User Creation ---
create_user() {
    local user=$1
    if ! id "$user" &>/dev/null; then
        echo "Creating user: $user"
        useradd -m -s /bin/bash "$user"
    else
        echo "User $user already exists"
    fi
}

# --- Idempotent Repo Checkout ---
checkout_repo() {
    local user=$1
    local repo_dir=$2
    if [[ ! -d "$repo_dir" ]]; then
        echo "Checking out repo for $user"
        sudo -u "$user" git clone --branch "$REPO_BRANCH" "$REPO_URL" "$repo_dir"
    else
        echo "Repo already exists for $user at $repo_dir"
        sudo -u "$user" git -C "$repo_dir" pull
    fi
}

# --- Create Log Directory ---
create_log_dir() {
    local user=$1
    local log_dir="/home/$user/logs"
    if [[ ! -d "$log_dir" ]]; then
        echo "Creating log directory for $user"
        sudo -u "$user" mkdir -p "$log_dir"
    else
        echo "Log directory already exists for $user"
    fi
}

# --- Install Dependencies ---
install_dependencies() {
    local user=$1
    local repo_dir=$2
    echo "Installing dependencies for $user"
    sudo -u "$user" bash -c "cd $repo_dir && uv sync"
}

# --- Start Action System Server ---
start_action_system() {
    local user=$1
    local repo_dir=$2
    local log_file="/home/$user/logs/action-system.log"
    echo "Starting action-system server as $user"
    sudo -u "$user" bash -c "cd $repo_dir && source .venv/bin/activate && zac actions-server --port $ACTION_SYSTEM_PORT" > "$log_file" 2>&1 &
    echo "Action-system server logs: $log_file"
}

# --- Start Gateway ---
start_gateway() {
    local user=$1
    local repo_dir=$2
    local log_file="/home/$user/logs/gateway.log"
    echo "Starting gateway as $user"
    sudo -u "$user" bash -c "cd $repo_dir && source .venv/bin/activate && zac gateway start --port $GATEWAY_PORT" > "$log_file" 2>&1 &
    echo "Gateway logs: $log_file"
}

# --- Main ---
create_user "$LITTLEZAC_USER"
create_user "$ACTIONS_USER"

checkout_repo "$LITTLEZAC_USER" "$LITTLEZAC_REPO_DIR"
checkout_repo "$ACTIONS_USER" "$ACTIONS_REPO_DIR"

create_log_dir "$LITTLEZAC_USER"
create_log_dir "$ACTIONS_USER"

install_dependencies "$LITTLEZAC_USER" "$LITTLEZAC_REPO_DIR"
install_dependencies "$ACTIONS_USER" "$ACTIONS_REPO_DIR"

start_action_system "$ACTIONS_USER" "$ACTIONS_REPO_DIR"
start_gateway "$LITTLEZAC_USER" "$LITTLEZAC_REPO_DIR"

echo "Setup complete!"
echo "Action-system server: http://localhost:$ACTION_SYSTEM_PORT"
echo "Gateway: http://localhost:$GATEWAY_PORT"