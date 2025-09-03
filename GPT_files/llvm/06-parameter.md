下面先把概念讲清，再给一段“可落地”的代码，能把**各种可能的入参类型**（struct/class/union、enum、typedef、指针/引用/数组、模板特化等）一路“去糖(desugar)”到**真正的类型声明处**，然后打印它定义所在的头文件。

# 什么是 `TagDecl`

* `TagDecl` 是 Clang AST 里**带“标记(tag)”的类型声明**的基类，覆盖四类：

  * `struct` / `class` → `CXXRecordDecl`（继承自 `RecordDecl` → `TagDecl`）
  * `union` → `RecordDecl`（→ `TagDecl`）
  * `enum` → `EnumDecl`（→ `TagDecl`）
* 你可以通过 `TagDecl::getLocation()` / `getBeginLoc()` 拿到声明位置，通过 `isCompleteDefinition()`/`getDefinition()`判断是否已有完整定义（而不仅是 `struct S;` 的前置声明）。
* 常见获取方式：

  * `qt->getAsTagDecl()`：若 `QualType` 表示 record/enum/union，会返回对应的 `TagDecl`。
  * `qt->getAsCXXRecordDecl()`：若是 C++ class/struct，直接拿到 `CXXRecordDecl`。

# 关键难点：参数类型可能是各种“包裹”

入参类型不一定直接是 `struct Foo`，它可能是：

* `typedef Foo T;` / `using T = Foo;` 再用 `T*`、`const T&`……
* `Foo*`、`const Foo&`、`Foo[3]`（指针/引用/数组）
* `std::vector<Foo>`（模板特化）
* `enum Bar`、`union Baz`
* `ElaboratedType`（如 `struct ::ns::Foo` 的语法层包装）
* `DecayedType`、`AttributedType` 等等

要稳妥拿到“**定义该类型的声明节点（Decl）**”，思路是**循环剥皮**：

1. 去掉顶层 cv 限定（`const/volatile`）；
2. 如果是 `TypedefType` / `TypeAliasType` → 取 `getDecl()->getUnderlyingType()` 继续；
3. 如果是 `ElaboratedType` / `AttributedType` / `DecayedType` → 取其 `desugar()` 或 `getNamedType()` 继续；
4. 如果是 `PointerType` / `ReferenceType` / `MemberPointerType` / `ArrayType` → 取“元素/被指向类型”继续；
5. 如果是模板类特化（`TemplateSpecializationType`）→ 如果它对应某个类模板的实例，通常能 `getAsCXXRecordDecl()`；
6. 最后若是 record/enum/union，拿 `TagDecl`；否则结束。

# 实用代码：找到声明，再打印其头文件

