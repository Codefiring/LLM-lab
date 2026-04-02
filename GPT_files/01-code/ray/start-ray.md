下面给你一个可直接用的 **Bash 脚本**，在 `109.105.132.52` 这台 server 上执行即可。

它会自动完成这些事情：

1. 用第一个账号登录到 `202.20.183.100`
2. 再进入第一个 GPU 节点
3. 设置 `TMOUT=0`
4. 在该 GPU 节点上创建 `tmux` 会话 `ray`
5. 激活 `envs/vllm-qwen/bin/activate`
6. 启动 Ray head
7. 自动获取 head 节点 IP
8. 用第二个账号登录到 `202.20.183.100`
9. 再进入第二个 GPU 节点
10. 设置 `TMOUT=0`
11. 在该 GPU 节点上创建 `tmux` 会话 `ray`
12. 激活环境并启动 Ray worker，连接到 head

---

## 脚本

保存为 `start_ray_cluster.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

# =========================
# 用法:
#   ./start_ray_cluster.sh <head_login_user> <head_gpu_node> <worker_login_user> <worker_gpu_node>
#
# 例子:
#   ./start_ray_cluster.sh hxiang.huang hgpu4017 meng01.huang hgpu4033
# =========================

if [[ $# -ne 4 ]]; then
  echo "Usage: $0 <head_login_user> <head_gpu_node> <worker_login_user> <worker_gpu_node>"
  exit 1
fi

HEAD_LOGIN_USER="$1"
HEAD_GPU_NODE="$2"
WORKER_LOGIN_USER="$3"
WORKER_GPU_NODE="$4"

LOGIN_HOST="202.20.183.100"
ENV_ACTIVATE="source envs/vllm-qwen/bin/activate"
TMUX_SESSION="ray"
RAY_PORT="6379"

log() {
  echo "[$(date '+%F %T')] $*"
}

# 在 login 节点再 ssh 到 gpu 节点执行命令
run_nested_ssh() {
  local login_user="$1"
  local gpu_node="$2"
  local remote_cmd="$3"

  ssh -T "${login_user}@${LOGIN_HOST}" bash <<EOF
export TMOUT=0
ssh -T "${gpu_node}" bash <<'INNER_EOF'
export TMOUT=0
set -euo pipefail
${remote_cmd}
INNER_EOF
EOF
}

# 检查 tmux 是否存在
check_tmux() {
  local login_user="$1"
  local gpu_node="$2"

  log "Checking tmux on ${gpu_node} ..."
  run_nested_ssh "${login_user}" "${gpu_node}" '
if ! command -v tmux >/dev/null 2>&1; then
  echo "ERROR: tmux not found on $(hostname)"
  exit 1
fi
echo "tmux ok on $(hostname)"
'
}

# 启动 head 节点
start_ray_head() {
  local login_user="$1"
  local gpu_node="$2"

  log "Starting Ray head on ${gpu_node} ..."
  run_nested_ssh "${login_user}" "${gpu_node}" "
# 如已有同名会话，先删掉
if tmux has-session -t ${TMUX_SESSION} 2>/dev/null; then
  tmux kill-session -t ${TMUX_SESSION}
fi

# 清理旧 ray
if command -v ray >/dev/null 2>&1; then
  ray stop -f >/dev/null 2>&1 || true
fi

tmux new-session -d -s ${TMUX_SESSION}
tmux send-keys -t ${TMUX_SESSION} 'export TMOUT=0' C-m
tmux send-keys -t ${TMUX_SESSION} '${ENV_ACTIVATE}' C-m
tmux send-keys -t ${TMUX_SESSION} 'ray start --block --head --port=${RAY_PORT}' C-m

sleep 5

echo '===== tmux session created on head ====='
tmux list-sessions
echo '===== last head logs ====='
tmux capture-pane -pt ${TMUX_SESSION} -S -30
"
}

# 获取 head 节点 IP
get_head_ip() {
  local login_user="$1"
  local gpu_node="$2"

  run_nested_ssh "${login_user}" "${gpu_node}" '
IP=$(hostname -I | awk "{print \$1}")
if [[ -z "${IP}" ]]; then
  echo "ERROR: failed to get head node IP" >&2
  exit 1
fi
echo "${IP}"
' | tail -n 1
}

# 启动 worker 节点
start_ray_worker() {
  local login_user="$1"
  local gpu_node="$2"
  local head_ip="$3"

  log "Starting Ray worker on ${gpu_node}, connecting to ${head_ip}:${RAY_PORT} ..."
  run_nested_ssh "${login_user}" "${gpu_node}" "
# 如已有同名会话，先删掉
if tmux has-session -t ${TMUX_SESSION} 2>/dev/null; then
  tmux kill-session -t ${TMUX_SESSION}
fi

# 清理旧 ray
if command -v ray >/dev/null 2>&1; then
  ray stop -f >/dev/null 2>&1 || true
fi

tmux new-session -d -s ${TMUX_SESSION}
tmux send-keys -t ${TMUX_SESSION} 'export TMOUT=0' C-m
tmux send-keys -t ${TMUX_SESSION} '${ENV_ACTIVATE}' C-m
tmux send-keys -t ${TMUX_SESSION} 'ray start --address=${head_ip}:${RAY_PORT}' C-m

sleep 5

echo '===== tmux session created on worker ====='
tmux list-sessions
echo '===== last worker logs ====='
tmux capture-pane -pt ${TMUX_SESSION} -S -30
"
}

# 查看状态
show_summary() {
  local head_ip="$1"

  cat <<EOF

========================================
Ray cluster startup finished
Head address: ${head_ip}:${RAY_PORT}

You can manually check logs with:

1) Head:
   ssh ${HEAD_LOGIN_USER}@${LOGIN_HOST}
   ssh ${HEAD_GPU_NODE}
   tmux attach -t ${TMUX_SESSION}

2) Worker:
   ssh ${WORKER_LOGIN_USER}@${LOGIN_HOST}
   ssh ${WORKER_GPU_NODE}
   tmux attach -t ${TMUX_SESSION}
========================================
EOF
}

main() {
  check_tmux "${HEAD_LOGIN_USER}" "${HEAD_GPU_NODE}"
  check_tmux "${WORKER_LOGIN_USER}" "${WORKER_GPU_NODE}"

  start_ray_head "${HEAD_LOGIN_USER}" "${HEAD_GPU_NODE}"

  log "Getting head node IP ..."
  HEAD_IP="$(get_head_ip "${HEAD_LOGIN_USER}" "${HEAD_GPU_NODE}")"
  log "Head IP = ${HEAD_IP}"

  start_ray_worker "${WORKER_LOGIN_USER}" "${WORKER_GPU_NODE}" "${HEAD_IP}"

  show_summary "${HEAD_IP}"
}

main
```

