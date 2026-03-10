先说结论：**在 6.7 上，所有你关心的 ioctl 都是三棵大树**：

* `/dev/kvm` → `kvm_chardev_ops` → `.unlocked_ioctl = kvm_dev_ioctl`
* `VM fd` → `kvm_vm_fops` → `.unlocked_ioctl = kvm_vm_ioctl`
* `VCPU fd` → `kvm_vcpu_fops` → `.unlocked_ioctl = kvm_vcpu_ioctl`

所以“展平 fops”其实就是：
**把 KVM API 里标成 system/vm/vcpu 的 ioctl，按 fd 类型归类到这三个 dispatcher 上**。下面我按 **x86 + Linux 6.7** 的视角，把常用 ioctl → 顶层处理函数梳理成表，方便你对照自己代码树里的 `switch (ioctl)`。

> 说明：
>
> 1. 内核文档已经明确每个 ioctl 是 system / vm / vcpu 类型，我用的就是 6.7 对应的 KVM API 文档。([docs.kernel.org][1])
> 2. 具体 helper 名可能在不同 patch 里有轻微差异（例如是否拆成 `kvm_vm_ioctl_create_vcpu()` 这种小函数），但 **所有分发点一定在这三个 dispatcher** 里。

---

## 一、`/dev/kvm` 的 fops：`kvm_chardev_ops` → `kvm_dev_ioctl`

在 6.7，`virt/kvm/kvm_main.c` 里大致是：

```c
static const struct file_operations kvm_chardev_ops = {
    .owner          = THIS_MODULE,
    .unlocked_ioctl = kvm_dev_ioctl,
#ifdef CONFIG_COMPAT
    .compat_ioctl   = compat_ptr_ioctl,   // 再转到 kvm_dev_ioctl_compat
#endif
    .llseek         = noop_llseek,
};
```

### 1.1 映射：system ioctl → 处理函数（x86 相关）

**全部 system ioctl 的顶层处理点：`kvm_dev_ioctl()`**

| ioctl（从 uapi/linux/kvm.h）                                   | 类型     | 顶层处理位置                                                   | 典型内部调用/说明                                                                                                           |
| ----------------------------------------------------------- | ------ | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `KVM_GET_API_VERSION`                                       | system | `kvm_dev_ioctl` 中 `case KVM_GET_API_VERSION`             | 直接返回常量 `KVM_API_VERSION (=12)`([docs.kernel.org][1])                                                                |
| `KVM_CREATE_VM`                                             | system | `kvm_dev_ioctl` → 通常有 `kvm_dev_ioctl_create_vm()` helper | 分配 `struct kvm`，然后通过 `anon_inode_getfd("[kvm-vm]", &kvm_vm_fops, kvm, flags)` 创建 VM fd([国家漏洞数据库][2])                |
| `KVM_GET_MSR_INDEX_LIST` / `KVM_GET_MSR_FEATURE_INDEX_LIST` | system | `kvm_dev_ioctl`                                          | 内部委托给 x86 arch 的 msr 列表获取函数([docs.kernel.org][1])                                                                   |
| `KVM_CHECK_EXTENSION`（system 版本）                            | system | `kvm_dev_ioctl`                                          | 调用通用 `kvm_vm_ioctl_check_extension_generic()` 再加上 `kvm_x86_ops->check_extension()`（名字可能有细微差异）([docs.kernel.org][1]) |
| `KVM_GET_VCPU_MMAP_SIZE`                                    | system | `kvm_dev_ioctl`                                          | 返回 `sizeof(struct kvm_run)` 等 mmap 区大小([docs.kernel.org][1])                                                        |

还有一些比较陈旧/冷门的 system ioctl（例如早期的 trace 相关、部分架构特殊的 system 级 ioctl），**在 6.7 上依然走 `kvm_dev_ioctl()` 的 switch**，只是对 x86 来说你一般不会在自测里用到。文档里都写着 `Type: system ioctl` 的那批，都可以粗暴归到：

