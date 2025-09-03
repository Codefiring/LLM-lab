要获取参数对应的头文件信息，可以利用 `ParmVarDecl` 上下文来追溯它的源文件。Clang AST 提供了 `getLocation()` 和 `getSourceManager()`，可以将参数声明的 `SourceLocation` 转换成文件名。

在你的 `VisitFunctionDecl` 中，可以这样写：

```cpp
bool VisitFunctionDecl(FunctionDecl *funcDecl) {
  if (!collect_func)
    return true;

  if (funcDecl->isThisDeclarationADefinition()) {
    std::string funcName = funcDecl->getNameAsString();
    if (!funcName.empty()) {
      llvm::outs() << "Function: " << funcName << "\n";

      for (auto param : funcDecl->parameters()) {
        std::string paramType = param->getType().getAsString();
        std::string paramName = param->getNameAsString();

        // 获取参数的源文件路径
        const SourceManager &SM = param->getASTContext().getSourceManager();
        SourceLocation loc = param->getLocation();
        std::string headerFile = SM.getFilename(loc).str();

        llvm::outs() << "  Param: " << paramType << " " << paramName
                     << "   [from: " << headerFile << "]\n";
      }

      output_decl(funcDecl, "func.jsonl");
    }
  }
  return true;
}
```

这样，如果你的函数定义在某个头文件或源文件里，比如：

```cpp
// myheader.h
int func(int a, int b);
```

命令行输出会是：

```
Function: func
  Param: int a   [from: /absolute/path/to/myheader.h]
  Param: int b   [from: /absolute/path/to/myheader.h]
```

### 要点

* `param->getLocation()` 给你这个参数在源码中的位置。
* 用 `SourceManager::getFilename(SourceLocation)` 可以拿到对应的文件路径（头文件/源文件）。
* 如果是宏展开或系统头文件，可能需要 `SM.getExpansionLoc(loc)` 来取展开后的真实位置。

要不要我帮你加上区分 **系统头文件**（比如 `<string>`）和 **用户头文件**（`"myheader.h"`）的逻辑？
