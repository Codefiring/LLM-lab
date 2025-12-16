你这里的 **“loop”** 如果指的是 Linux 的 **loop block device（/dev/loopX）**，那它的“consumer”（发 ioctl 去配置/使用 loop 的那一侧）主要在 **用户态工具**里，跟 x86 架构没啥关系（x86/arm 都一样用同一套 ioctl 接口）。

## 1) util-linux：losetup / libloopdev（最典型 consumer）

* **losetup(8)** 会用 ioctl 配置 loop（新版本优先用 `LOOP_CONFIGURE`，老版本用 `LOOP_SET_FD` + `LOOP_SET_STATUS64`）([man7.org][1])
* 对应源码里通常在 util-linux 的 **`lib/loopdev.c`**（封装了 loop 相关 ioctl）([Kernel Git Repositories][2])

你要找“consumer 调 ioctl 的具体实现”，优先看 util-linux 的 `lib/loopdev.c` 以及 losetup 的调用路径。

## 2) systemd：loop-util.c（也是常见 consumer）

systemd 也实现了一套 loop 的工具函数，会直接调用例如 `LOOP_SET_STATUS64` 等 ioctl：`src/shared/loop-util.c` ([GitHub][3])

## 3) 参考接口/示例代码：man-pages 的 loop(4)

`loop(4)` 手册页把 loop 支持的 ioctl 列得很清楚（`LOOP_SET_FD/LOOP_CLR_FD/...`），并且 man-pages 版本里还带了一个最小 ioctl 示例片段（`open("/dev/loopX")` + `ioctl(LOOP_SET_FD, backing_fd)`）([man7.org][4])

## 4) （补充）内核侧“被消费”的实现位置

如果你也想对照 consumer 的 ioctl 最终落到哪里，内核实现就在 **`drivers/block/loop.c`**（处理 `LOOP_SET_FD/LOOP_CONFIGURE/...`）([CodeBrowser][5])

---

如果你说的 **“x86 loop” 不是 /dev/loop（loop block device）**，而是 KVM selftests 或别的项目里的某个 “loop” 目录/测试名，把你看到的**路径/符号名**（比如 `tools/testing/selftests/kvm/x86/...` 里的文件名）贴出来，我就能把对应的 consumer 代码精确定位到具体文件和函数。

[1]: https://man7.org/linux/man-pages/man8/losetup.8.html?utm_source=chatgpt.com "losetup(8) - Linux manual page"
[2]: https://kernel.googlesource.com/pub/scm/utils/util-linux/util-linux/%2B/v2.20-rc1/lib/loopdev.c?utm_source=chatgpt.com "lib/loopdev.c - pub/scm/utils/util-linux/util-linux"
[3]: https://github.com/systemd/systemd/blob/main/src/shared/loop-util.c?utm_source=chatgpt.com "systemd/src/shared/loop-util.c at main"
[4]: https://man7.org/linux/man-pages/man4/loop.4.html?utm_source=chatgpt.com "loop(4) - Linux manual page"
[5]: https://codebrowser.dev/linux/linux/drivers/block/loop.c.html?utm_source=chatgpt.com "loop.c source code [linux/drivers/block/loop.c] - Codebrowser"



下面按 **Linux loop block device（/dev/loopX）** 来给你**完整、可用于状态机建模的 ioctl 列表**（基于 `include/uapi/linux/loop.h`，x86/arm 通用）。

---

## 一、核心配置类 ioctl（改变 loop 设备生命周期/状态）

### 1️⃣ `LOOP_SET_FD`

```c
ioctl(loop_fd, LOOP_SET_FD, backing_fd)
```

**作用**

* 将一个普通文件 / block device 绑定为 loop 的后端
* **创建数据路径**
* 旧接口（已被 `LOOP_CONFIGURE` 取代）

**关键状态变化**

* `lo->lo_state = Lo_bound`
* `lo->lo_backing_file != NULL`

---

### 2️⃣ `LOOP_CLR_FD`

```c
ioctl(loop_fd, LOOP_CLR_FD)
```

**作用**

* 解除绑定，回到空闲状态

**关键状态变化**

