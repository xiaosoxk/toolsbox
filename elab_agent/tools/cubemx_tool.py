"""STM32CubeMX 无头代码生成：-q 脚本模式。

.ioc 工程改完配置后，无需打开 GUI 即可重新生成 HAL 代码：
    config load <ioc>
    project generate <outdir>
    exit
注意：首次为某芯片家族生成代码时，CubeMX 可能需要联网下载固件包。
"""
import subprocess
import time
from pathlib import Path

from elab_agent.config import load_config, ensure_workspace
from elab_agent.tools.files import safe_resolve
from elab_agent.tools.registry import REGISTRY


@REGISTRY.register(
    "cubemx_generate",
    "用 STM32CubeMX 命令行模式重新生成代码：传入 .ioc 文件路径与输出目录，"
    "等价于 GUI 里点 GENERATE CODE。首次可能较慢（需加载 Java 与固件包）。",
    {
        "type": "object",
        "properties": {
            "ioc_path": {"type": "string", "description": ".ioc 工程文件路径"},
            "out_dir": {"type": "string", "description": "代码输出目录，默认与 ioc 同目录"},
        },
        "required": ["ioc_path"],
    },
)
def cubemx_generate(ioc_path: str, out_dir: str = "") -> str:
    exe = load_config()["paths"].get("cubemx")
    if not exe or not Path(exe).exists():
        return f"[error] STM32CubeMX.exe 不存在: {exe}"

    ioc = Path(ioc_path)
    if not ioc.is_absolute():
        ioc = safe_resolve(ioc_path)
    if not ioc.exists():
        return f"[error] ioc 不存在: {ioc}"

    output = Path(out_dir) if out_dir else ioc.parent
    output.mkdir(parents=True, exist_ok=True)

    script_dir = ensure_workspace() / "cubemx"
    script_dir.mkdir(exist_ok=True)
    script = script_dir / f"gen_{int(time.time() * 1000)}.txt"
    script.write_text(
        f"config load {ioc.as_posix()}\nproject generate {output.as_posix()}\nexit\n",
        encoding="utf-8",
    )
    started = time.perf_counter()
    proc = subprocess.run(
        [exe, "-q", str(script)],
        capture_output=True,
        timeout=900,
        cwd=str(output),
    )
    elapsed = time.perf_counter() - started
    decode = lambda raw: raw.decode("utf-8", errors="replace")  # noqa: E731
    summary_lines = [
        f"[exit={proc.returncode}] [{elapsed:.1f}s] output={output}",
    ]
    tail = (decode(proc.stdout or "") + "\n" + decode(proc.stderr or "")).strip()
    if tail:
        summary_lines.append("--- output tail ---\n" + "\n".join(tail.splitlines()[-15:]))
    main_c = output / "Core" / "Src" / "main.c"
    if main_c.exists():
        summary_lines.append(f"OK: {main_c}")
    return "\n".join(summary_lines)
