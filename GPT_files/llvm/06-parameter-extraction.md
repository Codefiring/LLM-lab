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



可以！思路是：当参数类型最终“剥皮”到 `struct/class/union`（即 `RecordDecl` / `CXXRecordDecl`）时，找到它的**声明/定义节点**，再用 `Lexer::getSourceText` 把该节点覆盖的源代码取出来并打印。

下面给出一套可直接整合进你现有访客的代码。要点：

* 复用“剥皮”逻辑把 `typedef`、指针/引用、数组、`ElaboratedType` 等外衣都去掉，定位到 `RecordDecl`。
* 优先拿**完整定义**（`getDefinition()`），若只有前置声明就拿声明。
* 用 `getSourceRange()` + `Lexer::getSourceText(...)` 取源码；为了把**分号**也包含上，尝试在 `end` 后找一个 `;`。
* 处理宏位置（`getSpellingLoc`/`getFileLoc`），并可选过滤系统头。

---

### 代码片段

```cpp
#include "clang/AST/AST.h"
#include "clang/AST/Decl.h"
#include "clang/AST/Type.h"
#include "clang/Basic/SourceManager.h"
#include "clang/Lex/Lexer.h"
#include "llvm/Support/raw_ostream.h"

using namespace clang;

static const RecordDecl* peelToRecordDecl(QualType T) {
  QualType cur = T.getCanonicalType().getUnqualifiedType();

  while (const Type *ty = cur.getTypePtrOrNull()) {
    // 直接是 C++ 类/struct 的情况
    if (const auto *CRD = ty->getAsCXXRecordDecl()) {
      if (const auto *Def = CRD->getDefinition()) return Def;
      return CRD;
    }
    // 其他 record（含 C 风格 struct/union）
    if (const auto *RTy = dyn_cast<RecordType>(ty)) {
      const RecordDecl *RD = RTy->getDecl();
      if (const auto *Def = RD->getDefinition()) return Def;
      return RD;
    }
    // typedef/using
    if (const auto *TT = dyn_cast<TypedefType>(ty)) {
      cur = TT->getDecl()->getUnderlyingType().getUnqualifiedType();
      continue;
    }
    // elaborated（如 "struct ns::S"）
    if (const auto *ET = dyn_cast<ElaboratedType>(ty)) {
      cur = ET->getNamedType().getUnqualifiedType();
      continue;
    }
    // attributed/decayed
    if (const auto *AT = dyn_cast<AttributedType>(ty)) {
      cur = AT->getEquivalentType().getUnqualifiedType();
      continue;
    }
    if (const auto *DT = dyn_cast<DecayedType>(ty)) {
      cur = DT->getOriginalType().getUnqualifiedType();
      continue;
    }
    // 指针/引用/成员指针/数组
    if (const auto *PT = dyn_cast<PointerType>(ty)) {
      cur = PT->getPointeeType().getUnqualifiedType(); continue;
    }
    if (const auto *RT = dyn_cast<ReferenceType>(ty)) {
      cur = RT->getPointeeType().getUnqualifiedType(); continue;
    }
    if (const auto *MPT = dyn_cast<MemberPointerType>(ty)) {
      cur = MPT->getPointeeType().getUnqualifiedType(); continue;
    }
    if (const auto *ATy = dyn_cast<ArrayType>(ty)) {
      cur = ATy->getElementType().getUnqualifiedType(); continue;
    }
    // 模板类实例（有时上面已覆盖）
    if (const auto *TST = dyn_cast<TemplateSpecializationType>(ty)) {
      if (const auto *CRD = TST->getAsCXXRecordDecl()) {
        if (const auto *Def = CRD->getDefinition()) return Def;
        return CRD;
      }
    }
    break; // 非 record
  }
  return nullptr;
}

static std::string getDeclSourceCode(const Decl *D, const ASTContext &Ctx) {
  const SourceManager &SM = Ctx.getSourceManager();
  const LangOptions &LangOpts = Ctx.getLangOpts();

  SourceRange SR = D->getSourceRange();
  if (SR.isInvalid()) return {};

  // 处理宏/包含，取 spelling loc，更贴近用户看到的位置
  SourceLocation Begin = SM.getSpellingLoc(SR.getBegin());
  SourceLocation End   = SM.getSpellingLoc(SR.getEnd());

  // 尝试把末尾分号也包含上
  SourceLocation After =
      Lexer::findLocationAfterToken(End, tok::semi, SM, LangOpts,
                                    /*SkipTrailingWhitespaceAndNewLine=*/true);
  if (After.isValid()) End = After;

  CharSourceRange CharSR = CharSourceRange::getCharRange(Begin, End);
  llvm::StringRef Text = Lexer::getSourceText(CharSR, SM, LangOpts);

  return Text.str();
}

static void printStructDeclIfAny(const ParmVarDecl *Param, const ASTContext &Ctx) {
  const RecordDecl *RD = peelToRecordDecl(Param->getType());
  if (!RD) return; // 非 struct/class/union，忽略

  const SourceManager &SM = Ctx.getSourceManager();

  // 如果只想打印“struct”的声明，且存在完整定义则优先打印定义
  const RecordDecl *Target = RD->getDefinition() ? RD->getDefinition() : RD;

  // 可选过滤系统头
  SourceLocation Loc = SM.getSpellingLoc(Target->getLocation());
  if (SM.isInSystemHeader(Loc)) {
    // 如果你想跳过系统头，直接 return; 否则继续打印
    // return;
  }

  std::string code = getDeclSourceCode(Target, Ctx);

  llvm::StringRef file = SM.getFilename(Loc);
  PresumedLoc PLoc = SM.getPresumedLoc(Loc);

  llvm::errs() << "=== struct/class/union declaration for param `"
               << Param->getNameAsString() << "` (" << Param->getType().getAsString()
               << ") ===\n";
  llvm::errs() << "File: " << (file.empty() ? "<unknown>" : file) << "\n";
  if (PLoc.isValid())
    llvm::errs() << "Line: " << PLoc.getLine() << ", Col: " << PLoc.getColumn() << "\n";
  llvm::errs() << "-----\n" << code << "\n-----\n";
}

