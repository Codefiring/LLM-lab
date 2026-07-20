直接回答：下面给出一个可落地的设计与实现方案（含 UI 流程、后端 agent 调度、报告生成格式、关键 Kotlin 代码示例、Bazel / 测试/运行说明），并列出分步的 PR 实现任务。如果你愿意，我可以把第一版实现做成一个分支并提交到仓库 — 你只需回复 “请实现/开始提交”，我就开始创建分支并推送变更。

总览（要实现的功能）
- 在 VCS Log（log tree）上添加上下文菜单 / 工具栏按钮：当用户选中 1 个 commit 或 2 个 commit 时，显示 “启动代码分析 Agent”。
  - 选中 1 个 commit：agent 分析该 commit 的变更内容（或分析当天所有 commit 的汇总，按用户选择）。
  - 选中 2 个 commit：agent 比较两次提交的差异并生成对比分析报告。
- 启动后运行“Code Agent”作为后台任务（不阻塞 UI），agent 会：
  - 获取对应 commit 的文件列表与 diff（通过 IntelliJ Git API 或本地 git 调用）。
  - 对差异/变更文件做静态分析（例如：统计影响文件、重要改动、潜在风险点、样式/API 断裂、性能/线程危险点等）。
  - （可选）调用外部 LLM 服务生成“通俗易懂”的自然语言总结/建议。
- 生成报告（Markdown 或 HTML）并在新 Tool Window 或 Editor Tab 中展示，用户可以导出为 Markdown/HTML/PDF。

实现要点与架构
1. UI 层（Kotlin，IntelliJ Platform）
   - 新增 AnAction（比如: AnalyzeWithAgentAction），注册在 VCS Log 的 context menu / toolbar。
   - 根据 selection（1 或 2 commits）启用/禁用 action，并把选中的 commit ids 传递给后台服务。

2. 后台 Agent Runner
   - 实现一个后台任务类（继承 Task.Backgroundable 或 使用 ProgressManager.runBackgroundableTask）。
   - 任务步骤：
     - 从 VCS 接口读取 commit 内容或通过 GitCommand 获取 patch（更鲁棒）。
     - 解析 patch，收集变更文件、添加/删除/修改统计、函数/类重命名等（可借助开源 diff parser 或自写简单解析）。
     - 针对每个变更文件运行一系列分析器（静态检查、查找 TODO/FIXME、危险 API 使用、并发相关 API 使用等）。
     - 汇总结果，并（可选）调用 LLM 提炼成自然语言报告（要注意隐私/外发政策）。
   - 生成报告为 Markdown/HTML，并返回展示入口（临时文件或虚拟文件系统）。

3. 报告展示 & 导出
   - 新增 ToolWindow 或 打开编辑器 Tab 显示报告（可用 Markdown Viewer 或 JEditorPane 渲染 HTML）。
   - 提供按钮：导出为 Markdown、保存为 HTML/PDF、打开差异上下文。

4. 配置与权限
   - 在插件设置中可配置：LLM 服务 URL / API Key、分析深度选项、是否上传 code 到远程等。

关键实现细节（示例代码片段）
- 注意：下面的代码为示例骨架，展示主要调用点与流程；在具体提交前会根据仓库实际代码结构、package、依赖以及 Bazel target 做调整并确保能编译。

1) AnAction：从 VCS Log 获取选中 commit(s) 并触发后台任务
```kotlin
// name=AnalyzeWithAgentAction.kt
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.progress.Task
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.vcs.log.VcsLog
import com.intellij.vcs.log.impl.VcsProjectLog

class AnalyzeWithAgentAction : AnAction("Start Code Agent Analysis") {
    override fun actionPerformed(e: AnActionEvent) {
        val project: Project = e.project ?: return
        // 从 VCS Log 上获取当前选中的 commit IDs（示意）
        val log = VcsProjectLog.getInstance(project).log
        val selectedCommits = VcsLogSelectionHelper.getSelectedCommitIds(log) // TODO: implement helper
        if (selectedCommits.isEmpty()) {
            Messages.showInfoMessage(project, "请先在 Log 中选择 1 个或 2 个提交。", "没有选择提交")
            return
        }

        object : Task.Backgroundable(project, "Running Code Agent") {
            override fun run(indicator: ProgressIndicator) {
                indicator.text = "Preparing analysis..."
                val agent = CodeAgentRunner(project)
                val reportMarkdown = if (selectedCommits.size == 1) {
                    agent.analyzeSingleCommit(selectedCommits.first(), indicator)
                } else {
                    agent.compareCommits(selectedCommits[0], selectedCommits[1], indicator)
                }
                // 在 UI 线程展示
                com.intellij.openapi.application.ApplicationManager.getApplication().invokeLater {
                    ReportViewer.showReport(project, reportMarkdown)
                }
            }
        }.queue()
    }

    override fun update(e: AnActionEvent) {
        // 基于 selection 大小控制 enable/visible
        val project = e.project
        e.presentation.isEnabledAndVisible = project != null && VcsLogSelectionHelper.hasSelection(project)
    }
}
```

