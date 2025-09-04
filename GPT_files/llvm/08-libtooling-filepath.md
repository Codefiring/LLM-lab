看起来不是源码“真不存在”，而是**路径解析被工作目录（cwd）和多线程并发搞乱了**。`ClangTool` 在运行时会根据 `compile_commands.json` 里每条编译指令的 `"directory"` 字段去 `chdir` 到相应目录（这是进程级别的，全线程共享！）。你现在把多个 `ClangTool::run()` 放到 `std::async` 里并行跑，就会出现各线程互相改 cwd 的竞态，结果有的线程在“错误”的 cwd 下去找相对路径，自然就报“文件不存在”。你观察到“在 test 目录运行报 test/test.c 不存在，在 test/src 下运行正常”，正是这个问题的典型表征。

下面给出几种可行的修复方式（任选其一或组合）：

---

### 方案 A：不要并行跑多个 `ClangTool::run()`

把所有 `sources` 一次性交给一个 `ClangTool`，顺序执行。最稳妥。

```cpp
// 准备绝对路径（非常重要）
std::vector<std::string> absSources;
absSources.reserve(sources.size());
for (const auto &s : sources) {
  llvm::SmallString<256> p(s);
  llvm::sys::fs::make_absolute(p);                 // 转成绝对路径
  llvm::sys::path::remove_dots(p, /*remove_dot_dot=*/true);
  absSources.emplace_back(p.str().str());
}

ClangTool tool(*CompilationDatabase, absSources);
auto factory = newFrontendActionFactory<StructAction>();
// 默认就会按 compile_commands.json 的 "directory" 切换工作目录
int rc = tool.run(factory.get());
```

**要点**

* `sources` 用**绝对路径**，并且要和 `compile_commands.json` 里的 `"file"` 字段一致（最好也用绝对路径）。
* `compile_commands.json` 中每条的 `"directory"` 应该能使相对包含与相对源文件路径正确解析。

---

### 方案 B：仍要并行？改为“多进程”而不是“多线程”

`chdir` 是进程级的，线程并行会打架；**用多进程**就互不干扰。做法是把你的工具本身当成子进程（像 `clang-tidy` 那样）对每个源文件启动一个进程，或用进程池（例如 `std::system`/`posix_spawn`/`CreateProcess` 等）。这样每个进程内部顺序跑一个 `ClangTool::run()`，就不会互相影响。

---

### 方案 C：强制使用绝对路径并避免相对路径依赖

如果你坚持线程并行（不推荐），至少要减少对 cwd 的依赖：

* `sources` 一律转为绝对路径（见上面的转法）。
* 确保 `compile_commands.json` 的 `"file"` 与命令行里的相对路径问题不冲突（最好也写绝对）。
* 仍然可能因为 `ClangTool` 内部会根据 `"directory"` 切换 cwd 而产生竞态，因此**线程并行依旧不安全**；这个方案只能*降低*而不能*消除*问题。

---

### 方案 D：直接用编译数据库给出的文件清单

避免自己拼相对路径：

```cpp
auto allFiles = CompilationDatabase->getAllFiles(); // 通常已是规范化路径
ClangTool tool(*CompilationDatabase, allFiles);
auto factory = newFrontendActionFactory<StructAction>();
tool.run(factory.get());
```

---

### 额外排查清单

1. **`compile_commands.json` 的 `"file"` 与 `"directory"`**：

   * 尽量使用**绝对路径**；
   * `"directory"` 应该是当时编译该文件时的工作目录（相对包含、宏文件路径都以它为基准）。
2. **你的 `sources` 列表**：

   * 不要混用形如 `src/test.c`、`./src/test.c`、`/abs/path/src/test.c` 的不同写法；统一成**绝对路径**。
3. **避免在多线程中调用 `ClangTool::run()`**：

   * 如果必须并行，改多进程。

---

### 一个更稳的代码骨架（顺序执行 + 绝对路径）

```cpp
std::vector<std::string> absSources;
absSources.reserve(sources.size());
for (const auto &s : sources) {
  llvm::SmallString<256> p(s);
  llvm::sys::fs::make_absolute(p);
  llvm::sys::path::remove_dots(p, /*remove_dot_dot=*/true);
  absSources.emplace_back(p.str().str());
}

ClangTool tool(*CompilationDatabase, absSources);
auto actionFactory = newFrontendActionFactory<StructAction>();
int rc = tool.run(actionFactory.get());
if (rc != 0) {
  // 根据需要处理错误
}
```

---

**结论**：你遇到的问题本质是**进程工作目录在多线程中被 `ClangTool` 改来改去**引发的路径解析乱象。最简单可靠的修复是**改为单个 `ClangTool` 顺序跑**（或改为**多进程并行**），并**统一使用绝对路径**，确保与 `compile_commands.json` 一致。
