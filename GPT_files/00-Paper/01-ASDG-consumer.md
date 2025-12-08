我先按你的理解，把「consumer 代码」理解成**从用户态使用这些内核接口的典型代码**（大量调用 ioctl 的那种），方便你反推合法的调用序列和状态机。如果你想要的是「内核里作为 framework consumer 的 driver」，大部分下面这些项目也能给你线索。

下面按 kvm / drm / media / loop / nbd / iommu / trusty 分项列出**推荐看的工程 + 关键源码文件路径**。

---

## 总览表

| 子系统                             | 设备节点 / 接口                    | 典型 consumer 工程                       | 关键源码文件（可直接 grep ioctl / 命令号）                                                                                                              |
| ------------------------------- | ---------------------------- | ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| KVM                             | `/dev/kvm`                   | QEMU                                 | `accel/kvm/kvm-all.c` ([Android Git 源代码][1])                                                                                              |
| DRM                             | `/dev/dri/card*`, render 节点  | libdrm + Mesa、Xorg、Wayland           | `libdrm/xf86drm.c`, `xf86drmMode.c` ([sources.debian.org][2])                                                                             |
| Media (V4L2 / Media Controller) | `/dev/video*`, `/dev/media*` | v4l-utils (`v4l2-ctl`, `media-ctl`)  | `utils/v4l2-ctl/*.c`, `utils/media-ctl/media-ctl.c` ([STMicroelectronics][3])                                                             |
| loop                            | `/dev/loop*`                 | util-linux `losetup` / `lib/loopdev` | `mount/losetup.c`, `lib/loopdev.c` ([Kernel Git Repositories][4])                                                                         |
| nbd                             | `/dev/nbd*`                  | `nbd-client`、BusyBox `nbd-client`    | `nbd-client.c`（上游）、`busybox/networking/nbd-client.c` ([sources.debian.org][5])                                                            |
| IOMMU                           | 无 /dev，内核内部 API              | 各种设备驱动（GPU/显示/remoteproc 等）          | 如 `drivers/gpu/drm/exynos/exynos_drm_dma.c`、`drivers/gpu/drm/msm/msm_iommu.c`、`drivers/gpu/drm/rockchip/rockchip_drm_drv.c` ([GitLab][6]) |
| Trusty                          | `/dev/trusty-ipc-dev0` 等     | Android `libtrusty` / `tipc-test`    | `trusty/libtrusty/tipc-test/tipc_test.c` ([Android Git 源代码][7])                                                                           |

下面每一类我再稍微展开一点，方便你去看状态机。

---

## 1. KVM 的 consumer 代码

**典型用户：QEMU**

* 工程：QEMU（官方主仓库）
* 关键文件：`accel/kvm/kvm-all.c` ([Android Git 源代码][1])
  里面可以看到：

  * 打开 `/dev/kvm`：

    * `s->fd = qemu_open_old("/dev/kvm", O_RDWR);`
  * 各种 ioctl 封装：

    * `kvm_ioctl(s, KVM_GET_API_VERSION, ...)`
    * `kvm_vm_ioctl(s, KVM_CREATE_VM, ...)`
    * `kvm_vcpu_ioctl(env, KVM_RUN, ...)`
  * QEMU 自己封装的 helper：`kvm_ioctl`, `kvm_vm_ioctl`, `kvm_vcpu_ioctl`，直接在里面 grep `ioctl(` / `KVM_` 就能把整个 KVM 状态机的典型路径挖出来。

> 用途：你可以基于 QEMU 的调用顺序（create VM → create VCPU → set user memory → run）作为 `/dev/kvm` ioctl 状态机的 ground-truth 行为序列。

---

## 2. DRM 的 consumer 代码

**用户态主要通过 libdrm 封装 ioctl，窗口系统 / Mesa 再在上面一层堆栈。**