```cpp
#include "clang/AST/AST.h"
#include "clang/AST/Decl.h"
#include "clang/AST/Type.h"
#include "clang/AST/TypeLoc.h"
#include "clang/Basic/SourceManager.h"
#include "llvm/Support/raw_ostream.h"

using namespace clang;

static const Decl* peelToDefiningDecl(QualType T) {
  // 去掉顶层 cv
  QualType cur = T.getCanonicalType().getUnqualifiedType();

  while (true) {
    const Type *ty = cur.getTypePtrOrNull();
    if (!ty) return nullptr;

    // 1) 若已是 record/enum/union，直接返回其 TagDecl
    if (const TagDecl *TD = ty->getAsTagDecl()) {
      // 若有定义，优先返回定义；否则返回声明
      if (const TagDecl *Def = dyn_cast_or_null<TagDecl>(TD->getDefinition()))
        return Def;
      return TD;
    }

    // 2) C++ 类（模板特化等）→ 取 CXXRecordDecl
    if (const CXXRecordDecl *CRD = ty->getAsCXXRecordDecl()) {
      if (const CXXRecordDecl *Def = CRD->getDefinition())
        return Def;
      return CRD;
    }

    // 3) 如果是 typedef/using，往下剥到底层
    if (const auto *TT = dyn_cast<TypedefType>(ty)) {
      const TypedefNameDecl *TD = TT->getDecl();
      QualType Under = TD->getUnderlyingType().getUnqualifiedType();
      if (Under == cur) return TD; // 防御：避免死循环
      cur = Under;
      continue;
    }

    // 4) ElaboratedType（如 "struct ::ns::Foo"）、AttributedType、DecayedType
    if (const auto *ET = dyn_cast<ElaboratedType>(ty)) {
      cur = ET->getNamedType().getUnqualifiedType();
      continue;
    }
    if (const auto *AT = dyn_cast<AttributedType>(ty)) {
      cur = AT->getEquivalentType().getUnqualifiedType();
      continue;
    }
    if (const auto *DT = dyn_cast<DecayedType>(ty)) {
      cur = DT->getOriginalType().getUnqualifiedType();
      continue;
    }

    // 5) 指针/引用/成员指针/数组 → 取元素类型继续
    if (const auto *PT = dyn_cast<PointerType>(ty)) {
      cur = PT->getPointeeType().getUnqualifiedType();
      continue;
    }
    if (const auto *RT = dyn_cast<ReferenceType>(ty)) {
      cur = RT->getPointeeType().getUnqualifiedType();
      continue;
    }
    if (const auto *MPT = dyn_cast<MemberPointerType>(ty)) {
      cur = MPT->getPointeeType().getUnqualifiedType();
      continue;
    }
    if (const auto *ATy = dyn_cast<ArrayType>(ty)) {
      cur = ATy->getElementType().getUnqualifiedType();
      continue;
    }

    // 6) 模板特化：有时不是 CXXRecordDecl，但能转成 RecordType 再取 Decl
    if (const auto *RTy = dyn_cast<RecordType>(ty)) {
      if (const RecordDecl *RD = RTy->getDecl()) {
        if (const RecordDecl *Def = RD->getDefinition())
          return Def;
        return RD;
      }
    }

    // 7) 走到这里：要么是内建（int/float），要么无法再剥
    // 返回 nullptr 表示没有“用户自定义声明”
    return nullptr;
  }
}

static void printParamTypeDefSite(const ParmVarDecl *Param, const ASTContext &Ctx) {
  QualType T = Param->getType();
  const Decl *D = peelToDefiningDecl(T);
  const SourceManager &SM = Ctx.getSourceManager();

  if (!D) {
    // 可能是内建类型或函数指针等没独立声明的情况
    llvm::errs() << "Param `" << Param->getNameAsString()
                 << "` type: " << T.getAsString()
                 << " — no user-defined decl (likely builtin or alias chain ended).\n";
    return;
  }

  // 取声明（或定义）位置；优先完整定义位置
  SourceLocation Loc;
  if (const auto *TD = dyn_cast<TagDecl>(D)) {
    Loc = (TD->isCompleteDefinition() ? TD->getLocation() : TD->getBeginLoc());
  } else {
    Loc = D->getLocation();
  }

  // 对于宏或包含栈，最好取 spelling loc
  Loc = SM.getSpellingLoc(Loc);

  llvm::StringRef File = SM.getFilename(Loc);
  PresumedLoc PLoc = SM.getPresumedLoc(Loc);

  llvm::errs() << "Param `" << Param->getNameAsString()
               << "` type: " << T.getAsString() << "\n"
               << "  Decl kind: " << D->getDeclKindName() << "\n"
               << "  Defined in: " << (File.empty() ? "<unknown>" : File) << "\n";
  if (PLoc.isValid()) {
    llvm::errs() << "  Line: " << PLoc.getLine() << ", Col: " << PLoc.getColumn() << "\n";
  }
}

bool VisitFunctionDecl(FunctionDecl *FD) {
  if (!collect_func) return true;
  if (!FD->isThisDeclarationADefinition()) return true;

  for (auto *Param : FD->parameters()) {
    printParamTypeDefSite(Param, FD->getASTContext());
  }

  // 你已有的输出逻辑
  // output_decl(FD, "func.jsonl");
  return true;
}
```

### 说明与小贴士

* **为什么不只用 `getAsTagDecl()`？**
  它只覆盖 record/enum/union。若参数是 `typedef` 包装的、指针/引用/数组包裹的、模板特化的 class 等，就需要先“剥皮”或换其他 API（如 `getAsCXXRecordDecl()`）。
* **`TypedefType` 与 `TypeAliasType`**
  Clang 里统一成 `TypedefNameDecl`（`TypedefDecl` / `TypeAliasDecl` 均继承）。处理时拿 `getUnderlyingType()` 继续向下。
* **系统头 vs 用户头**
  可用 `SourceManager::isInSystemHeader(Loc)`、`isInSystemMacro(Loc)` 过滤，只打印用户代码：

  ```cpp
  if (SM.isInSystemHeader(Loc)) { /* 跳过或标记为系统头 */ }
  ```
* **宏展开位置信息**
  建议使用 `SM.getSpellingLoc(Loc)` 或 `SM.getFileLoc(Loc)`，并通过 `getPresumedLoc` 打印行列，更贴近用户看到的文件/行号。
* **模板特化**
  对 `std::vector<Foo>` 之类，`getAsCXXRecordDecl()` 往往能直达类模板实例的 `CXXRecordDecl`。若拿到的是 `TemplateSpecializationType` 而无 `CXXRecordDecl`，`RecordType` 路径也常可取到 `RecordDecl`。

这样改造后，你的终端输出能可靠覆盖绝大多数真实项目里的参数类型形态。如果你想，我可以再加一个“**追踪 typedef 链的每一环**”的详细打印，帮助你调试复杂别名链。
