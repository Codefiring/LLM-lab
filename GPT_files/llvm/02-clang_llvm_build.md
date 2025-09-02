下面是一套在 Ubuntu 18.04 x86\_64 上，从源码自行构建 **LLVM/Clang 14.0.0** 及其二进制包（尽量复刻官方 `clang+llvm-14.0.0-x86_64-linux-gnu-ubuntu-18.04.tar.xz` 所含内容）的实操步骤与要点。按这个流程做，最终会得到一个结构与官方包类似的 `tar.xz`，包含 clang/llvm 各工具、lld、lldb、compiler-rt（ASan/TSan 等）、libc++/libc++abi/libunwind、OpenMP 等。

---

# 1) 准备环境（Ubuntu 18.04）

```bash
sudo apt update
sudo apt install -y \
  build-essential cmake ninja-build git python3 python3-dev \
  zlib1g-dev libtinfo-dev libxml2-dev libedit-dev libncurses5-dev \
  swig liblzma-dev libzstd-dev libffi-dev pkg-config \
  libssl-dev libudev-dev
```

> 说明
>
> * **最低编译器**：LLVM 14 构建需要 C++14 支持。Ubuntu 18.04 自带的 gcc/g++ 7 就能胜任。
> * **LLDB** 需要 `swig`、`python3-dev` 等。
> * 额外库（如 `libx11-dev`、`libxcb1-dev`）只在你启用特定选项或需要 GUI/调试集成时才可能需要。

---

# 2) 获取源码（单仓库 monorepo）

```bash
git clone https://github.com/llvm/llvm-project.git
cd llvm-project
# 切到 14.0.0 的官方 tag
git checkout llvmorg-14.0.0
```

> monorepo 里已经包含 `llvm/ clang/ lld/ lldb/ compiler-rt/ libcxx/ libcxxabi/ libunwind/ openmp/ polly/ clang-tools-extra/` 等项目。

---

# 3) 建议的构建布局与安装前缀

为了做出和官方包风格接近的安装树，建议用一个明确的前缀：

```bash
export PREFIX=/opt/llvm-14.0.0   # 最终会把这个目录打包
sudo mkdir -p "$PREFIX"
sudo chown -R "$(id -u)":"$(id -g)" "$PREFIX"
```

> 官方预编译包内部目录一般类似：`clang+llvm-14.0.0-x86_64-linux-gnu-ubuntu-18.04/`。
> 我们稍后会把 `$PREFIX` 重命名为这个名字再打包。

---

# 4) 一次性“统一构建”（projects + runtimes）

LLVM 14 起推荐用 *unified build*：在同一个 build 里指定需要的 **projects**（工具链）和 **runtimes**（运行时库：compiler-rt、libc++、libunwind、openmp 等），可一次构建并安装齐全。

```bash
mkdir -p build-llvm14 && cd build-llvm14

cmake -G Ninja ../llvm-project/llvm \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DLLVM_ENABLE_PROJECTS="clang;clang-tools-extra;lld;lldb;polly" \
  -DLLVM_ENABLE_RUNTIMES="compiler-rt;libcxx;libcxxabi;libunwind;openmp" \
  -DLLVM_TARGETS_TO_BUILD="X86;AArch64;ARM;PowerPC;RISCV" \
  -DLLVM_ENABLE_ASSERTIONS=OFF \
  -DLLVM_ENABLE_TERMINFO=ON \
  -DCLANG_DEFAULT_LINKER=lld \
  -DCLANG_DEFAULT_RTLIB=compiler-rt \
  -DCLANG_DEFAULT_CXX_STDLIB=libc++ \
  -DCLANG_VENDOR=Custom \
  -DLLDB_ENABLE_PYTHON=ON \
  -DPython3_EXECUTABLE=$(command -v python3)
```

然后编译并安装：

```bash
ninja -j$(nproc)
ninja install
```

> 说明与取舍
>
> * `LLVM_ENABLE_PROJECTS`：包含官方包常见的 clang/clang-tools-extra、lld、lldb、polly。
> * `LLVM_ENABLE_RUNTIMES`：包含 **compiler-rt**（各 sanitizer、builtins）、**libc++/libc++abi/libunwind**、**OpenMP**（`libomp`）。这些正是官方包里关键的运行时内容。
> * `LLVM_TARGETS_TO_BUILD`：官方包通常内置多目标后端（至少 X86，常见还带 AArch64/ARM/RISCV/PowerPC）。可按需裁剪以缩短时间。
> * `CLANG_DEFAULT_*`：让默认 C++ 标准库/运行库/链接器与官方包一致的习惯（libc++/compiler-rt/lld）。
> * `LLVM_ENABLE_ASSERTIONS`：官方预编译通常 **OFF**；若用于开发调试，可改为 ON。
> * 这一步完成后，`$PREFIX` 下会出现 `bin/`, `lib/`, `include/`, `lib/clang/14.0.0/`（含 sanitizer 运行库）等完整布局，以及 `include/c++/v1`（libc++ 头）、`lib/libc++.so` 等。

---

# 5) 额外可选：两阶段自举（提高一致性）

部分发行的官方包使用 **bootstrap**（用系统编译器构建 stage1 的 clang，然后再用 stage1 的 clang 构建 stage2/最终产物）。如果你也想这么做，可用 CMake 的 bootstrap 选项（14 代已支持），大致：

