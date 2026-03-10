下面给你一个**最小 KVM ioctl 调用示例**，演示典型的 x86 用户态流程：

* 打开 `/dev/kvm`
* `KVM_GET_API_VERSION`
* `KVM_CREATE_VM`
* `KVM_CREATE_VCPU`
* `KVM_GET_VCPU_MMAP_SIZE` + `mmap`
* 简单跑一次 `KVM_RUN`

> 注：这个例子只演示 ioctl 调用流程，并没有真正加载 guest 代码或设置内存映射，适合作为你做状态机/ fuzz 的骨架代码。

```c
// kvm_ioctl_example.c
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <errno.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/mman.h>

#include <linux/kvm.h>   // 关键：KVM_* ioctl 号定义

static void die(const char *msg)
{
    perror(msg);
    exit(EXIT_FAILURE);
}

int main(void)
{
    int kvm_fd = -1;
    int vm_fd  = -1;
    int vcpu_fd = -1;
    int ret;

    // 1. 打开 /dev/kvm
    kvm_fd = open("/dev/kvm", O_RDWR | O_CLOEXEC);
    if (kvm_fd < 0)
        die("open /dev/kvm");

    printf("[+] /dev/kvm opened, fd=%d\n", kvm_fd);

    // 2. 获取 KVM API 版本
    int api_version = ioctl(kvm_fd, KVM_GET_API_VERSION, 0);
    if (api_version < 0)
        die("ioctl KVM_GET_API_VERSION");

    printf("[+] KVM_GET_API_VERSION = %d\n", api_version);

    if (api_version != KVM_API_VERSION) {
        fprintf(stderr, "[-] Unsupported KVM api version: %d (expected %d)\n",
                api_version, KVM_API_VERSION);
        exit(EXIT_FAILURE);
    }

    // 3. 创建 VM：KVM_CREATE_VM 在 /dev/kvm 上调用
    vm_fd = ioctl(kvm_fd, KVM_CREATE_VM, (unsigned long)0);
    if (vm_fd < 0)
        die("ioctl KVM_CREATE_VM");
    printf("[+] VM created, vm_fd=%d\n", vm_fd);

    // 这里一般会对 VM 做一些设置：内存映射、IRQ、x86 特定 MSR 等
    // 为了简单，我们只展示 VCPU 创建和 KVM_RUN。

    // 4. 创建 VCPU：在 vm_fd 上调用 KVM_CREATE_VCPU
    int vcpu_index = 0;  // 第 0 个 vcpu
    vcpu_fd = ioctl(vm_fd, KVM_CREATE_VCPU, (unsigned long)vcpu_index);
    if (vcpu_fd < 0)
        die("ioctl KVM_CREATE_VCPU");
    printf("[+] VCPU created, vcpu_fd=%d (index=%d)\n", vcpu_fd, vcpu_index);

    // 5. 获取 VCPU run 结构 mmap 大小（在 kvm_fd 上）
    int vcpu_mmap_size = ioctl(kvm_fd, KVM_GET_VCPU_MMAP_SIZE, 0);
    if (vcpu_mmap_size < 0)
        die("ioctl KVM_GET_VCPU_MMAP_SIZE");
    printf("[+] VCPU mmap size: %d bytes\n", vcpu_mmap_size);

    // 6. mmap vcpu 的共享运行结构体 struct kvm_run
    struct kvm_run *run = mmap(NULL, vcpu_mmap_size,
                               PROT_READ | PROT_WRITE, MAP_SHARED,
                               vcpu_fd, 0);
    if (run == MAP_FAILED)
        die("mmap kvm_run");

    printf("[+] kvm_run mapped at %p\n", run);

    // 此处通常要：
    //   - KVM_SET_USER_MEMORY_REGION
    //   - KVM_SET_REGS / KVM_SET_SREGS
    // 把 guest code / 数据放到内存，然后设置 RIP/RSP 等寄存器。
    // 为了演示 ioctl 状态机，我们直接调用一次 KVM_RUN。

    printf("[+] Calling KVM_RUN once (guest state is uninitialized, "
           "we only看一下 exit reason)\n");

    ret = ioctl(vcpu_fd, KVM_RUN, 0);
    if (ret < 0) {
        // 大概率是因为 guest 没有合法内存 / 代码，但我们只看 exit_reason
        perror("ioctl KVM_RUN (expected to fail for demo)");
    }

    printf("[+] KVM_RUN exit_reason = %d\n", run->exit_reason);

    switch (run->exit_reason) {
    case KVM_EXIT_HLT:
        printf("    -> Guest EXIT: HLT\n");
        break;
    case KVM_EXIT_IO:
        printf("    -> Guest EXIT: IO (port = 0x%x, size = %d)\n",
               run->io.port, run->io.size);
        break;
    case KVM_EXIT_FAIL_ENTRY:
        printf("    -> Guest EXIT: FAIL_ENTRY, hardware_entry_failure_reason=0x%llx\n",
               (unsigned long long)run->fail_entry.hardware_entry_failure_reason);
        break;
    default:
        printf("    -> Guest EXIT: other (%d)\n", run->exit_reason);
        break;
    }

    // 7. 资源清理：正常流程中通常还会有更多 ioctl，如 KVM_SET_TSS_ADDR、MSR 设置等
    munmap(run, vcpu_mmap_size);
    close(vcpu_fd);
    close(vm_fd);
    close(kvm_fd);

    printf("[+] done.\n");
    return 0;
}
```