bool VisitFunctionDecl(FunctionDecl *FD) {
  if (!collect_func) return true;
  if (!FD->isThisDeclarationADefinition()) return true;

  for (auto *Param : FD->parameters()) {
    // 只有当参数类型最终是 struct/class/union 时才抓声明代码
    printStructDeclIfAny(Param, FD->getASTContext());
  }

  // 你原来的逻辑
  // output_decl(FD, "func.jsonl");
  return true;
}
```

---

### 说明与细节

* **拿“声明代码”的精度**

  * `RecordDecl::getSourceRange()` 基本覆盖从 `struct/class/union` 关键字到 `}`；不少场景下**不含分号**，上面用 `findLocationAfterToken(..., tok::semi, ...)` 试图把 `;` 包上。
  * 若声明/定义跨宏，`getSpellingLoc` 比 `getFileLoc` 更贴近用户源码；你也可以按需改成 `getFileLoc`。
* **只打印“声明”还是“定义”**
  代码里优先打印**完整定义**（可读性更强）。如果你只想看“最初的前置声明”，把 `Target` 改为 `RD`，并在没有 `getDefinition()` 时再回退到 `RD`。
* **系统头过滤**
  `SM.isInSystemHeader(Loc)` 可用于跳过标准库/系统头的 struct。
* **匿名/内联定义**
  若参数是“匿名 struct 的指针”等，`RecordDecl` 可能是匿名的（`isAnonymousStructOrUnion()`），这时也能把定义片段取出来，但没有名字。

如果你希望“同时打印 typedef 链每一步到底映射到哪个类型/文件”，我可以再加一个链路追踪的 verbose 输出，调试 typedef/using 特别好用。


下面给出一套基于 Clang LibTooling/AST 的完整实现思路与参考代码，直接把你现有的 `VisitFunctionDecl` 扩展为：

* 获取函数声明所在头文件
* 枚举每个入参，拿到：参数名、参数声明头文件、参数原始类型串、规范化类型串
* 若参数类型是“指向 struct/union/class 的指针（或本体）”，解析出记录类型（RecordDecl），定位其**定义位置**与**定义所在头文件**，并抽取**定义源码**
* 最终序列化为 JSON（可按行写入 JSONL）

> 说明：代码用到了 `llvm::json`、`SourceManager`、`Lexer::getSourceText` 等；对 `typedef/using`、`ElaboratedType`、指针/引用/数组做了去糖处理以找到底层 `RecordType`。

---

# 参考实现

```cpp
#include "clang/AST/AST.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/AST/Type.h"
#include "clang/AST/TypeLoc.h"
#include "clang/AST/Decl.h"
#include "clang/Basic/SourceManager.h"
#include "clang/Basic/SourceLocation.h"
#include "clang/Basic/LangOptions.h"
#include "clang/Lex/Lexer.h"
#include "llvm/ADT/StringRef.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/raw_ostream.h"

