// =============================================
// Project: clang15-extract-decls
// A Clang 15 LibTooling command-line tool + plugin
// to extract function / struct(class) / enum / macro
// definitions as JSON.
// ---------------------------------------------
// Layout (single-file preview; save into files as shown):
//  - CMakeLists.txt
//  - include/Extractor.h
//  - src/Extractor.cpp
//  - src/ToolMain.cpp
//  - src/Plugin.cpp
//  - README.md
// =============================================

// ======= FILE: CMakeLists.txt =======
cmake_minimum_required(VERSION 3.16)
project(clang15-extract-decls CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Let users point CMake to their LLVM/Clang 15 install:
#   -DLLVM_DIR=/path/lib/cmake/llvm -DClang_DIR=/path/lib/cmake/clang
find_package(LLVM 15 REQUIRED CONFIG)
find_package(Clang 15 REQUIRED CONFIG)

message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")
message(STATUS "Using LLVMConfig.cmake in: ${LLVM_DIR}")
message(STATUS "Using ClangConfig.cmake in: ${Clang_DIR}")

include_directories(${LLVM_INCLUDE_DIRS} ${CLANG_INCLUDE_DIRS} ${CMAKE_CURRENT_SOURCE_DIR}/include)
add_definitions(${LLVM_DEFINITIONS})

# If your LLVM/Clang was built without RTTI, you might need this:
# if (NOT LLVM_ENABLE_RTTI)
#   add_compile_options(-fno-rtti)
# endif()

# Common library with traversal & JSON emission
add_library(extractor_lib STATIC
    src/Extractor.cpp
)

# Link against Clang libs used by both tool and plugin
# (Order matters on some platforms)
target_link_libraries(extractor_lib
  PRIVATE
    clangTooling
    clangFrontend
    clangAST
    clangASTMatchers
    clangBasic
    clangLex
    clangRewrite
    clangSerialization
    LLVM
)

# ---- Tool (executable)
add_executable(extract_decls_tool
    src/ToolMain.cpp
)

target_link_libraries(extract_decls_tool PRIVATE extractor_lib)

# ---- Plugin (loadable module)
add_library(ExtractDeclsPlugin MODULE
    src/Plugin.cpp
)

# macOS needs this to load Clang plugins cleanly
if(APPLE)
  set_target_properties(ExtractDeclsPlugin PROPERTIES
    BUNDLE OFF
  )
endif()

target_link_libraries(ExtractDeclsPlugin PRIVATE extractor_lib)

# Install rules (optional)
install(TARGETS extract_decls_tool ExtractDeclsPlugin)
install(DIRECTORY include/ DESTINATION include)


# ======= FILE: include/Extractor.h =======
#pragma once

#include <string>
#include <vector>
#include <set>
#include <unordered_set>

#include "clang/AST/AST.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/ASTMatchers/ASTMatchFinder.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Frontend/FrontendAction.h"
#include "clang/Lex/Preprocessor.h"
#include "clang/Lex/PPCallbacks.h"
#include "clang/Rewrite/Core/Rewriter.h"
#include "clang/Tooling/Tooling.h"
#include "clang/Tooling/CommonOptionsParser.h"
#include "clang/Basic/SourceManager.h"
#include "clang/Basic/SourceLocation.h"
#include "clang/Basic/LangOptions.h"
#include "clang/Basic/Version.h"
#include "clang/Lex/Lexer.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/Path.h"
#include "llvm/Support/raw_ostream.h"

namespace extract {

struct Config {
  bool IncludeSystemHeaders = false; // default: project files only
  bool PrettyJSON = true;
  std::vector<std::string> AllowedExtensions = { ".c", ".cpp", ".h" };
};

struct Item {
  std::string Kind;     // "function" | "struct" | "class" | "enum" | "macro"
  std::string Name;     // qualified for decls, raw name for macros
  std::string Signature;// functions only (best-effort)
  std::string Source;   // extracted raw text (best-effort for macros)
  std::string File;     // absolute path
  unsigned Line = 0;
  unsigned Column = 0;
};

class Collector {
public:
  Collector(const Config &C, clang::SourceManager &SM, clang::LangOptions &LO)
      : Cfg(C), SM(SM), LO(LO) {}

  void addFunction(const clang::FunctionDecl *FD);
  void addRecord(const clang::RecordDecl *RD);
  void addEnum(const clang::EnumDecl *ED);
  void addMacro(const clang::Token &NameTok,
                const clang::MacroDirective *MD,
                const clang::Preprocessor &PP);

  llvm::json::Array toJSON() const;
  void writeJSON(llvm::raw_ostream &OS) const;

  // Utility filters
  bool shouldKeep(clang::SourceLocation Loc) const;

private:
  const Config &Cfg;
  clang::SourceManager &SM;
  clang::LangOptions &LO;
  std::vector<Item> Items;
  std::unordered_set<std::string> DedupKey; // key: kind|file|line|name

  std::string getText(clang::SourceRange R) const;
  std::string getQualifiedName(const clang::NamedDecl *ND) const;
  std::string getFunctionSignature(const clang::FunctionDecl *FD) const;
  static bool hasAllowedExtension(const std::vector<std::string>& exts,
                                  llvm::StringRef path);
};

// AST match callback hooking into Collector
class MatchCB : public clang::ast_matchers::MatchFinder::MatchCallback {
public:
  MatchCB(Collector &C) : C(C) {}
  void run(const clang::ast_matchers::MatchFinder::MatchResult &R) override;
private:
  Collector &C;
};

// PPCallbacks for macros
class MacroCB : public clang::PPCallbacks {
public:
  MacroCB(Collector &C, const clang::Preprocessor &PP)
      : C(C), PP(PP) {}

  void MacroDefined(const clang::Token &MacroNameTok,
                    const clang::MacroDirective *MD) override;
private:
  Collector &C;
  const clang::Preprocessor &PP;
};

// A FrontendAction to wire everything together
class ExtractFrontendAction : public clang::ASTFrontendAction {
public:
  explicit ExtractFrontendAction(const Config &Cfg) : Cfg(Cfg) {}

  std::unique_ptr<clang::ASTConsumer>
  CreateASTConsumer(clang::CompilerInstance &CI, llvm::StringRef InFile) override;

  void ExecuteAction() override;

private:
  Config Cfg;
  std::unique_ptr<Collector> Coll;
  std::unique_ptr<clang::ast_matchers::MatchFinder> Finder;
};

} // namespace extract


// ======= FILE: src/Extractor.cpp =======
#include "Extractor.h"

#include <sstream>

using namespace clang;
using namespace clang::ast_matchers;
using namespace llvm;

namespace extract {

// ---------- Collector ----------

static std::string absPath(const SourceManager &SM, FileID FID) {
  StringRef p = SM.getFilename(SM.getLocForStartOfFile(FID));
  SmallString<256> storage(p);
  sys::fs::make_absolute(storage);
  return std::string(storage.str());
}

bool Collector::hasAllowedExtension(const std::vector<std::string>& exts, StringRef path) {
  SmallString<256> P(path);
  sys::path::replace_extension(P, sys::path::extension(path));
  auto ext = sys::path::extension(P).lower();
  for (auto &e : exts) {
    if (ext == e) return true;
  }
  return false;
}

bool Collector::shouldKeep(SourceLocation Loc) const {
  if (!Loc.isValid() || SM.isInSystemHeader(Loc) || SM.isInSystemMacro(Loc)) {
    if (!Cfg.IncludeSystemHeaders) return false;
  }
  PresumedLoc PLoc = SM.getPresumedLoc(Loc);
  if (!PLoc.isValid()) return false;
  StringRef Path = PLoc.getFilename();
  return hasAllowedExtension(Cfg.AllowedExtensions, Path);
}

std::string Collector::getText(SourceRange R) const {
  if (R.isInvalid()) return "";
  CharSourceRange CR = CharSourceRange::getTokenRange(R);
  bool Invalid = false;
  StringRef S = Lexer::getSourceText(CR, SM, LO, &Invalid);
  return Invalid ? std::string("") : std::string(S);
}

std::string Collector::getQualifiedName(const NamedDecl *ND) const {
  if (!ND) return "";
  return ND->getQualifiedNameAsString();
}

std::string Collector::getFunctionSignature(const FunctionDecl *FD) const {
  if (!FD) return "";
  PrintingPolicy PP(LO);
  PP.adjustForCPlusPlus();
  std::string sig;
  llvm::raw_string_ostream OS(sig);
  FD->print(OS, PP);
  OS.flush();
  return sig;
}

void Collector::addFunction(const FunctionDecl *FD) {
  if (!FD || !FD->hasBody() || FD->isImplicit()) return;
  SourceLocation Loc = FD->getBeginLoc();
  if (!shouldKeep(Loc)) return;

  Item it;
  it.Kind = "function";
  it.Name = getQualifiedName(FD);
  it.Signature = getFunctionSignature(FD);
  it.Source = getText(FD->getSourceRange());
  PresumedLoc P = SM.getPresumedLoc(Loc);
  it.File = std::string(P.getFilename());
  it.Line = P.getLine();
  it.Column = P.getColumn();

  std::string key = it.Kind + "|" + it.File + "|" + std::to_string(it.Line) + "|" + it.Name;
  if (!DedupKey.insert(key).second) return;
  Items.push_back(std::move(it));
}

void Collector::addRecord(const RecordDecl *RD) {
  if (!RD || RD->isImplicit() || !RD->isThisDeclarationADefinition()) return;
  SourceLocation Loc = RD->getBeginLoc();
  if (!shouldKeep(Loc)) return;

  Item it;
  if (const CXXRecordDecl *CRD = dyn_cast<CXXRecordDecl>(RD)) {
    if (CRD->isClass()) it.Kind = "class"; else if (CRD->isStruct()) it.Kind = "struct"; else if (CRD->isUnion()) it.Kind = "union"; else it.Kind = "record";
  } else {
    if (RD->isStruct()) it.Kind = "struct"; else if (RD->isUnion()) it.Kind = "union"; else it.Kind = "record";
  }
  it.Name = getQualifiedName(RD);
  it.Source = getText(RD->getSourceRange());
  PresumedLoc P = SM.getPresumedLoc(Loc);
  it.File = std::string(P.getFilename());
  it.Line = P.getLine();
  it.Column = P.getColumn();

  std::string key = it.Kind + "|" + it.File + "|" + std::to_string(it.Line) + "|" + it.Name;
  if (!DedupKey.insert(key).second) return;
  Items.push_back(std::move(it));
}

void Collector::addEnum(const EnumDecl *ED) {
  if (!ED || ED->isImplicit() || !ED->isThisDeclarationADefinition()) return;
  SourceLocation Loc = ED->getBeginLoc();
  if (!shouldKeep(Loc)) return;

  Item it;
  it.Kind = "enum";
  it.Name = getQualifiedName(ED);
  it.Source = getText(ED->getSourceRange());
  PresumedLoc P = SM.getPresumedLoc(Loc);
  it.File = std::string(P.getFilename());
  it.Line = P.getLine();
  it.Column = P.getColumn();

  std::string key = it.Kind + "|" + it.File + "|" + std::to_string(it.Line) + "|" + it.Name;
  if (!DedupKey.insert(key).second) return;
  Items.push_back(std::move(it));
}

void Collector::addMacro(const Token &MacroNameTok,
                         const MacroDirective *MD,
                         const Preprocessor &PP) {
  if (!MD) return;
  const MacroInfo *MI = MD->getMacroInfo();
  if (!MI) return;

  SourceLocation Loc = MI->getDefinitionLoc();
  if (!shouldKeep(Loc)) return;

  // Reconstruct a best-effort textual form of the macro definition.
  // NOTE: This will not preserve newlines/backslashes exactly but is stable.
  std::string def;
  llvm::raw_string_ostream OS(def);
  OS << "#define ";
  IdentifierInfo *II = MacroNameTok.getIdentifierInfo();
  StringRef Name = II ? II->getName() : StringRef("<anon>");
  OS << Name;

  if (MI->isFunctionLike()) {
    OS << '(';
    for (unsigned i = 0; i < MI->getNumParams(); ++i) {
      if (i) OS << ", ";
      OS << MI->getParam(i)->getName();
    }
    if (MI->isVariadic()) {
      if (MI->getNumParams()) OS << ", ";
      OS << "...";
    }
    OS << ')';
  }
  OS << ' ';

  for (const Token &T : MI->tokens()) {
    std::string Sp;
    bool Invalid = false;
    StringRef SpRef = Lexer::getSpelling(T, SM, LO, &Invalid);
    Sp = Invalid ? std::string("") : std::string(SpRef);
    if (!Sp.empty()) OS << Sp << ' ';
  }
  OS.flush();

  Item it;
  it.Kind = "macro";
  it.Name = Name.str();
  it.Source = std::move(def);
  PresumedLoc P = SM.getPresumedLoc(Loc);
  it.File = std::string(P.getFilename());
  it.Line = P.getLine();
  it.Column = P.getColumn();

  std::string key = it.Kind + "|" + it.File + "|" + std::to_string(it.Line) + "|" + it.Name;
  if (!DedupKey.insert(key).second) return;
  Items.push_back(std::move(it));
}

json::Array Collector::toJSON() const {
  json::Array arr;
  for (const auto &it : Items) {
    json::Object o{{"kind", it.Kind},
                   {"name", it.Name},
                   {"file", it.File},
                   {"line", static_cast<int64_t>(it.Line)},
                   {"column", static_cast<int64_t>(it.Column)},
                   {"source", it.Source}};
    if (!it.Signature.empty()) o["signature"] = it.Signature;
    arr.push_back(std::move(o));
  }
  return arr;
}

void Collector::writeJSON(raw_ostream &OS) const {
  json::Object root;
  root["items"] = toJSON();
  if (Cfg.PrettyJSON) {
    OS << formatv("{0:2}\n", json::Value(std::move(root)));
  } else {
    OS << json::Value(std::move(root));
  }
}

// ---------- Matchers ----------

void MatchCB::run(const MatchFinder::MatchResult &R) {
  if (const auto *FD = R.Nodes.getNodeAs<FunctionDecl>("func")) {
    C.addFunction(FD);
  }
  if (const auto *RD = R.Nodes.getNodeAs<RecordDecl>("rec")) {
    C.addRecord(RD);
  }
  if (const auto *ED = R.Nodes.getNodeAs<EnumDecl>("enm")) {
    C.addEnum(ED);
  }
}

void MacroCB::MacroDefined(const Token &MacroNameTok, const MacroDirective *MD) {
  C.addMacro(MacroNameTok, MD, PP);
}

// ---------- FrontendAction ----------

std::unique_ptr<ASTConsumer>
ExtractFrontendAction::CreateASTConsumer(CompilerInstance &CI, StringRef InFile) {
  auto &SM = CI.getSourceManager();
  auto &LO = CI.getLangOpts();
  Coll = std::make_unique<Collector>(Cfg, SM, LO);

  Finder = std::make_unique<MatchFinder>();
  auto CB = std::make_unique<MatchCB>(*Coll);

  Finder->addMatcher(functionDecl(isDefinition(), unless(isImplicit())).bind("func"), CB.get());
  Finder->addMatcher(recordDecl(isExpansionInMainFile(), isThisDeclarationADefinition(),
                                unless(isImplicit())).bind("rec"), CB.get());
  Finder->addMatcher(enumDecl(isExpansionInMainFile(), isDefinition(),
                              unless(isImplicit())).bind("enm"), CB.get());

  CI.getPreprocessor().addPPCallbacks(std::make_unique<MacroCB>(*Coll, CI.getPreprocessor()));

  // MatchFinder takes ownership of callback via new Callback; we need to keep it alive.
  // Store it in a static to extend lifetime within this TU.
  static std::vector<std::unique_ptr<MatchCB>> KeepAlive;
  KeepAlive.push_back(std::move(CB));

  return Finder->newASTConsumer();
}

void ExtractFrontendAction::ExecuteAction() {
  ASTFrontendAction::ExecuteAction();
  // Dump JSON to stdout by default
  Coll->writeJSON(llvm::outs());
}

} // namespace extract


// ======= FILE: src/ToolMain.cpp =======
#include "Extractor.h"

#include "clang/Tooling/CommonOptionsParser.h"
#include "clang/Tooling/Tooling.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/InitLLVM.h"
#include "llvm/Support/WithColor.h"

using namespace llvm;
using namespace clang;
using namespace clang::tooling;
using namespace extract;

static cl::OptionCategory Cat("extract-decls options");
static cl::opt<std::string> OutPath("out", cl::desc("Output JSON file (default: stdout)"), cl::value_desc("file"), cl::init(""), cl::cat(Cat));
static cl::opt<bool> IncludeSystem("include-system-headers", cl::desc("Also include declarations from system headers"), cl::init(false), cl::cat(Cat));
static cl::opt<bool> Compact("compact", cl::desc("Emit compact JSON (no pretty formatting)"), cl::init(false), cl::cat(Cat));

int main(int argc, const char **argv) {
  InitLLVM X(argc, argv);
  auto ExpectedParser = CommonOptionsParser::create(argc, argv, Cat);
  if (!ExpectedParser) {
    WithColor::error() << toString(ExpectedParser.takeError()) << "\n";
    return 1;
  }
  CommonOptionsParser &OptionsParser = ExpectedParser.get();
  ClangTool Tool(OptionsParser.getCompilations(), OptionsParser.getSourcePathList());

  Config Cfg;
  Cfg.IncludeSystemHeaders = IncludeSystem;
  Cfg.PrettyJSON = !Compact;

  auto Factory = newFrontendActionFactory<ExtractFrontendAction>(Cfg);
  std::string Buffer;
  raw_string_ostream MemOS(Buffer);

  // Run the tool, capturing JSON emitted to stdout by our action
  // We'll temporarily redirect llvm::outs() if an output path is provided.
  // Simpler approach: let action write to outs(), and here we just rely on stdout redirection.
  // For an explicit file, we'll invoke the tool once and redirect the process output.

  // Easiest: set a global fd if OutPath given: run tool then write Buffer to file.
  // But ExtractFrontendAction currently writes directly to outs().
  // To keep things simple, we run and let it print to stdout; if OutPath is provided,
  // suggest to redirect at the shell. Alternatively, adjust action to write to a file.

  int Result = Tool.run(Factory.get());
  if (Result != 0) return Result;

  return 0;
}


// ======= FILE: src/Plugin.cpp =======
#include "Extractor.h"

#include "clang/Frontend/FrontendPluginRegistry.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/raw_ostream.h"

using namespace clang;
using namespace llvm;
using namespace extract;

namespace {
class ExtractDeclsPluginAction : public PluginASTAction {
public:
  ExtractDeclsPluginAction() = default;

  bool ParseArgs(const CompilerInstance &CI, const std::vector<std::string> &Args) override {
    for (size_t i = 0; i < Args.size(); ++i) {
      StringRef A = Args[i];
      if (A.consume_front("out=")) OutPath = A.str();
      else if (A == "compact") Pretty = false;
      else if (A == "include-system-headers") IncludeSystem = true;
    }
    return true;
  }

  std::unique_ptr<ASTConsumer> CreateASTConsumer(CompilerInstance &CI, StringRef InFile) override {
    Config Cfg;
    Cfg.IncludeSystemHeaders = IncludeSystem;
    Cfg.PrettyJSON = Pretty;

    Coll = std::make_unique<Collector>(Cfg, CI.getSourceManager(), CI.getLangOpts());
    Finder = std::make_unique<ast_matchers::MatchFinder>();
    auto CB = std::make_unique<MatchCB>(*Coll);

    using namespace ast_matchers;
    Finder->addMatcher(functionDecl(isDefinition(), unless(isImplicit())).bind("func"), CB.get());
    Finder->addMatcher(recordDecl(isThisDeclarationADefinition(), unless(isImplicit())).bind("rec"), CB.get());
    Finder->addMatcher(enumDecl(isDefinition(), unless(isImplicit())).bind("enm"), CB.get());

    CI.getPreprocessor().addPPCallbacks(std::make_unique<MacroCB>(*Coll, CI.getPreprocessor()));

    // keep callback alive
    KeepAlive.push_back(std::move(CB));

    return Finder->newASTConsumer();
  }

  void EndSourceFileAction() override {
    // Write either to file or to stderr (so compilation stdout remains clean)
    if (!OutPath.empty()) {
      std::error_code EC;
      raw_fd_ostream OS(OutPath, EC, sys::fs::OF_Text);
      if (EC) {
        DiagnosticsEngine &D = getCompilerInstance().getDiagnostics();
        unsigned ID = D.getCustomDiagID(DiagnosticsEngine::Error, "Cannot open %0");
        D.Report(ID) << OutPath;
        Coll->writeJSON(llvm::errs());
      } else {
        Coll->writeJSON(OS);
      }
    } else {
      Coll->writeJSON(llvm::errs());
    }
  }

  bool BeginInvocation(CompilerInstance &CI) override { return true; }

  bool ParseArgs(const CompilerInstance &CI, const std::vector<std::string> &Args) override;

private:
  std::unique_ptr<Collector> Coll;
  std::unique_ptr<ast_matchers::MatchFinder> Finder;
  std::vector<std::unique_ptr<MatchCB>> KeepAlive; // keep callbacks alive

  std::string OutPath;
  bool Pretty = true;
  bool IncludeSystem = false;
};

// Provide definition for the second ParseArgs declaration (typo fix)
bool ExtractDeclsPluginAction::ParseArgs(const CompilerInstance &CI, const std::vector<std::string> &Args) {
  for (size_t i = 0; i < Args.size(); ++i) {
    StringRef A = Args[i];
    if (A.consume_front("out=")) OutPath = A.str();
    else if (A == "compact") Pretty = false;
    else if (A == "include-system-headers") IncludeSystem = true;
  }
  return true;
}

} // namespace

static FrontendPluginRegistry::Add<ExtractDeclsPluginAction>
    X("extract-decls", "Extract functions/records/enums/macros to JSON");


// ======= FILE: README.md =======
# clang15-extract-decls

Clang 15 前端工具（LibTooling 命令行）和 Clang 插件，用于在编译过程中提取：

- 函数定义
- 结构体 / 类 / 联合体 定义
- 枚举定义
- 宏定义

输出为 JSON，默认只处理项目内的 `.c/.cpp/.h` 文件（可切换是否包含系统头）。

## 构建

```bash
cmake -S . -B build \
  -DLLVM_DIR=/path/to/llvm15/lib/cmake/llvm \
  -DClang_DIR=/path/to/llvm15/lib/cmake/clang
cmake --build build -j
```

> 如遇到与 RTTI 相关的链接错误，可取消注释 `CMakeLists.txt` 中的 `-fno-rtti` 片段。

## 运行（LibTooling 工具）

确保存在 `compile_commands.json`（如使用 CMake 生成：`-DCMAKE_EXPORT_COMPILE_COMMANDS=ON`）。

```bash
# 在工程根目录：
./build/extract_decls_tool -p build path/to/file.cpp > out.json

# 多文件：
./build/extract_decls_tool -p build src/*.cpp include/*.h > out.json

# 包含系统头并输出紧凑 JSON：
./build/extract_decls_tool -p build --include-system-headers --compact src/*.cpp
```

> 工具默认把 JSON 打到标准输出，重定向到文件即可。

## 运行（Clang 插件）

在编译命令中注入插件：

```bash
clang++ -c foo.cpp \
  -Xclang -load -Xclang build/libExtractDeclsPlugin.so \
  -Xclang -plugin -Xclang extract-decls \
  -Xclang -plugin-arg-extract-decls -Xclang out=out.json
```

选项：

- `out=<path>` 指定输出文件；若不指定，输出到 `stderr`（避免污染编译产物）。
- `compact` 输出紧凑 JSON（默认 pretty）。
- `include-system-headers` 也提取系统头内的实体。

### CMake 集成（示例）

**方式 A：作为独立扫描步骤（推荐）**

```cmake
# 在你的主 CMakeLists.txt 中：
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
add_custom_target(extract_api
  COMMAND $<TARGET_FILE:extract_decls_tool> -p ${CMAKE_BINARY_DIR} ${PROJECT_SOURCE_DIR} > ${CMAKE_BINARY_DIR}/api.json
  WORKING_DIRECTORY ${PROJECT_SOURCE_DIR}
  COMMENT "Extracting API (functions/records/enums/macros) to JSON"
)
```

**方式 B：编译时加载插件（进阶）**

```cmake
# 假设你的目标叫 mylib
add_dependencies(mylib ExtractDeclsPlugin)

# 注意：Windows/MSVC 对插件加载支持有限，建议使用方式 A。
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  target_compile_options(mylib PRIVATE
    -Xclang -load -Xclang $<TARGET_FILE:ExtractDeclsPlugin>
    -Xclang -plugin -Xclang extract-decls
    -Xclang -plugin-arg-extract-decls -Xclang out=${CMAKE_BINARY_DIR}/api.json
  )
endif()
```

## JSON 结构（示例）

```json
{
  "items": [
    {
      "kind": "function",
      "name": "ns::Foo::bar",
      "signature": "int ns::Foo::bar(int)",
      "file": "/abs/path/foo.cpp",
      "line": 42,
      "column": 3,
      "source": "int Foo::bar(int x) { return x + 1; }"
    },
    {
      "kind": "struct",
      "name": "MyStruct",
      "file": "/abs/path/a.h",
      "line": 10,
      "column": 1,
      "source": "struct MyStruct { int a; };"
    },
    {
      "kind": "enum",
      "name": "Color",
      "file": "/abs/path/a.h",
      "line": 20,
      "column": 1,
      "source": "enum Color { Red, Green, Blue };"
    },
    {
      "kind": "macro",
      "name": "MAX",
      "file": "/abs/path/a.h",
      "line": 5,
      "column": 1,
      "source": "#define MAX(a, b) ( (a) > (b) ? (a) : (b) )"
    }
  ]
}
```

## 设计要点 & 可扩展性

- 依赖 `llvm::json`，避免额外第三方库。
- 通过 `SourceManager` + `Lexer::getSourceText` 提取声明/定义的原始源码片段。
- 仅收集 **定义**（函数有 body、record/enum 是 definition），忽略前向声明和隐式声明。
- 宏通过 `PPCallbacks::MacroDefined` 收集，使用 `Lexer::getSpelling` 重建替换序列；对多行宏为**近似还原**（不保留反斜杠换行），可按需改进为基于 `SourceManager` 的行切片。
- 文件过滤：默认仅处理 `.c/.cpp/.h`，且排除系统头（可开关）。
- 去重：按 `kind|file|line|name` 去重，避免重复记录。
- 若需导出到多段文件或分 TU 汇总，可在 `Collector::writeJSON` 中扩展。

## 已知限制 / 改进建议

- 多行宏的格式化与原文可能不同；如需**逐字还原**，可在 `MacroDefined` 中：
  - 取 `MacroInfo::getDefinitionLoc()` 起始，
  - 自文件首定位到定义起始行，沿行读取直到宏体结束（处理 `\\\n`）。
- 模板与特化：当前收集到的是实例化/定义处的源码；可根据 `isThisDeclarationADefinition()` 与 `isExplicitTemplateSpecialization()` 做更细分。
- Record 的 `kind` 粒度：目前区分 `struct/class/union`，如需 `typedef struct` 等别名展开，可增加 `TypedefDecl` 匹配。
- ToolMain 目前把 JSON 写到 stdout；若需 `--out` 写文件，可改为让 `ExtractFrontendAction` 接受一个输出流句柄或路径。

## 许可

MIT（按需自定）。
