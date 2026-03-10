digraph nbd_ioctl_fsm {
  rankdir=LR;
  node [shape=record];

  S0_INIT      [label="{S0 INIT|SockPresent=0|Sized=0|Running=0}"];
  S1_SOCK      [label="{S1 SOCK_BOUND|SockPresent=1|Sized=0|Running=0}"];
  S2_SIZE      [label="{S2 SIZE_SET|SockPresent=0|Sized=1|Running=0}"];
  S3_READY     [label="{S3 READY|SockPresent=1|Sized=1|Running=0}"];
  S4_RUNNING   [label="{S4 RUNNING|SockPresent=1|Sized=1|Running=1|DiscReq=0}"];
  S5_DISC_REQ  [label="{S5 DISCONNECTING|SockPresent=1|DiscReq=1}"];
  S6_STOPPED   [label="{S6 STOPPED|SockPresent=0|Running=0|Disconnected=1}"];

  # --- 主正常路径 ---

  # 绑定 socket / 配大小（顺序可以调换）
  S0_INIT -> S1_SOCK [label="NBD_SET_SOCK"];
  S0_INIT -> S2_SIZE [label="NBD_SET_SIZE /\\nNBD_SET_SIZE_BLOCKS /\\nNBD_SET_BLKSIZE"];
  S1_SOCK -> S3_READY [label="NBD_SET_SIZE /\\nNBD_SET_SIZE_BLOCKS /\\nNBD_SET_BLKSIZE"];
  S2_SIZE -> S3_READY [label="NBD_SET_SOCK"];

  # 启动 I/O 循环
  S3_READY -> S4_RUNNING [label="NBD_DO_IT"];

  # 在未运行状态下调整 flags/timeout
  S0_INIT -> S0_INIT [label="NBD_SET_TIMEOUT /\\nNBD_SET_FLAGS"];
  S1_SOCK -> S1_SOCK [label="NBD_SET_TIMEOUT /\\nNBD_SET_FLAGS"];
  S2_SIZE -> S2_SIZE [label="NBD_SET_TIMEOUT /\\nNBD_SET_FLAGS"];
  S3_READY -> S3_READY [label="NBD_SET_TIMEOUT /\\nNBD_SET_FLAGS"];

  # --- 断开路径 ---

  # 正常断开：先 DISCONNECT，再 CLEAR_SOCK
  S4_RUNNING -> S5_DISC_REQ [label="NBD_DISCONNECT"];
  S5_DISC_REQ -> S6_STOPPED [label="NBD_CLEAR_SOCK"];

  # 异常/强制：直接 CLEAR_SOCK 中止运行
  S4_RUNNING -> S6_STOPPED [label="NBD_CLEAR_SOCK"];

  # 从非运行状态清理 socket
  S1_SOCK -> S0_INIT [label="NBD_CLEAR_SOCK"];
  S3_READY -> S0_INIT [label="NBD_CLEAR_SOCK"];

  # STOPPED 之后重新使用设备（重新 open/配置）
  S6_STOPPED -> S0_INIT [label="(re-open / new config)"];
}