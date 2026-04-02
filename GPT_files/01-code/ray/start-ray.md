
下面给你一个可直接用的 **Bash 脚本**，在 `109.105.132.52` 这台 server 上执行即可。

这个脚本会自动完成：

1. 登录跳板节点 `202.20.183.100`
2. 再登录对应 GPU 节点
3. 设置 `export TMOUT=0`
4. 创建或重建 `tmux` 会话 `ray`
5. 在第一个 GPU 上启动 `ray head`
6. 自动获取第一个 GPU 的内网 IP
7. 在第二个 GPU 上启动 `ray worker`
8. 最后打印查看日志的方法

我按你的场景把 bastion、环境名、tmux 名称、ray 端口都写成了默认值，也可以改。

---

### 脚本：`start_ray_cluster.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

#######################################
# 默认配置
#######################################
BASTION_USER_DEFAULT="hxiang.huang"
BASTION_HOST_DEFAULT="202.20.183.100"
TMUX_SESSION="ray"
VENV_ACTIVATE="source envs/vllm-qwen/bin/activate"
RAY_PORT="6379"

#######################################
# 用法
#######################################
usage() {
  cat <<EOF
用法:
  $0 <user1> <gpu1> <user2> <gpu2> [bastion_user] [bastion_host]

参数说明:
  user1         第一个账户 id（通常是 head 节点账户）
  gpu1          第一个 GPU 编号，例如 hgpu4017
  user2         第二个账户 id（通常是 worker 节点账户）
  gpu2          第二个 GPU 编号，例如 hgpu4033
  bastion_user  跳板机用户名，默认: ${BASTION_USER_DEFAULT}
  bastion_host  跳板机地址，默认: ${BASTION_HOST_DEFAULT}

示例:
  $0 hxiang.huang hgpu4017 hxiang.huang hgpu4033
EOF
}