> **system ioctl ⇒ `/dev/kvm` fd ⇒ `kvm_dev_ioctl()`**

---

## 二、VM fd 的 fops：`kvm_vm_fops` → `kvm_vm_ioctl`

VM fd 是通过 `KVM_CREATE_VM` 创建的匿名 inode，fops 形如（6.7 上结构基本一致）：

```c
static const struct file_operations kvm_vm_fops = {
    .owner          = THIS_MODULE,
    .unlocked_ioctl = kvm_vm_ioctl,
#ifdef CONFIG_COMPAT
    .compat_ioctl   = kvm_vm_compat_ioctl,
#endif
    .release        = kvm_vm_release,
    .llseek         = noop_llseek,
};
```

### 2.1 映射：vm ioctl → `kvm_vm_ioctl`（x86 常用子集）

下面这些在文档里都标了 `Type: vm ioctl` **并且 arch 包含 x86**，因此在 6.7 x86 上都由 `kvm_vm_ioctl()` 处理。([docs.kernel.org][1])

#### 2.1.1 内存 / memslot 类

| ioctl                                                           | 顶层处理位置         | 常见 helper / 行为                                                                       |
| --------------------------------------------------------------- | -------------- | ------------------------------------------------------------------------------------ |
| `KVM_SET_USER_MEMORY_REGION`                                    | `kvm_vm_ioctl` | 一般会调用 `kvm_set_user_memory_region()`，增加/删除/修改 `struct kvm_memory_slot`，刷新 MMU        |
| `KVM_SET_USER_MEMORY_REGION2`（如果你 6.7 树里已经有）                    | `kvm_vm_ioctl` | 处理扩展的 `kvm_userspace_memory_region_ext`，支持 fd-based/私有内存等，最终还是更新 memslot([Ruach][3]) |
| `KVM_GET_DIRTY_LOG`                                             | `kvm_vm_ioctl` | 调用类似 `kvm_vm_ioctl_get_dirty_log()`；读取 memslot 脏页 bitmap([docs.kernel.org][1])       |
| `KVM_CLEAR_DIRTY_LOG`（受 `KVM_CAP_MANUAL_DIRTY_LOG_PROTECT2` 控制） | `kvm_vm_ioctl` | 清理/重新保护 memslot 的脏页信息                                                                |

#### 2.1.2 VCPU / 设备创建

| ioctl               | 顶层处理位置                                        | 常见 helper / 行为                                                                                         |
| ------------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `KVM_CREATE_VCPU`   | `kvm_vm_ioctl` → `kvm_vm_ioctl_create_vcpu()` | 分配 `struct kvm_vcpu`，做 arch 初始化，`anon_inode_getfd("[kvm-vcpu]", &kvm_vcpu_fops, vcpu, ...)` 返回 vcpu fd |
| `KVM_CREATE_DEVICE` | `kvm_vm_ioctl`                                | 创建 `struct kvm_device`，根据 type 选择设备驱动，再给你一个“device fd”，后续 `.ioctl` 走各个设备驱动自己的 fops                     |

#### 2.1.3 IRQchip / eventfd / 中断相关

| ioctl                | 顶层处理位置         | 常见 helper / 行为                                                                       |
| -------------------- | -------------- | ------------------------------------------------------------------------------------ |
| `KVM_CREATE_IRQCHIP` | `kvm_vm_ioctl` | 在 VM 中创建内核 irqchip（PIC+IOAPIC 或 APICv），设置 `kvm->arch.*` 中断相关状态([docs.kernel.org][1]) |
| `KVM_GET_IRQCHIP`    | `kvm_vm_ioctl` | 读取 in-kernel irqchip 状态到 `struct kvm_irqchip`                                        |
| `KVM_SET_IRQCHIP`    | `kvm_vm_ioctl` | 从 `struct kvm_irqchip` 写入 irqchip 状态                                                 |
| `KVM_IRQFD`          | `kvm_vm_ioctl` | 注册/注销 irqfd：把一个 eventfd 跟 GSI 绑定，用于用户态向 KVM 注入中断([lwn.net][4])                       |
| `KVM_IOEVENTFD`      | `kvm_vm_ioctl` | 注册/注销 ioeventfd：guest MMIO/PIO 访问某个地址时，向 eventfd 写事件                                 |

