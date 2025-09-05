没问题！下面给你一份**完整可运行的 libTooling 工具**，把“`struct` → 其直接嵌套（字段里出现的）struct 列表”导出为一个 JSON 对象：`{ "A": ["B","C"], ... }`。
已处理：指针/引用/数组、typedef、elaborated/paren/attributed 包装类型，尽量还原到真正的 `RecordDecl`。未命名结构体会被跳过。

---

# 代码（单文件）

```cpp
// file: StructNesting2JSON.cpp
#include <set>
#include <map>
#include <vector>
#include <string>
#include <algorithm>

#include "clang/AST/AST.h"
#include "clang/AST/Decl.h"
#include "clang/AST/Type.h"
#include "clang/AST/TypeVisitor.h"
#include "clang/ASTMatchers/ASTMatchFinder.h"
#include "clang/ASTMatchers/ASTMatchers.h"
#include "clang/Frontend/FrontendActions.h"
#include "clang/Tooling/CommonOptionsParser.h"
#include "clang/Tooling/Tooling.h"

#include "llvm/Support/JSON.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/raw_ostream.h"

using namespace clang;
using namespace clang::tooling;
using namespace clang::ast_matchers;

static llvm::cl::OptionCategory ToolCat("struct-nesting2json options");

// 全局依赖图：StructName -> { NestedStructNames... }
static std::map<std::string, std::set<std::string>> DepGraph;

// 把类型剥到最底层的 RecordDecl（如果有）
static const RecordDecl* peelToRecordDecl(QualType QT) {
  if (QT.isNull()) return nullptr;
  QT = QT.getCanonicalType();

  while (true) {
    if (const auto *RT = llvm::dyn_cast<RecordType>(QT)) {
      return RT->getDecl();
    }
    if (const auto *PT = llvm::dyn_cast<PointerType>(QT)) {
      QT = PT->getPointeeType();
      QT = QT.getCanonicalType();
      continue;
    }
    if (const auto *RTy = llvm::dyn_cast<ReferenceType>(QT)) {
      QT = RTy->getPointeeType();
      QT = QT.getCanonicalType();
      continue;
    }
    if (const auto *AT = llvm::dyn_cast<ArrayType>(QT)) {
      QT = AT->getElementType();
      QT = QT.getCanonicalType();
      continue;
    }
    if (const auto *ET = llvm::dyn_cast<ElaboratedType>(QT)) {
      QT = ET->getNamedType();
      QT = QT.getCanonicalType();
      continue;
    }
    if (const auto *TT = llvm::dyn_cast<TypedefType>(QT)) {
      QT = TT->desugar();
      QT = QT.getCanonicalType();
      continue;
    }
    if (const auto *ATy = llvm::dyn_cast<AttributedType>(QT)) {
      QT = ATy->getModifiedType();
      QT = QT.getCanonicalType();
      continue;
    }
    if (const auto *PTy = llvm::dyn_cast<ParenType>(QT)) {
      QT = PTy->getInnerType();
      QT = QT.getCanonicalType();
      continue;
    }
    // 模板类（如 struct S<T>）的情况：若其是 RecordType，前面已捕获；
    // 若是 TemplateSpecializationType，但底层是记录类型，Clang 通常也会给 RecordType。
    break;
  }
  return nullptr;
}

class StructCollector : public MatchFinder::MatchCallback {
public:
  void run(const MatchFinder::MatchResult &Result) override {
    const auto *RD = Result.Nodes.getNodeAs<RecordDecl>("structDecl");
    if (!RD) return;
    if (!RD->isStruct()) return;
    if (!RD->isThisDeclarationADefinition()) return;

    // 当前结构体名称
    std::string owner = RD->getNameAsString();
    if (owner.empty()) {
      // 匿名 struct：跳过
      return;
    }

    // 确保图里有 key
    auto &depSet = DepGraph[owner];

    // 遍历字段，收集字段里出现的其他 struct
    for (const FieldDecl *F : RD->fields()) {
      QualType FT = F->getType();
      const RecordDecl *FRD = peelToRecordDecl(FT);
      if (!FRD) continue;

      // 仅记录 struct（不含 class/union；如需包含可移除 isStruct 判断）
      if (!FRD->isStruct()) continue;

      std::string used = FRD->getNameAsString();
      if (used.empty()) continue;         // 匿名的跳过
      if (used == owner) continue;        // 自引用跳过（如自指针）

      depSet.insert(used);
    }
  }
};

int main(int argc, const char **argv) {
  // 解析命令行（支持 compile_commands.json）
  auto ExpectedParser = CommonOptionsParser::create(argc, argv, ToolCat);
  if (!ExpectedParser) {
    llvm::errs() << ExpectedParser.takeError();
    return 1;
  }
  CommonOptionsParser &OptionsParser = ExpectedParser.get();
  ClangTool Tool(OptionsParser.getCompilations(), OptionsParser.getSourcePathList());

  StructCollector Collector;
  MatchFinder Finder;
  // 只匹配 struct 的定义
  Finder.addMatcher(recordDecl(isStruct(), isDefinition()).bind("structDecl"), &Collector);

  int rc = Tool.run(newFrontendActionFactory(&Finder).get());
  if (rc != 0) return rc;

  // 输出 JSON：key 为 struct 名字，value 为按字典序排序的 list
  llvm::json::Object root;
  for (auto &kv : DepGraph) {
    const std::string &owner = kv.first;
    std::vector<std::string> deps(kv.second.begin(), kv.second.end());
    std::sort(deps.begin(), deps.end());
    llvm::json::Array arr;
    for (auto &s : deps) arr.push_back(s);
    root[owner] = std::move(arr);
  }

  llvm::json::Value v(std::move(root));
  // 漂亮打印（2 空格缩进）
  llvm::outs() << llvm::formatv("{0:2}\n", v);
  return 0;
}
```

