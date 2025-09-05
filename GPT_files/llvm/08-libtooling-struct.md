可以！下面给你一套**基于 Clang 14 的完整 libTooling 工具**：读取 `compile_commands.json`，扫描工程里所有 **struct** 的字段类型，收集“结构体 A 的字段里用了哪些结构体 B”，并把结果写成 JSON（`{ "A": ["B", "C", ...], ... }`）。
要点：去除 `typedef`/`ElaboratedType`/指针/引用/数组等“外衣”，解析出真正的 `RecordDecl`；去重；默认跳过自引用（如 `struct A { A* next; }`）。

---

# 代码（单文件）

**src/struct\_nesting\_tool.cpp**

```cpp
#include <set>
#include <map>
#include <string>
#include <vector>
#include <algorithm>

#include "clang/AST/AST.h"
#include "clang/AST/Type.h"
#include "clang/AST/TypeLoc.h"
#include "clang/AST/RecordLayout.h"
#include "clang/ASTMatchers/ASTMatchFinder.h"
#include "clang/Frontend/FrontendActions.h"
#include "clang/Tooling/CommonOptionsParser.h"
#include "clang/Tooling/Tooling.h"

#include "llvm/Support/CommandLine.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/Path.h"
#include "llvm/Support/RawOstream.h"
#include "llvm/Support/FileSystem.h"

using namespace clang;
using namespace clang::tooling;
using namespace clang::ast_matchers;

namespace {

llvm::cl::OptionCategory ToolCategory("struct-nesting options");

llvm::cl::opt<std::string> OutputPath(
    "o",
    llvm::cl::desc("Output JSON file path"),
    llvm::cl::init("struct_nesting.json"),
    llvm::cl::cat(ToolCategory));

// strip typedef/elaborated/pointer/reference/array etc. to find underlying RecordDecl
const RecordDecl* peelToRecordDecl(QualType QT, ASTContext &Ctx) {
  // Desugar first
  QT = QT.getDesugaredType(Ctx);

  // Defensive iteration limit
  for (int i = 0; i < 16; ++i) {
    if (const auto *RT = QT->getAs<RecordType>()) {
      return RT->getDecl();
    }
    if (const auto *ELT = dyn_cast<ElaboratedType>(QT)) {
      QT = ELT->getNamedType().getDesugaredType(Ctx);
      continue;
    }
    if (const auto *TDT = dyn_cast<TypedefType>(QT)) {
      QT = TDT->desugar().getDesugaredType(Ctx);
      continue;
    }
    if (const auto *PT = QT->getAs<PointerType>()) {
      QT = PT->getPointeeType().getDesugaredType(Ctx);
      continue;
    }
    if (const auto *RTy = QT->getAs<ReferenceType>()) {
      QT = RTy->getPointeeType().getDesugaredType(Ctx);
      continue;
    }
    if (const auto *AT = Ctx.getAsArrayType(QT)) {
      QT = AT->getElementType().getDesugaredType(Ctx);
      continue;
    }
    break;
  }
  return nullptr;
}

struct Collector : public MatchFinder::MatchCallback {
  std::map<std::string, std::set<std::string>> &Graph;

  explicit Collector(std::map<std::string, std::set<std::string>> &G) : Graph(G) {}

  void run(const MatchFinder::MatchResult &Result) override {
    const auto *RD = Result.Nodes.getNodeAs<RecordDecl>("structDecl");
    if (!RD || !RD->isStruct() || !RD->isThisDeclarationADefinition())
      return;

    // 只针对命名的 struct
    std::string owner = RD->getQualifiedNameAsString();
    if (owner.empty()) return;

    // 初始化节点
    Graph.emplace(owner, std::set<std::string>{});

    // 遍历字段
    for (const FieldDecl *F : RD->fields()) {
      QualType FT = F->getType();
      const RecordDecl *FRD = peelToRecordDecl(FT, *Result.Context);
      if (!FRD) continue;

      if (!FRD->isStruct()) continue;               // 只关心 struct（类/联合可按需放开）
      std::string used = FRD->getQualifiedNameAsString();
      if (used.empty()) continue;
      if (used == owner) continue;                  // 跳过自引用（如 A* next）

      Graph[owner].insert(used);
    }
  }
};

} // namespace

int main(int argc, const char **argv) {
  llvm::InitLLVM X(argc, argv);

  auto ExpParser = CommonOptionsParser::create(argc, argv, ToolCategory);
  if (!ExpParser) {
    llvm::errs() << ExpParser.takeError();
    return 1;
  }
  CommonOptionsParser &OptionsParser = ExpParser.get();

  ClangTool Tool(OptionsParser.getCompilations(),
                 OptionsParser.getSourcePathList());

  std::map<std::string, std::set<std::string>> graph;

  Collector collector(graph);
  MatchFinder finder;
  finder.addMatcher(recordDecl(isStruct(), isDefinition()).bind("structDecl"), &collector);

  int rc = Tool.run(newFrontendActionFactory(&finder).get());
  if (rc != 0) return rc;

  // 转成 JSON
  llvm::json::Object root;
  for (auto &kv : graph) {
    std::vector<llvm::json::Value> arr;
    arr.reserve(kv.second.size());
    std::vector<std::string> sorted(kv.second.begin(), kv.second.end());
    std::sort(sorted.begin(), sorted.end());
    for (auto &s : sorted) arr.emplace_back(llvm::json::Value(s));
    root.insert({kv.first, llvm::json::Array(std::move(arr))});
  }

  // 输出文件
  std::error_code EC;
  llvm::raw_fd_ostream OS(OutputPath, EC, llvm::sys::fs::OF_Text);
  if (EC) {
    llvm::errs() << "Failed to open " << OutputPath << ": " << EC.message() << "\n";
    return 2;
  }
  OS << llvm::formatv("{0:2}", llvm::json::Value(std::move(root))) << "\n";
  OS.flush();

  return 0;
}
```

