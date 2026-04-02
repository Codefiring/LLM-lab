#!/usr/bin/env bash
set -euo pipefail

LOGIN_HOST="202.20.183.100"
DEFAULT_ENV_ACTIVATE="source envs/vllm-qwen/bin/activate"
DEFAULT_TMUX_RAY="ray"
DEFAULT_TMUX_VLLM="vllm"
DEFAULT_RAY_PORT="6379"

HEAD_USER=""
WORKER_USER=""
HEAD_GPU=""
WORKER_GPU=""

ENV_ACTIVATE="${DEFAULT_ENV_ACTIVATE}"
TMUX_RAY="${DEFAULT_TMUX_RAY}"
TMUX_VLLM="${DEFAULT_TMUX_VLLM}"
RAY_PORT="${DEFAULT_RAY_PORT}"

ACTION="${1:-}"
if [[ -z "${ACTION}" ]]; then
  echo "ERROR: missing action"
  exit 1
fi
shift || true

usage() {
  cat <<EOF
Usage:
  $0 <action> [options]

Actions:
  start-head
  start-worker
  start-vllm
  start-all
  status
  stop-all

Options:
  --head-user <user>         Head 登录账号，例如 hxiang.huang
  --worker-user <user>       Worker 登录账号，例如 meng01.huang
  --login-host <host>        登录跳板机，默认 ${LOGIN_HOST}
  --env-activate <cmd>       环境激活命令，默认: ${DEFAULT_ENV_ACTIVATE}
  --ray-port <port>          Ray 端口，默认 ${DEFAULT_RAY_PORT}
  --tmux-ray <name>          Ray tmux 会话名，默认 ${DEFAULT_TMUX_RAY}
  --tmux-vllm <name>         vLLM tmux 会话名，默认 ${DEFAULT_TMUX_VLLM}

Examples:
  $0 start-all --head-user hxiang.huang --worker-user meng01.huang
  $0 start-head --head-user hxiang.huang
  $0 start-worker --head-user hxiang.huang --worker-user meng01.huang
  $0 start-vllm --head-user hxiang.huang
  $0 status --head-user hxiang.huang --worker-user meng01.huang
  $0 stop-all --head-user hxiang.huang --worker-user meng01.huang
EOF
}

log() {
  echo "[$(date '+%F %T')] $*"
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --head-user)
      HEAD_USER="${2:-}"; shift 2 ;;
    --worker-user)
      WORKER_USER="${2:-}"; shift 2 ;;
    --login-host)
      LOGIN_HOST="${2:-}"; shift 2 ;;
    --env-activate)
      ENV_ACTIVATE="${2:-}"; shift 2 ;;
    --ray-port)
      RAY_PORT="${2:-}"; shift 2 ;;
    --tmux-ray)
      TMUX_RAY="${2:-}"; shift 2 ;;
    --tmux-vllm)
      TMUX_VLLM="${2:-}"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      die "unknown argument: $1" ;;
  esac
done

require_head() {
  [[ -n "${HEAD_USER}" ]] || die "--head-user is required"
}

require_worker() {
  [[ -n "${WORKER_USER}" ]] || die "--worker-user is required"
}

run_login_ssh() {
  local login_user="$1"
  local remote_cmd="$2"

  ssh -T "${login_user}@${LOGIN_HOST}" bash <<EOF
export TMOUT=0
set -euo pipefail
${remote_cmd}
EOF
}

run_nested_ssh() {
  local login_user="$1"
  local gpu_node="$2"
  local remote_cmd="$3"

  ssh -T "${login_user}@${LOGIN_HOST}" bash <<EOF
export TMOUT=0
set -euo pipefail
ssh -T "${gpu_node}" bash <<'INNER_EOF'
export TMOUT=0
set -euo pipefail
${remote_cmd}
INNER_EOF
EOF
}

detect_gpu_node() {
  local login_user="$1"

  log "Detecting GPU node for ${login_user} via phd list -r ..."

  local gpu_node
  gpu_node="$(
    run_login_ssh "${login_user}" '
if ! command -v phd >/dev/null 2>&1; then
  echo "ERROR: phd command not found" >&2
  exit 1
fi

phd list -r | awk '\''/Running[[:space:]]+hgpu[0-9]+/ {print $NF; exit}'\''
' | tail -n 1
  )"

  [[ -n "${gpu_node}" ]] || die "failed to detect GPU node for ${login_user}"
  echo "${gpu_node}"
}