#### 2.1.4 计时器 / 时钟 / PIT

| ioctl                                           | 顶层处理位置         | 行为                                                              |
| ----------------------------------------------- | -------------- | --------------------------------------------------------------- |
| `KVM_SET_CLOCK` / `KVM_GET_CLOCK`               | `kvm_vm_ioctl` | 通过 `struct kvm_clock_data` 设置/读取墙钟/tsc 关系([docs.huihoo.com][5]) |
| `KVM_SET_PIT` / `KVM_GET_PIT2` / `KVM_SET_PIT2` | `kvm_vm_ioctl` | 操作 in-kernel PIT 状态                                             |

#### 2.1.5 其他 VM 级配置

| ioctl                                           | 顶层处理位置         | 说明                                                                    |
| ----------------------------------------------- | -------------- | --------------------------------------------------------------------- |
| `KVM_SET_NR_MMU_PAGES` / `KVM_GET_NR_MMU_PAGES` | `kvm_vm_ioctl` | 配置 shadow/EPT 页表使用的页数（历史遗留，更多是 debug/调优）                              |
| `KVM_SET_TSS_ADDR`                              | `kvm_vm_ioctl` | x86 专用，设置 TSS 地址，Intel 上必需([docs.kernel.org][1])                      |
| `KVM_SET_IDENTITY_MAP_ADDR`                     | `kvm_vm_ioctl` | x86 专用，设置 identity map 的 GPA，用于 real-mode 映射([docs.huihoo.com][5])    |
| `KVM_SET_BOOT_CPU_ID`                           | `kvm_vm_ioctl` | 指定哪个 vCPU 是 boot CPU                                                  |
| `KVM_ENABLE_CAP`（vm 版本）                         | `kvm_vm_ioctl` | 打开 VM 范围的某些 capability（`KVM_CAP_ENABLE_CAP_VM`）([docs.kernel.org][1]) |
| `KVM_CHECK_EXTENSION`（vm 版本）                    | `kvm_vm_ioctl` | 当 `KVM_CAP_CHECK_EXTENSION_VM` 支持时，可以对单个 VM 查询能力                      |

> **总的规律：**
>
> * 文档里标了 `Type: vm ioctl` 的那堆，**在 x86/6.7 上统统是：VM fd → `kvm_vm_ioctl()`**。
> * 真正的“状态修改”基本都集中在 `kvm_main.c` + `arch/x86/kvm/*` 里的一堆 helper 中；你做状态机提取，就直接在这些 helper 里找写 `kvm->*` / `kvm->arch.*` / memslots 的地方。

---

## 三、VCPU fd 的 fops：`kvm_vcpu_fops` → `kvm_vcpu_ioctl`

VCPU fd 同样通过匿名 inode 创建：

```c
static const struct file_operations kvm_vcpu_fops = {
    .owner          = THIS_MODULE,
    .unlocked_ioctl = kvm_vcpu_ioctl,
#ifdef CONFIG_COMPAT
    .compat_ioctl   = kvm_vcpu_compat_ioctl,
#endif
    .mmap           = kvm_vcpu_mmap,
    .release        = kvm_vcpu_release,
    .llseek         = noop_llseek,
};
```

**所有 `Type: vcpu ioctl` 的 ioctl，统一走：`kvm_vcpu_ioctl()`**，再根据情况委托给 `kvm_arch_vcpu_ioctl()`／`kvm_arch_vcpu_ioctl_run()` 等 x86 特定逻辑。([docs.kernel.org][1])