---

# CMake（Clang/LLVM 14）

**CMakeLists.txt**

```cmake
cmake_minimum_required(VERSION 3.16)
project(struct_nesting_tool CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 如果你的 LLVM/Clang 安装不在默认路径，设置：
#   -DLLVM_DIR=/path/to/llvm-14/lib/cmake/llvm
#   -DClang_DIR=/path/to/llvm-14/lib/cmake/clang
find_package(LLVM 14 REQUIRED CONFIG)
find_package(Clang 14 REQUIRED CONFIG)

message(STATUS "Found LLVM: ${LLVM_PACKAGE_VERSION}")
message(STATUS "Using LLVMConfig.cmake in: ${LLVM_DIR}")
message(STATUS "Using ClangConfig.cmake in: ${Clang_DIR}")

include_directories(${LLVM_INCLUDE_DIRS})
include_directories(${CLANG_INCLUDE_DIRS})
add_definitions(${LLVM_DEFINITIONS})

add_executable(struct_nesting_tool
  src/struct_nesting_tool.cpp
)

# 防止 Windows 上符号问题
if(MSVC)
  add_definitions(-D_CRT_SECURE_NO_WARNINGS)
endif()

# 链接需要的 Clang/LLVM 库
target_link_libraries(struct_nesting_tool
  PRIVATE
    clangTooling
    clangASTMatchers
    clangAST
    clangBasic
    clangFrontend
    clangSerialization
    clangLex
    LLVM
)

# 开启更严格的编译选项（可选）
if (CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
  target_compile_options(struct_nesting_tool PRIVATE -Wall -Wextra -Wno-unused-parameter)
endif()
```

---

# 使用方法

1. 生成 `compile_commands.json`（例如 CMake 项目）：

```bash
cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
```

2. 编译工具：

```bash
mkdir -p tool_build
cmake -S . -B tool_build -DLLVM_DIR=/path/to/llvm-14/lib/cmake/llvm -DClang_DIR=/path/to/llvm-14/lib/cmake/clang
cmake --build tool_build --config Release -j
```

3. 运行（指向你的源码或待分析文件；`-p` 目录里要有 `compile_commands.json`）：

```bash
tool_build/struct_nesting_tool -p build <source-or-dir>... -o out_structs.json
# 例：分析整个源码树的所有 .c/.cpp：把源码目录传给它
tool_build/struct_nesting_tool -p build . -o struct_nesting.json
```

