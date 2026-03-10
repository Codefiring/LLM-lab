先说结论：
在我目前*能看到的代码*里，你这套 A54 内核里**可以确定有状态机**的设备驱动只有你上传的这份 NPU vertex 驱动（`npu-vertex.c`）。

GitHub 上的 `Codefiring/linux-a54` 仓库我这边访问是 404，所以没法直接遍历那一个仓库的 `drivers/` 目录做精确枚举；但结合三星公开的 A54 内核（`android_kernel_samsung_a54x`）和其它 Exynos 内核，可以比较有把握地给出**一批很大概率存在且带明显状态机的驱动类型**，你可以在本地树里按子系统去找对应文件。

---

## 1. 已确认：NPU vertex 驱动（你上传的 `npu-vertex.c`）

* **路径（典型）：** 类似 `drivers/vision/npu/core/npu-vertex.c`
* **状态变量：** `struct npu_vertex_ctx` 里的 `vctx->state`，用 `BIT(NPU_VERTEX_*)` 做 bitmask。
* 典型状态：

  * `NPU_VERTEX_OPEN`
  * `NPU_VERTEX_POWER`
  * `NPU_VERTEX_GRAPH`
  * `NPU_VERTEX_FORMAT`
  * `NPU_VERTEX_STREAMON`
  * `NPU_VERTEX_STREAMOFF`
  * `NPU_VERTEX_CLOSE` 等
* 各 ioctl / file op 对状态的约束非常典型，完全可以抽成状态机：

  * `open`：设置 `OPEN`，并通过 `__vref_get(&vertex->open_cnt)` 维护引用计数。
  * `npu_vertex_s_graph()`：要求 `OPEN` 已经置位，否则返回 `-EINVAL`；成功后设置 `GRAPH`。
  * `npu_vertex_s_format()`：

    * 进入时必须已经有 `GRAPH` 或 `FORMAT` 状态：

      ```c
      if (!(vctx->state & (BIT(NPU_VERTEX_GRAPH) | BIT(NPU_VERTEX_FORMAT)))) {
          ... ret = -EINVAL;
      }
      ```
    * 成功时设置 `FORMAT`，失败时清掉 `GRAPH`：

      ```c
      vctx->state |= BIT(NPU_VERTEX_FORMAT);
      ...
      ```

    p_err:
    vctx->state &= (~BIT(NPU_VERTEX_GRAPH));

    ```
    ```



* `npu_vertex_streamon()`：

  * 禁止重复 STREAMON：

    ```c
    if (vctx->state & BIT(NPU_VERTEX_STREAMON)) { ... -EINVAL; }
    ```
  * 要求已经 `FORMAT` + `GRAPH`。
  * 成功后置 `STREAMON`。
* `npu_vertex_streamoff()` / `__force_streamoff()`：清除 `STREAMON`，置 `STREAMOFF`，以及 `start_cnt` 的 refcount 退回。
* `release`：根据当前 `state` 分支处理（是否需要强制 streamoff、power notify、unload 等），是一个典型的**关闭路径状态机**。

> 这一块完全符合你要的 “基于 ioctl 的状态机” 模式，作为 fuzzing target 非常合适。

---

## 2. 在 A54 类内核中**高度可疑有状态机**的其它驱动类型（需要你在本地树里找对应文件）

下面这些是根据三星公开的 Exynos / A54 内核和主线文档推出来的**驱动类型**，不保证路径一模一样，但在 A54 这类手机内核里几乎肯定存在，而且都具有强状态机特征，尤其是 V4L2 相关驱动。

### 2.1 Exynos MFC 视频编解码器驱动（V4L2 mem2mem）

* **典型路径（主线 / 其它 Exynos 内核）：**
  `drivers/media/platform/samsung/exynos-mfc/` 或旧版 `drivers/media/video/exynos/mfc/`([lkml.org][1])
* 硬件：多格式编解码（MFC），所有 Exynos 多媒体 SoC 都有，比如你手机上的 H.264/H.265 编解码就是它干的。([git.ideasonboard.org][2])
* **状态机特点：**

  * 作为 V4L2 mem2mem 设备，用户态通过 ioctl 顺序：

    1. `VIDIOC_QUERYCAP`
    2. `VIDIOC_S_FMT` / `VIDIOC_REQBUFS`
    3. `VIDIOC_QBUF`
    4. `VIDIOC_STREAMON`
    5. 周期性 `VIDIOC_QBUF`/`VIDIOC_DQBUF`
    6. `VIDIOC_STREAMOFF`
  * MFC 驱动内部普遍有 `ctx->state` / `core_ctx->state` 之类的字段，在 streamon/streamoff、格式设置时做状态检查：([lkml.org][1])

    * “ENC streamon, state: %d”
    * 对重复 streamon/streamoff 的特殊处理。
  * 这类状态机和你的 NPU vertex 很接近：
    OPEN → CONFIGURED(S_FMT/REQBUFS) → STREAMON → STREAMOFF → CLOSED

