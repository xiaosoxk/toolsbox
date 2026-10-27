"""MATLAB 工具：无头执行（兼容 R2016b 及全部新版本）。

Windows 三个关键坑（都在这里处理）：
1. matlab.exe 是"启动器"，默认派生真 MATLAB 后立刻返回 —— 必须加 -wait；
2. -batch 是 R2019a+ 才有的参数，老版本会忽略并启动完整桌面导致永久挂起
   （本机实测 R2016b 就是这样）—— 因此用全版本通用的 -r + -logfile 方案；
3. -r 脚本若报错，末尾的 exit 不会执行 → 会话永不退出 —— 用 try/catch 包裹
   run() 并把异常 getReport 打印，无论成败都执行 exit。
输出经 -logfile 落盘后读回，不依赖启动器的 stdout 转发。
首次冷启动约 30~90 秒属正常。
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


def _run_matlab(args: list[str], timeout: int, cwd: Path) -> subprocess.CompletedProcess:
    exe = load_config()["paths"].get("matlab")
    if not exe or not Path(exe).exists():
        raise RuntimeError(f"config.yaml paths.matlab 无效: {exe}")
    return subprocess.run([exe, *args], capture_output=True, timeout=timeout, cwd=str(cwd))


@REGISTRY.register(
    "matlab_run",
    "在 MATLAB 中执行一段代码（自动保存为 .m 脚本后无头运行）。适合数值计算、"
    "控制系统仿真、信号处理、绘图出图（用 exportgraphics/saveas 把图存到当前目录）。"
    "首次冷启动约 30~90 秒，请耐心等待。",
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
    log_file = subdir / f"m_{stamp}.log"
    user_script.write_text(code, encoding="utf-8")

    # try/catch 包裹 + 无条件 exit：脚本报错也不会把 MATLAB 会话挂死
    command = "try, run('{user}'), catch e, disp(getReport(e)), end, exit".format(
        user=user_script.as_posix()
    )
    started = time.perf_counter()
    proc = _run_matlab(
        ["-nosplash", "-nodesktop", "-minimize", "-wait",
         "-logfile", str(log_file), "-sd", str(subdir), "-r", command],
        timeout, subdir,
    )
    elapsed = time.perf_counter() - started

    log_text = log_file.read_text(encoding="utf-8", errors="replace").strip() if log_file.exists() else ""
    out = _decode(proc.stdout or b"").strip()   # 空 bytes 是 falsy，必须用 b"" 兜底
    err = _decode(proc.stderr or b"").strip()

    parts = [f"[exit={proc.returncode}] [{elapsed:.1f}s] script={user_script}"]
    body = "\n".join(
        ln for ln in log_text.splitlines()
        if ln.strip() and not ln.strip().startswith(("<", "|"))  # 去掉 -logfile 的提示性边框行
    )
    parts.append("--- output ---\n" + (body or "(日志为空)"))
    if err:
        parts.append("--- stderr ---\n" + err)
    if proc.returncode != 0:
        parts.append("(exit 非零：检查上方输出中的错误信息)")
    return "\n".join(parts)
