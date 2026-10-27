"""MATLAB 工具：无头批处理执行（matlab -wait -batch + diary 输出捕获）。

Windows 两个关键坑（都在这里处理）：
1. matlab.exe 是"启动器"，默认派生真 MATLAB 后立刻返回 —— 必须加 -wait 才阻塞；
2. 它的 stdout 未必转发给调用者 —— 因此用 diary 把输出写入日志文件再读回，
   与进程捕获双保险，任何 MATLAB 版本都能拿到输出。
脚本本体原样落盘（保留局部函数定义等合法结构），由 runner 以 try/catch 包裹执行，
运行期错误会写入日志而不是无声丢失。首次启动约 20~60 秒属正常。
"""
import subprocess
import time
from pathlib import Path

from elab_agent.config import load_config, ensure_workspace
from elab_agent.tools.registry import REGISTRY


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _run_matlab(statement: str, timeout: int, cwd: Path) -> subprocess.CompletedProcess:
    exe = load_config()["paths"].get("matlab")
    if not exe or not Path(exe).exists():
        raise RuntimeError(f"config.yaml paths.matlab 无效: {exe}")
    # -wait: 等 MATLAB 会话真正结束（Windows 启动器默认立即返回）
    return subprocess.run(
        [exe, "-wait", "-batch", statement],
        capture_output=True, timeout=timeout, cwd=str(cwd),
    )


@REGISTRY.register(
    "matlab_run",
    "在 MATLAB 中执行一段代码（自动保存为 .m 脚本后无头运行）。适合数值计算、"
    "控制系统仿真、信号处理、绘图出图（用 exportgraphics/saveas 把图存到当前目录）。"
    "首次调用约 20~60 秒，请耐心等待。",
    {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "完整 MATLAB 代码，多行也可"},
            "timeout": {"type": "integer", "description": "超时秒数，默认 300"},
        },
        "required": ["code"],
    },
)
def matlab_run(code: str, timeout: int = 300) -> str:
    subdir = ensure_workspace() / "matlab"
    subdir.mkdir(exist_ok=True)
    stamp = int(time.time() * 1000)
    user_script = subdir / f"m_{stamp}.m"
    runner = subdir / f"r_{stamp}.m"
    log_file = subdir / f"m_{stamp}.log"
    user_script.write_text(code, encoding="utf-8")

    runner.write_text(
        "diary('{log}');\n"
        "try\n"
        "    run('{user}');\n"
        "catch err\n"
        "    fprintf(2, 'MATLAB_ERROR: %s\\n%s\\n', err.identifier, err.message);\n"
        "end\n"
        "diary off;\n".format(log=log_file.as_posix(), user=user_script.as_posix()),
        encoding="utf-8",
    )

    started = time.perf_counter()
    proc = _run_matlab(f"run('{runner.as_posix()}')", timeout, subdir)
    elapsed = time.perf_counter() - started

    log_text = log_file.read_text(encoding="utf-8", errors="replace").strip() if log_file.exists() else ""
    out = _decode(proc.stdout or b"").strip()   # 空 bytes 是 falsy，必须用 b"" 兜底
    err = _decode(proc.stderr or b"").strip()

    parts = [f"[exit={proc.returncode}] [{elapsed:.1f}s] script={user_script}"]
    body = log_text or "(diary 日志为空)"
    parts.append("--- output ---\n" + body)
    if out and out not in body:
        parts.append("--- stdout ---\n" + out)
    if err:
        parts.append("--- stderr ---\n" + err)
    if "MATLAB_ERROR" in body or "MATLAB_ERROR" in err:
        parts.append("(代码运行报错，见上方 MATLAB_ERROR 行)")
    return "\n".join(parts)
