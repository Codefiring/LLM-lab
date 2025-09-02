下面给你一版直接可用的改写：仅把 **analyze** 做成静态链接，其他（如 `usage`）仍按原来方式动态链接。要点是用 `llvm-config --link-static` 拿到静态链接所需的 flags，并在链接时把 C++ 运行时也静态化（`-static-libstdc++ -static-libgcc`）。另外对 Clang 的组件库加上 `-Wl,-Bstatic ... -Wl,-Bdynamic`，以便尽量用静态版（如果系统装了 `.a`），缺的再回落到动态。

```make
# Compiler
CXX       ?= clang++

# LLVM / Clang includes & flags
LLVM_INCLUDE       := $(shell llvm-config-14 --includedir)
# split out cxxflags/ldflags/libs，动态链接用
LLVM_CXXFLAGS      := $(shell llvm-config-14 --cxxflags)
LLVM_LDFLAGS       := $(shell llvm-config-14 --ldflags)
LLVM_LIBS          := $(shell llvm-config-14 --libs core)

# 静态链接用（关键：--link-static）
LLVM_LDFLAGS_STATIC:= $(shell llvm-config-14 --link-static --ldflags)
LLVM_LIBS_STATIC   := $(shell llvm-config-14 --link-static --libs core)

# Clang 组件库（顺序基本按依赖从高到低）
CLANG_LIBS := -lclangTooling -lclangFrontend -lclangDriver -lclangSerialization \
              -lclangParse -lclangSema -lclangAnalysis -lclangAST -lclangBasic \
              -lclangEdit -lclangLex -lclangASTMatchers -lclangRewrite

# 通用编译选项
CXXFLAGS  := -std=c++17 -pthread $(LLVM_CXXFLAGS) -I$(LLVM_INCLUDE)

# 动态链接时的 LDFLAGS/LIBS
LDFLAGS   := $(LLVM_LDFLAGS)
LDLIBS    := $(LLVM_LIBS) $(CLANG_LIBS)

# 静态链接时的 LDFLAGS/LIBS（尽量全部静态）
LDFLAGS_STATIC := $(LLVM_LDFLAGS_STATIC)
# 先强制对 clang 组件库静态，再回到动态（防止系统里没有某些 .a）
LDLIBS_STATIC  := -Wl,-Bstatic $(CLANG_LIBS) -Wl,-Bdynamic $(LLVM_LIBS_STATIC) \
                  -static-libstdc++ -static-libgcc

LOG_FILE := analyze-compile.log

# Object files
OBJ_FILES = helper.o

# Default target
all: analyze usage

# === 静态链接的 analyze ===
analyze: analyze.cpp $(OBJ_FILES)
	@echo "[link static] $@"
	@$(CXX) $^ -o $@ $(CXXFLAGS) $(LDFLAGS_STATIC) $(LDLIBS_STATIC) 2>&1 | tee $(LOG_FILE)

# === 保持动态链接的 usage（原样） ===
usage: usage.cpp $(OBJ_FILES)
	@echo "[link dynamic] $@"
	@$(CXX) $^ -o $@ $(CXXFLAGS) $(LDFLAGS) $(LDLIBS) 2>&1 | tee -a $(LOG_FILE)

# helper.o 只编译不链接，不需要 LLVM/Clang 的库
helper.o: helper.cpp helper.hpp
	@echo "[compile] $@"
	@$(CXX) -c $< -o $@ $(CXXFLAGS) 2>&1 | tee -a $(LOG_FILE)

clean:
	@rm -f analyze usage $(OBJ_FILES) $(LOG_FILE)

.PHONY: all clean
```

### 说明与小贴士

* 关键改动：

  * 使用 `llvm-config-14 --link-static` 获取静态链接所需的 `ldflags` 和 `libs`。
  * `analyze` 目标在链接时使用 `LDFLAGS_STATIC` 与 `LDLIBS_STATIC`，并添加 `-static-libstdc++ -static-libgcc`。
  * 对 `CLANG_LIBS` 加 `-Wl,-Bstatic ... -Wl,-Bdynamic`，以最大可能静态链接 clang 组件库，若系统无静态库会回退成动态（避免链接失败）。
* 如果你的发行版没有提供 `libclang*.a` 或 LLVM/Clang 的静态 `.a`，上面配置会尽量把能静态的都静态，剩余部分仍会以动态方式链接（这是 Linux 上比较现实的做法）。
* 若你**必须**完全静态（包括 glibc），可能需要使用 musl 工具链或确保系统安装了所有 `.a`，并在 `LDLIBS_STATIC` 前添加全局 `-static`（不推荐日常使用，会遇到 NSS/解析等问题）。
