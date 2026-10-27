"""Keil MDK 命令行编译：UV4.exe -b。

UV4 退出码约定：0=无警告无错误 1=有警告 2=有错误 3=致命 11=不能打开工程...
日志由 -o 指定输出文件（必须是完整路径），其中含 "x Error(s), y Warning(s)" 汇总行。
"""
import subprocess
from pathlib import Path

from elab_agent.config import load_config, ensure_workspace
from elab_agent.tools.files import safe_resolve
from elab_agent.tools.registry import REGISTRY

EXIT_MEANING = {0: "0 errors, 0 warnings", 1: "warnings present", 2: "errors present",
                3: "fatal error", 11: "cannot open project", 15: "target not found"}


@REGISTRY.register(
    "keil_build",
    "命令行编译 Keil(uVision) 工程。传 .uvprojx 文件路径（绝对路径或相对 workspace），"
    "可选 target 名。返回编译结果与错误行，用于 Agent 自动修编译错误（改代码->重编）。",
    {
        "type": "object",
        "properties": {
            "uvprojx": {"type": "string", "description": "工程文件路径 (.uvprojx)"},
            "target": {"type": "string", "description": "目标名，留空用默认 Target"},
        },
        "required": ["uvprojx"],
    },
)
def keil_build(uvprojx: str, target: str = "") -> str:
    exe = load_config()["paths"].get("keil_uv4")
    if not exe or not Path(exe).exists():
        return f"[error] UV4.exe 不存在: {exe}，请修改 config.yaml 的 paths.keil_uv4"

    project = Path(uvprojx)
    if not project.is_absolute():
        project = safe_resolve(uvprojx)
    if not project.exists():
        return f"[error] 工程不存在: {project}"

    log_dir = ensure_workspace() / "keil"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{project.stem}_build.log"
    log_file.unlink(missing_ok=True)

    cmd = [exe, "-b", str(project), "-j0", "-o", str(log_file)]
    if target:
        cmd += ["-t", target]
    proc = subprocess.run(cmd, capture_output=True, timeout=600)

    log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else "(无日志)"
    summary = EXIT_MEANING.get(proc.returncode, f"exit={proc.returncode}")
    error_lines = [ln for ln in log_text.splitlines() if "error" in ln.lower()]
    warning_lines = [ln for ln in log_text.splitlines() if "warning" in ln.lower()]
    parts = [
        f"[exit={proc.returncode}] {summary}",
        f"log={log_file}",
    ]
    if error_lines:
        parts.append("--- errors ---\n" + "\n".join(error_lines[:20]))
    if warning_lines:
        parts.append("--- warnings ---\n" + "\n".join(warning_lines[:20]))
    if not error_lines and not warning_lines:
        tail = "\n".join(log_text.strip().splitlines()[-12:])
        parts.append("--- log tail ---\n" + tail)
    return "\n".join(parts)
