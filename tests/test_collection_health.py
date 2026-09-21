"""元测试：确保没有「写了但 pytest 收集不到」的测试（静默丢失）。

**为什么需要它**

pytest 对某些写法会**静默跳过**整个类或函数 —— 最典型的是
`class TestX:` 里定义了 `__init__`（pytest 判定它不是测试类，直接不收集）。
这类丢失**不报错、不计入、套件看起来还是绿的**：
覆盖率与信心同时虚高，而没有任何现有检查能发现。

（另一种"测试坏了"的情况 —— 引用了不存在的符号 —— **不需要这里兜底**：
那会让 pytest 在收集期抛 ImportError，CI 直接红。所以只守"静默"这一类。）

**做法**

把源码里**声明**的 test 函数与 `conftest` 收集期记录的**真实 node id** 比对。
不另开子进程 —— 钩子就在同一次收集里把结果存下来了，零额外开销。
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

TESTS_DIR = pathlib.Path(__file__).parent
REPO = TESTS_DIR.parent


def _declared() -> set[tuple[str, str]]:
    """源码里声明的测试：{(相对路径, 函数名)}。

    只看**模块级**与**类内一层**。嵌套在函数体里的 `test_*` 不是测试，
    用 `ast.walk` 会把它们一起捞出来，造成误报。
    """
    out: set[tuple[str, str]] = set()

    def collect(body: list[ast.stmt], rel: str) -> None:
        for sub in body:
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith(
                "test_"
            ):
                out.add((rel, sub.name))

    for f in sorted(TESTS_DIR.rglob("test_*.py")):
        rel = f.relative_to(REPO).as_posix()
        tree = ast.parse(f.read_text(encoding="utf-8"))
        collect(tree.body, rel)  # 模块级
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                collect(node.body, rel)  # 类内一层
    return out


def _collected(nodeids: list[str]) -> set[tuple[str, str]]:
    """本次运行真实被收集到的测试：{(相对路径, 函数名)}。"""
    out: set[tuple[str, str]] = set()
    for nodeid in nodeids:
        path, _, rest = nodeid.partition("::")
        func = rest.split("::")[-1]
        func = re.sub(r"\[.*\]$", "", func)  # 去掉参数化后缀
        out.add((path.strip(), func))
    return out


class TestNoSilentlyDroppedTests:
    def test_declared_and_collected_match(self, collected_nodeids, is_full_test_run):
        # 「本次是否全量运行」的判据放在 conftest 的 is_full_test_run fixture 里。
        # ⚠️ 不能用「收集到的文件集合 == 磁盘文件集合」：某个文件的测试若**全部**被静默
        # 丢弃，它就不会出现在收集结果里，两个集合不等 → 判据会判定为「部分运行」而跳过，
        # 恰好在最该报警的时候沉默。（反向验证实测踩过这个坑。）
        if not is_full_test_run:
            pytest.skip("只跑了部分测试文件，「声明 vs 收集」的全量比对不适用")
        missing = sorted(_declared() - _collected(collected_nodeids))
        assert not missing, (
            f"有 {len(missing)} 个测试写了但 pytest 没收集到（静默丢失）:\n"
            + "\n".join(f"  {path}::{name}" for path, name in missing)
            + "\n\n常见原因：`Test*` 类里定义了 `__init__`（pytest 会整类跳过），"
            "或函数放在了 pytest 不扫描的命名空间里。"
        )

    def test_scan_actually_covers_the_suite(self):
        """元测试的元测试：扫到 0 个时上面那条会「零个问题」而**假绿**。

        这里只断言**磁盘扫描**的结果 —— 它读文件系统，与跑没跑无关，
        所以部分运行下也成立。收集侧的数量不能在这里断言（部分运行会很小）。
        """
        declared = _declared()
        assert len(declared) > 800, f"只扫到 {len(declared)} 个测试 —— 路径可能不对，主断言会假绿"
