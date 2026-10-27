"""工具注册表：LLM function calling 的本地执行层。

每个工具 = 名称 + 描述 + JSON Schema 参数 + Python 函数。
Agent 循环只依赖本注册表，因此新增工具 = 写一个带 @register 的函数，
LLM 侧自动获得对应 function 定义（这是整个项目最重要的扩展点）。
"""
from dataclasses import dataclass
import json
import traceback


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema: {"type":"object","properties":{...},"required":[...]}
    func: callable


class ToolRegistry:
    def __init__(self, output_limit: int = 8000):
        self._tools: dict[str, Tool] = {}
        self.output_limit = output_limit

    def register(self, name: str, description: str, parameters: dict):
        def deco(fn):
            if name in self._tools:
                raise ValueError(f"duplicate tool name: {name}")
            self._tools[name] = Tool(name, description, parameters, fn)
            return fn

        return deco

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name!r}, available: {sorted(self._tools)}")
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self) -> list[dict]:
        """OpenAI function-calling 格式（GLM/DeepSeek/Qwen 均兼容）。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    def call(self, name: str, args: dict | None) -> str:
        """执行工具并返回字符串结果；任何异常都归一为错误文本（让 LLM 能读到并自纠）。"""
        try:
            tool = self.get(name)
            arguments = args or {}
            result = tool.func(**arguments)
            text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)
        except KeyError as exc:
            text = f"[tool error] {exc}"
        except TypeError as exc:
            text = f"[tool error] 参数不匹配: {exc}"
        except Exception as exc:  # noqa: BLE001 - 工具崩溃不能打断 Agent 循环
            # 错误摘要放最前面：截断后 LLM 仍能看到真正的报错原因
            text = f"[tool error] {type(exc).__name__}: {exc}\n" + traceback.format_exc(limit=3)
        if len(text) > self.output_limit:
            text = text[: self.output_limit] + f"\n...(截断，原长 {len(text)} 字符)"
        return text


# 全局注册表：各工具模块导入它做注册；Agent 默认使用它
REGISTRY = ToolRegistry()
