"""画面の操作の流れと、公開構成の確認。"""
import os
import re
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from definereq.demos import builder
from definereq.media import probe

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")


def run(**state):
    at = AppTest.from_file(APP, default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def click(at, label):
    next(b for b in at.button if b.label == label).click()
    return at.run()


def test_demo_opens_from_home_without_keys():
    at = click(run(), "3分の案内で見る")
    assert not at.exception and at.session_state["project"]["is_demo"]
    assert at.session_state["project"]["demo"]["stage"] == 1 and at.session_state["tour_on"]


def test_tour_walks_to_the_end_across_stages():
    at = click(run(), "3分の案内で見る")
    stages = set()
    for _ in range(len(builder.catalog()[0]["tour"]) - 1):
        at = click(at, "次へ")
        assert not at.exception and not at.error
        stages.add(at.session_state["project"]["demo"]["stage"])
    assert {2, 3, 4} <= stages


def test_each_session_has_separate_copy():
    a = click(run(), "全画面を見る")
    b = click(run(), "全画面を見る")
    a.session_state["project"]["requirements"][0]["title"] = "Aだけの編集"
    assert b.session_state["project"]["requirements"][0]["title"] != "Aだけの編集"


def test_demo_is_read_only_on_every_page():
    from definereq.ui.shell import PAGES

    for page in PAGES:
        at = run(project=builder.build("d1", 4), page=page)
        assert not at.exception, page
        allowed = {"nav", "tour", "go", "ex", "next", "share"}
        for b in at.button:
            assert b.disabled or (b.key or "").split("_")[0] in allowed, (page, b.label, b.key)
        assert all(t.disabled for t in at.text_area), page
        assert not at.get("file_uploader"), page
        assert all(t.disabled for t in at.text_input if t.key not in ("why_q", "rq_q")), page


def test_new_project_is_editable():
    from definereq import project as pj

    at = run(project=pj.new_project("t", ["app"]), page="prep")
    assert not all(t.disabled for t in at.text_area)


def test_menu_shows_main_steps_and_details():
    from definereq.ui.shell import DETAILS, GROUPS, NEXT, PAGES

    assert sum(len(i) for _, i in GROUPS) <= 10 and DETAILS
    assert set(NEXT) == set(PAGES)
    assert all(t in PAGES for _, t in NEXT.values())


def test_next_step_button_moves_page():
    at = run(project=builder.build("d1", 4), page="prep")
    next(b for b in at.button if b.key == "next_prep").click()
    at = at.run()
    assert at.session_state["page"] == "sources" and not at.exception


def test_project_json_cannot_be_uploaded():
    at = run()
    assert not at.get("file_uploader")
    at = run(project=builder.build("d1", 4), page="share")
    assert not at.get("file_uploader")


def field(at, label):
    return next(t for t in at.text_input if t.label == label)


def create_button(at):
    return next(b for b in at.button if b.label == "案件を作成")


def test_create_disabled_until_valid_password(monkeypatch):
    monkeypatch.setenv("DEFINEREQ_ACCESS_CODES", "correct-password")
    at = run()
    assert create_button(at).disabled
    field(at, "AIパスワード").set_value("wrong")
    at = at.run()
    assert create_button(at).disabled and at.warning
    field(at, "AIパスワード").set_value("correct-password")
    at = at.run()
    assert not create_button(at).disabled and not at.warning


def test_create_disabled_when_no_password_configured():
    assert create_button(run()).disabled


def test_new_project_form_keeps_password_for_ai(monkeypatch):
    monkeypatch.setenv("DEFINEREQ_ACCESS_CODES", "correct-password")
    at = run()
    field(at, "案件名").set_value("勤怠の更新")
    field(at, "AIパスワード").set_value("correct-password")
    at = at.run()
    create_button(at).click()
    at = at.run()
    assert at.session_state["project"]["name"] == "勤怠の更新" and not at.exception
    assert at.session_state["ai_code"] == "correct-password"


def test_new_project_requires_name(monkeypatch):
    monkeypatch.setenv("DEFINEREQ_ACCESS_CODES", "correct-password")
    at = run()
    field(at, "AIパスワード").set_value("correct-password")
    at = at.run()
    create_button(at).click()
    at = at.run()
    assert at.error and "project" not in at.session_state


@pytest.mark.parametrize("page", ["candidates", "recordings", "usage"])
def test_password_input_exists_only_on_top(page):
    from definereq import project as pj

    at = run(project=pj.new_project("t", ["app"]), page=page)
    assert not any("パスワード" in t.label for t in at.text_input)
    assert any(t.label == "AIパスワード" for t in run().text_input)


def test_ai_panel_uses_password_from_top(monkeypatch):
    from definereq import project as pj

    monkeypatch.setenv("DEFINEREQ_ACCESS_CODES", "correct-password")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    monkeypatch.setenv("DEFINEREQ_ALLOW_LOCAL_LEDGER", "1")
    monkeypatch.setenv("DEFINEREQ_LOCAL_LEDGER", str(ROOT / "data" / "test_panel.db"))
    at = run(project=pj.new_project("t", ["app"]), page="candidates", ai_code="correct-password")
    assert any(not b.disabled for b in at.button if b.label == "この内容でAIを実行")


@pytest.mark.parametrize("page", ["prep", "candidates", "refine", "nfr", "conflicts", "risks", "scenarios"])
def test_ai_panel_on_new_project_without_keys_never_runs(page):
    from definereq import project as pj

    at = run(project=pj.new_project("t", ["app"]), page=page)
    assert not at.exception and not at.error


def test_ai_button_disabled_without_setup():
    from definereq import project as pj

    at = run(project=pj.new_project("t", ["app"]), page="candidates")
    assert all(b.disabled for b in at.button if b.label == "この内容でAIを実行")


def test_new_project_all_pages_render_empty():
    from definereq import project as pj
    from definereq.ui.shell import PAGES

    for page in PAGES:
        at = run(project=pj.new_project("t", ["app", "infra", "network"]), page=page)
        assert not at.exception and not at.error, page


def test_empty_tables_show_message_instead_of_grid():
    from definereq import project as pj
    from definereq.ui.shell import PAGES

    for page in PAGES:
        at = run(project=pj.new_project("t", ["app"]), page=page)
        for table in at.dataframe:
            assert len(table.value) > 0, page
    at = run(project=pj.new_project("t", ["app"]), page="requirements")
    assert not at.multiselect and any("要件はまだありません" in i.value for i in at.info)


def test_requirement_filter_with_no_match_shows_message():
    at = run(project=builder.build("d1", 4), page="requirements")
    next(t for t in at.text_input if t.label == "検索").set_value("存在しない言葉")
    at = at.run()
    assert not at.exception and any("該当する項目はありません" in c.value for c in at.caption)


def test_hero_has_short_lead_and_anchor_links():
    from definereq.ui import home

    source = (ROOT / "definereq" / "ui" / "home.py").read_text(encoding="utf-8")
    assert len(home.LEAD) < 80
    assert 'href="#dr-demo"' in source and 'id="dr-demo"' in source
    assert 'href="#dr-new"' in source and 'id="dr-new"' in source


def _luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return .2126 * r + .7152 * g + .0722 * b


def _contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + .05) / (low + .05)