**建议你在本地 A54 内核里：**

```bash
grep -R \"EXYNOS MFC\" -n drivers/media
grep -R \"MFC\" -n drivers/media
```

找到那个驱动之后，再用：

```bash
grep -R \"streamon\" -n path/to/exynos-mfc/*
grep -R \"state\" -n path/to/exynos-mfc/*
```

基本可以挖出一整套 ioctl 状态机，非常适合自动抽 DOT。

---

### 2.2 Exynos Camera / ISP 驱动（V4L2 摄像头管线）

* **典型路径：**

  * 新一点的内核一般在 `drivers/media/platform/samsung/` 下，名字里会带 `exynos-is`、`fimc-is`、`is-core` 等。([linuxtv.org][3])
* **硬件：** sensor + CSI + ISP + scaler 的 pipeline。
* **状态机特征：**

  * V4L2 camera pipeline 同样有严格的操作顺序：

    * `open` → `s_fmt`/`s_selection` → `reqbufs` → `qbuf` → `streamon` → `dqbuf` 循环 → `streamoff` → `close`
  * 很多 Exynos camera 驱动在内部维护一种 `enum is_state` 或类似 bitmask，控制：

    * pipeline 是否已经 configured；
    * sensor 是否已 stream on；
    * buffer 是否 ready。
  * 在错误路径 / suspend/resume 时会根据状态机做清理和恢复。

这类驱动的状态机复杂度通常比 MFC 更高（多 sub-device），如果你能自动分析到 subdev 之间的依赖，对 fuzzing 很有帮助。

---

### 2.3 Exynos G-Scaler / GSC / JPEG 等图像处理 IP

* **典型路径：**

  * `drivers/media/platform/exynos-gsc/`（G-Scaler）([git.ti.com][4])
  * `drivers/media/platform/samsung/exynos4-is/` 系列、`.../jpeg/` 驱动
* 都是 V4L2 mem2mem 风格（缩放、颜色转换、JPEG 编解码），跟 MFC 类似，也有：

  * 格式配置 → buffer 管理 → streamon/off 的状态机；
  * 用 `vb2_queue` + 自己的状态字段组合实现。

对你的框架来说，这一类和 MFC、NPU 属于同一个“模式族”，写好一套 pattern 基本可以半自动迁移。

---

### 2.4 Exynos DRM / 显示控制（DECON / DPP / MIXER）

* **典型路径（主线）：** `drivers/gpu/drm/exynos/`([Samsung Open Source][5])
* 虽然对用户空间暴露的是 DRM IOCTL（modeset、page flip 等），而不是简单的字符设备 ioctl，但内部同样有比较清晰的 KMS 状态机：

  * CRTC enable/disable
  * plane attach/detach
  * atomic commit 的顺序约束
* 这种状态机更多是「模式设置 / 帧提交顺序」，如果你打算以后扩展到 DRM fuzz，可以考虑它；不过相对 NPU/MFC 的简单 bitmask，这一块抽象会更复杂一点（atomic state 对象）。

---

### 2.5 其它 Vision / NPU 相关辅助驱动

从其它三星 Exynos 内核可以看到，除了 `npu-vertex.c` 以外，还会有：

* `npu-device.c`：负责整个 NPU 设备的上电、fw 下载、恢复流程。([GitHub][6])
* `npu-session.c`：对单个 session 的 buffer/graph 做状态管理和网络结果检查。([GitHub][7])

这些通常不是直接给用户空间 ioctl 的字符设备，但**内部状态机非常丰富**，比如：

* session 打开/关闭；
* graph load/unload；
* poweron / poweroff / emergency recovery；
* current frame、queue 状态等。

你如果愿意，可以把它们也纳入“内部状态机 ground truth”，用来对比你从外层 ioctl 推导出来的状态机是否一致。

---

## 3. 实际建议：怎么在你本地 linux-a54 里快速筛选这些驱动

因为我这边拿不到 `Codefiring/linux-a54` 的代码，只能从公开 Exynos/A54 内核推断“有哪些类型的驱动值得看”。你在本地树里可以用下面这种方式做**自动筛选**：

