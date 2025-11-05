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



好的！下面给你一份基于 Clang LibTooling（Clang 14）可直接嵌入到你现有 Visitor 的实现示例。它在遍历到**函数定义**时，反查其**声明（优先头文件中的声明）**，并为每个入参提取：

* 函数“声明”所在头文件名
* 入参名
* 入参的完整类型串（带指针/引用/限定符）
* 若入参底层为 `struct/union/class/enum` 或 `typedef`，解析出其**被定义/声明**的 `NamedDecl`、该声明所在头文件名、以及**类型定义/声明的源码**（尽量取完整定义，若仅有声明则取声明）
* 入参自身（形参标识符）声明所在头文件名（一般与函数声明同文件，但这里单独按形参位置取）

最终以 **JSON Lines（.jsonl）** 形式追加写入新文件（例如 `func_with_params.jsonl`）。示例不依赖第三方 JSON 库，使用 LLVM 自带 `llvm::json`。

> 你原来有 `get_decl_code` / `output_decl` 等工具函数；下方我提供了独立可用的 `getSourceTextForDecl` 与 `append_jsonl`，可以直接替换或并存。

---

### 关键点实现思路

1. **函数“声明”头文件**

   * 访问到定义 `FunctionDecl` 时，遍历 `redecls()` 选出更“像声明”的版本：

     * 优先选择位于头文件扩展名（`.h/.hh/.hpp/.hxx`）的那个；
     * 若都在源文件，则取**最早出现**的那个；
   * 这样能满足“函数声明所在头文件名称”的要求（若确实没在头文件声明，就会是源文件名）。

2. **参数与类型剥离**

   * 对 `ParmVarDecl` 取 `QualType`，逐层剥离 `ElaboratedType / PointerType / ReferenceType / TypedefType / AttributedType / ParenType / DecayedType`，直到拿到底层 `RecordType/EnumType` 或保留最近的 `TypedefDecl`。
   * 若是 `struct num *`，会剥到 `RecordType(num)`，返回其 `TagDecl` 的位置；同时如果中途有 `typedef`，也会记录 typedef 的声明与底层真正定义（尽量给“定义”的源码）。

3. **类型定义位置与源码**

   * 若为 `RecordDecl/EnumDecl` 且有 `isCompleteDefinition()`，取其定义 `SourceRange`；否则退化为声明 `SourceRange`。
   * `typedef` 则取 `TypedefDecl` 自己的 `SourceRange`，同时也会尝试解开到真正底层并给出底层的定义源码（若需要可保留/合并，下面示例只输出一个“最终确定的定义/声明”块以保持结构简单）。

4. **定位与源码提取**

   * 所有 `SourceLocation` 均先做 `getExpansionLoc`；
   * 头文件名用 `SourceManager::getFilename()` 并用 `llvm::sys::path::filename()` 提取**文件名（不含路径）**；
   * 源码用 `Lexer::getSourceText(CharSourceRange::getTokenRange(...))` 取文本。

---

### 代码示例（可直接拷贝集成）

