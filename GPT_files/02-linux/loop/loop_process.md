下面我按 **“真实代码执行顺序 + ioctl 状态机视角”**，把 **Linux loop block device 驱动（drivers/block/loop.c）** 的**完整流程**给你梳理一遍。这版是**为你做 ioctl 状态机 / fuzzing 设计**而写的，不是泛泛而谈。

---

## 一、整体结构总览（先给你一张“脑图”）

```
用户态
 ├─ open("/dev/loop-control")
 │    └─ LOOP_CTL_GET_FREE → 得到 N
 │
 ├─ open("/dev/loopN")
 │
 ├─ ioctl(LOOP_SET_FD / LOOP_CONFIGURE)
 │    └─ loop_set_fd()
 │         ├─ 校验状态 (lo_state == UNBOUND)
 │         ├─ 绑定 backing file
 │         ├─ 初始化 lo_* 字段
 │         ├─ register disk / set capacity
 │         └─ lo_state = BOUND
 │
 ├─ [可选] ioctl(LOOP_SET_STATUS64 / SET_BLOCK_SIZE / …)
 │
 ├─ read/write(/dev/loopN)
 │    └─ loop_make_request()
 │         └─ submit bio → backing file
 │
 ├─ close(fd) 或 ioctl(LOOP_CLR_FD)
 │    └─ loop_clr_fd()
 │         ├─ lo_state = RUNDOWN
 │         ├─ 冻结 I/O
 │         ├─ 清 backing
 │         └─ lo_state = UNBOUND
```

---

## 二、核心数据结构（状态机“真·根”）

### 1️⃣ `struct loop_device`

**状态几乎都在这里**

```c
struct loop_device {
    int            lo_number;
    enum lo_state  lo_state;          // UNBOUND / BOUND / RUNDOWN
    struct file   *lo_backing_file;   // 是否绑定的核心判据
    loff_t         lo_offset;
    loff_t         lo_sizelimit;
    unsigned int   lo_flags;           // RO / AUTOCLEAR / DIRECT_IO ...
    struct gendisk *lo_disk;
    struct request_queue *lo_queue;
    ...
};
```

👉 **你 fuzz 的“状态值”，本质就是这些字段的组合**

---

## 三、控制面流程（/dev/loop-control）

### STEP 1：获取 loop 设备号

```c
ioctl("/dev/loop-control", LOOP_CTL_GET_FREE)
```

内核：

```
loop_control_ioctl()
 └─ loop_control_get_free()
     └─ ida_alloc() → N
```

结果：

* **N 被分配**
* `/dev/loopN` 存在或可创建

⚠️ 注意：**这一步不影响 lo_state**

---

## 四、数据面流程（/dev/loopN）

---

### STEP 2：打开 loop 设备

```c
open("/dev/loopN", O_RDWR)
```

内核：

```
loop_open()
 └─ 增加引用计数
```

状态：

* `lo_state` **不变**
* 只是获得 fd

---

### STEP 3：绑定 backing file（状态机关键跃迁）

#### 3.1 老接口

```c
ioctl(loop_fd, LOOP_SET_FD, backing_fd)
```

#### 3.2 新接口（推荐）

```c
ioctl(loop_fd, LOOP_CONFIGURE, &cfg)
```

内核主路径：

```
loop_ioctl()
 └─ loop_set_fd()
     ├─ mutex_lock(&lo->lo_mutex)
     ├─ if (lo_state != UNBOUND) → -EBUSY
     ├─ lo_backing_file = backing
     ├─ lo_offset / lo_sizelimit / lo_flags = cfg
     ├─ setup queue / block size
     ├─ set_capacity()
     └─ lo_state = BOUND
```

**状态跃迁：**

```
UNBOUND → BOUND
```

---

### STEP 4：配置阶段（BOUND 内自环）

这些 ioctl **不会改变 bind 状态，只改变参数**

```c
LOOP_SET_STATUS64
LOOP_SET_BLOCK_SIZE
LOOP_SET_DIRECT_IO
LOOP_SET_CAPACITY
```

内核：

```
loop_ioctl()
 └─ switch(cmd)
     └─ 更新 lo_flags / offset / capacity / block_size
```

**状态：**

```
BOUND → BOUND
```

⚠️ fuzz 时这些是“高价值变异点”

---

### STEP 5：I/O 数据路径（bio → backing file）

```c
read()/write() on /dev/loopN
```

内核：

```
loop_make_request()
 └─ loop_submit_bio()
     └─ vfs_iter_read/write(backing_file)
```

* **不走 ioctl**
* 但会检查：

  * `lo_state == BOUND`
  * `LO_FLAGS_READ_ONLY`

---

## 五、解绑与销毁流程（另一条关键路径）

### STEP 6：显式解绑

```c
ioctl(loop_fd, LOOP_CLR_FD)
```

内核：

```
loop_clr_fd()
 ├─ lo_state = RUNDOWN
 ├─ freeze_queue()
 ├─ invalidate cache
 ├─ fput(lo_backing_file)
 ├─ reset lo_* fields
 └─ lo_state = UNBOUND
```

**状态跃迁：**

```
BOUND → RUNDOWN → UNBOUND
```

---

### STEP 7：AUTOCLEAR 隐式解绑（非常重要）

如果设置了：

```c
LO_FLAGS_AUTOCLEAR
```

则：

```
close(last loop fd)
 └─ loop_release()
     └─ __loop_clr_fd()
```

**状态跃迁：**

```
BOUND → RUNDOWN → UNBOUND
```

👉 **这是一个“无 ioctl 的状态跃迁”**
👉 fuzz 时如果你模拟 close()，一定要建模它

---

## 六、完整状态机（文字版）

```
[S0: UNBOUND]
   |
   | LOOP_SET_FD / LOOP_CONFIGURE
   v
[S1: BOUND]
   | \
   |  +-- LOOP_SET_STATUS64 / SET_BLOCK_SIZE / SET_CAPACITY
   |        (自环)
   |
   | LOOP_CLR_FD
   | close() with AUTOCLEAR
   v
[S2: RUNDOWN]
   |
   v
[S0: UNBOUND]
```

---

## 七、为 ioctl fuzz / 状态机抽取的关键结论

### 1️⃣ 真正的“状态切换 ioctl”只有两个

* `LOOP_SET_FD` / `LOOP_CONFIGURE`
* `LOOP_CLR_FD`

### 2️⃣ 其余 ioctl = **参数扰动**

非常适合：

* 有界序列 fuzz
* 状态向量扩展（flags / offset / block_size）

### 3️⃣ AUTOCLEAR = 非 ioctl 边

* **必须在模型里显式建模**
* 否则你会“少一条合法路径”

---

## 八、如果你愿意，下一步我可以直接帮你做的事

* 从 `drivers/block/loop.c` **逐行抽取**状态更新点
* 生成 **machine-readable JSON / DOT 状态机**
* 把 **close()/open()** 也纳入你的 ioctl 状态机
* 帮你和 **nbd / dm / kvm** 的状态机做结构对比（你之前提过）

你直接说一句：
👉 **“给我 loop.c 的状态更新点列表”** 或
👉 **“生成 loop 的 DOT 状态机”**
