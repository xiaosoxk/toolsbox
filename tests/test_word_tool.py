"""Word 工具测试：报告生成 + docx 回读（不依赖 WPS/Office，纯库操作）。"""
from elab_agent.tools import REGISTRY  # noqa: F401  (导入即注册)


def test_make_report_and_read_back():
    result = REGISTRY.call("word_make_report", {
        "title": "单元测试报告",
        "author": "tester",
        "filename": "unit_test_report.docx",
        "sections": [
            {"heading": "概述", "text": "这是一份由 pytest 自动生成的验证报告。"},
            {"heading": "数据",
             "table": {"headers": ["项", "值"], "rows": [["频率", "1kHz"], ["幅值", "3.3V"]]}},
        ],
    })
    assert result.startswith("saved:")
    docx_path = result.split(": ", 1)[1].strip()

    content = REGISTRY.call("word_read_docx", {"path": docx_path})
    assert "单元测试报告" in content
    assert "概述" in content
    assert "1kHz" in content  # 表格内容被读回


def test_make_report_missing_image_is_tolerated():
    result = REGISTRY.call("word_make_report", {
        "title": "缺图报告",
        "filename": "missing_image_report.docx",
        "sections": [{"heading": "结果", "text": "ok", "image": "figures/__no_such__.png"}],
    })
    assert result.startswith("saved:")
    content = REGISTRY.call("word_read_docx", {"path": result.split(": ", 1)[1].strip()})
    assert "[缺图]" in content


def test_filename_auto_suffix():
    result = REGISTRY.call("word_make_report", {
        "title": "后缀测试", "filename": "no_suffix_report", "sections": [],
    })
    assert result.endswith(".no_suffix_report.docx".replace(".no_suffix", "")) or result.endswith("no_suffix_report.docx")