```cpp
#include "clang/AST/AST.h"
#include "clang/AST/Decl.h"
#include "clang/AST/Type.h"
#include "clang/Basic/SourceManager.h"
#include "clang/Basic/LangOptions.h"
#include "clang/Lex/Lexer.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Support/Path.h"

using namespace clang;

static inline std::string justFileName(const SourceManager &SM, SourceLocation Loc) {
  if (!Loc.isValid()) return "";
  auto Exp = SM.getExpansionLoc(Loc);
  llvm::StringRef Path = SM.getFilename(Exp);
  if (Path.empty()) return "";
  return llvm::sys::path::filename(Path).str();
}

static inline std::string fullPath(const SourceManager &SM, SourceLocation Loc) {
  if (!Loc.isValid()) return "";
  auto Exp = SM.getExpansionLoc(Loc);
  llvm::StringRef Path = SM.getFilename(Exp);
  return Path.str();
}

static inline bool isHeaderPath(llvm::StringRef P) {
  llvm::StringRef Ext = llvm::sys::path::extension(P);
  return Ext.equals_lower(".h") || Ext.equals_lower(".hh") ||
         Ext.equals_lower(".hpp") || Ext.equals_lower(".hxx");
}

static inline std::string getSourceTextForRange(const SourceManager &SM,
                                                SourceRange SR,
                                                const LangOptions &LO) {
  if (!SR.isValid()) return "";
  CharSourceRange CR = CharSourceRange::getTokenRange(
      SourceRange(SM.getExpansionLoc(SR.getBegin()),
                  SM.getExpansionLoc(SR.getEnd())));
  llvm::StringRef Text = Lexer::getSourceText(CR, SM, LO);
  return Text.str();
}

static inline std::string getSourceTextForDecl(const Decl *D,
                                               const SourceManager &SM,
                                               const LangOptions &LO) {
  if (!D) return "";
  // 对于定义优先整个定义范围；否则声明范围
  SourceRange SR = D->getSourceRange();
  return getSourceTextForRange(SM, SR, LO);
}

// 解析类型：不断剥离直到获得 Record/Enum 的 Decl；如果遇到 Typedef，则优先返回底层的目标 Decl，若没有则返回 TypedefDecl
struct ResolvedTypeDecl {
  const NamedDecl *Decl = nullptr;      // 解析到的命名声明（RecordDecl/EnumDecl/TypedefDecl等）
  QualType        StrippedQT;           // 剥离指针/引用/typedef/elaborated 后的最终 QT
  const TypedefNameDecl *Typedef = nullptr; // 若途中遇到 typedef，记录一下（可选）
};

static ResolvedTypeDecl resolveTypeDecl(QualType QT) {
  ResolvedTypeDecl R;
  R.StrippedQT = QT;

  while (true) {
    if (auto AT = dyn_cast<AttributedType>(R.StrippedQT)) {
      R.StrippedQT = AT->getEquivalentType();
    } else if (auto ET = dyn_cast<ElaboratedType>(R.StrippedQT)) {
      R.StrippedQT = ET->getNamedType();
    } else if (R.StrippedQT->isPointerType()) {
      R.StrippedQT = R.StrippedQT->getPointeeType();
    } else if (R.StrippedQT->isReferenceType()) {
      R.StrippedQT = R.StrippedQT->getPointeeType();
    } else if (auto PT = dyn_cast<ParenType>(R.StrippedQT)) {
      R.StrippedQT = PT->getInnerType();
    } else if (auto DT = dyn_cast<DecayedType>(R.StrippedQT)) {
      R.StrippedQT = DT->getDecayedType();
    } else if (auto TT = dyn_cast<TypedefType>(R.StrippedQT)) {
      R.Typedef = TT->getDecl();
      R.StrippedQT = R.Typedef->getUnderlyingType();
    } else {
      break;
    }
  }

  if (auto RT = R.StrippedQT->getAs<RecordType>()) {
    R.Decl = RT->getDecl();
  } else if (auto ET = R.StrippedQT->getAs<EnumType>()) {
    R.Decl = ET->getDecl();
  } else if (!R.Decl && R.Typedef) {
    // 没有进一步解析到 Record/Enum，则以 typedef 本身作为“类型定义点”
    R.Decl = R.Typedef;
  }

  return R;
}

// 将一条 JSON 记录追加到 .jsonl 文件
static void append_jsonl(llvm::StringRef Path, const llvm::json::Object &Obj) {
  std::error_code EC;
  llvm::raw_fd_ostream OS(Path, EC, llvm::sys::fs::OF_Append | llvm::sys::fs::OF_Text);
  if (EC) {
    llvm::errs() << "Failed to open " << Path << " for append: " << EC.message() << "\n";
    return;
  }
  llvm::json::Value V(Obj);
  std::string Line;
  llvm::raw_string_ostream RS(Line);
  RS << V;
  RS.flush();
  OS << Line << "\n";
}

// 选择“更像声明”的重声明（优先头文件；否则最早的）
static const FunctionDecl* pickBestDeclForHeader(const FunctionDecl *FD,
                                                 const SourceManager &SM) {
  const FunctionDecl *Best = FD->getCanonicalDecl();
  auto BestPath = fullPath(SM, Best->getLocation());
  bool BestIsHeader = isHeaderPath(BestPath);

  for (const FunctionDecl *R : FD->redecls()) {
    auto P = fullPath(SM, R->getLocation());
    bool H = isHeaderPath(P);
    if (H && !BestIsHeader) {
      Best = R; BestPath = P; BestIsHeader = true;
      continue;
    }
    if (H == BestIsHeader) {
      // 同类型（都头文件或都非头文件）则取“更早”的（偏向位置小的）
      auto BL = SM.getFileOffset(SM.getExpansionLoc(Best->getLocation()));
      auto RL = SM.getFileOffset(SM.getExpansionLoc(R->getLocation()));
      if (RL < BL) {
        Best = R; BestPath = P; BestIsHeader = H;
      }
    }
  }
  return Best;
}

// ===== 你原来的 Visitor：改造 VisitFunctionDecl =====

bool VisitFunctionDecl(FunctionDecl *FuncDecl) {
  if (!collect_func) return true;
  if (!FuncDecl->isThisDeclarationADefinition())
    return true; // 只在看到定义时输出一次

  ASTContext &Ctx = FuncDecl->getASTContext();
  const SourceManager &SM = Ctx.getSourceManager();
  const LangOptions &LO = Ctx.getLangOpts();

  // 选出“函数声明”（尽量是头文件中的那一个）
  const FunctionDecl *DeclForHeader = pickBestDeclForHeader(FuncDecl, SM);

  // 函数名与声明头文件
  std::string FuncName = FuncDecl->getNameAsString();
  std::string FuncDeclHeader = justFileName(SM, DeclForHeader->getLocation());

  llvm::json::Array Params;

  for (const ParmVarDecl *P : DeclForHeader->parameters()) {
    llvm::json::Object PObj;

    // 1) 形参名
    std::string PName = P->getNameAsString();
    PObj["name"] = PName;

    // 2) 形参本身声明所在头文件（严格按形参 token 的位置取）
    std::string ParamDeclHeader = justFileName(SM, P->getLocation());
    PObj["param_decl_header"] = ParamDeclHeader;

    // 3) 形参类型串（保留原样，可读性强）
    QualType QT = P->getType();
    PObj["type_spelling"] = QT.getAsString();

    // 4) 解析底层类型定义点
    ResolvedTypeDecl RTD = resolveTypeDecl(QT);
    if (const NamedDecl *TD = RTD.Decl) {
      // 类型名（限定名）
      std::string TQName = TD->getQualifiedNameAsString();
      PObj["type_decl_qualified_name"] = TQName;

      // 类型声明/定义所在头文件名
      std::string TypeHeader = justFileName(SM, TD->getLocation());
      PObj["type_decl_header"] = TypeHeader;

      // 类型定义的源码（若有完整定义就取定义范围；否则声明范围）
      const Decl *ForText = TD;

      // 若是 Record/Enum 并且有定义，尽量用定义节点（某些场景 Location 指向前置声明）
      if (const auto *RD = dyn_cast<RecordDecl>(TD)) {
        if (const RecordDecl *Def = RD->getDefinition())
          ForText = Def;
      } else if (const auto *ED = dyn_cast<EnumDecl>(TD)) {
        if (const EnumDecl *Def = ED->getDefinition())
          ForText = Def;
      }
      std::string TypeCode = getSourceTextForDecl(ForText, SM, LO);
      PObj["type_decl_code"] = TypeCode;
    } else {
      // 没有解析到具体的命名 Decl（如内建类型、函数指针且底层不是 record/enum 等）
      PObj["type_decl_qualified_name"] = llvm::json::Value(nullptr);
      PObj["type_decl_header"] = llvm::json::Value(nullptr);
      PObj["type_decl_code"] = llvm::json::Value(nullptr);
    }

    Params.push_back(std::move(PObj));
  }

  // 组装函数级 JSON
  llvm::json::Object J;
  J["function_name"] = FuncName;
  J["function_decl_header"] = FuncDeclHeader;

  // 也可根据需要保留“定义文件名”与“定义源码”
  J["function_def_file"] = justFileName(SM, FuncDecl->getLocation());
  J["function_def_code"] = getSourceTextForDecl(FuncDecl, SM, LO);

  J["params"] = std::move(Params);

  // 追加写入新的 jsonl
  append_jsonl("func_with_params.jsonl", J);

  return true;
}
```

