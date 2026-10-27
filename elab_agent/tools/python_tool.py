"""Python 工具：子进程执行任意分析代码（隔离、超时、输出解码）。"""
import subprocess
import sys
import time

from elab_agent.config import ensure_workspace
from elab_agent.tools.registry import REGISTRY


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


@REGISTRY.register(
    "python_run",
    "在独立 Python 子进程中执行一段代码并返回 stdout/stderr。"
    "适合数据处理、画图（matplotlib 存 PNG 到工作区）、CSV 分析等。",
    {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "完整 Python 代码"},
            "timeout": {"type": "integer", "description": "超时秒数，默认 120"},
        },
        "required": ["code"],
    },
)
def python_run(code: str, timeout: int = 120) -> str:
    subdir = ensure_workspace() / "python"
    subdir.mkdir(exist_ok=True)
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        timeout=timeout,
        cwd=str(subdir),
    )
    elapsed = time.perf_counter() - started
    out = _decode(proc.stdout or b"").strip()   # 空 bytes 是 falsy，必须用 b"" 兜底
    err = _decode(proc.stderr or b"").strip()
    parts = [f"[exit={proc.returncode}] [{elapsed:.1f}s]"]
    if out:
        parts.append("--- stdout ---\n" + out)
    if err:
        parts.append("--- stderr ---\n" + err)
    return "\n".join(parts)