1. **先定位 V4L2 / 多媒体驱动目录：**

```bash
cd path/to/linux-a54

# 找 media 平台驱动
find drivers/media -maxdepth 3 -type d

# 看有没有 samsung / exynos 相关子目录
find drivers/media -maxdepth 5 -type f | grep -Ei 'exynos|mfc|gsc|jpeg|fimc|is-'
```

2. **在这些候选文件中搜状态变量：**

常见 pattern：

```bash
# BIT 状态机
grep -R \"state\" -n drivers/vision drivers/media drivers/gpu | grep 'BIT('

# 明确的 enum 状态类型
grep -R \"enum .*state\" -n drivers/vision drivers/media drivers/gpu
```

3. **优先挑出有明显 “条件 + -EINVAL” 模式的：**

例如 NPU 里这种：

```c
if (!(vctx->state & BIT(NPU_VERTEX_STREAMON))) {
    ... return -EINVAL;
}
```

这些代码就直接对应“某条边的前置条件不满足 → 非法输入”，非常适合做状态机抽象和约束 AFL 的输入生成。

---

### 总结一下 List（从“确定”到“高概率”）

1. ✅ **NPU vertex / vision 设备**

   * 文件：`npu-vertex.c`（你已提供）
   * 明确 bitmask 状态机，OPEN/GRAPH/FORMAT/STREAMON/STREAMOFF/POWER/CLOSE。

2. ⚠️ **Exynos MFC（视频编解码）驱动**

   * 典型：`drivers/media/platform/samsung/exynos-mfc/*` / `drivers/media/video/exynos/mfc/*`([lkml.org][1])
   * V4L2 mem2mem，内部 `ctx->state` + streamon/off 状态机。

3. ⚠️ **Exynos Camera / ISP（FIMC-IS 等）驱动**

   * 典型：`drivers/media/platform/samsung/exynos-*`（camera 子系统）([linuxtv.org][3])
   * 大型 V4L2 状态机（open / configure / streamon / streamoff）。

4. ⚠️ **Exynos GSC / JPEG 等图像处理驱动**

   * 典型：`drivers/media/platform/exynos-gsc/*` / `.../jpeg/*`([git.ti.com][4])
   * mem2mem 类 state machine（streamon/off）。

5. ⚠️ **Exynos DRM / 显示驱动**

   * 路径：`drivers/gpu/drm/exynos/*`([Samsung Open Source][5])
   * 内部有 KMS/modeset 状态机，适合更高级别的 fuzzing。

在你本地 `linux-a54` 树里，把上面这些子系统对应的 `.c` 文件找出来，再按 NPU 这种 `state & BIT()` + ioctl 的 pattern 去筛选，就能得到一个比较全面的“可能有状态机的设备驱动 list”。如果你愿意，把那些源码文件再贴几份上来，我可以直接帮你逐个标出状态变量和关键 ioctl，并给出更具体的状态机边集合。

[1]: https://lkml.org/lkml/2025/9/30/182?utm_source=chatgpt.com "[PATCH 24/29] media: mfc: Add encoder VB2 support to driver"
[2]: https://git.ideasonboard.org/samsung-utils.git/tree/v4l2-mfc-example/README.txt?id=49a80947f301ed5433010c7675d0ae974c4470b6&utm_source=chatgpt.com "README.txt « v4l2-mfc-example - samsung-utils.git"
[3]: https://www.linuxtv.org/downloads/v4l-dvb-apis-new/pdf/media.pdf?utm_source=chatgpt.com "Linux Media Documentation"
[4]: https://git.ti.com/cgit/rpmsg/remoteproc/commit/?h=rproc-linux-3.14.y&id=27c053aa8d18d1fa7b83041e36bad20bcdf55514&utm_source=chatgpt.com "Merge branch 'v4l_for_linus' of git://git.kernel.org/pub/scm/linux/ ..."
[5]: https://opensource.samsung.com/?utm_source=chatgpt.com "Samsung Open Source"
[6]: https://github.com/ianmacd/d2s/blob/master/drivers/vision/npu/npu-device.c?utm_source=chatgpt.com "d2s/drivers/vision/npu/npu-device.c at master · ianmacd/d2s"
[7]: https://github.com/LongtermSecurityInc/samsung_kernel_sm-g980f/blob/master/drivers/vision/npu/core/npu-session.c?utm_source=chatgpt.com "npu-session.c"