---

### 输出 JSON（示例）

每个函数一行 JSON（便于后处理）：

```json
{
  "function_name": "foo",
  "function_decl_header": "api.h",
  "function_def_file": "api.cc",
  "function_def_code": "int foo(struct num *n, double x) { ... }",
  "params": [
    {
      "name": "n",
      "param_decl_header": "api.h",
      "type_spelling": "struct num *",
      "type_decl_qualified_name": "num",
      "type_decl_header": "num.h",
      "type_decl_code": "struct num { int v; };"
    },
    {
      "name": "x",
      "param_decl_header": "api.h",
      "type_spelling": "double",
      "type_decl_qualified_name": null,
      "type_decl_header": null,
      "type_decl_code": null
    }
  ]
}
```

---

### 兼容性与注意事项（Clang 14）

* 头文件选择策略并非绝对（复杂项目里也可能只在 `.cc` 有唯一声明），我用“优先头文件扩展名、否则最早位置”的启发式来满足“尽量取声明处”的需求。若你有更强约定（例如“必须取 `#include` 头里的那份”），可以在 `pickBestDeclForHeader` 中加入路径前缀白名单或更复杂规则。
* `Lexer::getSourceText` 在 Clang 14 可用；若遇到宏产生的声明，`getExpansionLoc` 已做了基本展开位置归一化；极端情况下可考虑 `getFileLoc` 或 `getSpellingLoc` 做差异比较。
* `resolveTypeDecl` 已覆盖常见壳层（指针/引用/typedef/elaborated/paren/attributed/decayed）；若你项目里有 `AutoType`、模板形参等，可按同样思路扩展（例如 `DeducedType`、`TemplateSpecializationType` -> 通过 `getAsCXXRecordDecl()` 取特化的 `CXXRecordDecl`）。