* `-p build`：包含 `compile_commands.json` 的目录
* `<source-or-dir>`：一个或多个源码路径（与 `clang-tidy` 用法一致；给 `.` 会让 libTooling 以 compile\_commands.json 中的条目为准遍历）
* `-o`：输出 JSON 路径，默认 `struct_nesting.json`

---

# 输出示例

给定：

```cpp
struct B { int x; };
struct C {};
struct A {
  B b;
  C* pc;
  B arr[3];
};
```

得到（`struct_nesting.json`）：

```json
{
  "A": ["B", "C"],
  "B": [],
  "C": []
}
```

---

# 说明与可选增强

* 目前只统计 **struct → struct** 的依赖；若你也想要 class/union，可把匹配条件改为 `recordDecl(isDefinition()).bind(...)` 并在回调里接受 `FRD->isStruct() || FRD->isClass() || FRD->isUnion()`。
* 自引用（例如链表结点 `A* next;`）默认忽略；如需保留，把 `if (used == owner) continue;` 去掉即可。
* 匿名 struct/匿名嵌套会被跳过（名字为空）。如需处理，可给它们生成稳定 ID（文件+行号）。
* 若想忽略系统头文件定义的结构体，可在 owner/used 两侧加 `Result.SourceManager->isInSystemHeader(...)` 判断进行过滤。
* 若工程很大、跨 TU 重复很多，当前用 `std::set` 去重，输出稳定。

需要我再给你一个最小示例工程（含示例代码与 `compile_commands.json`）用来快速验证吗？



明白了 👍，这是典型的 **链接 LLVM 的方式不对** 的问题。

在 LLVM/Clang 的 CMake 包里，**通常不会有一个单独的 `-lLLVM` 静态库**，而是拆成了几十个子库（`LLVMSupport`、`LLVMCore`、`LLVMOption` 等等）。所以你在 CMake 里写 `target_link_libraries(... LLVM)` 会报错 `-lLLVM no such file or directory`。

---

## 解决办法

### ✅ 推荐：用 `llvm-config` 自动生成库列表

你可以在 CMakeLists 里用 `llvm-config` 拿到正确的库集：

```cmake
execute_process(
  COMMAND llvm-config-14 --libs --system-libs
  OUTPUT_VARIABLE LLVM_LIBS
  OUTPUT_STRIP_TRAILING_WHITESPACE
)

separate_arguments(LLVM_LIBS)
```

然后在 target 里加上：

```cmake
target_link_libraries(struct_nesting_tool
  PRIVATE
    clangTooling
    clangASTMatchers
    clangAST
    clangBasic
    clangFrontend
    clangSerialization
    clangLex
    ${LLVM_LIBS}
)
```

这样 CMake 会展开成一长串 `-lLLVMSupport -lLLVMCore -lLLVMOption ...`，不会出 `-lLLVM` 错误。

---

### 🚑 如果你坚持用 `find_package(LLVM REQUIRED CONFIG)`

那就不要写 `LLVM` 这个目标。LLVM CMake 提供了 **IMPORTED targets**，比如 `LLVMSupport`、`LLVMCore` 等。你可以写：

```cmake
target_link_libraries(struct_nesting_tool
  PRIVATE
    clangTooling
    clangASTMatchers
    clangAST
    clangBasic
    clangFrontend
    clangSerialization
    clangLex
    LLVMSupport
    LLVMCore
    LLVMOption
    LLVMFrontendOpenMP      # 根据需要加
)
```

通常最少要 `LLVMSupport`，否则连 `raw_ostream` 都用不了。

---

### ⚡ 小技巧

在命令行里执行：

```bash
llvm-config-14 --libs core support option
```

可以看到需要哪些库。你也能用：

```bash
llvm-config-14 --libs all --system-libs
```

直接输出全套库名。

---

## 建议做法

如果你只是写 **Clang Tooling 工具**，你大概率只需要：

* `LLVMSupport`
* `LLVMCore`
* `LLVMOption`

其余的由 Clang 库自己再拉。