init_nodes_once() {
  require_head

  if [[ -z "${HEAD_GPU}" ]]; then
    HEAD_GPU="$(detect_gpu_node "${HEAD_USER}")"
    log "HEAD GPU node: ${HEAD_GPU}"
  fi

  if [[ -n "${WORKER_USER}" && -z "${WORKER_GPU}" ]]; then
    WORKER_GPU="$(detect_gpu_node "${WORKER_USER}")"
    log "WORKER GPU node: ${WORKER_GPU}"
  fi
}

check_remote_basics() {
  local login_user="$1"
  local gpu_node="$2"

  run_nested_ssh "${login_user}" "${gpu_node}" '
command -v tmux >/dev/null 2>&1 || { echo "tmux not found"; exit 1; }
command -v bash >/dev/null 2>&1 || { echo "bash not found"; exit 1; }
echo "basic check ok on $(hostname)"
'
}

kill_tmux_if_exists() {
  local session_name="$1"
  cat <<EOF
if tmux has-session -t ${session_name} 2>/dev/null; then
  tmux kill-session -t ${session_name}
fi
EOF
}

ray_stop_if_exists() {
  cat <<'EOF'
if command -v ray >/dev/null 2>&1; then
  ray stop -f >/dev/null 2>&1 || true
fi
EOF
}

get_head_ip() {
  run_nested_ssh "${HEAD_USER}" "${HEAD_GPU}" '
IP=$(hostname -I | awk "{print \$1}")
if [[ -z "${IP}" ]]; then
  echo "failed to get head IP" >&2
  exit 1
fi
echo "${IP}"
' | tail -n 1
}

start_head() {
  log "Starting Ray head on ${HEAD_GPU}"
  check_remote_basics "${HEAD_USER}" "${HEAD_GPU}"

  run_nested_ssh "${HEAD_USER}" "${HEAD_GPU}" "
$(kill_tmux_if_exists "${TMUX_RAY}")
$(ray_stop_if_exists)

tmux new-session -d -s ${TMUX_RAY}
tmux send-keys -t ${TMUX_RAY} 'export TMOUT=0' C-m
tmux send-keys -t ${TMUX_RAY} '${ENV_ACTIVATE}' C-m
tmux send-keys -t ${TMUX_RAY} 'ray start --block --head --port=${RAY_PORT}' C-m

sleep 5
echo '===== head session ====='
tmux list-sessions
echo '===== head logs ====='
tmux capture-pane -pt ${TMUX_RAY} -S -50
"
}

start_worker() {
  require_worker

  local head_ip
  head_ip="$(get_head_ip)"
  log "Head IP detected: ${head_ip}"

  log "Starting Ray worker on ${WORKER_GPU}"
  check_remote_basics "${WORKER_USER}" "${WORKER_GPU}"

  run_nested_ssh "${WORKER_USER}" "${WORKER_GPU}" "
$(kill_tmux_if_exists "${TMUX_RAY}")
$(ray_stop_if_exists)

tmux new-session -d -s ${TMUX_RAY}
tmux send-keys -t ${TMUX_RAY} 'export TMOUT=0' C-m
tmux send-keys -t ${TMUX_RAY} '${ENV_ACTIVATE}' C-m
tmux send-keys -t ${TMUX_RAY} 'ray start --address=${head_ip}:${RAY_PORT}' C-m

sleep 5
echo '===== worker session ====='
tmux list-sessions
echo '===== worker logs ====='
tmux capture-pane -pt ${TMUX_RAY} -S -50
"
}

