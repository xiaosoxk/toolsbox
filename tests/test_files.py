"""文件沙箱测试：读写列目录 + 路径逃逸防护。"""
from elab_agent.tools import REGISTRY  # noqa: F401


def test_write_read_list_roundtrip():
    write = REGISTRY.call("write_file", {"name": "matlab/demo.m", "content": "disp(1+1);"})
    assert write.startswith("written:")
    read = REGISTRY.call("read_file", {"name": "matlab/demo.m"})
    assert "disp(1+1);" in read
    listing = REGISTRY.call("list_files", {})
    assert "matlab/demo.m" in listing


def test_path_escape_rejected():
    result = REGISTRY.call("write_file", {"name": "../escape.txt", "content": "x"})
    assert "sandbox" in result
    result2 = REGISTRY.call("read_file", {"name": "..\\escape.txt"})
    assert "sandbox" in result2


def test_read_missing_file_is_error_text():
    assert REGISTRY.call("read_file", {"name": "no/such.txt"}).startswith("[error]")
