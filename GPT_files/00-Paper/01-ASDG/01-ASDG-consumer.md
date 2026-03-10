我先按“**x86 上可以跑、而且大量使用 ioctl 的用户态 / 自测代码**”来理解你的 *consumer 代码* 需求，把每个子系统的典型入口给你列出来，基本都能直接在 QEMU x86 里用来驱动对应内核接口。

---

## 1. KVM

### 内核自带 selftests（强烈推荐当作 ioctl consumer）

* `tools/testing/selftests/kvm/x86/` 目录整套都是 x86 KVM 的用户态测试程序，比如：

  * `smm_test.c`
  * `state_test.c`
  * `userspace_io_test.c`
  * `sev_*_test.c`
  * `tdx_vm_test.c` 等([CodeBrowser][1])
* 这些都是纯用户态 C 程序，通过 `/dev/kvm` + ioctl 驱动 KVM，非常适合你直接拿来分析 / 精简，构造状态机 ground truth。

### 其它典型 x86 consumer

* **kvm-unit-tests**：独立仓库，专门测试 KVM，各架构有子目录，x86 有大量 VM bring-up / MSR / CPUID 等例子([docs.kernel.org][2])
* **QEMU (accel/kvm, hw/i386/***)：是最大的实际生产 consumer，但代码比较重，不太适合做首选分析对象。

---

## 2. DRM

### 内核侧自测 / 辅助代码

* `drivers/gpu/drm/selftests/`

  * 包含各种 KMS / framebuffer / dp_mst helper 的自测，例如 `test-drm_framebuffer.c`, `test-drm_dp_mst_helper.c` 等([Android Git 源代码][3])
  * 这些在内核里跑，但逻辑上很好地展示了驱动 API 的典型调用顺序，可作为状态机参考。

### 典型用户态 consumer（推荐）

* **IGT GPU Tools**（`igt-gpu-tools`）

  * 官方定位就是 “Test suite and tools for DRM/KMS drivers”([cgit.freedesktop.org][4])
  * 目录结构：

    * `tests/`：海量 `kms_*` / `gem_*` 等测试二进制，对 `/dev/dri/cardX` 做非常完整的 ioctl 覆盖。
    * `benchmarks/`：一些性能测试，同样走 DRM ioctl。
  * 这些都是在 x86 跑得最成熟的套件，**非常适合当作 DRM ioctl 状态机的真实“语言样本”**。

---

## 3. Media（V4L2 / DVB 等）

### 内核 selftests

* Linux 源码里：

  * `tools/testing/selftests/media/`
  * 其中 `v4l` 子目录（`tools/testing/selftests/media/v4l/`）包含一组 V4L2 测试用例，用 ioctl 操作 `/dev/video*` 设备([RPM Find][5])

### 用户态测试 / 合规工具

* **v4l2-compliance**（v4l-utils 项目内）

  * 可执行程序 `v4l2-compliance` 用来对 V4L2 驱动做一致性测试，“覆盖几乎所有 V4L2 ioctls”([Ubuntu Manpages][6])
  * 源码在 v4l-utils：`utils/v4l2-compliance/v4l2-compliance.cpp`
* **v4l2-ctl**（同样 v4l-utils）

  * 常见的控制工具，对流配置 / buffer 队列等路径同样是 ioctl 密集。

> 对 Media 子系统，你可以优先拿 `tools/testing/selftests/media/v4l` + `v4l2-compliance` 的调用序列来抽状态机。

---

## 4. loop（/dev/loopX）

### 内核相关测试 / 示例

* 管理 loop 设备主要是 userspace 工具 **util-linux** 里的 `losetup` 等；它们通过 ioctl 操作 `/dev/loopX`，是 loop 驱动最典型的 consumer。
* 内核 block 文档：

  * `Documentation/admin-guide/blockdev/zoned_loop.rst` 描述 zloop（分区化 loop 驱动）的典型使用方式([docs.kernel.org][7])
* 有补丁系列给 selftests 增加 loop 测试：

  * `selftests: block_seek_hole: add loop block driver tests`，在 `tools/testing/selftests/` 里增加针对 loop 支持 `llseek(SEEK_HOLE/SEEK_DATA)` 的测试([Patchew][8])

> 如果你只关心 ioctl 状态机，最直接的就是分析 util-linux 里 `losetup` 的源码（循环 ioctl `LOOP_SET_FD`, `LOOP_CONFIGURE`, `LOOP_SET_STATUS64`, `LOOP_CLR_FD` 等）。

---

## 5. NBD（Network Block Device）

### 内核文档 & 推荐用户态实现

* 文档：`Documentation/admin-guide/blockdev/nbd.rst`

  * 明确指出：内核只有 `nbd` 模块，**用户态的 nbd-server / nbd-client 完全在 userspace**，官方推荐去 GitHub 的 NetworkBlockDevice 项目获取源码([docs.kernel.org][9])

### 典型 consumer

* **nbd-client / nbd-server**

  * `nbd-client` man page 说明它将 NBD server 暴露的镜像映射为本地块设备（通过 `/dev/nbdX`）([man.archlinux.org][10])
  * 源码在 `github.com/NetworkBlockDevice/nbd`，很适合你直接 grep ioctl 调用，抽 `/dev/nbdX` 的状态机。
* **libnbd**（libguestfs 项目）

  * 一个 NBD 协议客户端库，用 C 封装了 NBD 的状态机和交互([libguestfs.org][11])

---

## 6. IOMMU / iommufd

### 内核自测 / mock consumer

* `tools/testing/selftests/iommu/`

  * kselftest 的 IOMMU/iommufd 专用用户态测试，配置要求在 `tools/testing/selftests/iommu/config` 中([android-kvm.git.googlesource.com][12])
* `drivers/iommu/iommu.c` 中提到：

  * 存在给 iommufd selftest 用的 “mock IOMMU driver”，配合上面的 selftests 一起组成 “consumer”([GitHub][13])

> 这些 selftests 跑在 x86 完全没问题，可以很好地覆盖 `iommufd` / DMA 映射这类状态化 ioctl / UAPI。

---

## 7. Trusty / tlk_device（含 x86 版本）

### Trusty 在 x86 上的分布

* Intel 有 **“Intel® x86 Architecture Distribution of Trusty OS”**，是基于虚拟化的 Trusty 解决方案，明确支持 x86 平台([Intel][14])

### Linux 侧 driver & consumer 逻辑

* Android/通用内核中的 Trusty driver 目录：

  * `drivers/trusty/trusty.c` / `trusty-ipc.c` / `trusty-virtio.c` 等([Android Git 源代码][15])
  * 这些是内核态对 Trusty OS 的“服务端”，暴露 `/dev/trusty-*` 一类字符设备。
* 对应的 **用户态 consumer** 一般在：

  * Android / AOSP 中的 Trusty client library 和测试应用（通过 `/dev/tlk_device` 或 `/dev/trusty-*` 做 ioctl / read / write）。
  * Syzkaller 里也有针对 `tlk_device` 的 description 文件 `sys/linux/dev_tlk_device.txt`，可以作为接口参考([GitLab][16])

> 如果你只关注 *x86* 场景，可以结合 Intel x86 Trusty 发行版 + 配套 Linux kernel，直接从那套树里找 user-space sample（通常会有 demo TA / client）。

---

## 怎么用这些东西做“状态机 consumer”分析？

如果你后面需要，我可以按子系统帮你做下一步：

1. 从上述 selftests / 工具里自动提取 **ioctl 调用序列**（`strace -f -e trace=ioctl`），
2. 对序列做简化和聚类，
3. 再跟你内核里抽出来的 ioctl 状态机对比（做前面我们讨论过的有界序列评估那一套）。

先把这些 x86 可用的 consumer 代码位置给你列清楚，你可以先挑感兴趣的一个子系统（比如 KVM 或 DRM）深入，我们再往下挖具体的状态机。

[1]: https://codebrowser.dev/linux/linux/tools/testing/selftests/kvm/x86/smm_test.c.html?utm_source=chatgpt.com "smm_test.c source code [linux/tools/testing/selftests/kvm/x86 ..."
[2]: https://docs.kernel.org/process/maintainer-kvm-x86.html?utm_source=chatgpt.com "5. KVM x86"
[3]: https://android.googlesource.com/kernel/common/%2B/35556bed836f/drivers/gpu/drm/selftests?autodive=0%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F&utm_source=chatgpt.com "drivers/gpu/drm/selftests - kernel/common - Git at Google"
[4]: https://cgit.freedesktop.org/drm/igt-gpu-tools/?utm_source=chatgpt.com "drm/igt-gpu-tools - Test suite and tools for DRM/KMS ..."
[5]: https://rpmfind.info/linux/RPM/almalinux/10.0/appstream/aarch64/usr_src_kernels_6.12.0-55.29.1.el10_0.aarch64_tools_testing_selftests_media_tests_Tree.html?utm_source=chatgpt.com "/var/www/html/linux/RPM/almalinux/10.0/appstream/aarch64 ..."
[6]: https://manpages.ubuntu.com/manpages/xenial/man1/v4l2-compliance.1.html?utm_source=chatgpt.com "v4l2-compliance - An application to test video4linux drivers"
[7]: https://docs.kernel.org/admin-guide/blockdev/zoned_loop.html?utm_source=chatgpt.com "Zoned Loop Block Device"
[8]: https://patchew.org/linux/20240328203910.2370087-1-stefanha%40redhat.com/20240328203910.2370087-4-stefanha%40redhat.com/?utm_source=chatgpt.com "[RFC 3/9] selftests: block_seek_hole: add loop block driver tests"
[9]: https://docs.kernel.org/admin-guide/blockdev/nbd.html?utm_source=chatgpt.com "Network Block Device (TCP version)"
[10]: https://man.archlinux.org/man/nbd-client.8.en?utm_source=chatgpt.com "nbd-client(8) - Arch manual pages"
[11]: https://libguestfs.org/libnbd.3.html?utm_source=chatgpt.com "libnbd - network block device (NBD) client library in ..."
[12]: https://android-kvm.git.googlesource.com/linux/%2B/0ea22c4669e323817f8405416a09f6f52cc2ad2c/tools/testing/selftests/iommu/?utm_source=chatgpt.com "tools/testing/selftests/iommu - linux"
[13]: https://github.com/torvalds/linux/blob/master/drivers/iommu/iommu.c?utm_source=chatgpt.com "linux/drivers/iommu/iommu.c at master · torvalds/linux"
[14]: https://www.intel.com/content/www/us/en/developer/topic-technology/open/trusty/overview.html?utm_source=chatgpt.com "Intel® x86 Architecture Distribution of Trusty* OS"
[15]: https://android.googlesource.com/kernel/common/%2B/android-trusty-3.10/drivers/trusty/trusty-ipc.c?utm_source=chatgpt.com "drivers/trusty/trusty-ipc.c - kernel/common - Git at Google"
[16]: https://gitlab.ispras.ru/p.nikulshin/syz-analyzer/-/blob/c6d3907c0e3c059194ae0e4903d0bf06139c66e0/sys/linux/dev_tlk_device.txt?utm_source=chatgpt.com "sys/linux/dev_tlk_device.txt - syz-analyzer"