2) Agent Runner（核心分析流程骨架）
```kotlin
// name=CodeAgentRunner.kt
import com.intellij.openapi.project.Project
import com.intellij.openapi.progress.ProgressIndicator

class CodeAgentRunner(private val project: Project) {
    fun analyzeSingleCommit(commitHash: String, indicator: ProgressIndicator): String {
        indicator.text = "Fetching commit diff..."
        val diffText = GitUtils.getPatchForCommit(project, commitHash) // TODO: implement Git helper
        indicator.text = "Analyzing changes..."
        val analysis = AnalysisEngine.runAnalysisOnPatch(diffText)
        indicator.fraction = 0.9
        val report = ReportGenerator.generateForSingleCommit(commitHash, analysis)
        return report
    }

    fun compareCommits(oldHash: String, newHash: String, indicator: ProgressIndicator): String {
        indicator.text = "Computing diff between commits..."
        val diffText = GitUtils.getPatchBetweenCommits(project, oldHash, newHash)
        indicator.text = "Analyzing changes..."
        val analysis = AnalysisEngine.runAnalysisOnPatch(diffText)
        val report = ReportGenerator.generateForComparison(oldHash, newHash, analysis)
        return report
    }
}
```

3) 报告生成器（Markdown 输出示例）
```kotlin
// name=ReportGenerator.kt
object ReportGenerator {
    fun generateForSingleCommit(commitHash: String, analysis: AnalysisResult): String {
        val sb = StringBuilder()
        sb.append("# Commit Analysis: $commitHash\n\n")
        sb.append("## Summary\n")
        sb.append(analysis.summary).append("\n\n")
        sb.append("## Files changed\n")
        analysis.files.forEach { f ->
            sb.append("- `${f.path}` — ${f.changeType} (${f.linesAdded} added, ${f.linesRemoved} removed)\n")
        }
        sb.append("\n## Findings\n")
        analysis.findings.forEach { finding ->
            sb.append("- ${finding.severity}: ${finding.title}\n  - ${finding.description}\n")
        }
        return sb.toString()
    }

    fun generateForComparison(old: String, new: String, analysis: AnalysisResult): String {
        // 类似结构，强调差异点和升级/兼容性问题
        TODO()
    }
}
```

辅助组件（概念说明）
- GitUtils: 封装 git 命令或调用 IntelliJ Git API，返回 patch 文本或文件列表。
- AnalysisEngine: 一组分析器（插件内实现），例如：
  - DiffParser -> 构建改动 AST / 文件列表
  - StaticCheckers -> TODO 查找、可能的 null-safety 问题、API 变化检测
  - HeuristicRules -> 检测高风险修改（并发、IO、缓存、权限变更）
  - (可选) LLMConnector -> 将结构化分析结果发送给 LLM 生成通俗语言摘要（需配置 API Key）
- ReportViewer: 在 IDE 中创建 EditorTab 或 ToolWindow 显示生成的 Markdown/HTML，并提供导出按钮。

Bazel / BUILD 调整（高层）
- 在相应 plugin 模块下新增源文件并更新 BUILD.bazel（或自动由 .iml 生成）。例如在 module git-client-plugin:
  - 增加 target //plugins/git-client:agent-analyzer (java/kotlin_plugin_library)
- 更新 plugin.xml 注册 action（plugin 元数据）：
  - 在 plugin.xml 添加 action 节点，绑定到 Vcs Log 的 group（例如 VcsLogPopupGroup 或 commit context menu）。

测试 & 验证
- 单元测试：对 AnalysisEngine 的规则写单元测试（小样例 patch -> 期望 findings）。
- 集成测试：在 Dev IDE 中运行插件，打开 VCS Log，选择 commit，触发 action，验证报告显示。
- 运行命令（仓库根目录）：
  - Bazel 构建: bazel build //plugins/git-client:agent-analyzer
  - 运行插件/IDE: 使用现有项目提供的 run configurations（或使用 gradle/IDE run configs）

隐私与安全注意
- 如果使用 LLM（外部服务）处理代码，请明确告知用户并提供开关，避免将敏感代码外泄。
- 依赖网络的步骤应可被禁用并提供本地-only 模式（只做静态规则分析）。

分步实现建议（优先级）
1. PR-1（基础骨架）
   - 新增 AnAction（context menu）与 plugin.xml 注册
   - 实现 CodeAgentRunner skeleton、GitUtils stub
   - 实现 ReportViewer（用于展示 Markdown）
   - Bazel BUILD target & 小的 smoke tests
2. PR-2（分析引擎）
   - 实现 DiffParser、基础静态规则（lines added/removed、TODO、文件类型统计）
   - 单元测试
3. PR-3（增强）
   - 支持比较两个 commit、更多规则（并发/资源泄露 heuristics）
   - 可选 LLM 接入（配置界面 + API 密钥安全存储）
4. PR-4（UX & 导出）
   - 添加导出、设置面板、错误/进度提示优化

我接下来可以做什么（请选择）
- 我现在给你做设计文档/详细接口定义（包括 class diagram、BUILD 变更）并贴到这里（无需对仓库提交）。
- 我可以直接在 DetachHead/rebased 仓库创建一个 feature 分支并提交 PR-1（基础骨架：action + runner + viewer）。如果同意，请回复“开始实现 PR-1”，我会：
  - 创建分支 feature/code-agent
  - 添加代码骨架和 BUILD 变更
  - 推送并把 PR 链接返回给你
- 或者：先由你告诉我你更偏向哪种报告格式（Markdown or HTML）及是否允许调用外部 LLM 服务，我再开始实现。

下一个建议的步骤（如果你想我动手实现）
- 回答两点：
  1. 允许我在仓库创建分支并提交初始实现吗？（是/否）
  2. 报告是否需要支持外部 LLM（是/否）？（如“是”，请提供/说明 API 要求与隐私偏好）
  
我已经准备好把 PR-1 的骨架实现并提交 — 你同意我现在开始在 DetachHead/rebased 上创建分支并提交吗？