编译 & 运行（在 x86_64 Linux 上）：

```bash
gcc -Wall -O2 kvm_ioctl_example.c -o kvm_ioctl_example
sudo ./kvm_ioctl_example
```

---

如果你后续需要的是**更完整的 x86 guest 初始化过程**（包括 `KVM_SET_USER_MEMORY_REGION`、设置 `CR0/CR4/EFER`、加载 GDT/IDT 等），我可以基于这个骨架再给你一个“可真正跑一条指令/HLT”的完整版 demo，方便你对照构造 ioctl 状态机。

另外，你之前 NPU 驱动里通过 `file->private_data` 保存会话上下文、再由 `.ioctl` 分派到不同操作的模式，其实和 KVM 在 `vm_fd` / `vcpu_fd` 层次的设计思路是类似的，都是“fd + ioctl 驱动状态机”的形态，可直接类比做 fuzz 设计。 



我先把「**官方/半官方、而且偏 x86 的 KVM userspace consumer**」系统地按代码路径列一遍，你可以直接 `grep ioctl` 或 `strace -e ioctl` 来抽状态机用。

---

## 一、Linux 内核源码树里的 KVM consumer

### 1. kselftests：`tools/testing/selftests/kvm/`

这是你最应该盯紧的一块 —— 内核维护者自己要求 KVM 改动必须跑 selftests + kvm-unit-tests。([内核文档][1])

在内核源码根目录下：

* 目录：`tools/testing/selftests/kvm/`([安卓源代码][2])
  重要子目录：

  * `x86_64/`：**x86 KVM 自测用例主目录**

    * 包含大量 C 测试程序，比如：

      * `vmx_apic_access_test.c`
      * `xapic_ipi_test.c`
      * `dirty_log_test.c`
      * `demand_paging_test.c`
      * `coalesced_io_test.c`
        等等，都在 `tools/testing/selftests/kvm/x86_64/` 下。([安卓源代码][2])
  * `lib/`：自测公用库（对 `/dev/kvm` 的封装）

    * `tools/testing/selftests/kvm/lib/kvm_util.c`：封装 VM/VCpu 创建、`KVM_CREATE_VM` / `KVM_CREATE_VCPU` / mmap 等操作，是 **ioctl 的集中入口**。([Lxr][3])
    * `tools/testing/selftests/kvm/lib/` 下还有 `vmx.c`、`svm.c` 等硬件特性辅助代码。
  * `lib/x86_64/`：x86 特定 helper（paging、GDT/IDT 布局、寄存器设置等）。([GitLab][4])
  * `include/`、`include/x86_64/`：各种 test-side 头文件，里边会出现很多和 vCPU 状态密切相关的数据结构。

> **对你做状态机抽取最有价值的地方：**
>
> * `lib/kvm_util.c` 里所有 `ioctl` 封装函数。
> * `x86_64/` 下每个测试的 `main()`，看它们是如何按序列调用 `vm_create_with_one_vcpu`、`vm_vcpu_add`、`vm_vcpu_run`、`vm_get_register` 等。

---

### 2. KVM 统计工具：`tools/kvm/kvm_stat/`

虽然 `kvm_stat` 主要是通过 debugfs/tracepoints 看 KVM 事件，不是典型「ioctl consumer」，但它是 **KVM 官方自带的用户态工具**，也在 Linux 源码树里。([linux-kvm.org][5])

* 目录：`tools/kvm/kvm_stat/`
  典型文件：([git.ti.com][6])

  * `tools/kvm/kvm_stat/kvm_stat`：Python 脚本（较新内核是 Python 版本），读 `/sys/kernel/debug/kvm/` 或 tracepoints。
  * `tools/kvm/kvm_stat/kvm_stat.txt`：使用说明(man 文本)。
  * `tools/kvm/kvm_stat/Makefile`：构建脚本。
  * 某些发行版还有 `kvm_stat.service` systemd 单元，用来后台采样。([android.googlesource.com][7])

> 这个对于**理解 KVM exit reason / vm-exit 路径**很有用，但不直接给 `/dev/kvm` 的状态机。你可以把它当成「辅助观测工具」，和你的 fuzz driver 一起跑。