```bash
mkdir -p build-llvm14-bootstrap && cd build-llvm14-bootstrap

cmake -G Ninja ../llvm-project/llvm \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DLLVM_ENABLE_PROJECTS="clang;clang-tools-extra;lld;lldb;polly" \
  -DLLVM_ENABLE_RUNTIMES="compiler-rt;libcxx;libcxxabi;libunwind;openmp" \
  -DLLVM_ENABLE_ASSERTIONS=OFF \
  -DCLANG_BOOTSTRAP_TARGETS="install" \
  -DCLANG_BOOTSTRAP_PASSTHROUGH="CMAKE_BUILD_TYPE;CMAKE_INSTALL_PREFIX;LLVM_ENABLE_RUNTIMES;LLVM_ENABLE_PROJECTS;LLVM_TARGETS_TO_BUILD;CLANG_DEFAULT_LINKER;CLANG_DEFAULT_RTLIB;CLANG_DEFAULT_CXX_STDLIB"

ninja clang-bootstrap-deps
ninja clang-bootstrap
# 最终会执行 install，把 stage2 安装到 $PREFIX
```

> 这会更贴近官方预编译的“自举”过程，尤其是优化水平与内置默认值的一致性。

---

# 6) 验证安装内容是否“接近官方包”

```bash
"$PREFIX/bin/clang" --version
"$PREFIX/bin/ld.lld" --version
"$PREFIX/bin/lldb" --version
tree -L 2 "$PREFIX" | less
```

你应能看到以下关键目录/文件（与官方包类似）：

* `bin/`: `clang`, `clang++`, `clang-14`, `lld`, `lldb`, 众多 `llvm-*` 工具
* `lib/clang/14.0.0/`: `lib/linux/` 下的 `libclang_rt.*`（ASan/TSan/UBSan 等）
* `include/c++/v1`: libc++ 头文件
* `lib/`: `libc++.so`, `libc++abi.so`, `libunwind.so`, `libomp.so` 等
* `libexec/`, `share/` 中的补充数据

---

# 7) 打包为与官方命名相似的 tarball

官方包名：`clang+llvm-14.0.0-x86_64-linux-gnu-ubuntu-18.04.tar.xz`。
我们把安装根目录改名为同名，然后打包：

```bash
cd /opt
sudo mv llvm-14.0.0 clang+llvm-14.0.0-x86_64-linux-gnu-ubuntu-18.04
sudo tar -cJf clang+llvm-14.0.0-x86_64-linux-gnu-ubuntu-18.04.tar.xz \
  clang+llvm-14.0.0-x86_64-linux-gnu-ubuntu-18.04
sudo chown "$(id -u)":"$(id -g)" clang+llvm-14.0.0-x86_64-linux-gnu-ubuntu-18.04.tar.xz
```

---

## 常见坑与对照项

* **编译器太老**：18.04 的 gcc/g++ 7 能编译 LLVM 14（C++14），但如果你启用某些更激进的优化或新特性，可能需要 gcc-8/9。
* **LLDB 的 Python 绑定**：确保 `python3` 与 `python3-dev` 存在且版本匹配，`-DLLDB_ENABLE_PYTHON=ON` 才能生成 `lldb` Python 模块。
* **runtimes 未安装齐**：确认 `LLVM_ENABLE_RUNTIMES` 包含 `compiler-rt;libcxx;libcxxabi;libunwind;openmp` 并且 `ninja install` 把它们安装到了 `$PREFIX`。
* **多目标后端**：官方包通常编进多个后端（不仅是 X86）。如果你只需要 X86，可把 `LLVM_TARGETS_TO_BUILD` 改成 `"X86"` 来缩短时间；但与官方包收录度会有所不同。
* **是否开启断言**：官方二进制一般 **关闭**（`OFF`），你若开启会在大小/性能上有差异。
* **RelWithDebInfo vs Release**：官方包多为 **Release**。如要更好调试可改为 `RelWithDebInfo`。

---

## 最后：如何“尽量等同官方包内容”

如果你的目标是**最大限度复刻**官方二进制的构成与默认行为：

1. 使用 **unified build**，同时拉上 `projects + runtimes`（上面的配置已覆盖）。
2. 采用 **bootstrap 两阶段**（可选，但更接近官方）。
3. 关闭断言（`LLVM_ENABLE_ASSERTIONS=OFF`），`CMAKE_BUILD_TYPE=Release`。
4. 包含常见目标后端（`X86;AArch64;ARM;PowerPC;RISCV`）。
5. 设置 `CLANG_DEFAULT_*` 让默认链接器/运行库/标准库与官方习惯一致（lld + compiler-rt + libc++）。
6. 打包时保持与官方同名的目录和压缩格式（`tar.xz`）。

如果你已经有官方包，想“对照差异”，可以把两边的安装树都 `tree` 出来做 diff（例如 `diff -ruN`），进一步微调 `CMake` 选项以靠拢。

---

需要的话我也可以给你一份最小化（仅 X86、无 lldb）的超快构建脚本，或者一个“完整复刻版（含 bootstrap）”的可直接执行脚本。你偏向哪种？