def test_flow_colors_are_readable_and_even():
    from definereq.ui import theme

    tints = [theme.mix(theme.PALETTE[n], "#FFFFFF", theme.TINT[n]) for n in theme.PALETTE]
    for n, tint in zip(theme.PALETTE, tints):
        assert _contrast("#2F3036", tint) >= 7, n     # 本文
        assert _contrast(theme.DEEP[n], tint) >= 4.5, n  # 番号
    lum = [_luminance(t) for t in tints]
    assert max(lum) - min(lum) < .13                  # 5枚の明るさをそろえる


def test_hero_keeps_original_colors_from_shared_palette():
    from definereq.ui import theme

    assert (theme.PALETTE["orange"], theme.PALETTE["coral"], theme.PALETTE["magenta"]) == ("#FF7A00", "#F23A1E", "#E0117F")
    assert "__orange__" not in theme._colored(theme._HERO_SVG)
    assert "__" not in theme.CSS.split("<style>")[0]
    assert "--c-purple" in theme.CSS and "__PALETTE_CSS__" not in theme.CSS


def test_why_page_example_question():
    at = run(project=builder.build("d1", 4), page="why")
    at = click(at, "なぜ再申請なのか")
    assert any("監査" in s.value for s in at.success)


def test_human_can_add_evidence_opinion_and_mark_sent():
    from definereq import project as pj
    from definereq.ingest import registry
    from definereq.logic import agreement as ag

    p = pj.new_project("t", ["app"])
    src = registry.ingest_paste(p, "メモ", "承認後は変更できない")
    r = pj.add(p, "requirements", pj.new_requirement(title="要件", body="本文"))
    at = run(project=p, page="requirements")
    next(t for t in at.text_area if t.label.startswith("引用")).set_value("承認後は変更できない")
    at = next(b for b in at.button if b.label == "根拠を追加").click().run()
    assert not at.exception
    e = at.session_state["project"]["requirements"][0]["evidence"][0]
    assert e["verified"] and e["source_id"] == src["id"] and r["id"] == "REQ-001"
    pj.add(p, "issues", {"topic": "論点", "opinions": [], "options": [], "extra_questions": [], "state": "未調整", "evidence": [], "related_requirements": []})
    at = run(project=p, page="issues")
    assert not at.exception and any(b.label == "意見を追加" for b in at.button)
    ag.new_decision(p, "判断", [{"id": "A", "label": "案"}])
    at = run(project=p, page="decisions")
    assert not at.exception and any(t.label == "利点：案" for t in at.text_input)


