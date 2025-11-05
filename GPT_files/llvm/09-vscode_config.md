下面是一套在 **VS Code 通过 Remote-SSH 调试 Linux 服务器上、由 Makefile 管理的 C++ 工程**的实操配置（一次到位，能跑能断点）。

---

# 1) 准备工作

1. 本机 VS Code 安装扩展

   * **Remote – SSH**
   * **C/C++**（ms-vscode.cpptools）

2. 服务器上需要的工具（示例为 Debian/Ubuntu）

   ```bash
   sudo apt-get update
   sudo apt-get install -y build-essential gdb make
   ```

   > 其他发行版用对应包管理器即可（如 `dnf`, `yum`, `pacman`）。

3. 用 Remote-SSH 连接服务器，在 VS Code 里 **打开远程工程根目录**。

---

# 2) Makefile：确保可调试

在你的 Makefile 中，保证编译带有调试符号且别被强优化“抹掉”断点：

```makefile
# 常见写法：DEBUG=1 时打开 -g 和 O0
ifeq ($(DEBUG),1)
  CXXFLAGS += -g -O0 -Wall -Wextra
else
  CXXFLAGS += -O2 -Wall -Wextra
endif

# 可选：统一把目标产物放到固定位置，便于 VSCode 写 program 路径
BINDIR ?= build
TARGET ?= app
$(BINDIR)/$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDFLAGS)
```

> 之后调试用 `make DEBUG=1` 就行，产物例如在 `build/app`。

---

# 3) VS Code 任务与调试配置

在工程根目录新建 `.vscode/` 目录，并添加两个文件。

## `.vscode/tasks.json`（构建/清理）

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "make debug",
      "type": "shell",
      "command": "make DEBUG=1",
      "group": "build",
      "problemMatcher": "$gcc"
    },
    {
      "label": "make clean",
      "type": "shell",
      "command": "make clean",
      "problemMatcher": []
    }
  ]
}
```

* `problemMatcher: "$gcc"` 让编译错误在 VS Code 的 “Problems” 面板里可点击跳转。

## `.vscode/launch.json`（启动 gdb 调试）

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "(gdb) Launch",
      "type": "cppdbg",
      "request": "launch",
      "program": "${workspaceFolder}/build/app",  // 改成你的可执行文件
      "args": [],                                  // 程序参数（需要就填）
      "stopAtEntry": false,
      "cwd": "${workspaceFolder}",
      "environment": [],
      "externalConsole": false,
      "MIMode": "gdb",
      "miDebuggerPath": "/usr/bin/gdb",
      "setupCommands": [
        { "text": "-enable-pretty-printing" }      // 开启 STL 等类型美化
      ],
      "preLaunchTask": "make debug"                // 调试前先编译
    }
  ]
}
```

> 你只需把 `program` 指向你通过 make 生成的可执行文件路径即可。

---

# 4) 多目标/多可执行文件的写法（可选）

如果一个工程有多个可执行文件，可以在 `launch.json` 里做一个输入选项：

```json
{
  "version": "0.2.0",
  "inputs": [
    {
      "id": "binName",
      "type": "pickString",
      "description": "选择要调试的可执行文件",
      "options": ["app", "tool", "server"]
    }
  ],
  "configurations": [
    {
      "name": "(gdb) Launch picked",
      "type": "cppdbg",
      "request": "launch",
      "program": "${workspaceFolder}/build/${input:binName}",
      "cwd": "${workspaceFolder}",
      "MIMode": "gdb",
      "miDebuggerPath": "/usr/bin/gdb",
      "preLaunchTask": "make debug",
      "setupCommands": [{ "text": "-enable-pretty-printing" }]
    }
  ]
}
```

---

# 5) 开始调试

1. 在代码里打断点。
2. 选择 `(gdb) Launch` 配置，直接 **F5**。
3. 变量、Watch、Call Stack、内存、寄存器、线程 等面板可直接用。

---

# 6) 进阶：附加到已运行的进程（attach）

如果程序已在服务器上跑着（或你想用命令行自行启动），可以 “附加”：

```json
{
  "name": "(gdb) Attach",
  "type": "cppdbg",
  "request": "attach",
  "program": "${workspaceFolder}/build/app",  // 可执行文件路径仍需正确
  "processId": "${command:pickProcess}",      // VS Code 弹出进程列表供选择
  "MIMode": "gdb",
  "miDebuggerPath": "/usr/bin/gdb"
}
```

> 如果进程是用 `sudo` 起的，最省事做法是在终端里用 `sudo` 启动它，然后用上面配置 **以 root 身份**的 VS Code 远程窗口附加（或在终端 `sudo gdb -p <pid>`）。直接让调试器“带 sudo”启动往往更麻烦。

---

# 7) 常见问题速查

* **断点灰色 / 不会命中**：

  1. 没有 `-g` 或被 `-O2` 优化过猛；
  2. `program` 指向了旧的/不同的二进制；
  3. 源码行与二进制不匹配（重新全量构建：`make clean && make DEBUG=1`）。

* **路径相关（源文件找不到）**：
  通过 Remote-SSH 打开的是服务器上的工程，VS Code Server 与 gdb 都在远端运行，**无需**做路径映射（`sourceFileMap` 通常用不到）。

* **动态库调试**：
  库也要带 `-g` 编译；运行时确保 `LD_LIBRARY_PATH` 或 rpath 正确，否则断不进库代码。

* **Core dump**：

  ```
  ulimit -c unlimited
  ./build/app ...
  gdb ./build/app core
  ```

  VS Code 里也可用 `cppdbg` 的 core 调试（`request: "launch", coreDumpPath: "core路径"`）。

---

# 8) 最小可用清单（你可以直接拷到工程里）

* Makefile：支持 `DEBUG=1`，产物到 `build/app`
* `.vscode/tasks.json`：如上
* `.vscode/launch.json`：如上（把 `program` 改成你的二进制）

---

需要我帮你把这两份 JSON 按你的工程结构改好吗？告诉我可执行文件实际路径（或 Makefile 的目标名），以及是否有程序参数/环境变量，我直接给你定制版本。