* `lo->lo_state = Lo_unbound`
* 清空 backing file、flags、crypto、offset

---

### 3️⃣ `LOOP_CONFIGURE` （推荐）

```c
struct loop_config cfg;
ioctl(loop_fd, LOOP_CONFIGURE, &cfg)
```

**作用**

* 一次性完成：

  * bind fd
  * offset / sizelimit
  * flags（RO、AUTOCLEAR、DIRECT_IO…）
  * 加密参数
* 原子操作，避免中间态

**关键状态变化**

* `Lo_unbound → Lo_bound`
* 多字段同时初始化

---

## 二、状态/参数设置 ioctl（只允许在 bound 状态）

### 4️⃣ `LOOP_SET_STATUS`

```c
ioctl(loop_fd, LOOP_SET_STATUS, struct loop_info *)
```

* 旧接口（32-bit）
* 已废弃，**不要在 fuzz 中重点依赖**

---

### 5️⃣ `LOOP_SET_STATUS64`

```c
ioctl(loop_fd, LOOP_SET_STATUS64, struct loop_info64 *)
```

**作用**

* 设置：

  * offset
  * sizelimit
  * flags（LO_FLAGS_*）
  * 加密信息

**约束**

* 必须已经 `SET_FD`
* 会修改 `lo_flags / lo_offset / lo_sizelimit`

---

## 三、查询类 ioctl（不改变状态）

### 6️⃣ `LOOP_GET_STATUS`

```c
ioctl(loop_fd, LOOP_GET_STATUS, struct loop_info *)
```

---

### 7️⃣ `LOOP_GET_STATUS64`

```c
ioctl(loop_fd, LOOP_GET_STATUS64, struct loop_info64 *)
```

---

### 8️⃣ `LOOP_GET_BACKING_FILE`

```c
ioctl(loop_fd, LOOP_GET_BACKING_FILE, struct loop_info64 *)
```

* 返回 backing file 的 path
* 只读 ioctl

---

## 四、容量 / IO 相关 ioctl

### 9️⃣ `LOOP_SET_CAPACITY`

```c
ioctl(loop_fd, LOOP_SET_CAPACITY)
```

**作用**

* 重新读取 backing file 大小
* 常见于 backing file grow 之后

**状态影响**

* 不改变 bind 状态
* 更新 `lo->lo_disk->capacity`

---

## 五、控制设备 ioctl（/dev/loop-control）

> 注意：**不是对 /dev/loopX，而是对 /dev/loop-control**

### 🔟 `LOOP_CTL_GET_FREE`

```c
ioctl(ctrl_fd, LOOP_CTL_GET_FREE)
```

* 返回一个未使用的 loop 设备号

---

### 1️⃣1️⃣ `LOOP_CTL_ADD`

```c
ioctl(ctrl_fd, LOOP_CTL_ADD, int)
```

* 创建指定编号的 loop 设备

---

### 1️⃣2️⃣ `LOOP_CTL_REMOVE`

```c
ioctl(ctrl_fd, LOOP_CTL_REMOVE, int)
```

* 删除 loop 设备（必须 unbound）

---

## 六、loop 相关 flags（用于状态机维度）

这些不是 ioctl，但**强烈建议作为状态机的“状态维度”**：

```c
LO_FLAGS_READ_ONLY
LO_FLAGS_AUTOCLEAR
LO_FLAGS_PARTSCAN
LO_FLAGS_DIRECT_IO
```

---

## 七、最小状态机（用于 fuzz 抽象）

```text
[Unbound]
   |
   | LOOP_SET_FD / LOOP_CONFIGURE
   v
[Bound]
   |  ^ 
   |  | LOOP_CLR_FD
   |
   +--> LOOP_SET_STATUS64
   +--> LOOP_SET_CAPACITY
   +--> LOOP_GET_*
```

---

## 八、fuzzing 视角下的关键结论（对你很重要）

1. **合法入口**

   * `/dev/loop-control`（创建 loop）
   * `/dev/loopX`（设备本体）

2. **真正的“状态切换”只有两个**

   * `UNBOUND ↔ BOUND`