start_vllm() {
  log "Starting vLLM on ${HEAD_GPU}"
  check_remote_basics "${HEAD_USER}" "${HEAD_GPU}"

  run_nested_ssh "${HEAD_USER}" "${HEAD_GPU}" "
$(kill_tmux_if_exists "${TMUX_VLLM}")

cat > /tmp/start_vllm.sh <<EOF_VLLM
#!/usr/bin/env bash
set -euo pipefail

echo '[vLLM] starting...'
export TMOUT=0

${ENV_ACTIVATE}

# =========================
# 在这里修改你的 vLLM 启动命令
# =========================

# 示例:
# CUDA_VISIBLE_DEVICES=0,1 \\
# vllm serve /data/Qwen2.5-72B \\
#   --tensor-parallel-size 2 \\
#   --gpu-memory-utilization 0.90 \\
#   --host 0.0.0.0 \\
#   --port 8000

vllm serve /data/model \
  --host 0.0.0.0 \
  --port 8000

EOF_VLLM

chmod +x /tmp/start_vllm.sh

tmux new-session -d -s ${TMUX_VLLM}
tmux send-keys -t ${TMUX_VLLM} 'bash /tmp/start_vllm.sh' C-m

sleep 5
echo '===== vllm session ====='
tmux list-sessions
echo '===== vllm logs ====='
tmux capture-pane -pt ${TMUX_VLLM} -S -50
"
}

status_one_node() {
  local login_user="$1"
  local gpu_node="$2"
  local node_tag="$3"

  log "Checking status on ${node_tag}: ${gpu_node}"
  run_nested_ssh "${login_user}" "${gpu_node}" "
echo '===== host ====='
hostname
echo '===== tmux sessions ====='
tmux list-sessions || true
echo '===== ray session logs ====='
tmux capture-pane -pt ${TMUX_RAY} -S -30 2>/dev/null || echo 'no ray session'
echo '===== vllm session logs ====='
tmux capture-pane -pt ${TMUX_VLLM} -S -30 2>/dev/null || echo 'no vllm session'
"
}

status_all() {
  status_one_node "${HEAD_USER}" "${HEAD_GPU}" "head"

  if [[ -n "${WORKER_USER}" ]]; then
    status_one_node "${WORKER_USER}" "${WORKER_GPU}" "worker"
  fi
}

stop_one_node() {
  local login_user="$1"
  local gpu_node="$2"

  run_nested_ssh "${login_user}" "${gpu_node}" "
if tmux has-session -t ${TMUX_VLLM} 2>/dev/null; then
  tmux kill-session -t ${TMUX_VLLM}
fi

if tmux has-session -t ${TMUX_RAY} 2>/dev/null; then
  tmux kill-session -t ${TMUX_RAY}
fi

if command -v ray >/dev/null 2>&1; then
  ray stop -f >/dev/null 2>&1 || true
fi

echo 'stopped on' \$(hostname)
"
}

stop_all() {
  stop_one_node "${HEAD_USER}" "${HEAD_GPU}"

  if [[ -n "${WORKER_USER}" ]]; then
    stop_one_node "${WORKER_USER}" "${WORKER_GPU}"
  fi
}

start_all() {
  require_worker

  start_head
  start_worker
  start_vllm

  local head_ip
  head_ip="$(get_head_ip)"

  cat <<EOF

========================================
Done.
Head node: ${HEAD_GPU}
Worker node: ${WORKER_GPU}
Head address: ${head_ip}:${RAY_PORT}

Check head:
  ssh ${HEAD_USER}@${LOGIN_HOST}
  ssh ${HEAD_GPU}
  tmux attach -t ${TMUX_RAY}

Check worker:
  ssh ${WORKER_USER}@${LOGIN_HOST}
  ssh ${WORKER_GPU}
  tmux attach -t ${TMUX_RAY}

Check vLLM:
  ssh ${HEAD_USER}@${LOGIN_HOST}
  ssh ${HEAD_GPU}
  tmux attach -t ${TMUX_VLLM}
========================================
EOF
}

main() {
  require_cmd ssh
  require_head

  case "${ACTION}" in
    start-head)
      init_nodes_once
      start_head
      ;;
    start-worker)
      require_worker
      init_nodes_once
      start_worker
      ;;
    start-vllm)
      init_nodes_once
      start_vllm
      ;;
    start-all)
      require_worker
      init_nodes_once
      start_all
      ;;
    status)
      init_nodes_once
      status_all
      ;;
    stop-all)
      init_nodes_once
      stop_all
      ;;
    *)
      usage
      die "unknown action: ${ACTION}"
      ;;
  esac
}

main