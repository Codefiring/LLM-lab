这个报错通常只有两种原因：

## 先判定是哪一种

1. **系统里真的没有系统头文件**
   在 Debian/Ubuntu 的精简环境里，如果没装 `libc` 开发头，`/usr/include/limits.h` 就确实不存在。

   * 检查：

     ```bash
     ls -l /usr/include/limits.h
     ```
   * 如果不存在，装系统 C 头：

     ```bash
     # Debian/Ubuntu
     sudo apt update
     sudo apt install libc6-dev   # 或者干脆：sudo apt install build-essential

     # Alpine（musl）
     sudo apk add musl-dev
     ```

   这一步**不依赖** `libclang-dev`，只是把系统标准头补齐。

2. **头文件在，但 ClangTool 没把系统头路径带上**
   常见于：用 /opt 的独立 Clang、跨编译、或者 `compile_commands.json` 里带了 `-isysroot` / `-nostdinc` 等选项，导致搜索路径被“重定向”。

   * 先看 Clang 当前搜索路径：

     ```bash
     echo "" | /opt/clang-14/bin/clang -x c -E -v -
     # 或 C++：
     echo "" | /opt/clang-14/bin/clang++ -x c++ -E -v -
     ```

     末尾会列出 `#include <...> search starts here:` 的真实路径；如果没有 `/usr/include` 或 `/usr/include/x86_64-linux-gnu`，就说明路径没带上。

---

## 修复方式（针对第 2 种）

### A. 运行你的 LibTooling 工具时补充“系统头/工具链”信息

给 LibTooling 可执行程序追加额外参数（会附加到每条 compile\_commands 指令后）：

```bash
# 假设你的工具叫 analyze，build 目录里有 compile_commands.json
analyze -p build \
  --extra-arg=--gcc-toolchain=/usr \
  --extra-arg=-isystem/usr/include \
  --extra-arg=-isystem/usr/include/x86_64-linux-gnu \
  --extra-arg=-resource-dir=/opt/clang-14/lib/clang/14.0.6
```

说明：

* `--gcc-toolchain=/usr` 让 clang 继承 GCC 的系统头/运行库布局（Debian/Ubuntu 上很管用）。
* `-isystem /usr/include` 与 `-isystem /usr/include/x86_64-linux-gnu` 显式补上 glibc 头的多架构路径。
* `-resource-dir` 指向你那套 clang 的 builtin headers 目录（路径按实际版本改）。

如果你是用 `ClangTool`/`CommonOptionsParser` 写的，可在代码里加：

```cpp
tool.appendArgumentsAdjuster(
  clang::tooling::getInsertArgumentAdjuster("--gcc-toolchain=/usr",
                                            clang::tooling::ArgumentInsertPosition::END));
tool.appendArgumentsAdjuster(
  clang::tooling::getInsertArgumentAdjuster("-isystem/usr/include", clang::tooling::ArgumentInsertPosition::END));
tool.appendArgumentsAdjuster(
  clang::tooling::getInsertArgumentAdjuster("-isystem/usr/include/x86_64-linux-gnu", clang::tooling::ArgumentInsertPosition::END));
```

### B. 清除 compile\_commands 里的“破坏性”选项

如果你的 `compile_commands.json` 来自交叉环境/SDK，可能带了 `-nostdinc`, `-isysroot=<某个SDK>`，而那个 SDK 没有 `limits.h`。
做法：

* 生成一个“本机构建”的 `compile_commands.json`（例如本机用 GCC/Clang 正常编一次）。
* 或在 LibTooling 层**移除**这些选项，再补 A 中的 `--gcc-toolchain` 和 `-isystem`。

### C. 指定 target，避免跑到错误的多架构路径

```bash
--extra-arg=-target --extra-arg=x86_64-linux-gnu
```

在本机 x86\_64 上可帮助选择正确的多架构 include 目录。

---

## 一次性快速排错清单

* `ls /usr/include/limits.h`：不存在 → 安装 `libc6-dev`（或对应发行版的 C 头包）。
* `clang -E -v -`：确认 include 搜索路径里是否有 `/usr/include` 与 `/usr/include/x86_64-linux-gnu`。
* 运行工具时加：`--gcc-toolchain=/usr`、`-isystem/usr/include`、`-isystem/usr/include/x86_64-linux-gnu`。
* 检查 `compile_commands.json` 是否含 `-isysroot`/`-nostdinc`，必要时移除或覆盖。
* 如果你用的是 `/opt/clang-14`，确保 `-resource-dir` 指向它的 `lib/clang/<ver>`（里面有 builtin headers）。

---

如果你把**工具的完整调用命令**（含 `-p` 和额外参数）以及一条**报错对应的 compile\_commands.json 的 command 行**贴出来，我可以帮你精确写出那一条的修正参数。
