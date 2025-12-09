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
