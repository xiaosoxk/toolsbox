"""工具集入口：导入各模块即完成注册（import 副作用 = 注册，约定俗成）。"""
from elab_agent.tools.registry import REGISTRY  # noqa: F401

# 依序导入触发注册；新增工具模块后在这里加一行即可
from elab_agent.tools import (  # noqa: F401, E402
    files,
    matlab_tool,
    python_tool,
    word_tool,
    keil_tool,
    cubemx_tool,
    launcher,
)