def test_sweep_old_temp_files(tmp_path):
    old, new = tmp_path / "definereq_old.mp4", tmp_path / "definereq_new.mp4"
    other = tmp_path / "other.mp4"
    for f in (old, new, other):
        f.write_bytes(b"x")
    past = time.time() - 7 * 3600
    os.utime(old, (past, past))
    os.utime(other, (past, past))
    assert probe.sweep_old_files(6, str(tmp_path)) == 1
    assert not old.exists() and new.exists() and other.exists()


# ---- 公開構成 ----
def test_space_readme_settings():
    head = (ROOT / "README.md").read_text(encoding="utf-8").split("---")[1]
    assert "sdk: docker" in head and "app_port: 8501" in head and "title:" in head
    desc = re.search(r"short_description: (.+)", head).group(1)
    assert len(desc) <= 60


def test_dockerfile_matches_spaces_rules():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "useradd -m -u 1000 user" in text and "USER user" in text and "--chown=user" in text
    assert "--server.port=8501" in text and "EXPOSE 8501" in text
    assert "API_KEY" not in text.replace("ANTHROPIC_API_KEY・", "")


def test_requirements_are_pinned():
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            assert "==" in line, line


def test_public_image_excludes_heavy_and_dev_deps():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for name in ("faster-whisper", "torch", "pytest", "playwright"):
        assert name not in text


def test_gitignore_blocks_secrets_and_data():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in text and "secrets.toml" in text and "data/" in text


def test_deploy_script_requires_confirmation_flag():
    text = (ROOT / "scripts" / "deploy_hf.py").read_text(encoding="utf-8")
    assert '"--yes" not in sys.argv' in text and "HF_TOKEN" in text


def test_deploy_list_excludes_private_files():
    import importlib.util

    spec = importlib.util.spec_from_file_location("deploy_hf", ROOT / "scripts" / "deploy_hf.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    files = mod.selected()
    assert "app.py" in files and "Dockerfile" in files
    assert not any(f.startswith((".venv", "tests/", "data/")) or f.endswith((".env", ".db")) or f == "DefineReq_AI.txt" for f in files)
