"""工作区文件工具：Agent 的一切脚本/数据/产物都落在 workspace/ 沙箱内。

沙箱规则：所有路径解析后必须仍在 workspace 内，防 LLM 幻觉写出逃逸路径。
"""
from pathlib import Path

from elab_agent.config import ensure_workspace
from elab_agent.tools.registry import REGISTRY


def safe_resolve(name: str) -> Path:
    root = ensure_workspace().resolve()
    target = (root / name).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"path escapes workspace sandbox: {name}")
    return target


@REGISTRY.register(
    "write_file",
    "把文本内容写入工作区文件（也用于生成 .m / .py / .c / .ioc 脚本后再执行）。"
    "name 相对 workspace 根，可含子目录，如 'matlab/step_resp.m'。",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "相对 workspace 的文件名"},
            "content": {"type": "string", "description": "完整文本内容（UTF-8）"},
        },
        "required": ["name", "content"],
    },
)
def write_file(name: str, content: str) -> str:
    path = safe_resolve(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"written: {path} ({len(content)} chars)"


@REGISTRY.register(
    "read_file",
    "读取工作区内文本文件的内容。",
    {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "相对 workspace 的文件名"}},
        "required": ["name"],
    },
)
def read_file(name: str) -> str:
    path = safe_resolve(name)
    if not path.exists():
        return f"[error] not found: {path}"
    text = path.read_text(encoding="utf-8", errors="replace")
    return f"{path}\n---\n{text}"


@REGISTRY.register(
    "list_files",
    "列出工作区（或其子目录）下的文件清单。",
    {
        "type": "object",
        "properties": {"subdir": {"type": "string", "description": "子目录，留空为根"}},
        "required": [],
    },
)
def list_files(subdir: str = "") -> str:
    base = safe_resolve(subdir) if subdir else ensure_workspace()
    if not base.exists():
        return f"[empty] {base}"
    entries = sorted(p.relative_to(ensure_workspace()) for p in base.rglob("*") if p.is_file())
    listing = "\n".join(str(e).replace("\\", "/") for e in entries)
    return (listing or "[empty]")