* 工程：`libdrm` ([sources.debian.org][2])
* 关键文件：

  1. `xf86drm.c`

     * `int drmIoctl(int fd, unsigned long request, void *arg)` 里就是裸 `ioctl(fd, request, arg)`。
     * `drmCommandNone/Read/Write/WriteRead` 通过 `DRM_IOC()` 组合出实际的 ioctl 号（`DRM_COMMAND_BASE + idx`）。
  2. `xf86drmMode.c`

     * 封装了 KMS 相关的 ioctl，比如：

       * `drmModeAddFB`
       * `drmModeSetCrtc`
       * `drmModePageFlip`
     * 内部通过 `DRM_IOCTL` 宏调用 `drmIoctl()`。

> 用途：对你的 fuzz driver 来说，**直接跟踪 libdrm 这一层**，把所有进入 `drmIoctl` / `DRM_IOCTL` 的 request 和参数抓出来，非常适合还原 `/dev/dri/card*` 的合法 ioctl 序列（尤其是 KMS 部分）。

---

## 3. Media（V4L2 + Media Controller）的 consumer 代码

### 3.1 V4L2：`/dev/video*`

* 工程：`v4l-utils`，特别是 `v4l2-ctl` ([STMicroelectronics][3])
* 关键文件（不同版本路径略有差异，大致在 `utils/v4l2-ctl/` 下）：

  * `v4l2-ctl-*.c`：各类功能分文件，比如 vidcap、controls 等。
  * 里面会调用经典 V4L2 ioctl：

    * `VIDIOC_QUERYCAP`
    * `VIDIOC_ENUM_FMT`
    * `VIDIOC_S_FMT`
    * `VIDIOC_REQBUFS`
    * `VIDIOC_QBUF` / `VIDIOC_DQBUF`
    * `VIDIOC_STREAMON` / `VIDIOC_STREAMOFF`
* 这些工具用法和 ioctl 对应关系在文档里也能查到，`--help-*` 部分会直接提到具体 ioctl 名字 ([STMicroelectronics][3])。

### 3.2 Media Controller：`/dev/media*`

* 工程：同样是 `v4l-utils` 里的 `media-ctl` ([GitHub][8])
* 关键文件：`utils/media-ctl/media-ctl.c`

  * 用 `MEDIA_IOC_DEVICE_INFO`、`MEDIA_IOC_ENUM_ENTITIES`、`MEDIA_IOC_ENUM_LINKS` 等 ioctl 读拓扑图。
  * 还能 `--print-dot` 直接吐 DOT 图（这个你可以拿来和自己抽的 DOT 状态机做对比）。

> 用途：
>
> * `/dev/video*`：流控 + buffer 生命周期状态机。
> * `/dev/media*`：媒体 pipeline 拓扑和 link enable/disable 的「图结构状态」。

---

## 4. loop 设备的 consumer 代码

**最标准的就是 util-linux 里的 losetup / libloopdev。**

* 工程：`util-linux` ([Kernel Git Repositories][4])

1. `mount/losetup.c`

   * 典型调用序列：

     * `ioctl(fd, LOOP_SET_FD, file_fd)`
     * `ioctl(fd, LOOP_SET_STATUS, &loopinfo)` 或 `LOOP_SET_STATUS64`
     * 卸载时 `LOOP_CLR_FD`
   * 体现了 loop 设备从「未绑定」→「绑定文件」→「设置参数」→「使用」→「清理」的完整状态。

2. `lib/loopdev.c`

   * 更复杂的封装，集中处理：

     * `LOOP_GET_STATUS64`
     * `LOOP_SET_STATUS64`
     * `LOOP_SET_BLOCK_SIZE`
     * 以及自动 retry、AUTOCLEAR flag 等逻辑 ([GitHub][9])

> 用途：从这两个文件可以几乎直接推 loop 的 ioctl 状态机（包括错误路径，比如 EBUSY/EAGAIN 时的 retry 或清理）。

---

## 5. nbd 的 consumer 代码

### 5.1 官方 nbd-client

