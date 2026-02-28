我想要基于这个库开发一个 mcp scan 的框架

由于他的前端代码没有开源，所以我的思路是把里面的 mcp-scan 部分单独拿出来进行二次开发。

我的要求是在这个基础上有如下一些已经确定的开发任务。

对于 Detection,
1.需要添加检测漏洞类型的prompt，目标是mcp安全的top25个类型。现阶段只有Tool posioning和rug pull的检测prompt。
2.添加Prompt的检测，当前扫描只有tool和静态resource的检测
3.添加mcp中template对应的resource检测，当前只有静态resource的检测
4.修改所有中文文本为英文，包括prompt。同时对新prompt造成的结果影响进行重新实验和调整。

对于 Function
1. 需要实现新的 UI 显示。当前库的 UI 不开源,因此需要开发。当前计划开发日志显示的UI界面。
2. 日志的存储功能，此部分也没有开源需要开发。
3. 批量扫描功能，当前只能一次进行一个mcp服务器的扫描。
4. 结果评价系统，当前在benchmark中mcp server扫描出的结果需要人工评估，计划使用llm进行打分来评估。

请你基于这个库中 mcp-scan 部分的代码。

基于上面给出的确定性任务，以及你也可以扩展一些新的任务。基于此帮我写一个 work scope 的报告文档。