---

要不要我给你改一个**精简版 CMakeLists.txt**，用 `llvm-config` 自动展开依赖，这样就不用手工维护 `-l` 列表了？


好的！这是一个**精简且健壮**的 `CMakeLists.txt`，适配 **Clang 14**，并用 `llvm-config` 自动拿到需要的 LLVM 库，避免了 `-lLLVM` 的链接错误。它会优先找 `llvm-config-14`，找不到再回退到 `llvm-config`。

把下面内容保存为项目根目录的 `CMakeLists.txt` 即可：

```cmake
cmake_minimum_required(VERSION 3.16)
project(struct_nesting_tool CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --- 找 llvm-config（优先 14 版，找不到再回退） ---
find_program(LLVM_CONFIG_EXE NAMES llvm-config-14 llvm-config REQUIRED)
message(STATUS "Using llvm-config: ${LLVM_CONFIG_EXE}")

# --- 拿到 LLVM 需要的库和系统库 ---
execute_process(COMMAND ${LLVM_CONFIG_EXE} --libs --system-libs
                OUTPUT_VARIABLE LLVM_LIBS_RAW
                OUTPUT_STRIP_TRAILING_WHITESPACE)
separate_arguments(LLVM_LIBS_RAW)
set(LLVM_LIBS ${LLVM_LIBS_RAW})

# 可选：如果你想更精简地只拉核心库，可以用：
# execute_process(COMMAND ${LLVM_CONFIG_EXE} --libs core support option --system-libs
#                 OUTPUT_VARIABLE LLVM_LIBS_RAW
#                 OUTPUT_STRIP_TRAILING_WHITESPACE)
# separate_arguments(LLVM_LIBS_RAW)
# set(LLVM_LIBS ${LLVM_LIBS_RAW})

# --- 也拿一下 LLVM 的 include 路径（一般 Clang 的 CMake 包已包含，不拿也行） ---
execute_process(COMMAND ${LLVM_CONFIG_EXE} --includedir
                OUTPUT_VARIABLE LLVM_INCLUDE_DIR
                OUTPUT_STRIP_TRAILING_WHITESPACE)

# --- 找 Clang 14（用它的 CMake 包提供的 imported targets，如 clangTooling 等） ---
# 如果安装路径不在默认目录，可在配置时传 -DClang_DIR=/path/to/llvm-14/lib/cmake/clang
find_package(Clang 14 REQUIRED CONFIG)
message(STATUS "Found Clang: ${Clang_DIR}")

# （可选）启用 Clang/LLVM 的头文件路径
include_directories(${LLVM_INCLUDE_DIR})
include_directories(${CLANG_INCLUDE_DIRS})

# --- 目标 ---
add_executable(struct_nesting_tool
  src/struct_nesting_tool.cpp
)

# --- 编译选项（精简） ---
if (CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
  target_compile_options(struct_nesting_tool PRIVATE -Wall -Wextra -Wno-unused-parameter)
elseif (MSVC)
  target_compile_options(struct_nesting_tool PRIVATE /W4)
  add_definitions(-D_CRT_SECURE_NO_WARNINGS)
endif()

# --- 链接 ---
# 关键点：不要写 “LLVM” 这个聚合名；使用 clang 的 imported targets + llvm-config 展开的库列表
target_link_libraries(struct_nesting_tool
  PRIVATE
    clangTooling
    clangASTMatchers
    clangAST
    clangBasic
    clangFrontend
    clangSerialization
    clangLex
    ${LLVM_LIBS}
)

# --- 小贴士输出 ---
message(STATUS "LLVM libs: ${LLVM_LIBS}")
message(STATUS "LLVM include: ${LLVM_INCLUDE_DIR}")
```

## 用法速记

```bash
# 1) 你的工程（含 src/struct_nesting_tool.cpp 与上面的 CMakeLists.txt）
# 2) 生成被分析项目的 compile_commands.json（示例）
cmake -S your_project -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

# 3) 构建本工具
cmake -S . -B tool_build -DClang_DIR=/path/to/llvm-14/lib/cmake/clang
cmake --build tool_build --config Release -j

# 4) 运行（-p 指向含 compile_commands.json 的目录）
tool_build/struct_nesting_tool -p build . -o struct_nesting.json
```