### 3.1 映射：vcpu ioctl → `kvm_vcpu_ioctl`（x86 常用）

#### 3.1.1 运行 / 事件类

| ioctl                 | 顶层处理位置           | 典型内部调用                                                                               |
| --------------------- | ---------------- | ------------------------------------------------------------------------------------ |
| `KVM_RUN`             | `kvm_vcpu_ioctl` | 调用 `kvm_arch_vcpu_ioctl_run(vcpu, kvm_run)` → 再下钻到 `vcpu_enter_guest()` / VMX/SVM 入口 |
| `KVM_NMI`             | `kvm_vcpu_ioctl` | 注入 NMI 到 vCPU（x86 特有）                                                                |
| `KVM_INTERRUPT`       | `kvm_vcpu_ioctl` | 入队一个硬件中断向量，通常调用 arch 层注入函数([docs.kernel.org][1])                                     |
| `KVM_SET_SIGNAL_MASK` | `kvm_vcpu_ioctl` | 设置运行时屏蔽哪些 host signal，会写 `vcpu->sigset` 等结构                                          |

#### 3.1.2 寄存器 / FPU / 调试

| ioctl                                     | 顶层处理位置                         | 行为                                                                       |
| ----------------------------------------- | ------------------------------ | ------------------------------------------------------------------------ |
| `KVM_GET_REGS` / `KVM_SET_REGS`           | `kvm_vcpu_ioctl` → arch helper | 读写通用寄存器 `struct kvm_regs`                                                |
| `KVM_GET_SREGS` / `KVM_SET_SREGS`         | 同上                             | 读写 `struct kvm_sregs`（段寄存器、CR0–CR4、EFER、GDT/IDT 等）([docs.kernel.org][1]) |
| `KVM_GET_FPU` / `KVM_SET_FPU`             | 同上                             | 读写 vCPU 的 FPU 状态                                                         |
| `KVM_GET_XSAVE` / `KVM_SET_XSAVE`（如果存在）   | 同上                             | 扩展状态（xsave 区）                                                            |
| `KVM_GET_XCRS` / `KVM_SET_XCRS`           | 同上                             | XCR0 等寄存器                                                                |
| `KVM_GET_DEBUGREGS` / `KVM_SET_DEBUGREGS` | 同上                             | 读写调试寄存器 DR0-DR7、调试控制位                                                    |
| `KVM_SET_GUEST_DEBUG`                     | `kvm_vcpu_ioctl`               | 配置单步、断点等 guest 调试行为                                                      |

#### 3.1.3 CPUID / MSR / 事件状态

| ioctl                                         | 顶层处理位置           | 行为                                                                                  |
| --------------------------------------------- | ---------------- | ----------------------------------------------------------------------------------- |
| `KVM_SET_CPUID` / `KVM_SET_CPUID2`            | `kvm_vcpu_ioctl` | 设置 vCPU CPUID 模型，影响来宾可见的 feature bits([docs.huihoo.com][5])                         |
| `KVM_GET_CPUID2`                              | 同上               | 读取当前 CPUID 模型                                                                       |
| `KVM_GET_MSRS` / `KVM_SET_MSRS`               | 同上               | 批量读写 MSR（通过 `struct kvm_msrs`）                                                      |
| `KVM_GET_VCPU_EVENTS` / `KVM_SET_VCPU_EVENTS` | `kvm_vcpu_ioctl` | 读写 pending exception/interrupt、NMI 状态等事件字段                                          |
| `KVM_GET_MP_STATE` / `KVM_SET_MP_STATE`       | `kvm_vcpu_ioctl` | 读写 AP 的启动状态（`RUNNABLE` / `INIT_RECEIVED` / `SIPI_RECEIVED` 等）([docs.kernel.org][1]) |