using namespace clang;

static std::string getHeaderFileName(const Decl *D, const SourceManager &SM) {
  if (!D) return "";
  SourceLocation Loc = D->getLocation();
  if (Loc.isInvalid()) return "";
  // 使用扩展后位置（展开宏后）
  PresumedLoc PLoc = SM.getPresumedLoc(SM.getExpansionLoc(Loc));
  if (!PLoc.isValid()) return "";
  return std::string(PLoc.getFilename());
}

static std::string getHeaderFileName(SourceLocation Loc, const SourceManager &SM) {
  if (Loc.isInvalid()) return "";
  PresumedLoc PLoc = SM.getPresumedLoc(SM.getExpansionLoc(Loc));
  if (!PLoc.isValid()) return "";
  return std::string(PLoc.getFilename());
}

// 抽取某个 Decl 对应的源码（尽量用声明/定义的完整范围）
static std::string getSourceForDecl(const Decl *D, const SourceManager &SM, const LangOptions &LangOpts) {
  if (!D) return "";
  SourceRange SR = D->getSourceRange();
  if (SR.isInvalid()) return "";

  SourceLocation Begin = SM.getExpansionLoc(SR.getBegin());
  SourceLocation End   = SM.getExpansionLoc(SR.getEnd());

  if (Begin.isInvalid() || End.isInvalid()) return "";

  // 把 End 扩到 token 末尾
  End = Lexer::getLocForEndOfToken(End, 0, SM, LangOpts);
  if (End.isInvalid()) return "";

  CharSourceRange CharRange = CharSourceRange::getCharRange(Begin, End);
  llvm::StringRef Text = Lexer::getSourceText(CharRange, SM, LangOpts);
  return Text.str();
}

// 递归去糖，拿到底层记录类型（struct/union/class）
static const RecordDecl* getUnderlyingRecordDecl(QualType QT) {
  if (QT.isNull()) return nullptr;

  // 去除 cv、指针、引用、数组等修饰
  QualType CT = QT.getCanonicalType().getUnqualifiedType();

  while (true) {
    if (const auto *PT = CT->getAs<PointerType>()) {
      CT = PT->getPointeeType().getUnqualifiedType();
      continue;
    }
    if (const auto *RT = CT->getAs<ReferenceType>()) {
      CT = RT->getPointeeType().getUnqualifiedType();
      continue;
    }
    if (const auto *AT = dyn_cast<ArrayType>(CT.getTypePtr())) {
      CT = AT->getElementType().getUnqualifiedType();
      continue;
    }
    break;
  }

  // 去 elaborated（如 "struct foo"）
  if (auto ET = dyn_cast<ElaboratedType>(CT.getTypePtr())) {
    CT = ET->getNamedType().getUnqualifiedType();
  }

  // 若是 Typedef/Using 再次取 canonical
  CT = CT.getCanonicalType().getUnqualifiedType();

  if (const auto *RTy = CT->getAs<RecordType>()) {
    return RTy->getDecl();
  }
  return nullptr;
}

