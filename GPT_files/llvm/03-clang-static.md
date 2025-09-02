下面给你一份“尽量全静态链接”的改写版 Makefile，并在后面说明关键点与可能的坑位。你可以直接把整份替换掉原文件试一下。

```make
# ==== Toolchain / Config ====
LLVM_CONFIG ?= llvm-config-14
CXX        ?= clang++
CXXSTD     ?= c++17

# - 静态链接的关键开关：
#   -static                尝试完全静态链接（包括 glibc）
#   -static-libstdc++      把 libstdc++ 静态化
#   -static-libgcc         把 libgcc 静态化（或对 clang 是 compiler-rt）
# 注：完全静态依赖你的系统装了对应的 *.a 静态库（glibc-static、libstdc++-static、LLVM/Clang 的 .a）
COMMON_STATIC := -static -static-libstdc++ -static-libgcc

# 从 llvm-config 拿到编译/链接参数；--link-static 让 llvm/clang 首选 .a
LLVM_INCLUDE := $(shell $(LLVM_CONFIG) --includedir)
LLVM_CFLAGS  := $(shell $(LLVM_CONFIG) --cxxflags)
LLVM_LDFLAGS := $(shell $(LLVM_CONFIG) --ldflags)
LLVM_LIBS    := $(shell $(LLVM_CONFIG) --link-static --libs core) \
                $(shell $(LLVM_CONFIG) --link-static --system-libs)

# 你原本手填的 clang 库清单，静态时仍然需要：
CLANG_LIBS := -lclangTooling -lclangFrontend -lclangDriver -lclangSerialization \
              -lclangParse -lclangSema -lclangAnalysis -lclangAST -lclangBasic \
              -lclangEdit -lclangLex -lclangASTMatchers -lclangRewrite

# C/C++ 编译选项
CXXFLAGS := -std=$(CXXSTD) -pthread -I$(LLVM_INCLUDE) $(LLVM_CFLAGS)
LDFLAGS  := $(LLVM_LDFLAGS) $(COMMON_STATIC)
LIBS     := $(LLVM_LIBS) $(CLANG_LIBS)

LOG_FILE := analyze-compile.log

# ==== Objects ====
OBJ_FILES := helper.o

# ==== Targets ====
.PHONY: all clean
all: analyze usage

analyze: analyze.cpp $(OBJ_FILES)
	@$(CXX) $^ -o $@ $(CXXFLAGS) $(LDFLAGS) $(LIBS) 2>&1 | tee $(LOG_FILE)

usage: usage.cpp $(OBJ_FILES)
	@$(CXX) $^ -o $@ $(CXXFLAGS) $(LDFLAGS) $(LIBS) 2>&1 | tee -a $(LOG_FILE)

# 只编译 .o（编译阶段不需要库）
helper.o: helper.cpp helper.hpp
	@$(CXX) -c $< -o $@ $(CXXFLAGS) 2>&1 | tee -a $(LOG_FILE)

clean:
	@rm -f analyze usage $(OBJ_FILES) $(LOG_FILE)
```

# 关键说明（静态化要点）

* `--link-static`：让 `llvm-config` 给出静态库优先的链接标志；这对 `libLLVM*.a` 生效。
* `-static -static-libstdc++ -static-libgcc`：尝试把 C 运行库、libstdc++、libgcc 都静态化。
  如果你用的是 clang，`-static-libgcc` 等价于把 compiler-rt 静态化；保持这个选项即可。
* **系统依赖**：完全静态通常需要这些包（名字按常见发行版举例）：

  * `glibc-static`（或等价提供者；有的发行版不提供全静态 glibc）
  * `libstdc++-static`
  * `llvm-static`/`clang-static` 或者包含 `libLLVM*.a`、`libclang*.a` 的开发包
* **现实限制**：很多发行版的 clang/llvm **默认只提供共享库**。如果缺少 `libclang*.a`，
  完全静态会失败。此时你有两个退路：

  1. 继续使用上面的 Makefile，但去掉最前面的 `-static`，只保留 `-static-libstdc++ -static-libgcc`，这样是“**大部分静态** + 动态 glibc/系统库”，兼容性更好；
  2. 自行静态构建 LLVM/Clang（开启 `LLVM_LINK_LLVM_DYLIB=OFF` 并生成 `.a`），再编译本项目。

# 常见报错与处理

* **“cannot find -lclangXXX”**：说明对应静态库没有安装或不在搜索路径。安装静态包，或把路径加到 `LDFLAGS`（例如 `-L/path/to/clang/static`）。
* **“/usr/bin/ld: cannot find -lc”**：缺少 glibc 静态包（或发行版不支持全静态 glibc）。可改用“部分静态”方案（去掉 `-static`）。
* **顺序问题**：某些平台对库顺序敏感。若仍报未定义符号，可以把 `$(LIBS)` 放在命令行最后（现在已在末尾），或尝试 `-Wl,--start-group ... -Wl,--end-group` 包裹 `$(LIBS)`。

需要我帮你检测你机器上有没有这些静态库（给我一份 `llvm-config-14 --version` 和 `locate libclang*.a` 的输出）的话，直接贴出来就行。
