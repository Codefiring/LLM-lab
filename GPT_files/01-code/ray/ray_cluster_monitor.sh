#!/usr/bin/env bash
set -euo pipefail

# ==========================================
# Monitor script for Ray + vLLM cluster
# Works together with: ray_cluster_ctl.sh
# ==========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTL_SCRIPT="${SCRIPT_DIR}/ray_cluster_ctl.sh"

LOGIN_HOST="202.20.183.100"
HEAD_USER=""
WORKER_USER=""

CHECK_INTERVAL=180
CURL_TIMEOUT=10
LOCAL_FORWARD_PORT=8888
STATE_FILE="${SCRIPT_DIR}/ray_cluster_monitor.state"
LOG_FILE="${SCRIPT_DIR}/ray_cluster_monitor.log"

ACTION="${1:-run}"
shift || true

usage() {
  cat <<EOF
Usage:
  $0 run [options]
  $0 once [options]

Options:
  --ctl-script <path>         控制脚本路径，默认: ${CTL_SCRIPT}
  --head-user <user>          Head 账号，例如 hxiang.huang
  --worker-user <user>        Worker 账号，例如 meng01.huang
  --login-host <host>         登录节点，默认: ${LOGIN_HOST}
  --interval <sec>            轮询间隔秒数，默认: ${CHECK_INTERVAL}
  --curl-timeout <sec>        curl 超时秒数，默认: ${CURL_TIMEOUT}
  --local-forward-port <p>    本地转发端口，默认: ${LOCAL_FORWARD_PORT}
  --state-file <path>         状态文件路径，默认: ${STATE_FILE}
  --log-file <path>           日志文件路径，默认: ${LOG_FILE}

Examples:
  $0 run --head-user hxiang.huang --worker-user meng01.huang
  $0 once --head-user hxiang.huang --worker-user meng01.huang
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ctl-script)
      CTL_SCRIPT="${2:-}"; shift 2 ;;
    --head-user)
      HEAD_USER="${2:-}"; shift 2 ;;
    --worker-user)
      WORKER_USER="${2:-}"; shift 2 ;;
    --login-host)
      LOGIN_HOST="${2:-}"; shift 2 ;;
    --interval)
      CHECK_INTERVAL="${2:-}"; shift 2 ;;
    --curl-timeout)
      CURL_TIMEOUT="${2:-}"; shift 2 ;;
    --local-forward-port)
      LOCAL_FORWARD_PORT="${2:-}"; shift 2 ;;
    --state-file)
      STATE_FILE="${2:-}"; shift 2 ;;
    --log-file)
      LOG_FILE="${2:-}"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage
      exit 1 ;;
  esac
done

require_head() {
  [[ -n "${HEAD_USER}" ]] || { echo "ERROR: --head-user is required" >&2; exit 1; }
}

require_worker() {
  [[ -n "${WORKER_USER}" ]] || { echo "ERROR: --worker-user is required" >&2; exit 1; }
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing command: $1" >&2; exit 1; }
}

log() {
  local msg="[$(date '+%F %T')] $*"
  echo "${msg}" | tee -a "${LOG_FILE}" >&2
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

  run_login_ssh "${login_user}" '
if ! command -v phd >/dev/null 2>&1; then
  echo "ERROR: phd command not found" >&2
  exit 1
fi

phd list -r | awk '\''/Running[[:space:]]+hgpu[0-9]+/ {print $NF; exit}'\''
' | tail -n 1 | tr -d "[:space:]"
}

check_vllm_health() {
  curl -fsS --max-time "${CURL_TIMEOUT}" "http://127.0.0.1:${LOCAL_FORWARD_PORT}/v1/models" >/dev/null 2>&1
}

check_gpu_reachable() {
  local login_user="$1"
  local gpu_node="$2"

  ssh -o BatchMode=yes -o ConnectTimeout=10 -T "${login_user}@${LOGIN_HOST}" bash <<EOF >/dev/null 2>&1
export TMOUT=0
set -euo pipefail
ssh -o BatchMode=yes -o ConnectTimeout=10 -T "${gpu_node}" 'echo ok' >/dev/null
EOF
}