---

# 用法

## 方式一：CMake（推荐）

`CMakeLists.txt`：

```cmake
cmake_minimum_required(VERSION 3.13)
project(struct_nesting2json CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(LLVM REQUIRED CONFIG)
find_package(Clang REQUIRED CONFIG)

message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")
message(STATUS "Using LLVMConfig.cmake in: ${LLVM_DIR}")
message(STATUS "Using ClangConfig.cmake in: ${Clang_DIR}")

include_directories(${LLVM_INCLUDE_DIRS} ${CLANG_INCLUDE_DIRS})
add_definitions(${LLVM_DEFINITIONS})

add_executable(struct_nesting2json StructNesting2JSON.cpp)

# 链接常用的 Clang/LLVM 组件
target_link_libraries(struct_nesting2json
  PRIVATE
    clangTooling
    clangASTMatchers
    clangFrontend
    clangSerialization
    clangAST
    clangBasic
    clangRewrite
    clangLex
    clangDriver
    LLVM
)
```

构建：

```bash
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . -j
```

## 方式二：手动编译（示例）

不同平台/发行版可能略有不同，示意如下：

```bash
clang++ -std=c++17 StructNesting2JSON.cpp \
  `llvm-config --cxxflags` \
  -o struct_nesting2json \
  -lclangTooling -lclangASTMatchers -lclangFrontend -lclangSerialization \
  -lclangAST -lclangBasic -lclangRewrite -lclangLex -lclangDriver \
  `llvm-config --ldflags --system-libs`
```

---

# 运行

假设你的工程已有 `compile_commands.json`（比如由 CMake 生成），执行：

```bash
./struct_nesting2json path/to/a.c path/to/b.c
```

或在工程根目录直接给出源文件（`compile_commands.json` 会提供正确的编译参数，如 include 路径、宏定义等）。

**输出示例：**
给定

```c
struct B { int x; };
typedef struct B B_alias;

struct A {
  B b;
  B_alias arr[3];
  struct B *pb;
};
```

输出：

```json
{
  "A": [
    "B"
  ],
  "B": []
}
```

---

# 备注与可选增强

* **包含 class/union**：把 `isStruct()` 条件去掉或并入 `isClass()/isUnion()`，并在输出里加上种类标记。
* **跨 TU 整合**：当前实现会把所有传入源文件内的定义整合到一个 JSON；若你想分文件输出，可在 `EndSourceFileAction` 里分别打印，但一般聚合更实用。
* **处理匿名/内嵌定义**：匿名结构体（无名）目前跳过；如果你希望保留，也可用位置或父声明名生成“伪名”。
* **去重**：使用 `std::set` 已去重，输出前再排序，保证稳定结果。

如果你把你的最小示例或仓库结构发给我，我也可以帮你快速调到能在你环境里直接跑的版本。
