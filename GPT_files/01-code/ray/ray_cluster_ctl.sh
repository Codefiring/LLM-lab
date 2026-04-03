#!/usr/bin/env bash
set -euo pipefail

LOGIN_HOST="202.20.183.100"
DEFAULT_ENV_ACTIVATE="source envs/vllm-qwen/bin/activate"
DEFAULT_TMUX_RAY="ray"
DEFAULT_TMUX_VLLM="vllm"
DEFAULT_TMUX_FWD="vllm-fwd"
DEFAULT_RAY_PORT="6379"
DEFAULT_REMOTE_VLLM_PORT="8888"
DEFAULT_LOCAL_FORWARD_PORT="8888"

HEAD_USER=""
WORKER_USER=""
HEAD_GPU=""
WORKER_GPU=""

ENV_ACTIVATE="${DEFAULT_ENV_ACTIVATE}"
TMUX_RAY="${DEFAULT_TMUX_RAY}"
TMUX_VLLM="${DEFAULT_TMUX_VLLM}"
TMUX_FWD="${DEFAULT_TMUX_FWD}"
RAY_PORT="${DEFAULT_RAY_PORT}"
REMOTE_VLLM_PORT="${DEFAULT_REMOTE_VLLM_PORT}"
LOCAL_FORWARD_PORT="${DEFAULT_LOCAL_FORWARD_PORT}"

ACTION="${1:-}"
if [[ -z "${ACTION}" ]]; then
  echo "ERROR: missing action" >&2
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
  start-forward
  start-all
  status
  stop-forward
  stop-all

Options:
  --head-user <user>           Head 登录账号，例如 hxiang.huang
  --worker-user <user>         Worker 登录账号，例如 meng01.huang
  --login-host <host>          登录跳板机，默认 ${LOGIN_HOST}
  --env-activate <cmd>         环境激活命令，默认: ${DEFAULT_ENV_ACTIVATE}
  --ray-port <port>            Ray 端口，默认 ${DEFAULT_RAY_PORT}
  --tmux-ray <name>            Ray tmux 会话名，默认 ${DEFAULT_TMUX_RAY}
  --tmux-vllm <name>           vLLM tmux 会话名，默认 ${DEFAULT_TMUX_VLLM}
  --tmux-fwd <name>            本地端口转发 tmux 会话名，默认 ${DEFAULT_TMUX_FWD}
  --remote-vllm-port <port>    GPU 节点上 vLLM 端口，默认 ${DEFAULT_REMOTE_VLLM_PORT}
  --local-forward-port <port>  本地 server 上转发端口，默认 ${DEFAULT_LOCAL_FORWARD_PORT}

Examples:
  $0 start-all --head-user hxiang.huang --worker-user meng01.huang
  $0 start-forward --head-user hxiang.huang
  $0 stop-forward --head-user hxiang.huang
EOF
}

log() {
  echo "[$(date '+%F %T')] $*" >&2
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
    --tmux-fwd)
      TMUX_FWD="${2:-}"; shift 2 ;;
    --remote-vllm-port)
      REMOTE_VLLM_PORT="${2:-}"; shift 2 ;;
    --local-forward-port)
      LOCAL_FORWARD_PORT="${2:-}"; shift 2 ;;
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

  # log "Detecting GPU node for ${login_user} via phd list -r ..."

  local gpu_node
  gpu_node="$(
    run_login_ssh "${login_user}" '
if ! command -v phd >/dev/null 2>&1; then
  echo "ERROR: phd command not found" >&2
  exit 1
fi

phd list -r | awk '\''/Running[[:space:]]+hgpu[0-9]+/ {print $NF; exit}'\''
' | tail -n 1 | tr -d "[:space:]"
  )"

  [[ -n "${gpu_node}" ]] || die "failed to detect GPU node for ${login_user}"
  printf '%s\n' "${gpu_node}"
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

kill_tmux_if_exists_remote() {
  local session_name="$1"
  cat <<EOF
if tmux has-session -t ${session_name} 2>/dev/null; then
  tmux kill-session -t ${session_name}
fi
EOF
}

kill_tmux_if_exists_local() {
  local session_name="$1"
  if tmux has-session -t "${session_name}" 2>/dev/null; then
    tmux kill-session -t "${session_name}"
  fi
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
$(kill_tmux_if_exists_remote "${TMUX_RAY}")
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
$(kill_tmux_if_exists_remote "${TMUX_RAY}")
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
$(kill_tmux_if_exists_remote "${TMUX_VLLM}")

cat > /tmp/start_vllm.sh <<EOF_VLLM
#!/usr/bin/env bash
set -euo pipefail

echo '[vLLM] starting...'
export TMOUT=0

${ENV_ACTIVATE}

# =========================
# 在这里修改你的 vLLM 启动命令
# 注意端口和 --remote-vllm-port 保持一致
# =========================

vllm serve /data/model \
  --host 0.0.0.0 \
  --port ${REMOTE_VLLM_PORT}

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

start_forward() {
  require_cmd tmux
  require_cmd ssh

  log "Starting local SSH port forwarding: 127.0.0.1:${LOCAL_FORWARD_PORT} -> ${HEAD_GPU}:${REMOTE_VLLM_PORT} via ${LOGIN_HOST}"

  kill_tmux_if_exists_local "${TMUX_FWD}"

  tmux new-session -d -s "${TMUX_FWD}" \
    "ssh \
      -o ExitOnForwardFailure=yes \
      -o ServerAliveInterval=60 \
      -o ServerAliveCountMax=3 \
      -N \
      -L 127.0.0.1:${LOCAL_FORWARD_PORT}:${HEAD_GPU}:${REMOTE_VLLM_PORT} \
      ${HEAD_USER}@${LOGIN_HOST}"

  sleep 3

  echo "===== local forward session ====="
  tmux list-sessions | grep -E \"^${TMUX_FWD}:\" || true
  echo "===== local forward logs ====="
  tmux capture-pane -pt "${TMUX_FWD}" -S -20 || true

  log "Port forward ready: http://127.0.0.1:${LOCAL_FORWARD_PORT}"
}

stop_forward() {
  log "Stopping local port forward session ${TMUX_FWD}"
  kill_tmux_if_exists_local "${TMUX_FWD}"
}

status_local_forward() {
  echo "===== local forward session ====="
  if tmux has-session -t "${TMUX_FWD}" 2>/dev/null; then
    tmux list-sessions | grep -E "^${TMUX_FWD}:" || true
    echo "===== local forward logs ====="
    tmux capture-pane -pt "${TMUX_FWD}" -S -20 || true
    echo "===== local access ====="
    echo "Use: curl http://127.0.0.1:${LOCAL_FORWARD_PORT}/v1/models"
  else
    echo "no local forward session"
  fi
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

  status_local_forward
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
  stop_forward
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
  start_forward

  local head_ip
  head_ip="$(get_head_ip)"

  cat <<EOF

========================================
Done.
Head node: ${HEAD_GPU}
Worker node: ${WORKER_GPU}
Head address: ${head_ip}:${RAY_PORT}

Remote vLLM:
  ${HEAD_GPU}:${REMOTE_VLLM_PORT}

Local forwarded endpoint on this server:
  http://127.0.0.1:${LOCAL_FORWARD_PORT}

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

Check local forward:
  tmux attach -t ${TMUX_FWD}

Test locally on this server:
  curl http://127.0.0.1:${LOCAL_FORWARD_PORT}/v1/models
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
    start-forward)
      init_nodes_once
      start_forward
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
    stop-forward)
      stop_forward
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