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
