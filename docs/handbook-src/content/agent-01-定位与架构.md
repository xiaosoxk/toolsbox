# 第1章 项目定位与架构

## 1.1 三十秒电梯陈述（背下来）

elab-agent 是一个本地工具调用型智能体：我把电子信息工程师日常工作里最耗时的八类外部工具——MATLAB 仿真、Python 分析、Word 报告、Keil 编译、STM32CubeMX 代码生成、Proteus/Multisim 电路仿真、WPS 文档——各自封装成带 JSON Schema 描述的 Python 函数，注册进一个统一的工具注册表；再实现一个 ReAct 式 function calling 循环，让大模型自主决定"先算什么、再画什么、最后怎么写进报告"，工具的报错会归一化成文本回喂给模型自我纠正，直到任务完成或达到步数上限。全项目零框架依赖（不引 LangChain），路径全部针对本机实测配置，配套 15 个 pytest 用例。

一句话总结定位：把"人开五个软件来回切"变成"一句话，Agent 自己编排"。

> 追问：这和 shell 脚本有什么区别？答：脚本是写死的流程，Agent 是按任务语义动态编排——同一个"写实验报告"能力，数据源、图表数量、章节结构都可以在运行时由模型决定；而且工具报错后模型能读日志自纠（比如 Keil 编译报错自动改代码重编），这是静态脚本做不到的。

## 1.2 需求从哪来（真实痛点）

电子信息专业的工作流有个鲜明特征：工具多而割裂。一个实验做完，要开 MATLAB 算数据画图、开 Keil 改代码编译、开 CubeMX 重新生成外设代码、开 Proteus 仿真验证，最后把截图和数据手动贴进 Word 报告。这些步骤彼此独立、重复性高，但每个软件的接口形态完全不同：MATLAB 有命令行、Keil 有命令行、CubeMX 有脚本模式、Proteus 干脆没有接口。

这个项目要解决的不是"接入某个软件"，而是两件事：第一，用统一的抽象（工具注册表）抹平八种异构接口；第二，用 Agent 循环把"编排权"交给模型。这也是面试时讲项目价值的两个支点。

## 1.3 为什么不用 LangChain（必问，重点准备）

> 追问：市面上有 LangChain / AutoGen / CrewAI，为什么自己写？

三条理由，按说服力排序：

1. **可控性与可调试性**：Agent 循环本体只有约 60 行（agent.py），消息序列、步数、截断策略全部显式可见；出问题时我能直接 print 整个 messages 数组定位。LangChain 的 AgentExecutor 是黑盒，改一个截断策略要翻它源码。
2. **依赖哲学**：这个项目唯一的外部依赖是 httpx/pyyaml/python-docx 三个稳定库。LangChain 版本迭代快、抽象层多，工具调用的字段格式跟着它版本走，与其适配它不如直接适配 OpenAI 兼容协议本身。
3. **学习目的与面试立场**：自研才能讲清 function calling 的字节级细节（消息结构、tool_call_id 配对、参数 JSON 解析容错）。用框架的人讲不出这些。

同时要诚实说边界（面试加分）：如果需要多 Agent 协作、复杂记忆管理、RAG 检索，自研成本会迅速上升，那时引入框架或 MCP 生态是合理选择。

## 1.4 架构总览

```
                ┌──────────────────── elab-agent ─────────────────────────┐
用户 ─任务─>  │  Agent 循环： LLM 决策 → 执行工具 → 观察结果 → … → 最终回答 │
                │     ↑                      │                             │
                │  LLMClient(OpenAI兼容)  ToolRegistry(JSON Schema 注册表)  │
                │  GLM/DeepSeek/Ollama       │                             │
                └────────────────────────────┼─────────────────────────────┘
            ┌─────────┬─────────┬────────────┼──────────┬──────────┬─────────┐
        matlab_run python_run word_*    keil_build  cubemx_*  *_open 启动器  files 沙箱
            │          │        │           │           │          │            │
        matlab.exe  子进程   python-docx  UV4 -b    CubeMX -q   Popen 分离   workspace/
```

关键分层：**LLM 层**（llm.py，只管协议）与 **工具层**（tools/，只管执行）完全解耦，中间靠 **注册表**（registry.py，100 行）连接。这带来两个工程收益：没有 API key 时工具层可以当纯函数库用（doctor/report 命令零 LLM 依赖）；换厂商只改 config.yaml 一行。

## 1.5 一次任务的完整时序（面试时在白纸上画这个）

以"用 MATLAB 算正弦数据并写进 Word 报告"为例，messages 数组的演化：

```
[system]   工作台系统提示词（工具用法+工作区规则）
[user]     任务描述
[assistant tool_calls=[{id:call_1, name:"matlab_run", args:{code:...}}]]
[tool      call_1 的结果文本（图已保存路径）]        ← 注册表执行后回填
[assistant tool_calls=[{id:call_2, name:"word_make_report", args:{...image:上一步路径}}]]
[tool      call_2 结果 "saved: .../report.docx"]
[assistant "报告已生成，路径 …，tau 测量值 1.003ms"]   ← 无 tool_calls，循环终止
```

三条循环终止条件：模型不再发起 tool_calls（正常结束）、达到 max_steps（兜底，防止模型无限重试）、客户端异常上抛。这套消息结构是 OpenAI function calling 的标准协议，GLM/DeepSeek 全兼容——这也是"兼容层"只归一化两个字段（content、tool_calls）就能通吃各厂商的原因。

## 1.6 技术栈清单（如实回答"用了什么"）

| 组件 | 选型 | 一句话理由 |
|---|---|---|
| 语言 | Python 3.11 | 生态与所有工具链原生 |
| LLM 协议 | OpenAI 兼容 /chat/completions | 国内外厂商通吃，一行配置切换 |
| HTTP | httpx | 无 SDK 依赖，超时/异常可控 |
| 配置 | pyyaml + 环境变量 | 密钥不落盘 |
| Word | python-docx | 纯库生成 .docx，WPS/Office 双开 |
| 进程 | subprocess | 每个外部工具一个受控子进程 |
| 测试 | pytest + FakeLLM 注入 | 不启动任何外部软件，秒级跑完 |