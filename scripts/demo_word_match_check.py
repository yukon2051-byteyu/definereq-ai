"""デモ3件の最終画面で、画面の代表例・全文プレビュー・ダウンロードした要件定義書（Word）の対応を照合する（デスクトップ）。

照合する項目：要件ID・合意状態・関連する判断（ID）・根拠（資料名と位置）。AIは使わない。
使い方：python scripts/demo_word_match_check.py <URL> <保存先>
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

from docx import Document
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT = sys.argv[1], Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
problems: list[str] = []
DEMOS = (("経費申請", "REQ-002"), ("売上集計・クラウド移行", "REQ-004"), ("ネットワーク更新", "REQ-006"))


def check(ok, message):
    print(("OK  " if ok else "NG  ") + message)
    if not ok:
        problems.append(message)


def facts(text: str, rid: str) -> dict:
    """要件の見出しから次の要件までの範囲で、状態・関連する判断・根拠を読む。"""
    lines = text.splitlines()
    i = next((n for n, l in enumerate(lines) if l.startswith(f"{rid} ") and "（" in l), None)
    if i is None:
        return {}
    block = []
    for l in lines[i + 1:i + 60]:  # 全文プレビューは行の間が空くため、次の要件の見出しまで読む
        if re.match(r"^REQ-\d+ ", l):
            break
        block.append(l)
    status = re.search(r"（([^（）]+)）$", lines[i])
    rel = next((l for l in block if l.startswith("関連する判断：")), "")
    src = next((l for l in block if l.startswith("根拠：")), "")
    return {"状態": status.group(1) if status else None, "判断": sorted(set(re.findall(r"DEC-\d+", rel))), "根拠": src.removeprefix("根拠：")}


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    for demo, rid in DEMOS:
        g = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True).new_page()
        m = g.locator("[data-testid=stMain]")
        g.goto(URL)
        g.wait_for_selector(".dr-hero", timeout=120000)
        g.wait_for_timeout(1500)
        g.get_by_role("button", name=f"{demo}のデモを見る").click()
        g.wait_for_selector(".dr-loc", timeout=60000)
        g.wait_for_timeout(2500)
        for _ in range(7):
            m.get_by_role("button", name=re.compile("^次へ：")).first.click()
            g.wait_for_timeout(2800)
        g.wait_for_selector(".dr-end-h", timeout=60000)
        g.wait_for_timeout(3000)
        rep = g.locator(".dr-rep").inner_text()
        screen = {"状態": (re.search(r"状態：(\S+)", rep) or [None, None])[1], "判断": sorted(set(re.findall(r"DEC-\d+", rep))),
                  "根拠": re.findall(r"」（(.+?)）", rep)}
        check(rid in rep and screen["状態"] and screen["判断"], f"{demo}：画面の代表例 {rid}（状態 {screen['状態']}、判断 {screen['判断']}）")
        with g.expect_download(timeout=60000) as d:
            m.get_by_role("button", name="要件定義書をWordでダウンロード").click()
        data = Path(d.value.path()).read_bytes()
        (OUT / f"{demo}_要件定義書.docx").write_bytes(data)
        doc = Document(io.BytesIO(data))
        word = facts("\n".join(x.text for x in doc.paragraphs), rid)
        m.get_by_role("button", name="要件定義書の全文を見る").click()
        m.get_by_text("この文書について").first.wait_for(timeout=30000)
        g.wait_for_timeout(1500)
        preview = facts(m.inner_text(), rid)
        check(word.get("状態") == screen["状態"] == preview.get("状態"), f"{demo}：状態が一致（画面 {screen['状態']}／全文 {preview.get('状態')}／Word {word.get('状態')}）")
        check(word.get("判断") == preview.get("判断") and set(screen["判断"]) == set(word.get("判断", [])),
              f"{demo}：関連する判断が一致（画面 {screen['判断']}／全文 {preview.get('判断')}／Word {word.get('判断')}）")
        check(all(c in word.get("根拠", "") for c in screen["根拠"]) and word.get("根拠") == preview.get("根拠"),
              f"{demo}：根拠（資料名と位置）が一致（Word：{word.get('根拠')}）")
        g.screenshot(path=OUT / f"{demo}_最終画面.png")
        g.context.close()
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