#######################################
# 参数检查
#######################################
if [[ $# -lt 4 ]]; then
  usage
  exit 1
fi

USER1="$1"
GPU1="$2"
USER2="$3"
GPU2="$4"
BASTION_USER="${5:-$BASTION_USER_DEFAULT}"
BASTION_HOST="${6:-$BASTION_HOST_DEFAULT}"

#######################################
# 工具函数
#######################################
log() {
  echo "[$(date '+%F %T')] $*"
}

# 在 bastion 上再 ssh 到 gpu 节点执行命令
run_on_gpu() {
  local remote_user="$1"
  local gpu_node="$2"
  local remote_cmd="$3"

  ssh -tt "${BASTION_USER}@${BASTION_HOST}" bash -lc "'
    export TMOUT=0
    ssh -tt ${remote_user}@${gpu_node} bash -lc '\"'\"'
      export TMOUT=0
      ${remote_cmd}
    '\"'\"'
  '"
}

# 在指定 GPU 上启动 tmux + 命令
start_tmux_job() {
  local remote_user="$1"
  local gpu_node="$2"
  local job_cmd="$3"

  run_on_gpu "${remote_user}" "${gpu_node}" "
    if tmux has-session -t ${TMUX_SESSION} 2>/dev/null; then
      tmux kill-session -t ${TMUX_SESSION}
    fi

    tmux new-session -d -s ${TMUX_SESSION}
    tmux send-keys -t ${TMUX_SESSION} 'export TMOUT=0' C-m
    tmux send-keys -t ${TMUX_SESSION} '${VENV_ACTIVATE}' C-m
    tmux send-keys -t ${TMUX_SESSION} 'ray stop -f >/dev/null 2>&1 || true' C-m
    tmux send-keys -t ${TMUX_SESSION} '${job_cmd}' C-m
  "
}

#######################################
# 1) 获取 head 节点 IP
#######################################
log "获取 head 节点 ${GPU1} 的内网 IP ..."
HEAD_IP=$(
  ssh -tt "${BASTION_USER}@${BASTION_HOST}" bash -lc "'
    export TMOUT=0
    ssh -tt ${USER1}@${GPU1} bash -lc '\"'\"'
      export TMOUT=0
      hostname -I | awk '\"'\"'{print \$1}'\"'\"'
    '\"'\"'
  '" 2>/dev/null | tr -d '\r' | tail -n 1 | xargs
)

if [[ -z "${HEAD_IP}" ]]; then
  echo "错误：无法获取 ${GPU1} 的 IP"
  exit 1
fi

log "head 节点 IP: ${HEAD_IP}"

#######################################
# 2) 启动 head 节点
#######################################
log "在 ${GPU1} 上启动 Ray head ..."
start_tmux_job "${USER1}" "${GPU1}" "ray start --block --head --port=${RAY_PORT}"

# 等几秒，给 ray head 启动时间
sleep 8

#######################################
# 3) 启动 worker 节点
#######################################
log "在 ${GPU2} 上启动 Ray worker，连接到 ${HEAD_IP}:${RAY_PORT} ..."
start_tmux_job "${USER2}" "${GPU2}" "ray start --block --address='${HEAD_IP}:${RAY_PORT}'"

sleep 3

#######################################
# 4) 输出检查方式
#######################################
cat <<EOF

========================================
Ray 集群启动命令已下发完成

Head:
  用户: ${USER1}
  节点: ${GPU1}
  地址: ${HEAD_IP}:${RAY_PORT}

Worker:
  用户: ${USER2}
  节点: ${GPU2}

查看 head 日志:
  ssh ${BASTION_USER}@${BASTION_HOST}
  ssh ${USER1}@${GPU1}
  tmux attach -t ${TMUX_SESSION}

查看 worker 日志:
  ssh ${BASTION_USER}@${BASTION_HOST}
  ssh ${USER2}@${GPU2}
  tmux attach -t ${TMUX_SESSION}

如果要退出 tmux 但不停止服务:
  Ctrl+b 然后按 d
========================================
EOF
```

---

### 使用方式

先保存：

```bash
nano start_ray_cluster.sh
```

把上面的内容贴进去，然后赋权：

```bash
chmod +x start_ray_cluster.sh
```

执行：

```bash
./start_ray_cluster.sh hxiang.huang hgpu4017 hxiang.huang hgpu4033
```

如果两个 GPU 对应的是不同账号，也可以这样：

```bash
./start_ray_cluster.sh userA hgpu4017 userB hgpu4033
```

---

### 这个脚本的几个处理点

这个版本默认做了几件对你比较实用的事：

1. **tmux 会话重建**
   如果已经存在 `ray` 会话，会先 kill 再重建，避免旧的 ray 残留。

2. **先执行 `ray stop -f`**
   防止之前已有 ray 进程占端口。

3. **自动获取 head 节点 IP**
   不依赖手工从日志里复制 `ray start --address=...`。

4. **使用 `--block`**
   这样 ray 进程会一直挂在 tmux 会话里，终端断开也不会退出。

---

### 更稳一点的建议

如果你的环境里 `hgpu4017` / `hgpu4033` 这种名字只能在跳板机上解析，这个脚本没问题，因为它就是先 ssh 到跳板机，再从跳板机 ssh 到 GPU。

但有两个前提：

* 从跳板机到 GPU 节点也已经配置好免密，或者至少不会卡住要求你交互输密码
* GPU 节点之间网络互通，worker 能访问 head 的 `${HEAD_IP}:6379`

---

### 建议你加一个检查脚本

如果你希望，我还可以继续给你补一个版本，增加这些能力：

* 自动检查 `tmux` / `ray` / Python 环境是否存在
* 自动验证 head 端口是否成功监听
* 自动在两个节点上启动 vLLM 服务
* 失败时自动打印是哪一步失败
* 支持一次传入多台 worker 节点，不止两台

我也可以直接给你改成 **更适合生产环境的 Python 版本**，日志和报错会比 Bash 清晰很多。
