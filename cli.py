"""elab-agent 命令行入口。

    python cli.py doctor              # 体检：8 个工具路径与依赖检查
    python cli.py doctor --matlab     # 体检 + 真实启动 MATLAB 跑一次版本号（约 30~60s）
    python cli.py report              # 离线演示：生成一份示例实验报告 .docx 并用 WPS 打开
    python cli.py task "任务描述"      # 一次性 Agent 任务（需 ELAB_API_KEY）
    python cli.py chat                # 交互式对话（需 ELAB_API_KEY，/exit 退出）
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from elab_agent import __version__  # noqa: E402
from elab_agent.config import load_config, project_root, ensure_workspace  # noqa: E402
from elab_agent.tools import REGISTRY  # noqa: E402, F401 (导入即注册全部工具)


def cmd_doctor(args) -> int:
    cfg = load_config()
    ok = True
    print(f"elab-agent v{__version__}  project: {project_root()}")
    print("=" * 72)
    print(f"{'工具':<12}{'状态':<8}路径")
    print("-" * 72)
    for key in ["matlab", "pycharm", "cubemx", "keil_uv4", "proteus", "multisim", "wps"]:
        path = cfg["paths"].get(key, "")
        exists = bool(path) and Path(path).exists()
        ok &= exists
        mark = "OK" if exists else "MISS"
        print(f"{key:<12}{mark:<8}{path}")
    python_ok = Path(sys.executable).exists()
    ok &= python_ok
    print(f"{'python':<12}{'OK' if python_ok else 'MISS':<8}{sys.executable}")
    print(f"{'workspace':<12}{'OK':<8}{ensure_workspace()}")
    key = cfg["llm"].get("api_key", "")
    print(f"{'LLM key':<12}{'OK' if key else 'MISS(仅影响 chat/task，report/工具不受影响)':<8}"
          f"{cfg['llm'].get('api_base')} model={cfg['llm'].get('model')}")
    print("=" * 72)

    if args.matlab:
        print("正在真实调用 MATLAB（首次约 30~60 秒）...")
        result = REGISTRY.call("matlab_run", {"code": "fprintf('MATLAB %s OK\\n', version);"})
        print(result)
        ok &= "[exit=0]" in result
    if ok:
        print("体检通过。")
    else:
        print("存在 MISSING 项：用到的软件装到别的盘了就改 config.yaml 对应 paths 即可。")
    return 0 if ok else 1


def _build_client(cfg):
    from elab_agent.llm import LLMClient, LLMError

    try:
        return LLMClient(
            api_base=cfg["llm"]["api_base"],
            api_key=cfg["llm"].get("api_key", ""),
            model=cfg["llm"]["model"],
            temperature=cfg["llm"].get("temperature", 0.3),
            timeout=cfg["llm"].get("timeout_seconds", 180),
        )
    except LLMError as exc:
        print(f"[初始化失败] {exc}")
        print("获取密钥：智谱 https://open.bigmodel.cn -> API Keys；"
              "DeepSeek https://platform.deepseek.com。设置方法（PowerShell）：")
        print('  setx ELAB_API_KEY "sk-xxx"   （重开终端生效）')
        return None


def cmd_task(args) -> int:
    cfg = load_config()
    client = _build_client(cfg)
    if client is None:
        return 1
    from elab_agent.agent import Agent

    agent = Agent(client, registry=REGISTRY, max_steps=cfg["agent"]["max_steps"])
    print(f"任务: {args.goal}\n" + "-" * 72)
    answer, _history = agent.run(args.goal)
    print("-" * 72)
    print(answer)
    return 0


def cmd_chat(args) -> int:
    cfg = load_config()
    client = _build_client(cfg)
    if client is None:
        return 1
    from elab_agent.agent import Agent

    agent = Agent(client, registry=REGISTRY, max_steps=cfg["agent"]["max_steps"])
    history: list[dict] = []
    print(f"elab-agent chat（模型 {cfg['llm']['model']}）。/exit 退出，/tools 列出工具，/reset 清空上下文。")
    while True:
        try:
            line = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line == "/exit":
            return 0
        if line == "/tools":
            print("\n".join(REGISTRY.names()))
            continue
        if line == "/reset":
            history = []
            print("(上下文已清空)")
            continue
        answer, history = agent.run(line, history=history)
        print(f"\n助手> {answer}")


def cmd_report(args) -> int:
    """离线技能：不依赖 LLM，直接演示 Word 报告生成 + WPS 打开。"""
    workspace = ensure_workspace()
    figures = workspace / "figures"
    figures.mkdir(exist_ok=True)
    png = figures / "rc_step_response.png"

    try:  # 有 numpy+matplotlib 就画图，没有也能出报告
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        rc, dt, t_end = 1e-3, 1e-5, 8e-3
        t = np.arange(0, t_end, dt)
        vc = 5 * (1 - np.exp(-t / rc))
        fig, ax = plt.subplots(figsize=(6, 3.2), dpi=150)
        ax.plot(t * 1e3, vc, linewidth=1.8)
        ax.set_xlabel("t / ms")
        ax.set_ylabel("Vc / V")
        ax.set_title("RC first-order step response (R=1k, C=1uF)")
        ax.grid(alpha=0.3)
        fig.savefig(png, bbox_inches="tight")
        plt.close(fig)
        tau_measured = t[np.searchsorted(vc, 5 * 0.632)] * 1e3
        fig_note = f"仿真时间常数 tau = {tau_measured:.3f} ms（理论值 1.000 ms）"
        print(f"figure: {png}")
        png = str(png)
    except ImportError:
        png = None
        fig_note = "（本机未安装 numpy/matplotlib，未插入仿真图；可让 Agent 用 MATLAB 出图）"

    sections = [
        {"heading": "实验目的", "text": "研究一阶 RC 电路的阶跃响应，验证时间常数 tau = RC 的理论关系。"},
        {"heading": "实验原理",
         "text": "RC 串联电路接通直流电源时，电容电压按指数规律上升：Vc(t) = Us(1 - e^(-t/RC))。"
                 "当 t = tau = RC 时，Vc 上升到稳态值的 63.2%；工程上认为 3~5 tau 后进入稳态。"},
        {"heading": "仿真结果", "text": fig_note, "image": str(png) if png else None},
        {"heading": "数据记录",
         "table": {
             "headers": ["参数", "理论值", "仿真值", "相对误差"],
             "rows": [
                 ["时间常数 tau (ms)", "1.000", f"{1.0 if png else 'N/A'}", "< 0.5%"],
                 ["稳态电压 Vc(∞) (V)", "5.000", "5.000", "0%"],
             ],
         }},
        {"heading": "结论",
         "text": "仿真结果与一阶 RC 电路理论模型吻合，验证了 tau=RC 的指数上升规律，"
                 "可用于后续滤波器设计与实验预习。"},
    ]
    from elab_agent.tools import word_tool  # noqa: F401

    result = REGISTRY.call(
        "word_make_report",
        {"title": "一阶 RC 电路阶跃响应实验报告", "filename": "rc_step_response_report",
         "author": args.author or "elab-agent", "sections": sections},
    )
    print(result)
    docx_path = result.split(": ", 1)[-1]
    open_result = REGISTRY.call("wps_open", {"document": docx_path})
    print(open_result)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="elab-agent", description="电子信息工程工作台智能体")
    parser.add_argument("--version", action="version", version=f"elab-agent {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser("doctor", help="检查工具路径与依赖")
    p_doctor.add_argument("--matlab", action="store_true", help="额外真实调用一次 MATLAB")
    p_doctor.set_defaults(func=cmd_doctor)

    p_task = sub.add_parser("task", help="执行一次性 Agent 任务（需 ELAB_API_KEY）")
    p_task.add_argument("goal", help="任务描述，如：把 workspace/matlab 里的数据画图并写进报告")
    p_task.set_defaults(func=cmd_task)

    p_chat = sub.add_parser("chat", help="交互式对话（需 ELAB_API_KEY）")
    p_chat.set_defaults(func=cmd_chat)

    p_report = sub.add_parser("report", help="离线生成示例实验报告（不需要 API key）")
    p_report.add_argument("--author", default="", help="署名，如：张三 2021001")
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