#### 3.1.4 其他 vCPU 能力相关

| ioctl                                 | 顶层处理位置           | 说明                                                      |
| ------------------------------------- | ---------------- | ------------------------------------------------------- |
| `KVM_ENABLE_CAP`（vcpu 版本）             | `kvm_vcpu_ioctl` | 启用 vCPU 级别的 capability（例如某些调试/性能计数器功能）                  |
| `KVM_GET_ONE_REG` / `KVM_SET_ONE_REG` | `kvm_vcpu_ioctl` | 统一的 “reg ID → 值” 接口，用来读写各种体系结构寄存器([docs.huihoo.com][5]) |

---

## 四、怎么用这些表来做你要的状态机 / fuzz 逻辑

你现在如果要从 6.7 源码里做 **ioctl 状态机**，可以这么用上面这些信息：

1. **先按 fd 类型切三块：**

   * system ioctl 集合 ⇒ `/dev/kvm` ⇒ `kvm_dev_ioctl`
   * vm ioctl 集合 ⇒ `VM fd` ⇒ `kvm_vm_ioctl`
   * vcpu ioctl 集合 ⇒ `VCPU fd` ⇒ `kvm_vcpu_ioctl`

   这些集合可以直接从文档里搜 `Type: system/vm/vcpu ioctl` 得到。([docs.kernel.org][1])

2. **在源码里 `git grep` ioctl 宏名，对齐到具体 case：**

   例如：

   ```bash
   # system
   git grep "KVM_CREATE_VM"      virt/kvm

   # vm
   git grep "KVM_SET_USER_MEMORY_REGION" virt/kvm arch/x86/kvm

   # vcpu
   git grep "KVM_RUN"            virt/kvm arch/x86/kvm
   ```

   你就能很快定位到 `switch (ioctl)` 的 case，和它调用的 helper。

3. **做状态机时，只需要关心“写状态的 helper”**：

   * `/dev/kvm` 层：几乎只有 `KVM_CREATE_VM` 会创建新 `struct kvm`，是一个重要状态转移。
   * `kvm_vm_ioctl` 层：

     * memslot 相关 ioctl 改变 `kvm->memslots`
     * vcpu/irqchip/irqfd/ioeventfd 相关 ioctl 改变 `kvm->vcpus[]`、`kvm->arch.irqchip_in_kernel` 等
   * `kvm_vcpu_ioctl` 层：

     * regs/sregs/MSR/CPUID 类 ioctl 改变 `vcpu->arch.*`
     * `KVM_RUN` 调用过程中大量内部状态变化（包括 vm-exit 处理），可以视为“运行边”

---

如果你接下来想要**更细一级**（比如：“帮我把 `kvm_vm_ioctl` 里所有 case，精确列成：`KVM_xxx → kvm_vm_ioctl_xxx()`”），我可以按你关心的那一层（system / vm / vcpu 任选一层），给你写一个更细的对照表 + 建议的 `git grep` 路线，方便你直接写脚本来做自动抽取。

[1]: https://docs.kernel.org/virt/kvm/api.html "The Definitive KVM (Kernel-based Virtual Machine) API Documentation — The Linux Kernel  documentation"
[2]: https://nvd.nist.gov/vuln/detail/CVE-2024-53105?utm_source=chatgpt.com "CVE-2024-53105 Detail - NVD"
[3]: https://ruach.github.io/posts/QEMU-KVM-ADDRESS-SPACE/?utm_source=chatgpt.com "QEMU Side Memory Management for VM with RAMBLOCK"
[4]: https://lwn.net/Articles/332924/?utm_source=chatgpt.com "kvm: add support for irqfd"
[5]: https://docs.huihoo.com/doxygen/linux/kernel/3.7/include_2uapi_2linux_2kvm_8h.html?utm_source=chatgpt.com "Linux Kernel: include/uapi/linux/kvm.h File Reference - Huihoo"