---

## 使用方式

先给执行权限：

```bash
chmod +x start_ray_cluster.sh
```

然后执行：

```bash
./start_ray_cluster.sh hxiang.huang hgpu4017 meng01.huang hgpu4033
```

---

## 说明

这个脚本默认：

* 中转登录节点固定是：`202.20.183.100`
* tmux 会话名固定是：`ray`
* Python 环境激活命令固定是：

```bash
source envs/vllm-qwen/bin/activate
```

* Ray head 端口固定是：`6379`

---

## 它做了哪些容错

脚本里已经帮你做了这些处理：

* 自动 `export TMOUT=0`
* 如果已有同名 tmux 会话 `ray`，会先删掉再重建
* 如果旧的 ray 进程还在，会先 `ray stop -f`
* 自动获取 head 节点 IP，而不是依赖日志里那条提示命令
* 启动后会打印最近的 tmux 日志，方便你确认是否成功

---

## 可能需要注意的点

### 1. `ray start --block --head` 会一直阻塞

这是正常的，因为它在 tmux 里跑，所以不会卡住你本地脚本。

### 2. worker 节点这里我用的是：

```bash
ray start --address=${head_ip}:6379
```

这和你手动从日志里复制的思路一致，只是这里自动拼出来了。

### 3. `hostname -I | awk '{print $1}'`

这是为了自动获取 head 节点 IP。
如果你们集群里这个 IP 不是 Ray 实际可达的网卡地址，可能要改成固定网卡，比如：

```bash
hostname -I | awk '{print $2}'
```

或者直接手工指定。

---

## 更稳一点的增强版思路

如果你担心自动获取 IP 不准确，可以把脚本改成：

* head 启动后
* 从 `tmux capture-pane` 里解析 Ray 打印出来的 `--address='x.x.x.x:6379'`
* 再把这个地址传给 worker

不过通常 `hostname -I` 已经够用了，而且更简单稳定。

---

## 一个更灵活的版本建议

如果你后面还想顺手在 head 节点里继续启动 vLLM 服务，我建议把脚本扩展成：

* `start_head`
* `start_worker`
* `start_vllm`

三段式，这样后面更方便接：

```bash
python -m vllm.entrypoints.openai.api_server ...
```

---

如果你要，我可以下一条直接帮你再写一个 **增强版脚本**，支持这些能力：

* 支持传入环境路径
* 支持自定义 Ray 端口
* 支持 head 启动成功后自动在 tmux 里启动 vLLM
* 支持查看状态 / 停止集群 的子命令
