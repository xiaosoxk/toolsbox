"""OpenAI 兼容 LLM 客户端（httpx 直连，不依赖 openai SDK）。

兼容：智谱 GLM / DeepSeek / 通义 Qwen / Kimi / 本地 Ollama——
只要 base_url 支持 POST /chat/completions + function calling 即可。
返回值做了一层归一化：{"content": str|None, "tool_calls": [...]|None}，
让 Agent 循环与测试不用关心各厂商的字段差异。
"""
import httpx


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, api_base: str, api_key: str, model: str,
                 temperature: float = 0.3, timeout: int = 180):
        if not api_key:
            raise LLMError(
                "缺少 API key：请先设置环境变量 ELAB_API_KEY"
                "（或在 config.yaml 的 llm.api_key 填写，但不推荐入库）"
            )
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        body: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            body["tools"] = tools
        try:
            resp = httpx.post(
                f"{self.api_base}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"请求失败（检查网络/代理/api_base）: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"响应格式异常: {str(data)[:500]}") from exc

        tool_calls = None
        if message.get("tool_calls"):
            tool_calls = [
                {
                    "id": tc.get("id", f"call_{i}"),
                    "name": tc["function"]["name"],
                    "arguments": tc["function"].get("arguments") or "{}",
                }
                for i, tc in enumerate(message["tool_calls"])
            ]
        return {"content": message.get("content"), "tool_calls": tool_calls}
