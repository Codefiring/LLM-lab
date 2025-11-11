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
