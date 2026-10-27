# 第2章 核心模块逐段精讲

## 2.1 工具注册表：整个项目的"协议层"

注册表只有 100 行，但承担四个职责：注册（name→函数）、Schema 生成（给 LLM 的"函数说明书"）、调用分发、结果治理。先看数据结构：

```python
@dataclass
class Tool:
    name: str
    description: str
    parameters: dict   # JSON Schema: {"type":"object","properties":...,"required":[...]}
    func: callable

class ToolRegistry:
    def register(self, name, description, parameters):
        def deco(fn):
            self._tools[name] = Tool(name, description, parameters, fn)
            return fn
        return deco

    def schemas(self) -> list[dict]:
        return [{"type": "function",
                 "function": {"name": t.name, "description": t.description,
                              "parameters": t.parameters}}
                for t in self._tools.values()]
```

原理要点：JSON Schema 里的 description 不是注释，而是模型选择工具与填参数的唯一依据——写"把文本写入工作区文件（也用于生成 .m/.py 脚本后再执行）"比写"写文件"的调用准确率高得多。工具描述本质是一种 prompt engineering，这是使用 LLM 的工程共识。

### 结果治理：异常归一与输出截断（两个容易讲深的细节）

```python
def call(self, name, args):
    try:
        result = tool.func(**arguments)
        ...
    except Exception as exc:
        # 错误摘要放最前面：截断后 LLM 仍能看到真正的报错原因
        text = f"[tool error] {type(exc).__name__}: {exc}\n" + traceback.format_exc(limit=3)
    if len(text) > self.output_limit:
        text = text[: self.output_limit] + "\n...(截断)"
    return text
```

设计决策一：工具崩溃绝不能打断 Agent 循环，异常转成文本喂回模型，让它自己决定重试、换参数还是放弃——这是 ReAct 模式自纠能力的来源。设计决策二：traceback 的最后一行才是真正的错误，但截断是从头截，所以把"异常类型+消息"提到第一行，否则截断后模型只看到一堆文件路径。这个细节是实测后改出来的（单元测试 test_call_success_and_error_normalization 锁定该行为）。

> 追问：为什么不让工具直接抛异常终止任务？答：外部工具的失败是常态（编译报错、文件不存在），多数可以通过修改输入自愈；终止是把"可自愈问题"升级成"人工介入"，得不偿失。真正的终止条件由循环层控制（max_steps）。

## 2.2 Agent 循环：60 行的 ReAct

```python
for _step in range(self.max_steps):
    response = self.client.chat(messages, tools=self.registry.schemas())
    if not response.get("tool_calls"):
        content = response.get("content") or "(空回复)"
        messages.append({"role": "assistant", "content": content})
        return content, messages          # 终止：模型给出最终回答

    messages.append(assistant_msg_with_tool_calls)     # 必须先回填 assistant 消息
    for tc in response["tool_calls"]:
        try:
            args = json.loads(tc["arguments"]) if tc["arguments"] else {}
        except json.JSONDecodeError:
            args = {}                     # 坏参数容错：不崩，交给工具层报参数错误
        result = self.registry.call(tc["name"], args)
        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
```

三个协议细节（面试官若懂 LLM 会追问）：

1. **tool_call_id 必须严格配对**：assistant 消息里声明了哪些 tool_call，后面就必须有等量同 id 的 role=tool 消息，否则厂商 API 直接 400。
2. **参数是 JSON 字符串不是对象**：协议里 arguments 是字符串，解析失败不能崩——容错成空参数，让注册表返回"参数不匹配"错误文本，模型下一轮会修正。
3. **max_steps 是唯一安全阀**：模型可能陷入"重试-失败-重试"循环（比如一直读一个不存在的文件），步数上限保证任务必然终止，超限时明确告知用户缩小范围。

可测试性设计：Agent 的 client 和 registry 都是构造参数注入。测试里用一个 FakeLLM（按剧本返回预设响应）就能驱动完整循环，15 个测试用例不启动 MATLAB、不碰网络，秒级完成——这是"依赖注入让副作用可替换"的直接体现。

## 2.3 LLM 客户端：一层归一化通吃各厂商

```python
resp = httpx.post(f"{self.api_base}/chat/completions",
                  json=body, headers={"Authorization": f"Bearer {self.api_key}"},
                  timeout=self.timeout)
message = resp.json()["choices"][0]["message"]
tool_calls = [{"id": tc.get("id", f"call_{i}"),
               "name": tc["function"]["name"],
               "arguments": tc["function"].get("arguments") or "{}"}
              for i, tc in enumerate(message.get("tool_calls") or [])]
return {"content": message.get("content"), "tool_calls": tool_calls}
```

只归一化两个字段，Agent 循环就完全不感知厂商差异（GLM 偶尔缺 tool_call id，这里补上）。错误分两类处理：httpx.HTTPError（网络/超时）给"检查网络与 api_base"的操作性提示；非 200 直接带响应体前 500 字符上抛——密钥错误和模型名错误必须让用户第一眼看到原文。

> 追问：为什么不用 openai 官方 SDK？答：SDK 会绑死 base_url 行为且引入十几层依赖；这个协议本质就是一个带 Bearer 头的 POST，httpx 30 行实现且行为 100% 可预期。

## 2.4 文件沙箱：对 LLM 的行为必须设边界

```python
def safe_resolve(name: str) -> Path:
    root = ensure_workspace().resolve()
    target = (root / name).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"path escapes workspace sandbox: {name}")
    return target
```

模型是概率系统，可能幻觉出不存在的路径，也可能被用户输入诱导（提示注入）去写系统文件。沙箱规则：所有文件工具的路径解析后必须落在 workspace/ 内，逃逸即报错。对应测试：write_file("../escape.txt") 与 "..\\escape.txt"（反斜杠变体）都被拒绝——测试要覆盖 Windows 路径分隔符变体，这是实测经验。

> 追问：为什么不用操作系统级隔离（容器）？答：单机个人工具，路径白名单已挡住主要风险；如果做成多人服务，会升级到独立用户 + 容器 + 磁盘配额。回答的关键是展示"风险分级"意识而不是堆技术。

## 2.5 配置与密钥管理

config.yaml 存路径与模型名（可入库），密钥只走环境变量 ELAB_API_KEY（setx 写入用户级，永不入库）。加载时默认值与 yaml 浅合并，环境变量最后覆盖——优先级清晰：代码默认 < 配置文件 < 环境变量，这是十二要素应用的标准做法。