---

如果你愿意，我也可以把这段封装成一个最小可运行的 `FrontendAction` 小工具模板，或把输出从 `.jsonl` 改为单个 `.json`（数组）并在 `EndSourceFileAction` 统一写出。


# fix json write

出现“有些行不是完整 JSON”的常见原因主要有三类。结合你当前的实现（每次在 `VisitFunctionDecl` 里打开文件并 `append`），最容易踩的坑是**并发写同一个 .jsonl 文件**导致的行间“交错”。下面按概率从高到低列问题与可落地的修复办法（附可直接替换的代码片段）。

---

## 可能原因

1. **并发/多进程同时写同一文件（最常见）**

* 如果你的工具以 `-j N` 并行跑多个 TU，或者你在多个进程里同时写 `func_with_params.jsonl`，每个进程/线程都在“追加”，但**一次 JSON 行可能被拆成多次系统调用**，从而被别的进程的输出“插队”截断，形成半行或两行粘在一起。
* `llvm::raw_fd_ostream` 带缓冲，也可能把一行分成多次 `write()`。

2. **写入内容不是有效 UTF-8 或含有奇怪的控制字符**

* `llvm::json` 期望字符串是 UTF-8。若源码文件非 UTF-8（例如 GBK）、或包含非法字节/内嵌 NUL，序列化后可能让下游解析器失败（虽然 llvm 会转义大多数控制字符，但**非法 UTF-8** 本身会是问题）。

3. **异常中止导致行没写完**

* 进程崩溃/被信号中断，缓冲区尚未 flush；或你在 Windows 用文本模式（`OF_Text`）遇到换行转换与编码混用造成意外。

---

## 推荐修复策略（从根本到权衡）

### A. 最稳：**每个 TU 写各自的临时文件，结束后再合并**

* 方案：把输出改成 `func_with_params.<pid>.<tu>.jsonl`（或放到一个临时目录），跑完再顺序 `cat` 合并到最终 `func_with_params.jsonl`。
* 优点：无锁、跨平台、完全避免竞争；行完整且追加顺序可控。
* 缺点：需要一个合并步骤（脚本或 `EndSourceFileAction` / 稍后工具做 merge）。

### B. 若必须直写同一个文件：**确保“单次写入原子化” + 进程间加锁**

* 关键点：把**整行 JSON（含结尾 `\n`）一次系统调用**写入，避免流式多次 write；并使用**文件锁**保证不同进程不会交错写。
* 在 POSIX 上，单次 `write(fd, buf, len)` 到 `O_APPEND` 打开的文件是原子的（整段会插入为一个连续块），但**两次 write 就不原子**。
* 加锁可用 `llvm::LockFileManager`（基于 lock 文件）或平台原生 `flock` / `CreateFile` 共享模式。