* 工程：`nbd`（上游工具） ([sources.debian.org][5])
* 关键文件：`nbd-client.c`

  * 核心 ioctl：

    * `NBD_SET_SOCK`
    * `NBD_SET_BLKSIZE`
    * `NBD_SET_SIZE` / `NBD_SET_SIZE_BLOCKS`
    * `NBD_SET_TIMEOUT`
    * `NBD_DO_IT`
    * `NBD_CLEAR_SOCK` / `NBD_CLEAR_QUEUE` / `NBD_DISCONNECT`
  * 典型顺序：

    1. `open("/dev/nbdX")`
    2. socket 连接 server
    3. 协商 size / flags
    4. ioctl 设置 size / blocksize / timeout
    5. `ioctl(nbd, NBD_SET_SOCK, sock)`
    6. `ioctl(nbd, NBD_DO_IT)` 进入长期阻塞循环
    7. 退出时 `NBD_CLEAR_QUEUE`、`NBD_CLEAR_SOCK`

### 5.2 BusyBox nbd-client

* 工程：BusyBox ([Carbslinux Git][10])
* 文件：`networking/nbd-client.c`

  * 自己定义 ioctl 号（`_IO(0xab, ...)`），逻辑更紧凑，非常适合阅读和移植到 fuzz driver 里。

> 用途：直接映射出 `/dev/nbd*` 的状态机：**配置 → set sock → DO_IT → 断开 → 清理**。

---

## 6. IOMMU 的「consumer」代码（内核内部）

IOMMU 不暴露 `/dev` 设备，只有 **内核驱动**作为 consumer 调用 IOMMU API：

* 常见调用：

  * `iommu_domain_alloc(...)`
  * `iommu_attach_device(domain, dev)`
  * `iommu_detach_device(...)`
  * 以及各种 `dma_map_*` / `dma_unmap_*` 宏（在很多 platform 上由 IOMMU backend 实现）。

几个比较典型、容易看懂的例子：

* Exynos DRM IOMMU glue：`drivers/gpu/drm/exynos/exynos_drm_dma.c`，里面有 `iommu_attach_device(priv->mapping, subdrv_dev);` 等逻辑 ([GitLab][6])
* MSM DRM IOMMU：`drivers/gpu/drm/msm/msm_iommu.c`，使用 `iommu_attach_device(iommu->domain, mmu->dev);` ([GitLab][11])
* Rockchip DRM：`drivers/gpu/drm/rockchip/rockchip_drm_drv.c`，在 probe 时通过 `iommu_domain_alloc` / `iommu_attach_device` 把设备挂入 IOMMU ([GitLab][12])

> 对 fuzzing ioctl 状态机来说：IOMMU 本身没有 ioctl；
> 你如果只是关注**用户态 → ioctl → 驱动状态机**，可以暂时把 IOMMU 看成内部资源，不必建单独状态机，只需要在「设备初始化成功」状态假定 IOMMU 已经 attach。

---

## 7. Trusty 的 consumer 代码（Android libtrusty）

在 Android 上，Trusty IPC 通过 `/dev/trusty-ipc-dev0` 暴露给用户态。

* 工程：AOSP `system/core` 里的 `trusty/libtrusty` ([Android Git 源代码][7])
* 关键文件：`trusty/libtrusty/tipc-test/tipc_test.c`

  * 使用：

    * 默认设备名：`#define TIPC_DEFAULT_DEVNAME "/dev/trusty-ipc-dev0"`
    * 调用 `tipc_connect(dev_name, service_name)` 建立 channel
    * 利用 `read`/`write`/`select` 等在该 fd 上进行通信
  * `tipc_connect` 的实现（在 libtrusty 其他文件）内部会：

    * `open("/dev/trusty-ipc-dev0", ...)`
    * 使用私有 ioctl / `mmap` 建立与安全世界的共享内存（具体 ioctl 依平台版本而异）

> 用途：
>
> * 你可以通过跟踪 `tipc_test` 或实际 Android 进程里 libtrusty 的调用来还原 `/dev/trusty-ipc-dev*` 的实际 ioctl/调用序列。
> * 状态机上通常是：`open → connect(service) → 反复收发 → close`，中间可能有基于 ioctl 的 session 建立 / buffer 映射。

