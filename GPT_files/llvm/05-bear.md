可以，不用 CMake 也能拿到 **driver 风格** 的 `compile_commands.json`。常见做法有 4 类，按“稳妥程度/可控性”排序给你：

---

## 1) 让 **clang 驱动**自己产出（最干净、最可控）

* **`-MJ <file>`**：对每次编译，clang 驱动会写出一个“CDB 片段”（单条 JSON）。把所有片段用 `[` 和 `]` 包起来、用逗号连接，就得到完整 `compile_commands.json`。这是 clang 官方支持的方式。([clang.llvm.org][1])
  示例（Makefile 中给 `CXXFLAGS` 加一条，或临时加在命令行）：

  ```bash
  clang++ -c foo.cpp -o foo.o -MJ cdb-frags/foo.cpp.json
  ```
* **`-gen-cdb-fragment-path <dir>`**：更省心的“目录版 `-MJ`”。每次编译会把片段写到目录 `<dir>` 下，事后把这些片段合并即可（很多项目就是用它做 Xcode/自定义构建的 CDB）。([reviews.llvm.org][2], [docs.sonarsource.com][3], [Gist][4])
  合并示例（bash）：

  ```bash
  cd cdb-frags
  sed -e '1s/^/[\
  /' -e '$s/,$/\
  ]/' *.json > ../compile_commands.json
  ```

> 这两种方式一定是 **driver 风格**（`clang++ -I... -target ...`），不会混进 `-cc1`。官方 JSON CDB 文档也明确写了 `-MJ` 产物可直接拼成 CDB。([clang.llvm.org][1])

---

## 2) 用 **intercept-build**（scan-build 系列）

* 命令：`intercept-build <你的构建命令>`
  它用编译器 **wrapper/拦截** 记录 **driver 调用** 并生成 `compile_commands.json`，常用于非 CMake 的 Make/自研脚本等。带 `--override-compiler`/`--intercept-first` 可强制走 wrapper 以避免抓到奇怪的中间层。([GitHub][5])
  参考用法与选项文档：([oneapi-src.github.io][6], [Intel][7])

---

## 3) 用 **Ninja 自带**（如果你的项目本来就用 ninja）

* `ninja -t compdb cxx cc > compile_commands.json`
  这是 ninja 工具内置的导出器，直接吐 driver 风格命令。适合已在用 ninja 的项目（不依赖 CMake 也可以，只要你的 `build.ninja` 定义了 `cc/cxx` 规则）。([Gist][8])

---

## 4) 仍想用 **Bear**（有时会混入 `-cc1`，但可试）

* `bear -- <你的构建命令>`
  Bear 通过系统调用拦截记录“真实执行的命令”。如果你的构建链路里有包装器/二次 exec，它**可能**记录到 `cc1` 调用，导致出现 `-cc1/-triple`。这是它的工作方式特性。([GitHub][9])
  如果必须用 Bear，尽量：

  * 让它拦到**最外层 `clang/clang++` 驱动**（减少 wrapper/ccache 影响，必要时用它的 wrapper 模式或调整构建脚本）。([GitHub][5])

---

### 小结与建议

* **首选**：在你的构建命令里加 `-gen-cdb-fragment-path cdb-frags`（或 `-MJ`），构建一次后合并片段，得到完全标准的 **driver 风格** CDB。最稳。([clang.llvm.org][1], [reviews.llvm.org][2])
* **次选**：`intercept-build`。
* **能用则用**：`ninja -t compdb`（如果你用 ninja）。([Gist][8])
* **最后**：Bear（可能混入 `-cc1`，不稳定）。([GitHub][10])

如果你贴一下你现在的构建命令（Makefile 里的一条或手打命令），我可以直接给出把 `-gen-cdb-fragment-path` 或 `-MJ` 嵌进去的最小修改示例。

[1]: https://clang.llvm.org/docs/JSONCompilationDatabase.html?utm_source=chatgpt.com "JSON Compilation Database Format Specification - Clang"
[2]: https://reviews.llvm.org/D66555?utm_source=chatgpt.com "[driver] add a new option `-gen-cdb-fragment-path` to emit ..."
[3]: https://docs.sonarsource.com/sonarqube-cloud/advanced-setup/languages/c-family/prerequisites/?utm_source=chatgpt.com "Prerequisites | SonarQube Cloud Documentation"
[4]: https://gist.github.com/T1T4N/f4d63a44476eb5c7046cc561cb8c7f77?utm_source=chatgpt.com "Generate a JSON Compilation Database from an Xcode ..."
[5]: https://github.com/rizsotto/scan-build?utm_source=chatgpt.com "Clang's scan-build re-implementation in python"
[6]: https://oneapi-src.github.io/SYCLomatic/dev_guide/migration/generate-compilation-db.html?utm_source=chatgpt.com "Generate a Compilation Database"
[7]: https://www.intel.com/content/www/us/en/docs/dpcpp-compatibility-tool/developer-guide-reference/2024-2/intercept-build-options.html?utm_source=chatgpt.com "intercept-build Options"
[8]: https://gist.github.com/gtors/effe8eef7dbe7052b22a009f3c7fc434?utm_source=chatgpt.com "Makefile -> compilation_commands.json"
[9]: https://github.com/rizsotto/Bear/wiki/Usage?utm_source=chatgpt.com "Usage · rizsotto/Bear Wiki"
[10]: https://github.com/rizsotto/Bear?utm_source=chatgpt.com "rizsotto/Bear: Bear is a tool that generates a compilation ..."