### C. **规范与清洗字符串**，避免坏编码破坏 JSON

* 用 `llvm::json::fixUTF8()` 清洗所有要进 JSON 的字符串（函数源码、类型源码、文件名等）。
* 去掉内嵌 NUL 或将其替换为 `\u0000`。
* 编译/运行时确保源码转为 UTF-8（`-finput-charset=utf-8`，或在读取文本时做转换）。

---

## 代码改造示例

### 1) 替换 `append_jsonl` 为“单次写入 + 可选文件锁 + UTF-8 清洗”

```cpp
#include "llvm/Support/JSON.h"
#include "llvm/Support/Path.h"
#include "llvm/Support/Errc.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/LockFileManager.h"
#include <system_error>

static inline std::string fix_utf8(llvm::StringRef S) {
  return llvm::json::fixUTF8(S);
}

// 递归清洗 JSON 对象内所有字符串（避免非法 UTF-8 / 内嵌 NUL）
static void sanitize_json(llvm::json::Value &V) {
  if (auto *S = V.getAsString()) {
    std::string T = fix_utf8(*S);
    // 可选：过滤 NUL
    T.erase(std::remove(T.begin(), T.end(), '\0'), T.end());
    V = llvm::json::Value(T);
    return;
  }
  if (auto *O = V.getAsObject()) {
    for (auto &KV : *O) sanitize_json(KV.second);
    return;
  }
  if (auto *A = V.getAsArray()) {
    for (auto &E : *A) sanitize_json(E);
    return;
  }
}

// 原子地把一整行 JSON 写到文件；支持跨进程锁（可按需启用）
static void append_jsonl_atomic(llvm::StringRef Path, llvm::json::Object Obj,
                                bool UseFileLock = false) {
  // 1) 清洗 UTF-8
  llvm::json::Value V(Obj);
  sanitize_json(V);

  // 2) 序列化到内存缓冲（含结尾换行）
  std::string Line;
  {
    llvm::raw_string_ostream RS(Line);
    RS << V;          // 紧凑单行 JSON
    RS << '\n';       // 行分隔
  }

  // 3) 可选：文件级锁，避免多进程交错（基于 .lock file）
  std::unique_ptr<llvm::LockFileManager> LFM;
  if (UseFileLock) {
    std::string LockPath = (Path.str() + ".lock");
    LFM = std::make_unique<llvm::LockFileManager>(LockPath);
    auto State = LFM->getState();
    if (State == llvm::LockFileManager::LFS_Error) {
      llvm::errs() << "Lock error for " << LockPath << "\n";
      // 不中断；继续尝试写
    } else if (State == llvm::LockFileManager::LFS_Shared) {
      // 等待独占锁
      if (auto EC = LFM->waitForUnlock()) {
        llvm::errs() << "Wait for unlock failed: " << EC.message() << "\n";
      }
      // 重新获取
      LFM = std::make_unique<llvm::LockFileManager>(LockPath);
    }
    // 现在我们持有独占锁（LFS_Owned）
  }

  // 4) 以 O_APPEND 打开并**一次 write**写入整行
#if !defined(_WIN32)
  int FD;
  if (auto EC = llvm::sys::fs::openFileForWrite(Path, FD,
        llvm::sys::fs::CD_CreateAlways,   // 若不存在创建；若存在仅打开（见 Flag）
        llvm::sys::fs::OF_Append)) {
    // 注意：CD_* 语义在不同 LLVM 版本有差异，如有编译问题可改用 ::open
    // 退化到 raw_fd_ostream 也行，但原子性会差些
    std::error_code EC2;
    llvm::raw_fd_ostream OS(Path, EC2, llvm::sys::fs::OF_Append);
    if (EC2) { llvm::errs() << "open failed: " << EC2.message() << "\n"; return; }
    OS << Line; // 可能多次 write（不完全原子）
    return;
  }
  // 使用 ::write 保证一次系统调用写入
  ssize_t N = ::write(FD, Line.data(), Line.size());
  (void)N;
  ::close(FD);
#else
  // Windows：使用 raw_fd_ostream 退化（建议采用方案A分文件合并，或用 Win32 原生 API）
  std::error_code EC;
  llvm::raw_fd_ostream OS(Path, EC, llvm::sys::fs::OF_Append | llvm::sys::fs::OF_None);
  if (EC) { llvm::errs() << "open failed: " << EC.message() << "\n"; return; }
  OS << Line; // 可能多次 write；可换成 CreateFile/WriteFile 做一次性写入
#endif
}
```