如果你的系统包名不是 `llvm-config-14`（比如用的自编译或不同发行版），只要 `llvm-config` 在 PATH 里也没问题；上面的脚本会自动回退。需要我给你一个同时兼容 **Clang 13/15** 的变体吗？



这是经典的**RTTI/链接**问题。`undefined reference to typeinfo for clang::ASTFrontendAction` 通常由以下几种原因之一导致：

1. 没有启用 RTTI（被某处 `-fno-rtti` 关掉了）；
2. 少链接了产生该类型 vtable/typeinfo 的库（主要是 **clangFrontend** 及其同伴库）；
3. 使用静态库时，链接器顺序/循环依赖，导致符号没被拉进来。

下面给你一个稳妥的**精简修复方案**（在你当前的精简版 CMake 基础上补几行即可）：

---

## CMake 修复片段

把你的 `CMakeLists.txt` 里 `target_link_libraries` 和编译选项部分改成这样（关键新增点已注释）：

```cmake
# 1) 确保开启 RTTI（避免被全局 flags 关掉）
if (CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
  target_compile_options(struct_nesting_tool PRIVATE -Wall -Wextra -Wno-unused-parameter -frtti)
elseif (MSVC)
  target_compile_options(struct_nesting_tool PRIVATE /W4 /GR)  # /GR 打开 RTTI
endif()

# 2) Clang/LLVM 需要的库（补齐 Frontend 工具链相关）
set(CLANG_LIBS
  clangTooling
  clangASTMatchers
  clangAST
  clangBasic
  clangLex
  clangSerialization
  clangFrontend
  clangFrontendTool      # ✅ 常见遗漏
  clangDriver            # ✅ 常见遗漏
  clangRewriteFrontend   # 可选，但很多工具会间接用到
  clangRewrite           # 可选
  clangEdit              # 可选
)

# 3) 如果你用的是静态构建的 LLVM/Clang，建议把库放进 --start-group/--end-group
#    这样能解决循环依赖导致的“未定义引用”
if (UNIX AND NOT APPLE)  # GNU ld
  set(START_GROUP -Wl,--start-group)
  set(END_GROUP   -Wl,--end-group)
endif()

# 4) 继续沿用你之前通过 llvm-config 拿到的 LLVM_LIBS（保持不变）
#    假设变量 ${LLVM_LIBS} 已由前文 execute_process + separate_arguments 得到

target_link_libraries(struct_nesting_tool
  PRIVATE
    ${START_GROUP}
    ${CLANG_LIBS}
    ${LLVM_LIBS}
    ${END_GROUP}
)
```

---

## 额外检查清单

* **确认没有 `-fno-rtti`**：检查你的全局 CXXFLAGS、工具链默认选项或公司模板 CMake；如果看到 `-fno-rtti`，删掉或在目标上用 `-frtti` 覆盖。
* **确认包含头**：`#include "clang/Frontend/FrontendActions.h"`（注意是 **FrontendActions.h** 复数）；以及先前修正过的 `#include "llvm/Support/InitLLVM.h"` / `#include "llvm/Support/raw_ostream.h"`。
* **库是否存在**：如果某些发行版把 `clangFrontendTool` 拆分得不一样，跑一遍

  ```bash
  llvm-config-14 --link-static --libs --system-libs
  ```

  或

  ```bash
  llvm-config-14 --libs all --system-libs
  ```

  看看是否需要改名/增减库。
* **静态 vs 动态**：若你链接的是**静态** LLVM/Clang（常见于自编译），`--start-group/--end-group` 很关键；如果是动态库，通常不需要，但加上也无害。
* **libstdc++/libc++**：尽量与 LLVM/Clang 的编译选项一致（两者都用 libstdc++ 或都用 libc++），避免 C++ ABI 不一致造成奇怪链接报错。

---

如果按上面改完仍报同样的错，把你的**完整链接命令行**（`cmake --build` 的 verbose 输出）贴我，我帮你定位具体是哪个库没进来或顺序问题。
