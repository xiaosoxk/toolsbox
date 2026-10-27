"""Word 实验报告生成（python-docx，生成的 .docx 用 WPS/Office 都能打开）。

排版约定（贴近高校实验报告习惯）：
- 中文正文宋体小四、西文 Times New Roman、1.3 倍行距、首行缩进 2 字符；
- 标题黑体；图题/表题居中五号；
- 支持每节插入图片（来自 MATLAB/Python 输出的 PNG）与三线式表格。
"""
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from elab_agent.config import ensure_workspace
from elab_agent.tools.files import safe_resolve
from elab_agent.tools.registry import REGISTRY


def _set_cjk(style_or_run_font, eastasia: str) -> None:
    """python-docx 的中文字体必须写 w:eastAsia 才对 WPS/Word 生效。"""
    rpr = style_or_run_font._element.get_or_add_rPr()
    rpr.rFonts.set(qn("w:eastAsia"), eastasia)


def _base_styles(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)  # 小四
    _set_cjk(normal.font, "宋体")
    normal.paragraph_format.line_spacing = 1.3
    normal.paragraph_format.first_line_indent = Pt(24)  # 2 字符
    for level, size in (("Heading 1", 16), ("Heading 2", 14)):
        st = doc.styles[level]
        st.font.name = "Times New Roman"
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = None  # 跟随主题黑
        _set_cjk(st.font, "黑体")


def _add_table(doc: Document, headers: list[str], rows: list[list]) -> None:
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for col, text in enumerate(headers):
        cell = table.rows[0].cells[col]
        cell.text = str(text)
        for run in cell.paragraphs[0].runs:
            run.font.bold = True
    for r, row in enumerate(rows, start=1):
        for c, value in enumerate(row):
            table.rows[r].cells[c].text = str(value)


@REGISTRY.register(
    "word_make_report",
    "生成 .docx 实验报告到 workspace/reports/。sections 数组中每项为一个章节："
    "heading(必填)、text(段落)、table{headers,rows}(表格)、image(图片路径，"
    "通常是 matlab/python 生成的 PNG)。生成后可用 wps_open 打开查看。",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "报告标题"},
            "author": {"type": "string", "description": "作者/学号等署名信息"},
            "filename": {"type": "string", "description": "输出文件名，如 exp3_rc.docx"},
            "sections": {
                "type": "array",
                "description": "章节列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string"},
                        "text": {"type": "string"},
                        "image": {"type": "string", "description": "图片路径"},
                        "table": {
                            "type": "object",
                            "properties": {
                                "headers": {"type": "array", "items": {"type": "string"}},
                                "rows": {
                                    "type": "array",
                                    "items": {"type": "array", "items": {"type": "string"}},
                                },
                            },
                            "required": ["headers", "rows"],
                        },
                    },
                    "required": ["heading"],
                },
            },
        },
        "required": ["title", "filename", "sections"],
    },
)
def word_make_report(title: str, filename: str, sections: list[dict], author: str = "") -> str:
    if not filename.endswith(".docx"):
        filename += ".docx"
    doc = Document()
    _base_styles(doc)

    main_title = doc.add_heading(title, level=0)
    main_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    today = date.today().strftime("%Y 年 %m 月 %d 日")
    run = info.add_run(f"{author}　　{today}" if author else today)
    run.font.size = Pt(10.5)

    reports_dir = ensure_workspace() / "reports"
    reports_dir.mkdir(exist_ok=True)

    for index, section in enumerate(sections, start=1):
        doc.add_heading(f"{index}　{section.get('heading', '')}", level=1)
        if section.get("text"):
            doc.add_paragraph(section["text"])
        if section.get("image"):
            image_arg = section["image"]
            image_path = Path(image_arg)
            if not image_path.is_absolute():
                image_path = safe_resolve(image_arg)
            if image_path.exists():
                doc.add_picture(str(image_path), width=Cm(14))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                doc.add_paragraph(f"图 {index}").alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                doc.add_paragraph(f"[缺图] {image_arg}")
        if section.get("table"):
            spec = section["table"]
            doc.add_paragraph()  # 表前空行，避免贴住正文
            _add_table(doc, spec["headers"], spec["rows"])

    out = reports_dir / filename
    doc.save(str(out))
    return f"saved: {out}"


@REGISTRY.register(
    "word_read_docx",
    "读取 .docx 的全部文字与表格内容（用于让 Agent 了解已有报告再修改）。",
    {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "docx 路径（绝对或相对 workspace）"}},
        "required": ["path"],
    },
)
def word_read_docx(path: str) -> str:
    doc_path = Path(path)
    if not doc_path.is_absolute():
        doc_path = safe_resolve(path)
    if not doc_path.exists():
        return f"[error] not found: {doc_path}"
    doc = Document(str(doc_path))
    lines: list[str] = []
    for para in doc.paragraphs:
        if para.text.strip():
            style = para.style.name
            prefix = "# " if style.startswith("Heading") else ""
            lines.append(prefix + para.text)
    for table in doc.tables:
        lines.append("[表格]")
        for row in table.rows:
            lines.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(lines) or "[empty document]"