> 简化版：如果不方便引入锁，至少保证“**一次系统调用写一整行**”。在 POSIX 上这就能显著减少（几乎消除）行被切开的概率。

然后把你原来的

```cpp
append_jsonl("func_with_params.jsonl", J);
```

改为

```cpp
append_jsonl_atomic("func_with_params.jsonl", J, /*UseFileLock=*/true);
```

---

### 2) 若选择“每 TU 单独输出再合并”（推荐）

* 生成文件名：`func_with_params.<pid>.<basename_of_main_file>.jsonl`

  ```cpp
  auto MainFile = SM.getFileEntryForID(SM.getMainFileID());
  std::string TUBase = MainFile ? llvm::sys::path::stem(MainFile->getName()).str()
                                : "unknown_tu";
  std::string Out = ("out_dir/func_with_params." + std::to_string(::getpid())
                    + "." + TUBase + ".jsonl");
  append_jsonl_atomic(Out, J, /*UseFileLock=*/false); // 每TU独占，不需要锁
  ```
* 结束后用简单脚本顺序 `cat out_dir/*.jsonl > func_with_params.jsonl`。
  也可在 `EndSourceFileAction` / `EndInvocation` 里做一次合并（单线程执行）。

---

### 3) 对**编码/非法字符**的加固（如果你的源码不是 UTF-8）

* 对所有要进 JSON 的字符串（函数源码、类型源码、文件名、类型名等）调用上面的 `fix_utf8`；
* 若你观察到 NUL 或其它奇异控制符，保守做法是**删除**或**转义成可打印形式**（上面的 `sanitize_json` 已演示 NUL 过滤）。
* 构建时显式使用 UTF-8：`-finput-charset=utf-8 -fexec-charset=utf-8`（视编译器支持而定）。

---

## 额外排查清单

* 运行参数里是否用到了并发：`-j` 或你自己的并行框架；若有，先降成串行做对照测试。
* 把 `append_jsonl_atomic` 临时改成写到 `stderr` 看是否还能复现（若不复现，多半就是文件并发/原子性问题）。
* 检查“坏行”是否正好是两条 JSON 粘在一起/中间断开——粘连/截断 = 并发交错；解析报“非法字节” = 编码问题。
* Windows 上避免 `OF_Text`，统一用二进制方式并自己控制换行。

---

### TL;DR

* **最简单稳定**：每个 TU 写各自的 `.jsonl`，最后**合并**。
* 若必须同写一个文件：**一次系统调用写一整行** + （尽量）**文件锁**。
* 统一把所有字符串过一遍 `fixUTF8` 清洗，避免非 UTF-8 把 JSON “写坏”。

出现“有些行不是完整 JSON”的常见原因（Linux）主要有这几类：

1. 并发追加写入发生了**写入交错**

* 你可能在同一进程的多线程里（`ClangTool -j`）或多个进程同时往同一个 `.jsonl` 里写。
* `llvm::raw_fd_ostream` 在 `OF_Append` 模式下**不保证一次 `<<` 就只对应一次底层 `write()`**；一次逻辑行可能被拆成多次系统调用，被其他线程/进程插入。

2. 写入不是**单次原子 write()**

* 即使使用 `O_APPEND`，如果一次逻辑行被拆成多次 `write()`，在多并发下仍会交叉。
* `raw_fd_ostream` 可能缓冲/分多次写。

3. 生成的字符串很长（包含源码），在换行前程序异常退出或缓冲未及时 flush，也会出现**半行**。

> JSON 里换行符本身没问题，`llvm::json` 会自动做转义（`\n`），不是它导致的“半行”。

---

## 改造思路

* 不再用 `raw_fd_ostream` 直接写；改为：

  * 先把一整行 JSON 字符串（末尾带 `\n`）**拼好**；
  * **加文件锁**（`flock()` 或 `fcntl()`），保证跨线程/跨进程互斥；
  * 使用**单次或尽量少次的 `write()`** 写入整行（带重试处理 `EINTR`）；
  * `fsync()`（可选，根据性能权衡）；
  * 释放锁、关闭文件。
