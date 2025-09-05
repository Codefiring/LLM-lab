好的！你不想新建 class，只通过“增加函数 + 轻改 VisitFunctionDecl”来完成：在函数定义体里**仅收集直接调用的子函数（不递归到被调函数内部）**，并把结果输出成 JSON，key 为函数名、value 为它直接包含的其他函数名列表。下面给出可直接粘贴的最小改动实现，适配 **Clang 14 / 纯 C 工程**。

### 做法概览

* 在函数体 `Stmt*` 上做一次**语法树遍历**，只找 `CallExpr`；
* 通过 `CallExpr::getDirectCallee()` 或从 `DeclRefExpr` 提取被调函数名（跳过函数指针等无法解析到名字的情况）；
* 去重后按 `{ "<function>": ["callee1","callee2", ...] }` 的结构写入 **JSONL** 文件（每行一个 JSON 对象），便于后续合并或流式处理。

---

### 需要的头文件

```cpp
#include "clang/AST/AST.h"
#include "clang/AST/Expr.h"
#include "clang/AST/Stmt.h"
#include "llvm/ADT/SmallSet.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Support/FileSystem.h"
```

### 新增的辅助函数（不新增 class）

```cpp
// 在语句树内收集“直接调用”的被调函数名（不跨函数递归）
static void collect_direct_callees(const clang::Stmt *S,
                                   llvm::SmallSet<std::string, 64> &Out) {
  using namespace clang;
  if (!S) return;

  if (const auto *CE = llvm::dyn_cast<CallExpr>(S)) {
    const FunctionDecl *CalleeFD = CE->getDirectCallee();
    if (CalleeFD) {
      std::string Name = CalleeFD->getNameAsString();
      if (!Name.empty()) Out.insert(std::move(Name));
    } else {
      // 尝试从 Callee 表达式里拿 DeclRef（有时也能解析到函数名）
      const Expr *Callee = CE->getCallee();
      if (Callee) {
        Callee = Callee->IgnoreParenImpCasts();
        if (const auto *DRE = llvm::dyn_cast<DeclRefExpr>(Callee)) {
          if (const auto *FD = llvm::dyn_cast<FunctionDecl>(DRE->getDecl())) {
            std::string Name = FD->getNameAsString();
            if (!Name.empty()) Out.insert(std::move(Name));
          }
        }
      }
    }
  }

  // 遍历子节点（只是遍历语句树，不会递归到其他函数定义里）
  for (const Stmt *Child : S->children()) {
    if (Child) collect_direct_callees(Child, Out);
  }
}

// 以 { "func": ["callee1","callee2"] } 结构，逐行写入 JSONL 文件
static void output_func_calls_jsonl(const clang::FunctionDecl *FD,
                                    llvm::StringRef OutPath) {
  using namespace clang;
  llvm::SmallSet<std::string, 64> Callees;
  const Stmt *Body = FD->getBody();
  if (Body) collect_direct_callees(Body, Callees);

  // 组织 JSON
  llvm::json::Array Arr;
  for (const auto &Name : Callees) Arr.push_back(Name);

  llvm::json::Object Obj;
  Obj[FD->getNameAsString()] = std::move(Arr);

  // 追加写入 .jsonl
  std::error_code EC;
  llvm::raw_fd_ostream OS(OutPath, EC,
                          llvm::sys::fs::OF_Append | llvm::sys::fs::OF_Text);
  if (EC) {
    llvm::errs() << "Failed to open " << OutPath << ": " << EC.message() << "\n";
    return;
  }
  llvm::json::OStream J(OS);
  J.value(Obj);
  OS << "\n";
}
```

### 改动你的 `VisitFunctionDecl`

只需在你已有逻辑里多调用一次上面的输出函数即可（不改变现有输出行为）：

```cpp
bool VisitFunctionDecl(FunctionDecl *funcDecl) {
  if (!collect_func)
    return true;

  if (funcDecl->isThisDeclarationADefinition()) {
    std::string funcName = funcDecl->getNameAsString();
    std::string sourceCode = get_decl_code(funcDecl);
    if (!funcName.empty()) {
      // 你原有的输出
      output_decl(funcDecl, "func.jsonl");
      // 新增：输出 直接被调函数 列表（JSONL，每行一条）
      output_func_calls_jsonl(funcDecl, "func_calls.jsonl");
    }
  }
  return true;
}
```

---

### 输出说明

* 文件：`func_calls.jsonl`
* 每行一个 JSON 对象，形如：

  ```json
  {"foo": ["printf", "bar", "baz"]}
  ```
* 只包含**直接**调用（单个函数体内的 `CallExpr`），不会递归到被调函数的定义继续展开。
* 无法静态解析出名字（如函数指针调用）的，会被跳过。

> 如果你确实需要生成“一个大 JSON（所有函数聚合成一个字典）”，也可以在 `FrontendAction` 结束时收口统一写一次；但你要求“不新增 class”，且当前代码风格用的是 jsonl 逐条输出，上面实现保持了同样的追加写入模式，落地最小。需要聚合版的话告诉我，我给你一个不引入新类的静态全局容器版本。
