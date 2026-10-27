"""Agent 循环：任务 -> LLM 决策 -> 工具执行 -> 观察结果 -> ... -> 最终回答。

经典 ReAct 式 function-calling 循环。所有工具异常已由注册表归一为文本，
循环只会因 max_steps 兜底退出，不会因某个工具崩溃而中断任务。
"""
import json

from elab_agent.tools.registry import REGISTRY, ToolRegistry

SYSTEM_PROMPT = """你是「电子信息工程工作台」的智能体助手，服务对象是电子信息专业的工程师/学生。

你可以调用工具完成实际工作，请遵守以下工作准则：
1. 涉及计算/仿真/绘图：先想清楚方案，用 write_file 写代码或直接用 matlab_run / python_run 执行；
   产生的图保存在 workspace 下（MATLAB 用 exportgraphics/saveas，Python 用 matplotlib 的 savefig）。
2. 涉及 Keil 工程：用 keil_build 编译，若报错则 read_file 看日志、修改源码后重编，直到 0 Error。
3. 涉及 STM32CubeMX：改配置类需求用 cubemx_open 让用户操作；纯重新生成代码用 cubemx_generate。
4. 报告类任务：先收集数据/图片，再用 word_make_report 生成 .docx，最后用 wps_open 打开给用户检查。
5. Proteus/Multisim 没有可编程接口：需要交互操作时用 proteus_open/multisim_open 打开并明确告诉用户接下来该点什么。
6. 所有文件读写都在 workspace 沙箱内；引用文件路径时给绝对路径方便用户查找。
7. 用中文回复；结论先行；给出关键数据；不确定的假设要明说。
"""


class Agent:
    def __init__(self, client, registry: ToolRegistry | None = None,
                 max_steps: int = 15, verbose: bool = True):
        self.client = client
        self.registry = registry or REGISTRY
        self.max_steps = max_steps
        self.verbose = verbose

    def _log(self, text: str) -> None:
        if self.verbose:
            print(text)

    def run(self, task: str, history: list[dict] | None = None) -> tuple[str, list[dict]]:
        messages: list[dict] = list(history) if history else [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.append({"role": "user", "content": task})

        for _step in range(self.max_steps):
            response = self.client.chat(messages, tools=self.registry.schemas())

            if not response.get("tool_calls"):
                content = response.get("content") or "(空回复)"
                messages.append({"role": "assistant", "content": content})
                return content, messages

            assistant_msg = {"role": "assistant", "content": response.get("content") or "",
                             "tool_calls": [
                                 {"id": tc["id"], "type": "function",
                                  "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                                 for tc in response["tool_calls"]
                             ]}
            messages.append(assistant_msg)

            for tc in response["tool_calls"]:
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                self._log(f"  => 调用工具 {tc['name']} 参数: {json.dumps(args, ensure_ascii=False)[:200]}")
                result = self.registry.call(tc["name"], args)
                self._log(f"  <= 结果: {result[:150].replace(chr(10), ' | ')}")
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

        fallback = f"已达最大步数（{self.max_steps}），任务未完成。请缩小任务范围或提高 agent.max_steps。"
        messages.append({"role": "assistant", "content": fallback})
        return fallback, messages