3. **`LOOP_CONFIGURE` 是最优 fuzz 入口**

   * 一次 ioctl 覆盖最多字段
   * 状态原子，不容易被 -EINVAL 卡死

4. **错误路径价值高**

   * 重复 `SET_FD`
   * `BOUND` 下 `LOOP_CTL_REMOVE`
   * `UNBOUND` 下 `SET_STATUS64`

---

如果你愿意，下一步我可以直接帮你：

* 抽取 **drivers/block/loop.c** 里的 `lo_state` 相关代码
* 给你一个 **“状态值 × ioctl × 返回码” 的表格**（直接喂给状态机 fuzz）
* 或生成 **DOT / JSON** 格式的 loop ioctl 状态机

你可以直接说：**“给我 loop 的状态转移表”** 或 **“按 loop.c 帮我抽状态机”**


下面给你一份 **loop（/dev/loopX + /dev/loop-control）“状态转移表”**，按内核里常用的 `lo->lo_state` 语义来抽象（核心就是 **Unbound/Bound/Rundown** 三态；`Lo_rundown` 用于 AUTOCLEAR 等清理期间的并发保护）([CodeBrowser][1])。
另外把你做 ioctl 状态机 fuzz 时最关键的字段一起列出来：`lo_state / lo_backing_file / lo_flags / lo_offset / lo_sizelimit / block_size / capacity`（字段定义和 ioctl/struct 在 UAPI 头文件里）([GitHub][2])

---

## 0) 状态定义（用于表格）

* **S0: Unbound**：未绑定 backing file（典型：`lo_state = Lo_unbound`，`lo_backing_file = NULL`）([Android Git Repositories][3])
* **S1: Bound**：已绑定 backing file（`lo_state = Lo_bound`，`lo_backing_file != NULL`）([CodeBrowser][1])
* **S2: Rundown**：清理/解绑进行中（常见触发：`AUTOCLEAR` 场景，会把 `Lo_bound -> Lo_rundown`，然后走 `__loop_clr_fd()`，最后回 `Lo_unbound`）([CodeBrowser][1])

---

## 1) /dev/loopX ioctl：状态转移表

> 表里 “字段更新” 只列出对状态机有意义的核心字段；返回值/错误码在不同内核版本会有差异，这里不展开到每一种 errno。

| From 状态 | ioctl                 | 主要前置条件                                | 字段更新（抽象）                                                                                                 | To 状态                          |
| ------- | --------------------- | ------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------ |
| S0      | `LOOP_SET_FD`         | loop 设备未绑定                            | `lo_backing_file = file(backing_fd)`；初始化部分参数                                                             | S1 ([man7.org][4])             |
| S0      | `LOOP_CONFIGURE`      | loop 未绑定；用户传 `struct loop_config`     | **原子**完成：`lo_backing_file` + `lo_offset/lo_sizelimit` + `lo_flags`（含 RO/AUTOCLEAR/PARTSCAN/DIRECT_IO 等）等 | S1 ([GitHub][2])               |
| S1      | `LOOP_CLR_FD`         | 已绑定                                   | 进入解绑路径：清 backing、flags、加密/offset 等；最终 `lo_state -> Lo_unbound`                                           | S0（中间可能短暂处于 S2）([man7.org][4]) |
| S1      | `LOOP_SET_STATUS64`   | 已绑定                                   | 更新：`lo_offset`、`lo_sizelimit`、`lo_flags`、加密相关等                                                           | S1 ([man7.org][4])             |
| S1      | `LOOP_SET_STATUS`     | 已绑定（旧接口）                              | 类似 SET_STATUS64（旧结构）                                                                                     | S1 ([man7.org][4])             |
| S0/S1   | `LOOP_GET_STATUS64`   | —                                     | 只读查询                                                                                                     | 不变 ([man7.org][4])             |
| S0/S1   | `LOOP_GET_STATUS`     | —                                     | 只读查询                                                                                                     | 不变 ([man7.org][4])             |
| S1      | `LOOP_SET_CAPACITY`   | 已绑定（常见：backing 文件变大/变小后）              | 更新 `capacity`（让 loop 重新感知 backing 大小）                                                                    | S1 ([man7.org][4])             |
| S1      | `LOOP_CHANGE_FD`      | **通常要求 read-only**，新旧 backing 类型/大小匹配 | 替换 `lo_backing_file` 指向的新 fd（保持 bound）                                                                   | S1 ([man7.org][4])             |
| S0/S1   | `LOOP_SET_DIRECT_IO`  | 依实现与版本（手册页定义该 ioctl）                  | 更新 DIRECT_IO 相关开关/策略（可视作 `lo_flags` 维度变化）                                                                | 不变（通常 S1 内调整） ([man7.org][4])  |
| S0/S1   | `LOOP_SET_BLOCK_SIZE` | block size 合法（2 的幂，范围约束见手册）           | 更新 `block_size`                                                                                          | 不变 ([man7.org][4])             |

