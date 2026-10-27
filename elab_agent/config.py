"""配置加载：config.yaml 为主，缺省值兜底，环境变量可覆盖 LLM 配置。"""
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "config.yaml"
WORKSPACE = PROJECT_ROOT / "workspace"

DEFAULTS = {
    "paths": {},
    "llm": {
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "temperature": 0.3,
        "timeout_seconds": 180,
    },
    "agent": {"max_steps": 15, "tool_output_limit": 8000},
}


def load_config(path: Path | None = None) -> dict:
    """合并默认值与 config.yaml；结构浅合并（一层深，够用且可预期）。"""
    cfg = {**DEFAULTS, "paths": {}, "llm": {}, "agent": {}}
    for key, value in DEFAULTS.items():
        if isinstance(value, dict):
            cfg[key] = dict(value)
    source = path or CONFIG_FILE
    if source.exists():
        with open(source, encoding="utf-8") as fh:
            user_cfg = yaml.safe_load(fh) or {}
        for section in ("paths", "llm", "agent"):
            if isinstance(user_cfg.get(section), dict):
                cfg[section].update(user_cfg[section])
    # 环境变量覆盖（不落盘的密钥来源）
    import os

    api_key = os.environ.get("ELAB_API_KEY", "")
    if api_key:
        cfg["llm"]["api_key"] = api_key
    else:
        cfg["llm"]["api_key"] = user_cfg.get("llm", {}).get("api_key", "") if source.exists() else ""
    return cfg


def ensure_workspace() -> Path:
    WORKSPACE.mkdir(exist_ok=True)
    return WORKSPACE


def project_root() -> Path:
    return PROJECT_ROOT
