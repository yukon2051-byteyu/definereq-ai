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
    a = click(run(), "自由に操作する")
    b = click(run(), "自由に操作する")
    a.session_state["project"]["requirements"][0]["title"] = "Aだけの編集"
    assert b.session_state["project"]["requirements"][0]["title"] != "Aだけの編集"


def test_demo_reset_restores_initial_state():
    at = click(run(), "自由に操作する")
    at.session_state["project"]["requirements"][0]["title"] = "編集"
    at.session_state["project"]["demo"]["edited"] = True
    at = click(at.run(), "デモを初期状態に戻す")
    assert at.session_state["project"]["requirements"][0]["title"] != "編集"


def test_project_json_cannot_be_uploaded():
    at = run()
    assert not at.get("file_uploader")
    at = run(project=builder.build("d1", 4), page="share")
    assert not at.get("file_uploader")


def test_new_project_form():
    at = run()
    at.text_input[0].set_value("勤怠の更新")
    at = click(at, "案件を作成")
    assert at.session_state["project"]["name"] == "勤怠の更新" and not at.exception


def test_new_project_requires_name():
    at = click(run(), "案件を作成")
    assert at.error and "project" not in at.session_state


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
