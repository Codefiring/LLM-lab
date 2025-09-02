要在遍历到一个 `EnumDecl` 时把它的 **枚举常量（EnumConstantDecl）** 一并提取出来，你可以直接从 `EnumDecl` 迭代它的 enumerators。Clang 已经帮你按标准把值算好了（即使没有显式初始化），用 `getInitVal()` 就能拿到一个 `llvm::APSInt`。下面给你一段可直接嵌入的实现思路与代码。

## 要点速览

* `for (auto *EC : enumDecl->enumerators())` 迭代常量。
* 名称：`EC->getNameAsString()`
* 值（规范化后的整数）：`EC->getInitVal()`（`APSInt` -> 用 `toString(10)` 转十进制字符串）
* 源码拼写（若显式初始化）：`EC->getInitExpr()` 拿到 `Expr*`，再用你的 `get_decl_code`/`get_source_text` 取原文。
* 作用域枚举判定：`enumDecl->isScoped()`（`enum class`）
* 固定底层类型：`enumDecl->getIntegerType()`（若用户写了 `: unsigned` 等）
* 匿名枚举：`enumDecl->getNameAsString()` 为空，可用 `getQualifiedNameAsString()` 或位置信息区分；也可以记录它的 `typedef` 别名（若存在）在别处关联。

---

## 直接在你的 `VisitEnumDecl` 中补充提取逻辑

```cpp
bool VisitEnumDecl(clang::EnumDecl *enumDecl) {
  if (!collect_enum) return true;

  if (!enumDecl->isThisDeclarationADefinition())
    return true;

  std::string enumName = enumDecl->getNameAsString();             // 可能为空（匿名枚举）
  std::string qname    = enumDecl->getQualifiedNameAsString();    // 带命名空间/类作用域
  std::string source   = get_decl_code(enumDecl);                 // 你已有的函数
  bool isScoped        = enumDecl->isScoped();                    // enum class ?
  clang::QualType underlying = enumDecl->getIntegerType();        // 固定底层类型（可能为空）

  // 1) 先输出枚举本体（你已有）
  if (!enumName.empty())
    output_decl(enumDecl, "enum.jsonl");

  // 2) 输出该枚举的每个枚举常量
  for (const clang::EnumConstantDecl *EC : enumDecl->enumerators()) {
    std::string constName = EC->getNameAsString();

    // 规范化值（无论是否显式初始化，Clang 都计算好了）
    llvm::APSInt val = EC->getInitVal();
    // 以十进制字符串形式保存（带符号与否由 APSInt 内部控制）
    std::string valueStr = val.toString(10);

    // 如果显式写了初始化表达式，拿原始源码（可选）
    std::string spelledInit;
    if (const clang::Expr *Init = EC->getInitExpr()) {
      spelledInit = get_decl_code(Init); // 或者你实现的 get_source_text(Init)
    }

    // 可选：位置信息，方便溯源
    std::string filePath;
    unsigned line = 0, col = 0;
    {
      const auto &SM = enumDecl->getASTContext().getSourceManager();
      clang::SourceLocation loc = EC->getLocation();
      clang::PresumedLoc P = SM.getPresumedLoc(loc);
      if (P.isValid()) {
        filePath = P.getFilename();
        line = P.getLine();
        col = P.getColumn();
      }
    }

    // 你可以重载/新增一个输出函数；或复用 output_decl 并通过额外字段传下去
    // 下面示例展示“构造一个对象然后输出 JSONL”的思路（伪代码/示意）：
    output_enum_constant(
      /*node=*/EC,
      /*outfile=*/"enum-constants.jsonl",
      /*fields:*/{
        {"enumName", enumName},                 // 可能为空
        {"qualifiedEnumName", qname},
        {"scoped", isScoped},
        {"underlyingType", underlying.isNull() ? "" : underlying.getAsString()},
        {"name", constName},
        {"value", valueStr},
        {"spelledInit", spelledInit},
        {"file", filePath},
        {"line", std::to_string(line)},
        {"col", std::to_string(col)}
      }
    );
  }

  return true;
}
```

> 如果你只想要“把常量数组嵌入到枚举的 JSON 里”，也可以先把常量收集到 `std::vector<YourConstStruct>`，然后在 `output_decl(enumDecl, "enum.jsonl")` 时把这个数组一并序列化输出。

---

## 一个可能的 `output_enum_constant` 实现（示意）

如果你使用 `llvm::json` 写 JSONL（每行一个 JSON 对象）：

```cpp
#include "llvm/Support/JSON.h"
#include "llvm/Support/raw_ostream.h"

void output_enum_constant(const clang::EnumConstantDecl *EC,
                          llvm::StringRef outFile,
                          std::initializer_list<std::pair<llvm::StringRef, std::string>> kvs) {
  llvm::json::Object obj;
  for (auto &kv : kvs)
    obj[kv.first] = kv.second;

  // 也可以附带 USR、位置等更多信息
  // obj["usr"] = getUSR(EC);

  std::error_code ECerr;
  llvm::raw_fd_ostream os(outFile, ECerr, llvm::sys::fs::OF_Append);
  if (ECerr) {
    // 处理打开文件失败
    llvm::errs() << "Failed to open " << outFile << ": " << ECerr.message() << "\n";
    return;
  }
  os << llvm::formatv("{0}\n", llvm::json::Value(std::move(obj)));
}
```

---

## 处理细节与边界情况

* **匿名枚举**：`enumName` 可能为空。这类枚举常见于头文件或局部作用域。你可以用 `qname`、文件位置或外层 `DeclContext` 的信息来标识它，或者在解析 `typedef` 阶段把别名与之关联。
* **有/无固定底层类型**：`enum class E : unsigned` 之类的会有非空 `getIntegerType()`；C 风格 `enum` 通常为空（实现决定底层宽度）。
* **值的有符号性**：`APSInt` 自带有符号位信息；直接 `toString(10)` 即可得到带符号的十进制文本。若你想强制以无符号打印，可用 `val.abs().toString(10)` 或 `val.zextOrTrunc(...)` 处理，但一般没必要。
* **显式初始化源码**：`getInitExpr()` 仅在写了初始化器时非空（如 `A = 1 << 3`）。用它抓取原始拼写有助于可读性，同时用 `getInitVal()` 记录规范化后的数值，二者都存，最保险。
* **模板/依赖枚举**：在模板上下文里，部分信息可能依赖实例化；但 `VisitEnumDecl` 通常在具体语义可解时被访问（取决于你的前端动作与语义分析阶段）。

---

## 最小可验证示例

```c
// test.c
enum E1 { A, B = 4, C };
enum class E2 : unsigned { X = 1u, Y = 2u, Z };

```

对上面代码，`E1` 的 `A=0`, `B=4`, `C=5`；`E2` 的 `X=1`, `Y=2`, `Z=3`。上述实现会把两组常量分别写入 `enum-constants.jsonl`，每行一条记录（含所属枚举名、是否 scoped、底层类型、常量名、值与拼写等）。

---

这样集成后，你就能在保留原有 `enum.jsonl`（记录枚举本体）的同时，新增一份 **`enum-constants.jsonl`**，专门存放每个枚举常量的详细信息，方便后续检索与分析。