// 尝试找到记录类型的“定义”（而非仅前置声明）
static const RecordDecl* getRecordDefinition(const RecordDecl *RD) {
  if (!RD) return nullptr;
  if (const auto *Def = RD->getDefinition()) return Def;
  // 有的场景是 CXXRecordDecl
  if (const auto *CRD = dyn_cast<CXXRecordDecl>(RD)) {
    if (const auto *Def = CRD->getDefinition()) return Def;
  }
  return nullptr;
}

// 将函数信息写入 JSON（单条/JSONL）
static void writeJSONLine(const llvm::json::Object &Obj, llvm::raw_ostream &OS) {
  std::string S;
  llvm::raw_string_ostream RS(S);
  RS << llvm::formatv("{0:2}\n", llvm::json::Value(Obj)); // 紧凑/可读
  RS.flush();
  OS << S;
}

// 你已有的：从 Decl 拿到原始代码
extern std::string get_decl_code(const Decl *D);
// 你已有的：是否启用采集
extern bool collect_func;

// 这里把 VisitFunctionDecl 完整实现起来
bool VisitFunctionDecl(FunctionDecl *FD) {
  if (!collect_func) return true;
  if (!FD || !FD->isThisDeclarationADefinition()) return true;

  ASTContext &Ctx = FD->getASTContext();
  const SourceManager &SM = Ctx.getSourceManager();
  const LangOptions &LangOpts = Ctx.getLangOpts();

  std::string FuncName = FD->getNameAsString();
  if (FuncName.empty()) return true;

  // 1) 函数声明（定义）所在头文件
  std::string funcHeader = getHeaderFileName(FD, SM);

  // 2) 函数源码（可选）
  std::string funcSource = get_decl_code(FD);

  // 3) 组装参数信息
  llvm::json::Array paramsArr;

  for (const ParmVarDecl *P : FD->parameters()) {
    if (!P) continue;

    llvm::json::Object PObj;
    PObj["name"] = P->getNameAsString();

    QualType T = P->getType();
    // 参数声明位置所在头文件
    std::string paramHeader = getHeaderFileName(P, SM);

    // 类型原文与规范化串
    std::string spelledType, canonicalType;
    {
      llvm::raw_string_ostream RS(spelledType);
      T.print(RS, PrintingPolicy(LangOpts));
      RS.flush();
    }
    {
      llvm::raw_string_ostream RS(canonicalType);
      T.getCanonicalType().print(RS, PrintingPolicy(LangOpts));
      RS.flush();
    }

    PObj["decl_header"] = paramHeader;
    PObj["type_spelled"] = spelledType;
    PObj["type_canonical"] = canonicalType;

    // 4) 若类型对应到 record（或指针/引用/数组包裹 record），找定义
    const RecordDecl *MaybeRD = getUnderlyingRecordDecl(T);
    if (MaybeRD) {
      const RecordDecl *Def = getRecordDefinition(MaybeRD);
      llvm::json::Object TypeInfo;

      // 记录名
      std::string recName = MaybeRD->getNameAsString();
      if (recName.empty()) {
        if (const auto *Tag = dyn_cast<TagDecl>(MaybeRD)) {
          recName = Tag->getNameAsString();
        }
      }
      TypeInfo["record_name"] = recName;

      // 定义位置
      if (Def) {
        SourceLocation defLoc = Def->getLocation();
        std::string defHeader = getHeaderFileName(defLoc, SM);
        TypeInfo["def_header"] = defHeader;

        // 5) 类型定义源码
        std::string defCode = getSourceForDecl(Def, SM, LangOpts);
        TypeInfo["def_code"] = defCode;
      } else {
        // 只有前置声明情况
        std::string declHeader = getHeaderFileName(MaybeRD, SM);
        TypeInfo["decl_header"] = declHeader;
        TypeInfo["def_header"] = llvm::json::Value(nullptr);
        TypeInfo["def_code"] = llvm::json::Value(nullptr);
      }

      PObj["record_type_info"] = std::move(TypeInfo);
    } else {
      // 非 record 类型（如内建、枚举、函数指针等）
      PObj["record_type_info"] = llvm::json::Value(nullptr);
    }

    paramsArr.push_back(std::move(PObj));
  }

  // 最终 JSON 对象
  llvm::json::Object FuncObj;
  FuncObj["function_name"] = FuncName;
  FuncObj["decl_header"]   = funcHeader;
  FuncObj["source"]        = funcSource;
  FuncObj["params"]        = std::move(paramsArr);

  // 写文件（JSONL）
  // 你原先写 "func.jsonl"，这里改为 jsonl 形式，每个函数一行
  std::error_code EC;
  static std::unique_ptr<llvm::raw_fd_ostream> Out;
  static bool opened = false;
  if (!opened) {
    Out = std::make_unique<llvm::raw_fd_ostream>("func.jsonl", EC, llvm::sys::fs::OF_Append);
    if (EC) {
      llvm::errs() << "open func.jsonl failed: " << EC.message() << "\n";
      return true;
    }
    opened = true;
  }
  writeJSONLine(FuncObj, *Out);

  return true;
}
```

---

# 关键点说明与边界处理

1. **函数声明所在头文件**

* `getHeaderFileName(Decl*, SM)` 使用 `getPresumedLoc(getExpansionLoc(loc))`，可得到宏展开后的真实文件路径；对头文件/源文件都适用。

2. **每个入参**

* 遍历 `FD->parameters()`，对每个 `ParmVarDecl` 取 `name`、`getType()`、`getLocation()`。

3. **每个入参的类型 + 若为 `struct num *` 找到定义位置**

* 用 `getUnderlyingRecordDecl(QualType)`：通过 `getCanonicalType()` + 剥离指针/引用/数组/ElaboratedType/typedef，拿到底层 `RecordType`；
* 再用 `getRecordDefinition(RD)` 拿“定义”（可能在别处），否则只有前置声明。
* 定义位置用 `getHeaderFileName(Def, SM)`；源码用 `getSourceForDecl(Def, SM, LangOpts)`。

4. **每个入参定义所在头文件**

* 即 `ParmVarDecl` 的 `getLocation()` 映射的文件名。

5. **每个入参类型定义的具体代码**

* 用 Lexer 抽取 `RecordDecl` 的 `SourceRange` 文本。
* 如果是 `typedef struct num {...} num_t;` 这类**别名名不等于记录名**，我们依然以 `RecordDecl` 的定义体为准；若你还想把 `typedef/using` 的别名声明源码也存起来，可再沿 `TypedefType`/`TypeAliasDecl` 解析并追加。

---

# 输出 JSON 结构（示例）

写入 `func.jsonl` 的每行形如：

```json
{
  "function_name": "foo",
  "decl_header": "/path/include/a.h",
  "source": "int foo(struct num *n, int x) { ... }",
  "params": [
    {
      "name": "n",
      "decl_header": "/path/include/a.h",
      "type_spelled": "struct num *",
      "type_canonical": "struct num *",
      "record_type_info": {
        "record_name": "num",
        "def_header": "/path/include/num.h",
        "def_code": "struct num { int v; };"
      }
    },
    {
      "name": "x",
      "decl_header": "/path/include/a.h",
      "type_spelled": "int",
      "type_canonical": "int",
      "record_type_info": null
    }
  ]
}
```

---

# 可选增强

* **处理 `typedef/using` 的别名源码**：沿 `TypedefType` 找到 `TypedefNameDecl` 或 `TypeAliasDecl`，记录其 `getLocation()` 和定义文本。
* **模板与特化**：若参数为 `T*` 或 `std::vector<Foo>`，可对 `TemplateSpecializationType` 做展开，追加一个 `template_args` 字段。
* **只输出头文件基名**：可用 `llvm::sys::path::filename()` 提取。
* **跨 TU**：若类型定义在别的 TU 未参与编译，`getDefinition()` 可能拿不到，这种情况下保持 `def_header: null, def_code: null`。

把以上代码嵌到你现有的工具里即可直接产出目标 JSONL。如需我再加上 `Typedef/using` 的跟踪或把输出结构换成单一 JSON 文件（数组形式），我可以直接给出替换版。

