下面用一个**极简但“对源码友好”的图**，把 **kvm_chardev_ops / kvm_vm_fops / kvm_vcpu_fops / kvm_device_fops** 之间的 **fd 派生与 ioctl 逻辑**画清楚。
这是**按你现在正在读的 Linux 6.7 KVM 源码结构**来的。

---

## 一、fd 派生关系图（“谁创建谁”）

```
userspace
   |
   | open("/dev/kvm")
   v
+----------------------+
|  /dev/kvm fd         |
|  fops:               |
|    kvm_chardev_ops   |
|  ioctl:              |
|    kvm_dev_ioctl()   |
+----------------------+
           |
           | ioctl: KVM_CREATE_VM
           |   (anon_inode_getfd)
           v
+----------------------+
|  VM fd               |
|  fops:               |
|    kvm_vm_fops       |
|  private_data: kvm* |
|  ioctl:              |
|    kvm_vm_ioctl()   |
+----------------------+
        |                    |
        |                    |
        | ioctl:             | ioctl:
        | KVM_CREATE_VCPU    | KVM_CREATE_DEVICE
        | (anon_inode_getfd) | (anon_inode_getfd)
        v                    v
+------------------+    +---------------------+
|  vCPU fd         |    |  device fd          |
|  fops:           |    |  fops:              |
|    kvm_vcpu_fops |    |    kvm_device_fops  |
|  private_data:   |    |  private_data: dev* |
|    vcpu*         |    |  ioctl:             |
|  ioctl:          |    |    kvm_device_ioctl |
|    kvm_vcpu_ioctl|
+------------------+    +---------------------+
```

---

## 二、把图和“代码路径”一一对上

### 1️⃣ `/dev/kvm fd`

* **哪里来的**：`open("/dev/kvm")`
* **fops**：`kvm_chardev_ops`
* **关键 ioctl**：`KVM_CREATE_VM`
* **源码位置**：

  * `virt/kvm/kvm_main.c`
  * `kvm_dev_ioctl()`

**作用一句话**：

> 只是一个“控制入口 fd”，不代表任何 VM。

---

### 2️⃣ `VM fd`

* **哪里来的**：
  `/dev/kvm fd` 上 `ioctl(KVM_CREATE_VM)`
* **fops**：`kvm_vm_fops`
* **private_data**：`struct kvm *`
* **关键 ioctl**：

  * `KVM_SET_USER_MEMORY_REGION`
  * `KVM_CREATE_VCPU`
  * `KVM_CREATE_IRQCHIP`
  * `KVM_CREATE_DEVICE`
* **源码位置**：

  * `kvm_dev_ioctl_create_vm()`
  * `kvm_vm_ioctl()`

**作用一句话**：

> **一台虚拟机本身**，所有资源（内存 / vcpu / 设备）都从它派生。

---

### 3️⃣ `vCPU fd`

* **哪里来的**：
  `vm_fd` 上 `ioctl(KVM_CREATE_VCPU)`
* **fops**：`kvm_vcpu_fops`
* **private_data**：`struct kvm_vcpu *`
* **关键 ioctl**：

  * `KVM_RUN`
  * `KVM_SET_REGS / GET_REGS`
  * `KVM_SET_CPUID2`
* **特殊点**：

  * `mmap(vcpu_fd)` → `struct kvm_run`
* **源码位置**：

  * `kvm_vm_ioctl_create_vcpu()`
  * `kvm_vcpu_ioctl()`

**作用一句话**：

> **一颗 CPU**，真正“跑 guest 指令”的地方。

---

### 4️⃣ `device fd`

* **哪里来的**：
  `vm_fd` 上 `ioctl(KVM_CREATE_DEVICE)`
* **fops**：`kvm_device_fops`
* **private_data**：`struct kvm_device *`
* **关键 ioctl**：

  * device-specific ioctl / attr
* **源码位置**：

  * `kvm_ioctl_create_device()`
  * `kvm_device_ioctl()`

**作用一句话**：

> **VM 内的一个内核设备对象**，把复杂设备从 VM ioctl 里拆出来。

---

## 三、把“fd 操作顺序”也画出来（时间轴）

```
open("/dev/kvm")
    |
    |-- ioctl(KVM_CREATE_VM) ------------------> vm_fd
    |                                             |
    |                                             |-- ioctl(KVM_SET_USER_MEMORY_REGION)
    |                                             |
    |                                             |-- ioctl(KVM_CREATE_IRQCHIP)
    |                                             |
    |                                             |-- ioctl(KVM_CREATE_VCPU) ------> vcpu_fd
    |                                             |                                  |
    |                                             |                                  |-- mmap(vcpu_fd) -> kvm_run
    |                                             |                                  |
    |                                             |                                  |-- ioctl(KVM_RUN)
    |                                             |
    |                                             |-- ioctl(KVM_CREATE_DEVICE) ----> device_fd
```

---

## 四、从你“做状态机”的角度怎么用这张图

你可以直接把这张图当成 **三层 + 一支叉的状态机骨架**：

* **system 层**：`/dev/kvm fd`

  * 状态：`no_vm → vm_created`
* **vm 层**：`vm_fd`

  * 状态：`mem=0 → mem>0`
  * 状态：`vcpu=0 → vcpu>=1`
  * 状态：`irqchip=none → in-kernel`
* **vcpu 层**：`vcpu_fd`

  * 状态：`not_run → running`
* **device 层**：`device_fd`

  * 状态：device-specific

---

### 一句话总总结（记住这个就够了）

> **KVM 用“ioctl 创建新 fd”的方式，把 system → VM → vCPU / device 串成一棵 fd 树；
> 读源码时，永远先看“这个 fd 是谁创建的”，就能立刻知道它的 fops、private_data 和能改哪些状态。**

如果你愿意，我可以下一步直接帮你把这张图 **翻译成 DOT / Mermaid**，或者按你之前的需求，直接给你一个“按 fd 分层的 ioctl 状态机模板”。
