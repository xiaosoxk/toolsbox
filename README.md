# elab-agent —— 电子信息工程工作台智能体

一个**真实可用**的本地 Agent：把 MATLAB、Python、Word(WPS)、Keil、Proteus、Multisim、
STM32CubeMX 封装成 LLM 工具，用一条命令让大模型自主编排你的日常工程流程——
算仿真、出图、编译报错自动修、生成实验报告、打开对应软件接手人工操作。

所有软件路径均为本机实测填写（`config.yaml`），`python cli.py doctor` 一键体检。

## 30 秒上手

```bash
cd elab-agent
pip install -r requirements.txt

python cli.py doctor              # ① 体检：8 个工具是否就位（不需要 API key）
python cli.py report              # ② 离线演示：自动生成实验报告 .docx 并用 WPS 打开

setx ELAB_API_KEY "sk-xxx"        # ③ 想用 LLM 自主编排时才需要（重开终端生效）
python cli.py task "用MATLAB仿真RC阶跃响应并生成Word实验报告"
python cli.py chat                # 交互式对话（/tools 看工具，/exit 退出）
```

## 能干什么（按真实工作流）

| 场景 | 对 Agent 说 | 它会怎么做 |
|---|---|---|
| 实验报告流水线 | "仿真 RC 阶跃响应，出图，写实验报告" | `matlab_run` 算+存图 → `word_make_report` 生成 .docx → `wps_open` 打开 |
| STM32 开发 | "把工程里的串口波特率改成 115200 后重新编译" | `write_file` 改源码 → `keil_build` 编译 → 有 Error 自动改再编，直到 0 Error |
| CubeMX 重新生成 | "我改了 .ioc，重新生成代码" | `cubemx_generate` 无头调 `STM32CubeMX -q`，不开 GUI |
| 电路仿真 | "打开我的 Proteus 工程准备仿真" | `proteus_open` 载入 .pdsprj，告诉你接下来人工点哪步（Proteus 无编程接口） |
| 数据处理 | "把 CSV 里的幅频响应数据画成波特图" | `python_run`/`matlab_run` 计算绘图 → PNG 落在工作区 |

**设计哲学**：能无头自动化的（MATLAB/Keil/CubeMX/Python/Word）全部自动；必须人机交互的
（Proteus/Multisim/CubeMX 图形配置）由 Agent 打开软件并给出操作指引——不假装能做做不到的事。

## 架构

```
                ┌──────────────────────── elab-agent ────────────────────────┐
 你 ──任务──> │  Agent 循环：  LLM 决策 → 工具调用 → 观察结果 → … → 最终回答   │
                │      ↑                    │                                │
                │   LLM(OpenAI兼容)     ToolRegistry（JSON Schema 自动生成）    │
                │   GLM/DeepSeek/Qwen       │                                │
                └───────────────────────────┼────────────────────────────────┘
             ┌──────────┬──────────┬────────┼─────────┬─────────┬──────────┐
          matlab_run python_run word_*  keil_build cubemx_* proteus_open multisim_open wps_open
             │           │         │        │          │         │            │          │
        matlab.exe  子进程沙箱  python-docx  UV4 -b   CubeMX -q  PDS.EXE   multisim.exe  WPS
          E:\ma\bin              (docx读写)  D:\Keil_v5  D:\stm32cube  ...     E:\mu13   ...
```

## 工具清单（注册后 LLM 自动可见）

| 工具 | 说明 | 无头/交互 |
|---|---|---|
| `matlab_run` | 写 .m 脚本 → `matlab -batch` 执行，返回 stdout | 无头 |
| `python_run` | 子进程执行 Python 代码（隔离+超时） | 无头 |
| `word_make_report` / `word_read_docx` | 生成/读取 .docx 报告（含图、表） | 无头 |
| `keil_build` | `UV4 -b` 编译工程，解析 Error/Warning 行 | 无头 |
| `cubemx_generate` | `CubeMX -q` 脚本模式重新生成 HAL 代码 | 无头 |
| `write_file` / `read_file` / `list_files` | workspace 沙箱内文件读写（防路径逃逸） | 无头 |
| `proteus_open` / `multisim_open` / `pycharm_open` / `wps_open` / `cubemx_open` | 启动 GUI 软件并可选载入文件 | 交互 |

## 接入 LLM

`config.yaml` 的 `llm.api_base` 换一行即可切换厂商（均为 OpenAI 兼容协议）：

| 厂商 | api_base | 常用 model |
|---|---|---|
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | glm-4-flash（免费）/ glm-4-plus |
| DeepSeek | `https://api.deepseek.com/v1` | deepseek-chat |
| 本地 Ollama | `http://127.0.0.1:11434/v1` | qwen2.5:14b 等 |

密钥放环境变量 `ELAB_API_KEY`（PowerShell: `setx ELAB_API_KEY "sk-xxx"`）。
**没有 key 也不影响 doctor / report / 全部工具**——工具层与 LLM 层完全解耦，可以直接
在自己的代码里 `REGISTRY.call("matlab_run", {...})` 把它当工具库用。

## 扩展一个新工具只要 8 行

```python
# elab_agent/tools/my_tool.py
from elab_agent.tools.registry import REGISTRY

@REGISTRY.register("ltspice_run", "运行 LTspice 仿真并返回波形数据摘要", {
    "type": "object",
    "properties": {"netlist": {"type": "string", "description": ".asc/.cir 路径"}},
    "required": ["netlist"],
})
def ltspice_run(netlist: str) -> str:
    ...  # subprocess 调你的仿真器
```
然后在 `tools/__init__.py` 里 `from elab_agent.tools import my_tool` 加一行，LLM 立即可用。

## 项目结构

```
elab-agent/
├── cli.py                 # doctor / task / chat / report 四个入口
├── config.yaml            # 本机软件路径 + LLM 配置（全部实测填写）
├── elab_agent/
│   ├── agent.py           # ReAct 式工具调用循环（max_steps 兜底）
│   ├── llm.py             # OpenAI 兼容客户端（httpx，无 SDK 依赖）
│   ├── config.py          # yaml 配置 + 环境变量覆盖
│   └── tools/
│       ├── registry.py    # 注册表：Schema 生成 / 异常归一 / 输出截断
│       ├── matlab_tool.py / python_tool.py / word_tool.py
│       ├── keil_tool.py / cubemx_tool.py / launcher.py / files.py
├── tests/                 # 21 个用例：注册表 / Agent循环(假LLM) / Word / 沙箱
└── workspace/             # Agent 的沙箱：脚本、图片、报告、日志都落在这里
```

## 测试

```bash
python -m pytest -v        # 不启动任何外部软件，全部秒级完成
```

覆盖：注册表 Schema/异常归一/截断、Agent 循环（两步工具调用/历史复用/最大步数兜底/
坏参数容错）、Word 生成与回读/缺图容错、文件沙箱逃逸防护。

## 已知边界（诚实声明）

- MATLAB 首次启动 20~60 秒（license + JVM），是 -batch 模式的固有开销；
- Proteus/Multisim 无官方命令行接口，只能启动+载文件，仿真操作需人工；
- CubeMX 首次为新芯片家族生成代码可能要联网下载固件包；
- Keil 编译要求 .uvprojx 里 Target 配置完整（头文件路径等），Agent 修不了工程配置类问题，
  会把日志原样给你。
