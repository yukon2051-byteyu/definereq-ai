"""全画面の表示確認（Streamlit の AppTest を利用。実APIは呼ばない）。"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from definereq.ui.shell import PAGES

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def fresh():
    at = AppTest.from_file(APP, default_timeout=60)
    return at.run()


def test_home_renders_without_keys():
    at = fresh()
    assert not at.exception


@pytest.mark.parametrize("demo", ["d1", "d2", "d3"])
@pytest.mark.parametrize("stage", [1, 2, 3, 4])
def test_every_page_every_stage(demo, stage):
    from definereq.demos import builder

    for page in list(PAGES) + ["demo_map"]:
        at = AppTest.from_file(APP, default_timeout=60)
        at.session_state["project"] = builder.build(demo, stage)
        at.session_state["page"] = page
        at.run()
        assert not at.exception, (demo, stage, page, at.exception)
        assert not at.error, (demo, stage, page, [e.value for e in at.error])