---

## 怎么用这些 consumer 代码做状态机

给你一个通用思路（适用于上面每一类）：

1. **选定一个 consumer 工程**（比如 QEMU / libdrm / v4l2-ctl / losetup / nbd-client / tipc-test）。
2. 在代码里：

   * `grep ioctl(`
   * `grep KVM_ / DRM_IOCTL / VIDIOC_ / LOOP_ / NBD_ / MEDIA_IOC_` 等宏名。
3. 结合 call graph，看：

   * 哪些 ioctl 只在初始化阶段出现；
   * 哪些是重复出现的「steady-state operation」；
   * 哪些在错误路径或 teardown 分支。
4. 把这些顺序抽象到你的 **ioctl-state machine** 里：

   * 节点：设备的「逻辑状态」（例如：未绑定文件 / 已绑定未设置参数 / 已 stream on 等）。
   * 边：某个 ioctl，从状态 A → 状态 B，条件是「参数满足约束」。

如果你之后希望针对某一个子系统，我也可以帮你根据这些 consumer 代码直接画成 DOT 状态机草图。

[1]: https://android.googlesource.com/platform/external/qemu/%2B/refs/heads/main/kvm-all.c?utm_source=chatgpt.com "kvm-all.c - platform/external/qemu - Git at Google"
[2]: https://sources.debian.org/src/libdrm/2.4.97-1/xf86drm.c/?utm_source=chatgpt.com "File: xf86drm.c"
[3]: https://wiki.st.com/stm32mpu/wiki/V4l2-ctl?utm_source=chatgpt.com "V4l2-ctl - stm32mpu - ST wiki"
[4]: https://kernel.googlesource.com/pub/scm/utils/util-linux/util-linux/%2B/eb63b9b8f4cecb34c2478282567862bc48ef256d/mount/losetup.c?utm_source=chatgpt.com "mount/losetup.c - pub/scm/utils/util-linux/util-linux"
[5]: https://sources.debian.org/src/nbd/1%3A3.8-4/nbd-client.c?utm_source=chatgpt.com "File: nbd-client.c"
[6]: https://gitlab.navisincontrol.com/varigit/linux-imx/-/blob/imx_5.4.70_2.3.2_var01/drivers/gpu/drm/exynos/exynos_drm_dma.c?utm_source=chatgpt.com "drivers/gpu/drm/exynos/exynos_drm_dma.c · imx_5.4.70_2 ..."
[7]: https://android.googlesource.com/platform/system/core/%2B/master/trusty/libtrusty/tipc-test/tipc_test.c?utm_source=chatgpt.com "trusty/libtrusty/tipc-test/tipc_test.c - platform/system/core"
[8]: https://github.com/gjasny/v4l-utils/blob/master/utils/media-ctl/media-ctl.c?utm_source=chatgpt.com "media-ctl.c"
[9]: https://github.com/mmalecki/util-linux/blob/master/lib/loopdev.c?utm_source=chatgpt.com "util-linux/lib/loopdev.c at master"
[10]: https://git.carbslinux.org/forks/busybox/tree/networking/nbd-client.c?h=1_33_stable&id=6937487be73cd4563b876413277a295a5fe2f32c&utm_source=chatgpt.com "nbd-client.c « networking - forks/busybox"
[11]: https://gitlab.sdu.dk/sdurobotics/linux-kernels/kernel/-/blob/stable/drivers/gpu/drm/msm/msm_iommu.c?utm_source=chatgpt.com "drivers/gpu/drm/msm/msm_iommu.c · stable"
[12]: https://gitlab.nic.cz/turris/linux/-/blob/0f32ab8cfac478be053cb526ced8918ef6f4df47/drivers/gpu/drm/rockchip/rockchip_drm_drv.c?utm_source=chatgpt.com "drivers/gpu/drm/rockchip/rockchip_drm_drv.c"
