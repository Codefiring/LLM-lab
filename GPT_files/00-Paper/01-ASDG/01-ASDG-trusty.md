
digraph trusty_tipc_fd {
    rankdir=LR;
    node [shape=ellipse];

    CLOSED           [label="CLOSED (无 dn)"];
    DISCONNECTED     [label="TIPC_DISCONNECTED"];
    CONNECTING       [label="TIPC_CONNECTING"];
    CONNECTED        [label="TIPC_CONNECTED"];
    STALE            [label="TIPC_STALE"];

    // 打开/关闭 fd
    CLOSED -> DISCONNECTED [label="open(/dev/trusty-ipc-*)\n(tipc_open)"];
    {DISCONNECTED CONNECTING CONNECTED STALE} -> CLOSED
        [label="close()\n(tipc_release)", style=dashed];

    // 连接 ioctl
    DISCONNECTED -> CONNECTING
        [label="TIPC_IOC_CONNECT(name)\n(发送 CONN_REQ)"];

    // 连接中的结果（由 secure world / virtio 回来）
    CONNECTING -> CONNECTED
        [label="CONN_RSP status=0\n_handle_conn_rsp → dn_connected()"];
    CONNECTING -> DISCONNECTED
        [label="CONN_RSP status!=0\n_handle_conn_rsp → dn_disconnected()"];
    CONNECTING -> STALE
        [label="连接超时\nREPLY_TIMEOUT → dn_wait_for_reply()"];

    // 再次调用 CONNECT 的特殊情况
    CONNECTING -> CONNECTING
        [label="TIPC_IOC_CONNECT(同名)\n返回 0，不变"];
    CONNECTING -> CONNECTING
        [label="TIPC_IOC_CONNECT(不同名)\n-EALREADY", style=dotted];
    CONNECTED  -> CONNECTED
        [label="TIPC_IOC_CONNECT(同名)\n返回 0，不变"];
    CONNECTED  -> CONNECTED
        [label="TIPC_IOC_CONNECT(不同名)\n-EISCONN", style=dotted];
    STALE      -> STALE
        [label="TIPC_IOC_CONNECT\n-ESHUTDOWN", style=dotted];

    // 收 / 发 数据（只在 CONNECTED 合法）
    CONNECTED -> CONNECTED
        [label="read()/aio_read\n有消息: 正常返回\n无消息: 阻塞等待",
         style=dashed];
    {DISCONNECTED CONNECTING STALE} -> {DISCONNECTED CONNECTING STALE}
        [label="read()/aio_read\n返回 -ENOTCONN / -ESHUTDOWN",
         style=dotted];

    CONNECTED -> CONNECTED
        [label="write()/aio_write\n→ tipc_chan_queue_msg",
         style=dashed];
    {DISCONNECTED CONNECTING STALE} -> {DISCONNECTED CONNECTING STALE}
        [label="write()/aio_write\n返回 -ENOTCONN / -ESHUTDOWN",
         style=dotted];

    // 远端 / 设备下线导致的状态变化
    CONNECTED  -> DISCONNECTED
        [label="远端断开\nDISC_REQ / TIPC_CHANNEL_DISCONNECTED",
         style=dashed];
    CONNECTING -> DISCONNECTED
        [label="远端拒绝\nDISC_REQ / status!=0",
         style=dashed];
    {DISCONNECTED CONNECTING CONNECTED} -> STALE
        [label="_go_offline() / 设备下线\nTIPC_CHANNEL_SHUTDOWN",
         style=dashed];
}