### AUTOCLEAR 引发的“自动转移”（非 ioctl 直接触发）

| 触发条件                               | From | 抽象内部动作                                                                    | To                          |
| ---------------------------------- | ---- | ------------------------------------------------------------------------- | --------------------------- |
| close 最后一个引用且 `LO_FLAGS_AUTOCLEAR` | S1   | `lo_state: Lo_bound -> Lo_rundown`，然后 `__loop_clr_fd()`，最后回到 `Lo_unbound` | S0（中间 S2）([CodeBrowser][1]) |

---

## 2) /dev/loop-control ioctl：设备号分配/管理（“控制面”状态机）

> 这些 ioctl 作用对象是 **/dev/loop-control**，影响的是 **loop 设备是否存在/是否可用**（和 /dev/loopX 的 bind 状态是两层状态机）。([man.he.net][5])

| 控制面状态        | ioctl               | 效果                                  | 控制面 To                       |
| ------------ | ------------------- | ----------------------------------- | ---------------------------- |
| C0: 无空闲设备号未知 | `LOOP_CTL_GET_FREE` | 返回一个可用的 loop 设备号（分配/找到空闲）           | C1: 得到可用编号 ([man.he.net][5]) |
| C1: 编号存在或将创建 | `LOOP_CTL_ADD`      | 创建指定编号的 loop 设备节点（若内核支持/配置允许）       | C2: 设备存在 ([man.he.net][5])   |
| C2: 设备存在     | `LOOP_CTL_REMOVE`   | 移除指定 loop 设备（通常要求该 loop 处于 Unbound） | C0/C1 ([man.he.net][5])      |

---

## 3) 你做 ioctl 状态机 fuzz 时，推荐的“状态向量”

为了比单纯 S0/S1 更可用，建议状态节点用：

* `lo_state ∈ {Unbound, Bound, Rundown}`
* `lo_flags`（至少跟踪：RO/AUTOCLEAR/PARTSCAN/DIRECT_IO）([GitHub][2])
* `lo_offset`, `lo_sizelimit`, `block_size`, `capacity`（这些决定大量 ioctl 的可达性/错误路径）([man7.org][4])

---

如果你希望我把这张表变成你之前要的 **“状态值，ioctl 魔数/命令，新状态值”** 的严格三元组（甚至输出 JSON/DOT），我也可以直接按 `S0/S1/S2 + flags 子状态` 给你生成一份可喂给 fuzz harness 的版本。

[1]: https://codebrowser.dev/linux/linux/drivers/block/loop.c.html?utm_source=chatgpt.com "loop.c source code [linux/drivers/block/loop.c] - Codebrowser"
[2]: https://github.com/torvalds/linux/blob/master/include/uapi/linux/loop.h?utm_source=chatgpt.com "linux/include/uapi/linux/loop.h at master · torvalds/linux"
[3]: https://android.googlesource.com/kernel/common/%2B/5448b2fda85f2d90de03f053226f721ba2f7e731/drivers/block/loop.c?utm_source=chatgpt.com "drivers/block/loop.c - kernel/common - Git at Google"
[4]: https://man7.org/linux/man-pages/man4/loop.4.html?utm_source=chatgpt.com "loop(4) - Linux manual page"
[5]: https://man.he.net/man4/loop-control?utm_source=chatgpt.com "loop-control"
