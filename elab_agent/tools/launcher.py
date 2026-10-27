"""GUI 应用启动器：Proteus / Multisim / PyCharm / WPS / CubeMX。

这些软件没有可用的无头接口，Agent 的正确用法是"打开它让人接手"：
启动即返回（DETACHED_PROCESS），不阻塞对话。
"""
import subprocess
import sys
from pathlib import Path

from elab_agent.config import load_config
from elab_agent.tools.files import safe_resolve
from elab_agent.tools.registry import REGISTRY

DETACHED = 0x00000008 if sys.platform == "win32" else 0


def _launch(tool_key: str, args: list[str] | None = None) -> str:
    exe = load_config()["paths"].get(tool_key)
    if not exe or not Path(exe).exists():
        return f"[error] 未找到 {tool_key} 可执行文件（config.yaml paths.{tool_key} = {exe}）"
    subprocess.Popen([exe, *(args or [])], creationflags=DETACHED, close_fds=True)
    return f"launched: {exe} {' '.join(args or [])}"


@REGISTRY.register(
    "proteus_open",
    "打开 Proteus 仿真软件；可传 .pdsprj 工程文件路径直接载入电路。",
    {
        "type": "object",
        "properties": {"project": {"type": "string", "description": ".pdsprj 路径，可留空"}},
        "required": [],
    },
)
def proteus_open(project: str = "") -> str:
    args = [str(safe_resolve(project))] if project else []
    return _launch("proteus", args)


@REGISTRY.register(
    "multisim_open",
    "打开 NI Multisim 电路仿真软件；可传 .ms13 等电路文件路径。",
    {
        "type": "object",
        "properties": {"circuit": {"type": "string", "description": "电路文件路径，可留空"}},
        "required": [],
    },
)
def multisim_open(circuit: str = "") -> str:
    args = [str(safe_resolve(circuit))] if circuit else []
    return _launch("multisim", args)


@REGISTRY.register(
    "pycharm_open",
    "用 PyCharm 打开一个文件夹（工程）。",
    {
        "type": "object",
        "properties": {"folder": {"type": "string", "description": "文件夹路径，可留空"}},
        "required": [],
    },
)
def pycharm_open(folder: str = "") -> str:
    args = [folder] if folder else []
    return _launch("pycharm", args)


@REGISTRY.register(
    "wps_open",
    "用 WPS 打开文档（.docx/.xlsx/.pptx），常用于查看刚生成的实验报告。",
    {
        "type": "object",
        "properties": {"document": {"type": "string", "description": "文档路径（绝对或相对 workspace）"}},
        "required": ["document"],
    },
)
def wps_open(document: str) -> str:
    doc = Path(document)
    if not doc.is_absolute():
        doc = safe_resolve(document)
    if not doc.exists():
        return f"[error] 文档不存在: {doc}"
    return _launch("wps", [str(doc)])


@REGISTRY.register(
    "cubemx_open",
    "打开 STM32CubeMX 图形界面（需要交互式配置引脚/时钟时使用；"
    "纯重新生成代码请用 cubemx_generate）。",
    {"type": "object", "properties": {}, "required": []},
)
def cubemx_open() -> str:
    return _launch("cubemx")
