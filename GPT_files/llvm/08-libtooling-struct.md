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