---

## 二、内核外、官方推荐的 KVM 测试框架（x86 支持最好）

### 3. kvm-unit-tests（独立仓库）

这是另一个「官方推荐必须跑」的测试框架，**完全是 userspace**，但它自己又会构造 guest image，在 guest 里跑几十行 C/asm 作为用例。([linux-kvm.org][8])

* 官方页面：`linux-kvm.org -> KVM-unit-tests`([linux-kvm.org][8])
* 仓库（当前主用）：`https://gitlab.com/kvm-unit-tests/kvm-unit-tests.git` ([about.gitlab.com][9])

**仓库里的 x86 相关路径：**

根目录（参考 GitHub / GitLab 镜像）([GitHub][10])

* `x86/`

  * x86 专用的测试源码与链接脚本（各类 `.c` / `.S` + `Makefile.common`）。
  * 编译后的测试镜像通常是：`x86/*.flat`。
* `x86-run`

  * 运行 x86 测试的脚本，会调用 QEMU 并开启 `-accel kvm`，典型用法：

    * `./x86-run ./x86/msr.flat`([linux-kvm.org][8])
* `lib/`

  * 公共运行时库（libcflat 等）：

    * `lib/`：架构无关部分。
    * `<ARCH> 专用子目录`（新版本中会拆到 `lib/x86/` 等）。([linux-kvm.org][11])
* 其它你可能关心的文件：

  * `config-x86-common.mak`, `config-x86_64.mak`：编译配置。([GitHub][10])
  * `unittests.cfg`：列出每个架构要跑的 test 列表。

> **从状态机视角怎么用：**
>
> * Host 侧：`x86-run` + `run_tests.sh` 只是调 QEMU，本身 ioctl 不多。
> * 真正和 `/dev/kvm` 打交道的是 QEMU，所以如果你要抽「全栈」状态机，可以：
>
>   * 用 `kvm-unit-tests` 驱动 QEMU；
>   * 对 QEMU 进程做 `strace -f -e trace=ioctl`，收集 `/dev/kvm` 的序列；
>   * 再和你从 kernel 源码抽出来的状态机比对。

---

## 三、生产级 VMM consumer：QEMU（带 KVM 加速）

KVM 官方文档一般把 **QEMU** 看作主要 userspace VMM，所有 `/dev/kvm` ioctl 都从这里发出。([维基百科][12])

* 仓库：`https://gitlab.com/qemu-project/qemu` ([qemu.org][13])

对 **x86 + KVM** 最关键的几个目录：

1. `accel/kvm/`

   * 通用 KVM 加速器框架：

     * `accel/kvm/kvm-all.c`
     * `include/sysemu/kvm_int.h`（或 `include/system/kvm.h`）等([qemu.org][13])
   * 里面可以看到：

     * `kvm_ioctl()`, `kvm_vm_ioctl()`, `kvm_vcpu_ioctl()` 等包装函数；
     * 建立 VM/VCpu、设置内存、注册设备的公共路径。

2. `target/i386/` 目录下的 KVM 相关代码

   * 典型文件：

     * 旧版本：`target/i386/kvm.c`([GitLab][14])
     * 新版本：KVM 相关逻辑可能拆到 `target/i386/` 子目录中（`kvm/pmu`, `kvm/hyperv` 等），配合 `accel/kvm/kvm-all.c`。([GitHub][15])
   * 这里面是「x86 架构层面对 KVM UAPI 的使用」：

     * 设置 CPUID：`KVM_SET_CPUID2`；
     * 配置 MSR：`KVM_SET_MSRS`；
     * 建立 vCPU 寄存器初始状态：`KVM_SET_REGS`、`KVM_SET_SREGS`；
     * 配置 PMU、debug 特性等 ioctl。([Stack Overflow][16])

> 如果你只想抽「**/dev/kvm 的 ioctl 状态机**」，建议：
>
> * 在 QEMU 中限定 `-accel kvm`，尽量关闭其它复杂设备；
> * 在跑简单 guest（比如只跑 `kvm-unit-tests` 的某个用例）时抓 `strace -f -e trace=ioctl`；
> * 从 `target/i386/kvm*.c`、`accel/kvm/kvm-all.c` 这几个文件里，对照具体调用点，反推状态变量。

---

## 四、轻量级 VMM：kvmtool（lkvm）

这货虽然不在内核树里，但和 KVM 高度「一对一绑定」，结构极简单，非常适合你**反推出一个最小的 KVM ioctl 状态机**。([redhat.com][17])

* 仓库：`https://github.com/kvmtool/kvmtool` ([GitHub][18])
* 特点：

  * 只支持同架构虚拟化（x86 host→x86 guest），天然适合你在 QEMU/x86 上跑。
  * 没有像 QEMU 那样复杂的设备模型代码，读起来轻松很多。