load_state() {
  if [[ -f "${STATE_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${STATE_FILE}"
  fi
  LAST_HEAD_GPU="${LAST_HEAD_GPU:-}"
  LAST_WORKER_GPU="${LAST_WORKER_GPU:-}"
}

save_state() {
  local head_gpu="$1"
  local worker_gpu="$2"

  cat > "${STATE_FILE}" <<EOF
LAST_HEAD_GPU="${head_gpu}"
LAST_WORKER_GPU="${worker_gpu}"
EOF
}

run_ctl() {
  "${CTL_SCRIPT}" "$@"
}

restart_all_cluster() {
  log "Restarting full cluster ..."
  run_ctl stop-all \
    --head-user "${HEAD_USER}" \
    --worker-user "${WORKER_USER}" || true

  run_ctl start-all \
    --head-user "${HEAD_USER}" \
    --worker-user "${WORKER_USER}"
}

restart_vllm_only() {
  log "Restarting vLLM + local forward ..."
  run_ctl start-vllm \
    --head-user "${HEAD_USER}"

  run_ctl start-forward \
    --head-user "${HEAD_USER}"
}

monitor_once() {
  load_state

  if check_vllm_health; then
    log "vLLM healthy on http://127.0.0.1:${LOCAL_FORWARD_PORT}"
    return 0
  fi

  log "vLLM health check failed, checking GPU state ..."

  local current_head_gpu=""
  local current_worker_gpu=""

  current_head_gpu="$(detect_gpu_node "${HEAD_USER}" 2>/dev/null || true)"
  current_worker_gpu="$(detect_gpu_node "${WORKER_USER}" 2>/dev/null || true)"

  if [[ -z "${current_head_gpu}" || -z "${current_worker_gpu}" ]]; then
    log "Failed to detect current GPU node(s). Will retry later."
    return 1
  fi

  log "Detected current head GPU: ${current_head_gpu}"
  log "Detected current worker GPU: ${current_worker_gpu}"

  if [[ -z "${LAST_HEAD_GPU}" || -z "${LAST_WORKER_GPU}" ]]; then
    log "No previous GPU state found, saving current state first."
    save_state "${current_head_gpu}" "${current_worker_gpu}"
  fi

  if [[ "${current_head_gpu}" != "${LAST_HEAD_GPU}" || "${current_worker_gpu}" != "${LAST_WORKER_GPU}" ]]; then
    log "GPU node changed: head ${LAST_HEAD_GPU} -> ${current_head_gpu}, worker ${LAST_WORKER_GPU} -> ${current_worker_gpu}"
    restart_all_cluster
    save_state "${current_head_gpu}" "${current_worker_gpu}"

    if check_vllm_health; then
      log "Cluster recovered after full restart."
      return 0
    fi

    log "Cluster restart finished but vLLM still unhealthy."
    return 1
  fi

  log "GPU node names unchanged, checking reachability ..."

  if ! check_gpu_reachable "${HEAD_USER}" "${current_head_gpu}"; then
    log "Head GPU ${current_head_gpu} is currently unreachable. Will retry later."
    return 1
  fi

  if ! check_gpu_reachable "${WORKER_USER}" "${current_worker_gpu}"; then
    log "Worker GPU ${current_worker_gpu} is currently unreachable. Will retry later."
    return 1
  fi

  log "GPU nodes are reachable. Trying vLLM-only recovery first."
  if restart_vllm_only && check_vllm_health; then
    log "vLLM recovered after vLLM-only restart."
    save_state "${current_head_gpu}" "${current_worker_gpu}"
    return 0
  fi

  log "vLLM-only restart failed, escalating to full cluster restart."
  restart_all_cluster
  save_state "${current_head_gpu}" "${current_worker_gpu}"

  if check_vllm_health; then
    log "Cluster recovered after escalation restart."
    return 0
  fi

  log "Full restart completed but vLLM is still unhealthy."
  return 1
}

init_state_if_needed() {
  load_state

  local current_head_gpu=""
  local current_worker_gpu=""

  current_head_gpu="$(detect_gpu_node "${HEAD_USER}" 2>/dev/null || true)"
  current_worker_gpu="$(detect_gpu_node "${WORKER_USER}" 2>/dev/null || true)"

  if [[ -n "${current_head_gpu}" && -n "${current_worker_gpu}" ]]; then
    save_state "${current_head_gpu}" "${current_worker_gpu}"
    log "Initial GPU state saved: head=${current_head_gpu}, worker=${current_worker_gpu}"
  else
    log "Initial GPU state detection failed. Monitor will continue and retry."
  fi
}

main() {
  require_cmd ssh
  require_cmd curl
  require_head
  require_worker
  [[ -x "${CTL_SCRIPT}" ]] || { echo "ERROR: control script not executable: ${CTL_SCRIPT}" >&2; exit 1; }

  mkdir -p "$(dirname "${STATE_FILE}")"
  mkdir -p "$(dirname "${LOG_FILE}")"

  init_state_if_needed

  case "${ACTION}" in
    once)
      monitor_once
      ;;
    run)
      log "Monitor started. interval=${CHECK_INTERVAL}s, local_port=${LOCAL_FORWARD_PORT}"
      while true; do
        monitor_once || true
        sleep "${CHECK_INTERVAL}"
      done
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main