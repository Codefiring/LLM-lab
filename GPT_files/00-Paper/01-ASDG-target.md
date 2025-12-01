我先说结论：

* 我**能给出一份比较完整的“dev_*.txt → 设备名”的列表**，但因为 GitHub 网页本身有点难一次性抓全目录，这个列表是「尽量完整 + 少量推断」版，有可能漏一两个非常偏门的 description。
* 在这些设备里，**非常适合作为“ioctl 状态机 fuzzing”目标的那批**我会特别用 ⭐ 标出来。

下面分两步：先列设备名，再标哪些 ioctl 很可能存在明显状态机。

---

## 1. sys/linux 里 Linux 设备 description 的设备名列表（dev_*.txt 系列）

这里主要按 **syzkaller/sys/linux/dev_*.txt** 来列，对应的典型 `/dev/...` 名称（有些是子目录或通配符）。

> 说明：前一部分是直接从当前 upstream 目录解析到的 dev_*.txt，后一部分是上游文档/博客里明确提到但目录页没列全、但在当前 syzkaller 树里仍然存在或曾长期存在的 dev_*.txt（比如 dev_random, dev_ptmx, dev_video4linux 等）。([GitHub][1])

### 1.1 直接在目录中看到的 dev_*.txt

这些都是在 `sys/linux` 目录页能直接看到的文件名：([GitHub][1])

* **dev_ashmem.txt** → `/dev/ashmem`（Android 共享内存）
* **dev_bifrost.txt** → Bifrost GPU 设备（典型是 Mali Bifrost，/dev 名称厂商相关）
* **dev_binder.txt** → `/dev/binder`, `/dev/hwbinder`, `/dev/vndbinder`
* **dev_binderfs.txt** → binderfs 下的 binder 设备（挂载点内的 `/dev/binder` 风格节点）
* **dev_block.txt** → 各种块设备（syzkaller 通过 syz_open_dev 打开 `/dev/sdX`, `/dev/nvme*` 一类）([GitHub][2])
* **dev_bus_usb.txt** → `/dev/bus/usb/*`（USB 总线设备）
* **dev_camx.txt** → 高通 CAMX 摄像头设备（/dev 名称平台相关）
* **dev_cdrom.txt** → `/dev/cdrom`, `/dev/sr0` 等 CD-ROM 块设备
* **dev_cec.txt** → `/dev/cec*`（HDMI CEC 控制）
* **dev_char_usb.txt** → 一些字符类 USB 设备（如 `/dev/ttyACM*` 等，通过抽象接口）
* **dev_dma_heap.txt** → `/dev/dma_heap/*`（DMA-HEAP 内存分配器）([GitHub][3])
* **dev_dri.txt** → `/dev/dri/card*`, `/dev/dri/renderD*`（DRM core）
* **dev_dsp.txt** → `/dev/dsp` 等（OSS/音频兼容接口）
* **dev_fb.txt** → `/dev/fb*`（framebuffer）
* **dev_floppy.txt** → `/dev/fd*`（软盘）
* **dev_hidraw.txt** → `/dev/hidraw*`（原始 HID）
* **dev_i2c.txt** → `/dev/i2c-*`（I²C 总线）([Google Groups][4])
* **dev_i915.txt** → Intel i915 DRM 设备（/dev/dri/card*，专门的 i915 UAPI）
* **dev_img_rogue.txt** → Imagination Rogue GPU 设备
* **dev_infiniband_rdma.txt** → `/dev/infiniband/rdma_cm` 等 RDMA 控制节点
* **dev_infiniband_rdma_cm.txt** → 更细粒度的 RDMA CM 设备
* **dev_input.txt** → `/dev/input/event*`, `/dev/input/js*` 等输入设备
* **dev_iommu.txt** → 一些 IOMMU 控制设备（根据平台不同）
* **dev_kvm.txt** → `/dev/kvm`（KVM 虚拟化接口）([Linux Kernel Archives][5])
* **dev_kvm_arm64.txt** → ARM64 特定的 /dev/kvm 接口扩展
* **dev_loop.txt** → `/dev/loop*`（loop 设备）([man7.org][6])
* **dev_mali.txt** → `/dev/mali*`（另一类 Mali GPU）
* **dev_media.txt** → `/dev/media*`（media controller）
* **dev_msm.txt** → 高通 MSM（display/camera 等 SoC 设备）
* **dev_msr.txt** → `/dev/cpu/*/msr`（MSR 寄存器访问）