* 如果你只在**单进程单线程**里运行，也至少保证“单次 write 完整行”，避免 `raw_fd_ostream` 的分片。

下面给出一个 Linux 版更稳妥的 `append_jsonl`（使用 `flock`，依赖 `<sys/file.h>`）。你可以直接替换原函数：

```cpp
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>

static bool write_all(int fd, const char* buf, size_t len) {
  size_t off = 0;
  while (off < len) {
    ssize_t n = ::write(fd, buf + off, len - off);
    if (n < 0) {
      if (errno == EINTR) continue;     // 被信号打断，重试
      return false;                     // 其他错误
    }
    off += static_cast<size_t>(n);
  }
  return true;
}

// 将一条 JSON 记录追加到 .jsonl 文件（Linux，原子化 & 并发安全）
static void append_jsonl(llvm::StringRef Path, const llvm::json::Object &Obj) {
  // 1) 先在内存里把整行 JSON 组好
  llvm::json::Value V(Obj);
  std::string line;
  {
    llvm::raw_string_ostream rs(line);
    rs << V;
    rs.flush();
  }
  line.push_back('\n'); // JSON Lines 以换行分隔

  // 2) 以 O_APPEND 打开（必要时创建），权限 0644
  int fd = ::open(Path.str().c_str(), O_CREAT | O_WRONLY | O_APPEND, 0644);
  if (fd < 0) {
    llvm::errs() << "append_jsonl: open failed: " << Path
                 << " error=" << strerror(errno) << "\n";
    return;
  }

  // 3) 加文件锁（跨进程/跨线程保护，避免交叉写）
  //    注意：flock 锁是“建议锁”(advisory)，要求所有写入方都遵守。
  if (::flock(fd, LOCK_EX) != 0) {
    llvm::errs() << "append_jsonl: flock(LOCK_EX) failed: " << Path
                 << " error=" << strerror(errno) << "\n";
    ::close(fd);
    return;
  }

  // 4) 单次/少次 write 将整行写完
  bool ok = write_all(fd, line.data(), line.size());
  if (!ok) {
    llvm::errs() << "append_jsonl: write failed: " << Path
                 << " error=" << strerror(errno) << "\n";
    // 失败也要解锁+关闭
    ::flock(fd, LOCK_UN);
    ::close(fd);
    return;
  }

  // 5) 可选：确保落盘（视性能取舍）
  // 如果你担心宕机导致尾行丢失，可以启用 fsync
  // 若性能敏感，可以注释掉或改成按需批量 fsync。
  if (::fsync(fd) != 0) {
    // 不把 fsync 失败当致命错误，仅记录
    llvm::errs() << "append_jsonl: fsync failed: " << Path
                 << " error=" << strerror(errno) << "\n";
  }

  // 6) 释放锁、关闭
  (void)::flock(fd, LOCK_UN);
  ::close(fd);
}
```

### 说明与建议

* **为什么不用 `raw_fd_ostream`？**
  它可能拆分为多次 `write()`，在并发下就会和别人交错；上面实现明确保证了“一条记录一次批量写入 + 文件锁”。

* **`flock` vs `fcntl`**
  `flock` 对同一文件描述符的协作更直观；只要**所有**写入者都采用 `flock` 同步，就能避免交错。若你的环境或代码库倾向 `fcntl` 记录锁，也可以换成 `fcntl`。

* **性能**

  * 逐条 `fsync` 会慢；如果你是大量输出，可以去掉 `fsync`，或在更高层做缓冲/批量。
  * 也可以采取“每个编译单元写到一个临时文件，最后再合并”的方式彻底避免锁竞争。

* **内容中的换行**
  用 `llvm::json` 打印出的字符串会做必要转义（包括 `\n`、`"` 等），所以 JSON 行中不会出现“裸换行”破坏一行一条的结构。

* **仍然出现半行怎么办**
  若你看到半行，大概率仍有其他写入路径没走此函数（例如旧的 `output_decl` 也在写同一个文件），或某些代码在写“裸文本”。统一走 `append_jsonl` 并开启锁即可消除。

这样修改后，即使你用 `-j` 并行跑多个 TU 或多个进程同时写，也不会再出现“部分行不是完整 JSON”的问题。
