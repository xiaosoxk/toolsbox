"""工具注册表测试：注册/查询/Schema 生成/调用与异常归一。"""
import pytest

from elab_agent.tools.registry import ToolRegistry


@pytest.fixture
def registry():
    reg = ToolRegistry(output_limit=200)

    @reg.register("echo", "原样返回文本", {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    })
    def echo(text: str) -> str:
        return f"echo:{text}"

    @reg.register("boom", "总是抛异常", {"type": "object", "properties": {}, "required": []})
    def boom() -> str:
        raise RuntimeError("exploded")

    return reg


def test_register_and_get(registry):
    tool = registry.get("echo")
    assert tool.name == "echo"
    assert registry.names() == ["boom", "echo"]
    with pytest.raises(KeyError):
        registry.get("nope")


def test_schemas_openai_format(registry):
    schemas = registry.schemas()
    assert schemas[0]["type"] == "function"
    fn = schemas[0]["function"]
    assert fn["name"] in ("echo", "boom")
    assert fn["parameters"]["type"] == "object"


def test_call_success_and_error_normalization(registry):
    assert registry.call("echo", {"text": "hi"}) == "echo:hi"
    result = registry.call("boom", {})
    assert result.startswith("[tool error]")
    assert "exploded" in result  # 异常信息可见，LLM 才能自纠


def test_call_missing_args_becomes_error_text(registry):
    assert registry.call("echo", {}).startswith("[tool error]")


def test_output_truncated(registry):
    @registry.register("long", "长输出", {"type": "object", "properties": {}, "required": []})
    def long() -> str:
        return "x" * 1000

    result = registry.call("long", {})
    assert len(result) < 300 and "截断" in result
