逻辑直接说：

你要在 `VisitEnumDecl` 里，枚举 `EnumDecl` 下所有 `EnumConstantDecl`，取出名字和常量值，逐个写到新的 `jsonl` 文件里，例如：

```json
{"name":"MFCINST_INIT","source":100}
{"name":"MFCINST_GOT_INST","source":101}
...
```

下面给你一份适配 Clang 14 的完整示例实现，你可以直接塞进现在的代码结构里用（沿用你之前的 `output_***` 风格）。

### 实现要点

* `EnumDecl::enumerators()` 能拿到所有 `EnumConstantDecl`.
* `EnumConstantDecl::getInitVal()` 返回的是 `llvm::APSInt`，里边已经是“算完”的值（包括像 `MFCINST_GOT_INST` 这种自增出来的）。
* 从 `APSInt` 里拿 `getSExtValue()` / `getZExtValue()` 转成整型输出到 JSON。
* 每个枚举常量一行 jsonl。

### 代码示例

先假设你有个简单的写 jsonl 的工具函数（如果你已经有类似 `output_decl` 的封装，可以在里面换成这个逻辑）：

```cpp
#include <fstream>
#include <sstream>
#include "clang/AST/Decl.h"
#include "llvm/ADT/APSInt.h"

using namespace clang;

static void output_enum_const_jsonl(const std::string &fileName,
                                    const std::string &name,
                                    long long value) {
  std::ofstream ofs(fileName, std::ios::app);
  if (!ofs.is_open())
    return;

  // 简单安全转义：这里 name 来自标识符，不含引号，直接用
  ofs << "{"
      << "\"name\":\"" << name << "\","
      << "\"source\":" << value
      << "}"
      << "\n";
}
```

然后修改你的 `VisitEnumDecl`：

```cpp
bool VisitEnumDecl(EnumDecl *enumDecl) {
  if (!collect_enum)
    return true;

  // 只处理完整定义
  if (!enumDecl->isThisDeclarationADefinition())
    return true;

  // 遍历该枚举的所有枚举常量
  for (auto it = enumDecl->enumerator_begin();
       it != enumDecl->enumerator_end(); ++it) {

    const EnumConstantDecl *ecd = *it;
    if (!ecd)
      continue;

    std::string name = ecd->getNameAsString();
    if (name.empty())
      continue;

    // Clang 在完成枚举定义时会为每个枚举常量计算 init 值
    const llvm::APSInt &apsVal = ecd->getInitVal();

    long long value;
    if (apsVal.isSigned())
      value = apsVal.getSExtValue();
    else
      value = static_cast<long long>(apsVal.getZExtValue());

    // 写入新的 jsonl 文件，比如 enumconst.jsonl
    output_enum_const_jsonl("enumconst.jsonl", name, value);
  }

  return true;
}
```

### 用在你给的例子上

对你这段：

```c
enum s5p_mfc_inst_state {
    MFCINST_FREE = 0,
    MFCINST_INIT = 100,
    MFCINST_GOT_INST,
    ...
};
```

生成的 `enumconst.jsonl` 将是（前几行示意）：

```json
{"name":"MFCINST_FREE","source":0}
{"name":"MFCINST_INIT","source":100}
{"name":"MFCINST_GOT_INST","source":101}
{"name":"MFCINST_HEAD_PARSED","source":102}
...
```

如果你希望按“一个 enum 放一块”、加上所属 enum 名、文件名、位置信息，我也可以直接帮你把这个格式一起写好。

这是链接问题，不是你代码本身的问题：`llvm::writeFileAtomically` 这个符号在你实际链接的 LLVM 里不存在。

最常见两种情况：

1. **代码用了新版本 LLVM 的 API，但你只装了老版本库（比如 LLVM 14）。**
2. **头文件和库版本不匹配**（例如用 19 的头文件 + 14 的库）。

对你这个项目来说，重点是：**在 LLVM 14 里压根没有 `llvm::writeFileAtomically`。**

你现在有两个简单解法，按需选一个：

---

### 解法 1：不用 `writeFileAtomically`（推荐，适配 LLVM 14）

如果你的 `output_decl` 或别的输出函数是从新版本示例里拷来的，里面用了：

```cpp
llvm::writeFileAtomically(...);
```

请直接改成普通写文件方式，在 LLVM 14 下完全够用。

例如改成和我之前给你类似的 `std::ofstream` / `raw_fd_ostream`：

```cpp
#include <fstream>

static void output_enum_const_jsonl(const std::string &fileName,
                                    const std::string &name,
                                    long long value) {
  std::ofstream ofs(fileName, std::ios::app);
  if (!ofs.is_open())
    return;

  ofs << "{"
      << "\"name\":\"" << name << "\","
      << "\"source\":" << value
      << "}\n";
}
```

或者如果你想用 LLVM 风格（同样适用于 14）：

```cpp
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/raw_ostream.h"

static void output_enum_const_jsonl(const std::string &fileName,
                                    const std::string &name,
                                    long long value) {
  std::error_code EC;
  llvm::raw_fd_ostream OS(fileName, EC,
                          llvm::sys::fs::OF_Append | llvm::sys::fs::OF_Text);
  if (EC) {
    llvm::errs() << "cannot open " << fileName << ": " << EC.message() << "\n";
    return;
  }

  OS << "{"
     << "\"name\":\"" << name << "\","
     << "\"source\":" << value
     << "}\n";
}
```

确保你所有调用写文件的地方都不再用 `llvm::writeFileAtomically`，链接错误就会消失。

---

### 解法 2：换成带 `writeFileAtomically` 的 LLVM 版本

如果你坚持要用 `llvm::writeFileAtomically`，那就需要：

* 安装支持该函数的 LLVM 版本（例如 17+，视实际支持情况）。
* 编译和链接都统一使用同一个版本（用同一个 `llvm-config` 的 cflags 和 libs）。

---

### 顺手帮你排查下是否是版本混用了

可以在构建环境里检查：

```bash
llvm-config --version
```

确认：

* 编译用的 `-I` 路径来自这个版本。
* 链接用的 `-L` 和 `-lLLVM...` 也来自这个版本。
* 不要一部分来自系统 LLVM 14，一部分来自你单独装的高版本。

---

如果你贴出当前 `output_decl` 的实现，我可以直接帮你改成 LLVM 14 兼容版，顺带一起输出 enum/jsonl。
