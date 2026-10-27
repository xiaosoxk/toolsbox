"""Agent 循环测试：用假 LLM 驱动完整的 决策->工具->观察->回答 流程。"""
import json

from elab_agent.agent import Agent
from elab_agent.tools.registry import ToolRegistry


class FakeLLM:
    """按剧本依次返回响应；记录每次收到的 messages 供断言。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[list[dict]] = []

    def chat(self, messages, tools=None):
        # 拷贝快照：Agent 会在调用后继续向同一列表追加消息
        self.calls.append([dict(m) for m in messages])
        return self.script.pop(0)


def make_registry():
    reg = ToolRegistry()

    @reg.register("py_echo", "回声", {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    })
    def py_echo(text: str) -> str:
        return f"PY:{text}"

    return reg


def test_two_step_tool_loop():
    script = [
        {"content": None, "tool_calls": [
            {"id": "call_1", "name": "py_echo", "arguments": json.dumps({"text": "hello"})}
        ]},
        {"content": "计算完成，结果是 hello", "tool_calls": None},
    ]
    llm = FakeLLM(script)
    agent = Agent(client=llm, registry=make_registry(), verbose=False)
    answer, history = agent.run("跑一下 echo")

    assert answer == "计算完成，结果是 hello"
    # messages 结构：system + user + assistant(tool_calls) + tool + assistant(final)
    roles = [m["role"] for m in history]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]
    tool_msg = history[3]
    assert tool_msg["tool_call_id"] == "call_1"
    assert "PY:hello" in tool_msg["content"]


def test_history_is_reusable_for_followup():
    llm = FakeLLM([
        {"content": "好的", "tool_calls": None},
    ])
    agent = Agent(client=llm, registry=make_registry(), verbose=False)
    _, history = agent.run("第一句", history=[
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "旧话"},
        {"role": "assistant", "content": "旧答"},
    ])
    # 第二轮的输入应包含全部历史 + 新任务
    assert llm.calls[0][0]["content"] == "sys"
    assert llm.calls[0][-1]["content"] == "第一句"
    assert history[-1]["content"] == "好的"


def test_max_steps_guard():
    endless = {"content": None, "tool_calls": [
        {"id": "x", "name": "py_echo", "arguments": "{}"}
    ]}
    llm = FakeLLM([endless] * 10)
    agent = Agent(client=llm, registry=make_registry(), max_steps=3, verbose=False)
    answer, _ = agent.run("永远跑不完的任务")
    assert "最大步数" in answer


def test_bad_json_arguments_do_not_crash():
    script = [
        {"content": None, "tool_calls": [
            {"id": "c", "name": "py_echo", "arguments": "{not valid json"}
        ]},
        {"content": "已处理异常参数", "tool_calls": None},
    ]
    agent = Agent(client=FakeLLM(script), registry=make_registry(), verbose=False)
    answer, _ = agent.run("参数是坏的")
    assert answer == "已处理异常参数"