* 关键文件（以当前版本为例）：

  * 顶层目录下的 `kvm.c`, `machine/*.c` 等，里面大量直接调用 `ioctl(vm_fd, KVM_*)`。

---

## 小结：如果你只关心「从哪开始下手」：

**优先级建议：**

1. **内核树 kselftests（强烈推荐）：**

   * `tools/testing/selftests/kvm/lib/kvm_util.c`
   * `tools/testing/selftests/kvm/x86_64/*.c`

2. **轻量 VMM kvmtool：**

   * 整个 `kvmtool` 仓库，重点看 `ioctl` 调用路径。

3. **生产 VMM QEMU（针对 x86）：**

   * `accel/kvm/kvm-all.c`
   * `target/i386/kvm.c` / `target/i386/kvm/*`

4. **配合 kvm-unit-tests 作为驱动 workload：**

   * 仓库根目录：

     * `x86/` + `x86-run`
     * `lib/`（运行时）

---

如果你愿意，我下一步可以帮你**选一个具体文件（比如 `kvm_util.c` 或 `target/i386/kvm.c`）**，直接按函数级别把「哪些 ioctl、对应哪些逻辑状态」梳成一张初始状态机草图，方便你跟内核中的 bitmask 状态机对接。

[1]: https://docs.kernel.org/process/maintainer-kvm-x86.html?utm_source=chatgpt.com "5. KVM x86"
[2]: https://android.1.googlesource.com/kernel/common/%2B/0f8e26b38d7ac72b3ad764944a25dd5808f37a6e/tools/testing/selftests/kvm/?utm_source=chatgpt.com "tools/testing/selftests/kvm - kernel/common"
[3]: https://lxr.missinglinkelectronics.com/linux/tools/testing/selftests/kvm/lib/kvm_util.c?utm_source=chatgpt.com "LXR linux/tools/testing/selftests/kvm/lib/kvm_util.c"
[4]: https://gitlab.sdu.dk/sdurobotics/linux-kernels/kernel/-/tree/3c24d247a86bb82cf89e640a241696387203ef0e/tools/testing/selftests/kvm/lib/x86_64?utm_source=chatgpt.com "tools/testing/selftests/kvm/lib/x86_64"
[5]: https://www.linux-kvm.org/page/Perf_events?utm_source=chatgpt.com "Perf events"
[6]: https://git.ti.com/cgit/ti-linux-kernel/ti-linux-kernel/plain/tools/kvm/kvm_stat/?h=10.00.07-rt&id=f78271dfb77353c4d045f9735deebe21839fb2ed&utm_source=chatgpt.com "/tools/kvm/kvm_stat/"
[7]: https://android.googlesource.com/kernel/common/%2B/445019bbca5d8/tools/kvm/kvm_stat/kvm_stat.service?utm_source=chatgpt.com "tools/kvm/kvm_stat/kvm_stat.service - kernel/common"
[8]: https://www.linux-kvm.org/page/KVM-unit-tests?utm_source=chatgpt.com "KVM-unit-tests"
[9]: https://gitlab.com/kvm-unit-tests/kvm-unit-tests?utm_source=chatgpt.com "KVM-Unit-Tests"
[10]: https://github.com/columbia/kvm-unit-tests?utm_source=chatgpt.com "columbia/kvm-unit-tests"
[11]: https://www.linux-kvm.org/images/5/5f/03x05-Aspen-Andrew_Jones_kvm_unit_tests.pdf?utm_source=chatgpt.com "KVM-UNIT-TESTS"
[12]: https://en.wikipedia.org/wiki/Kernel-based_Virtual_Machine?utm_source=chatgpt.com "Kernel-based Virtual Machine"
[13]: https://www.qemu.org/docs/master/devel/codebase.html?utm_source=chatgpt.com "Codebase — QEMU documentation"
[14]: https://gitlab.uni-freiburg.de/opensourcevdi/qemu/-/blob/v2.11.0-rc5/target/i386/kvm.c?utm_source=chatgpt.com "target/i386/kvm.c · v2.11.0-rc5 - Qemu"
[15]: https://github.com/qemu/qemu/blob/master/target/i386/machine.c?utm_source=chatgpt.com "qemu/target/i386/machine.c at master"
[16]: https://stackoverflow.com/questions/66277749/how-do-i-get-every-supported-cpu-flags-as-qemu-cpu-flags?utm_source=chatgpt.com "How do I get every supported CPU flags as QEMU ..."
[17]: https://www.redhat.com/en/blog/all-you-need-know-about-kvm-userspace?utm_source=chatgpt.com "All you need to know about KVM userspace"
[18]: https://github.com/kvmtool/kvmtool?utm_source=chatgpt.com "kvmtool/kvmtool: Stand-alone Native Linux KVM Tool repo"