### 1.2 通过文档/其他镜像确认存在或曾长期存在的 dev_*.txt

这些在博客、分析工具、Android/fuchsia syzkaller 镜像、或 syz-analyzer 等里明确出现，并与 upstream syzkaller 同步或只做轻量修改。([Kiprey's Blog][7])

* **dev_nbd.txt** → `/dev/nbd*`（Network Block Device）([GitLab][8])
* **dev_random.txt** → `/dev/random`, `/dev/urandom`（随机数设备）([blingbling's blog][9])
* **dev_ptmx.txt** → `/dev/ptmx`，通过 ioctl 操作 TTY/终端属性 ([Android Git Repositories][10])
* **dev_video4linux.txt** → `/dev/video*`, `/dev/v4l-subdev*`（V4L2 视频/子设备）([GitLab][11])
* **dev_trusty.txt** → `/dev/trusty-ipc`（Android Trusty TEE IPC）([GitHub][12])
* **dev_ion.txt** → `/dev/ion`（旧的 Android ION 分配器，内核已移除但 syzkaller 仍保留描述一段时间）([Kiprey's Blog][7])
* **dev_tlk_device.txt** → `/dev/tlk_device`（Android/Qualcomm TEE 相关）([Kiprey's Blog][7])
* **dev_watch_queue.txt** → Linux watch queue 设备/接口（不是传统 /dev 节点，但 syzkaller 以 dev_ 前缀描述）([Kiprey's Blog][7])

> 此外，还有一些「不是 dev_ 前缀但也是具体设备」的描述文件，例如：
>
> * `uinput.txt` → `/dev/uinput`（虚拟输入设备）([邮件归档][13])
> * 早期的 `input.txt` / `acpi_thermal_rel.txt` 等，更多是子系统接口而不是单一设备节点。

---

## 2. 哪些设备的 ioctl 很可能存在“状态机”（需要特定调用顺序）

这里我用一个简单标记：

* ⭐ **强状态机**：典型需要严格的 ioctl 调用顺序 / 多级对象创建，天然适合做状态机抽象和依赖分析；
* △ **中等状态 / 配置型**：有一定顺序或资源生命周期，但不如上面那么复杂；
* – **基本无复杂状态机**：更多是单次配置/查询，或少数 flag，不太值得做复杂状态机建模（除非你想做“很细”的行为模型）。

### 2.1 ⭐ 强状态机类（非常推荐做 ioctl 状态机）

**虚拟化 / VM：**

* ⭐ **dev_kvm.txt / dev_kvm_arm64.txt → /dev/kvm**

  KVM UAPI 本身就是典型的层级状态机：

  * `open("/dev/kvm")` → `KVM_CREATE_VM` → 得到 VM fd
  * VM fd 上：`KVM_SET_USER_MEMORY_REGION`、`KVM_CREATE_VCPU` 等
  * vCPU fd 上再有 run、调试等 ioctl。这个流程在官方 KVM API 文档和 LWN 教程里写得很清楚：`/dev/kvm` fd → `KVM_CREATE_VM` → VM fd → `KVM_CREATE_VCPU` 等。([Linux Kernel Archives][5])

  👉 **结论**：KVM 是「多级资源 + 严格顺序」的典型，非常适合你要做的那种 ioctl 状态机挖掘/ground truth 构建。

---

**GPU / 显示：DRM & 专用 GPU 驱动**

* ⭐ **dev_dri.txt → /dev/dri/card*, /dev/dri/renderD***
* ⭐ **dev_i915.txt → Intel i915 特定 UAPI**
* ⭐ **dev_mali.txt / dev_bifrost.txt / dev_img_rogue.txt → 各家 GPU 设备**

  DRM UAPI 中：

  * 有 **对象创建/销毁**（buffer object、context、FB、plane…）；
  * 有 **mode setting / atomic commit** 这种必须按顺序设置参数之后再提交的语义；
  * 很多 ioctl 都要求「先前 setup 完成后才有效」。官方 DRM 用户态接口文档明确提到大量 ioctl 行为、错误码等，体现出强状态性。([Linux内核文档][14])

  👉 **结论**：DRM/GPU 设备和 KVM 一样，是“高级状态机”的富矿。

---

**多媒体 / 摄像头 / 视频：V4L2 & Media Controller**

* ⭐ **dev_media.txt → /dev/media***
* ⭐ **dev_video4linux.txt → /dev/video*, /dev/v4l-subdev***
* ⭐ **dev_camx.txt / dev_msm.txt**（高通 camera/display 子系统）

  V4L2+Media 的 ioctl 使用几乎是教科书级状态机：

  * 流式 IO：`VIDIOC_REQBUFS` → `VIDIOC_QUERYBUF` → `VIDIOC_QBUF` → `VIDIOC_STREAMON` → … → `VIDIOC_STREAMOFF`
  * 控制接口：控制 ID、查询、设置；以及「stateful/stateless decoder」文档中清楚给出期望的调用序列。([DRI Wiki][15])

  👉 **结论**：非常值得用你已有的“状态语句提取框架”做精细状态机，特别是 memory-to-memory 编码/解码的那几条路径。

---

**块设备框架 / 虚拟块设备**

* ⭐ **dev_loop.txt → /dev/loop***
* ⭐ **dev_nbd.txt → /dev/nbd***
* △ **dev_block.txt → 泛化的块设备接口**

  以 loop 为例，manpage / 提案里明确说过：

  * 传统使用：`LOOP_SET_FD` → `LOOP_SET_STATUS`/`LOOP_CONFIGURE`，中间存在窗口和竞态问题；
  * 新的 `LOOP_CONFIGURE` 是为了「一次性原子配置」，避免中间状态。([man7.org][6])

  NBD 也有“设置参数/连接/断开”的多步流程。

  👉 **结论**：loop/nbd 都是“带配置状态 + 生命周期”的块设备，对状态机 fuzz 很友好（而且在 QEMU 里很好跑）。

---

**RDMA / InfiniBand**

* ⭐ **dev_infiniband_rdma.txt / dev_infiniband_rdma_cm.txt → /dev/infiniband/rdma_cm 等**

  RDMA CM + QP 管理天生是状态机（IDLE→ADDR_RESOLVED→ROUTE_RESOLVED→CONNECTED…），各类 create/modify/destroy ioctl 之间有严格依赖，只是 syzkaller 的描述可能没完全覆盖所有复杂性。

---

**IOMMU / TrustZone / Android TEE**

* ⭐ **dev_iommu.txt**
* ⭐ **dev_trusty.txt**
* ⭐ **dev_tlk_device.txt**
* △ **dev_ashmem.txt / dev_ion.txt / dev_dma_heap.txt**

  这些接口通常有「创建句柄 → 配置属性 → 映射/解除映射 → 销毁」的典型生命周期，是非常自然的状态机模型（只是文档不像 KVM/V4L2 那么详细，需要按你之前的方法从 driver 源码提取）。

---

### 2.2 △ 中等状态 / 配置型（有状态，但比上面简单）

* △ **dev_cdrom.txt** → tray 打开/关闭、音频控制、介质状态等 ioctl，有一些顺序依赖，但更多是“控制命令集合”。
* △ **dev_floppy.txt** → 格式化/参数设定/探测，存在配置生命周期，但现代环境较少使用。
* △ **dev_input.txt / dev_hidraw.txt** → 有「设置模式/特性」一类的 ioctl，但总体更偏向配置 + event 读取。
* △ **dev_i2c.txt** → 设置 slave 地址、功能标志，然后做读写/SMBus 操作，一般是「轻量状态机」。
* △ **dev_msr.txt** → 基本是寄存器读写（几乎无状态机）。
* △ **dev_dsp.txt / 音频类（不经 ALSA 的旧 OSS 接口）** → 有 buffer/参数设置顺序，但文档和使用都越来越少。

这些如果你想把“所有 ioctl 行为”都形式化，也能建出一个小状态机，但相较于 KVM/DRM/V4L2 这几类收益会小一点。

---

### 2.3 – 基本可以视为“弱状态/无状态”的

* – **dev_random.txt** → 大部分 ioctl 是统计/配置（entropy、池大小等），基本不依赖复杂顺序。([blingbling's blog][9])
* – **dev_ptmx.txt** → 虽然 TTY/termios 是有状态的，但更多是「当前参数集合」，而不是像 KVM 那样的多级对象/严格步骤状态机。([Android Git Repositories][10])
* – 一些 GPU/SoC 设备里的单纯 debug/io 控制 ioctl，如果只是「一次性 ioctl 修改某个寄存器位」也可以看作弱状态。

---

## 3. 给你一个可直接用的“候选状态机设备”子集

如果你的目标是：

> “在 syzkaller 已支持的设备中，挑一批最容易/最有价值抽象出 ioctl 状态机的驱动”

我会优先推荐你用下面这一小撮做 ground truth & 评价：

1. **虚拟化 / VM**

   * ⭐ dev_kvm.txt（x86）
   * ⭐ dev_kvm_arm64.txt（ARM64）

2. **GPU / 显示**

   * ⭐ dev_dri.txt
   * ⭐ dev_i915.txt
   * ⭐ dev_mali.txt / dev_bifrost.txt / dev_img_rogue.txt（挑你 QEMU/目标平台能跑的那一个）

3. **多媒体 / 视频**

   * ⭐ dev_media.txt
   * ⭐ dev_video4linux.txt
   * ⭐ dev_camx.txt / dev_msm.txt（如果你 fuzz 的是手机 SoC kernel）

4. **存储 / 块设备**

   * ⭐ dev_loop.txt
   * ⭐ dev_nbd.txt
   * △ dev_block.txt（可以作为“跨设备、通用块层状态”的补充）

5. **RDMA / IOMMU / TEE**

   * ⭐ dev_infiniband_rdma*.txt
   * ⭐ dev_iommu.txt
   * ⭐ dev_trusty.txt / dev_tlk_device.txt（Android/ARM 环境）

这批基本都能在 QEMU 里跑（尤其是 KVM / DRM 部分，如果你做的是带图形的 guest 或者使用虚拟 GPU），而且每个子系统都有比较清晰的文档，可以手工构建一份“人工 ground truth 状态机”，然后和你自动提取的结果做对比。

---

如果你愿意，下一步我可以**针对其中一两个具体设备（比如 dev_loop 或 dev_kvm）帮你把 syzkaller 的 description + 内核文档翻成一份“人工 DOT 状态机草图”**，方便你直接用来做 ground truth。

[1]: https://github.com/google/syzkaller/tree/master/sys/linux "syzkaller/sys/linux at master · google/syzkaller · GitHub"
[2]: https://github.com/google/syzkaller/blob/master/sys/linux/dev_block.txt?utm_source=chatgpt.com "syzkaller/sys/linux/dev_block.txt at master"
[3]: https://github.com/google/syzkaller/issues/533?utm_source=chatgpt.com "things to test · Issue #533 · google/syzkaller - sys/linux"
[4]: https://groups.google.com/g/syzkaller/c/4I0qZauaiA0?utm_source=chatgpt.com "How to target specific linux drivers"
[5]: https://www.kernel.org/doc/Documentation/virt/kvm/api.txt?utm_source=chatgpt.com "KVM API documentation"
[6]: https://man7.org/linux/man-pages/man4/loop.4.html?utm_source=chatgpt.com "loop(4) - Linux manual page"
[7]: https://kiprey.github.io/2022/03/syzkaller-1/?utm_source=chatgpt.com "syzkaller 源码阅读笔记-1 - Kiprey's Blog"
[8]: https://gitlab.ispras.ru/p.nikulshin/syz-analyzer/-/blob/c6d3907c0e3c059194ae0e4903d0bf06139c66e0/sys/linux/dev_nbd.txt?utm_source=chatgpt.com "sys/linux/dev_nbd.txt - syz-analyzer"
[9]: https://blingblingxuanxuan.github.io/2019/10/26/syzkaller/?utm_source=chatgpt.com "syzkaller fuzz 工具的使用方法及实践实例"
[10]: https://android.googlesource.com/platform/external/syzkaller/%2B/HEAD/sys/linux/dev_ptmx.txt?utm_source=chatgpt.com "sys/linux/dev_ptmx.txt - platform/external/syzkaller - Git at Google"
[11]: https://gitlab.ispras.ru/p.nikulshin/syz-analyzer/-/blob/c6d3907c0e3c059194ae0e4903d0bf06139c66e0/sys/linux/dev_video4linux.txt?utm_source=chatgpt.com "sys/linux/dev_video4linux.txt - syz-analyzer"
[12]: https://github.com/google/syzkaller/blob/master/sys/linux/dev_trusty.txt?utm_source=chatgpt.com "syzkaller/sys/linux/dev_trusty.txt at master"
[13]: https://www.mail-archive.com/linux-media%40vger.kernel.org/msg136276.html?utm_source=chatgpt.com "Re: VIVID/VIMC and media fuzzing"
[14]: https://docs.kernel.org/gpu/drm-uapi.html?utm_source=chatgpt.com "Userland interfaces"
[15]: https://dri.freedesktop.org/docs/drm/media/uapi/v4l/v4l2.html?utm_source=chatgpt.com "Part I - Video for Linux API"
