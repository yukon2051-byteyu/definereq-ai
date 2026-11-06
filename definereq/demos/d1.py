"""デモ1：申請・承認アプリ（業務アプリ）。強み：合意、変更、矛盾、理由の追跡。"""
from __future__ import annotations

from .. import project as pj
from ..logic import agreement as ag
from ..logic import checks
from ..export import share
from .builder import accept, action, issue, measure, opt, risk, scenario

ID = "d1"
NAME = "申請・承認アプリの刷新"
DOMAINS = ["app"]
TRAITS = ["approval", "data", "confidential"]
LEAD = "承認後の金額訂正をめぐる現場と管理部門の対立を、比較・判断・履歴までつなぐ。"
STRENGTH = "合意・変更・矛盾・理由の追跡"
SITUATION = "現場は承認後の金額訂正を希望していますが、経理は直接変更を認めていません。"
HIGHLIGHTS = ["対立する条件を整理し、訂正方法を比較する", "判断理由を残し、後から出た変更要望まで追跡する"]
FEATURE = "部門間の対立を判断と履歴につなぐ例です。"
TOUR = [
    {"stage": 1, "page": "prep", "title": "会議前に質問を準備する", "input": "要望メモと経費申請規程", "ai": "質問と不足情報の候補（準備済み）", "human": "質問を選び、確認相手を決める", "result": "確認観点ごとの質問リスト"},
    {"stage": 2, "page": "recordings", "title": "会議での発言", "input": "議事録と第2回の字幕", "ai": "なし（字幕の取込）", "human": "話者を確認する。最後の発言は未確認のまま", "result": "話者と確認状態のついた発言"},
    {"stage": 2, "page": "candidates", "title": "候補を採否する", "input": "資料と発言", "ai": "要望・決定候補（準備済み）", "human": "担当者が採用・却下した結果を確認する", "result": "根拠付きの要件"},
    {"stage": 2, "page": "issues", "title": "対立を整理する", "input": "佐藤と田中の発言", "ai": "なし", "human": "3案を比較し判断者が決める", "result": "再申請を採用。不採用の理由も記録"},
    {"stage": 3, "page": "changes", "title": "追加要望の影響を調べる", "input": "経理の直接訂正の要望", "ai": "影響候補（準備済み）", "human": "受付のみ。要件はまだ変わらない", "result": "矛盾候補と影響、未調査の領域"},
    {"stage": 4, "page": "trail", "title": "判断と変遷を確認する", "input": "判断の記録", "ai": "なし", "human": "却下と一部採用を判断", "result": "変更前後と理由の履歴"},
    {"stage": 4, "page": "why", "title": "なぜ再申請かを聞く", "input": "「なぜ再申請なのか」", "ai": "なし（登録情報から回答）", "human": "回答の引用を確認する", "result": "採用理由・比較案・判断者・引用"},
    {"stage": 4, "page": "share", "title": "資料を出力する", "input": "案件データ", "ai": "なし", "human": "掲載する引用を選ぶ", "result": "Word・Excel・JSON"},
]


def step1(b):
    p = b.p
    b.profile({"purpose": "確認済み", "problem": "仮説"},
              background="紙とExcelの申請で、承認までの状況が見えない。",
              purpose="申請から精算までを一つのアプリで追えるようにする。",
              problem="金額の誤りが承認後に見つかったときの扱いが決まっていない。",
              request="申請、承認、差し戻し、精算連携を画面で行いたい。",
              constraints="次の決算期までに利用を開始したい。",
              current="紙の申請書とExcelの管理台帳で運用している。")
    b.stake("佐藤", "営業部", "申請者の代表", "現場の要望の確認")
    b.stake("田中", "経理課", "課長", "規程の解釈の確認")
    b.stake("鈴木", "情報システム課", "担当", "実現方式の検討")
    b.stake("山本", "管理部", "部長", "方式と範囲の判断", certainty="本人申告")
    b.term("再申請", "元の申請を取り消し、内容を引き継いで新しい申請を作ること")
    b.src("memo", "d1_要望メモ.txt", "要望", date="2026-09-01")
    b.src("rule", "d1_経費申請規程.pdf", "制約", visibility="関係者限定", date="2026-04-01")
    p["prep"].update(
        understanding="申請から精算までの可視化が目的。承認後の変更は規程で禁止されているが、訂正の手順は未確認である。",
        purpose="承認後の訂正の扱いと、今回の範囲を確認する。",
        gaps=["金額の誤りの発生頻度", "訂正の現状の手順", "代理承認の運用"],
        materials=["現行の管理台帳", "差し戻しの記録"],
        agenda=["訂正の現状", "承認の例外", "今回の範囲"],
        decide_today=["訂正の方式の比較案を作ること"])
    b.fill_prep_questions(6)
    b.question("承認後に金額の誤りが見つかったとき、今はどう処理していますか。", "規程と実務の差を確認するため。", "経理課", "高")
    cands = b.ai_prepared("prep", [
        {"kind": "質問", "text": "承認後の変更を禁止する範囲はどこまでですか。", "detail": "規程は内容の変更を禁じているが、訂正の手順の記載がない。", "ask": "経理課",
         "evidence": [{"source_id": b.s["rule"], "unit_id": "", "quote": "承認された申請の内容は変更できない"}]},
        {"kind": "不足情報", "text": "金額の誤りの発生頻度が記録されていません。", "detail": "", "ask": "営業部", "evidence": []},
    ], source_ids=[b.s["memo"], b.s["rule"]])
    b.resolve_candidate(cands[0], "採用")


def step2(b):
    p = b.p
    b.src("minutes", "d1_第1回議事録.docx", "議事録", date="2026-09-08")
    b.rec("mtg2", "第2回打ち合わせ", "d1_第2回字幕.vtt", "subtitle", "2026-09-15", note="会議ツールの字幕を取り込んだもの")
    b.confirm_speakers("mtg2", {"佐藤": "佐藤", "田中": "田中", "鈴木": "鈴木", "山本": "山本"})
    b.paste("mail", "判断の確認メール", "山本：金額の訂正は再申請とする方式を承認します。\n山本：代理承認は今回は保留とします。", "議事録", "2026-09-15")
    rec = pj.get(p, "recordings", b.s["mtg2"])
    kinds = ["要望", "制約", "質問", "決定", "決定"]
    for s, k in zip(rec["segments"], kinds):
        s["kind"] = k
    rec["segments"][-1]["speaker_status"] = "未確認"

    for q in p["questions"]:
        if "承認後に金額の誤り" in q["text"]:
            q.update(status="回答済み", answer="現状は担当者が台帳を手で直している。",
                     evidence=[b.E("minutes", "金額を1桁間違えたまま承認されることが月に数件ある")])

    b.req("immut", domain="app", kind="機能", title="承認後の申請は変更しない", body="承認済みの申請は変更できない。",
          evidence=[b.E("rule", "承認された申請の内容は変更できない"), b.E("memo", "承認後の申請は変更できないようにしたい")],
          priority="高", scope="今回必須", scope_reason="規程の要件のため", decider="山本", status="提案",
          acceptance=[accept("承認済みの申請がある", "申請者が編集を試みる", "編集できない理由が表示される", "画面操作で確認")])
    b.req("resubmit", domain="app", kind="機能", title="金額の誤りは再申請で訂正する",
          body="承認後に金額の誤りが見つかったときは、元の申請を取り消し、内容を引き継いだ再申請で訂正する。",
          evidence=[b.E("mtg2", "再申請なら元の申請を取り消して新しく作る"), b.E("mtg2", "元の記録が残るので監査で説明できます")],
          exceptions="精算後の申請は対象外", priority="高", scope="今回必須", scope_reason="監査で説明できることと、現場の訂正の両立のため",
          scope_decider="山本", scope_decided_at="2026-09-15", decider="山本", status="提案", related=[],
          acceptance=[accept("承認済みの申請がある", "申請者が再申請する", "元の申請が取消となり、内容を引き継いだ下書きができる", "画面操作で確認")])
    b.req("limit", domain="app", kind="機能", title="10万円以上は部長の承認を必要とする", body="10万円以上の申請は部長の承認を必要とする。再申請でも同じ基準を適用する。",
          evidence=[b.E("rule", "10万円以上の申請は部長の承認を必要とする"), b.E("mtg2", "再申請でも金額の基準は同じです")],
          measures=[measure("部長承認の基準額", 10, "万円以上", "人が確定した設計制約", "全ての申請", "経費申請規程 第6条", "確認待ち", origin="資料に記載")],
          priority="高", scope="今回必須", scope_reason="規程の要件のため", decider="山本", status="提案",
          acceptance=[accept("金額が99,999円の申請", "提出する", "部長の承認を求めない", "境界値で確認"),
                      accept("金額が100,000円の申請", "提出する", "部長の承認を求める", "境界値で確認")])
    b.req("settled", domain="app", kind="機能", title="精算後の申請は再申請の対象外とする", body="精算後の申請は再申請できない。",
          evidence=[b.E("rule", "精算後の申請は取り消せない"), b.E("mtg2", "精算後の申請は対象外にしてください")],
          priority="高", scope="今回必須", scope_reason="規程の要件のため", decider="山本", status="提案",
          acceptance=[accept("精算済みの申請", "再申請を試みる", "実行できず理由が表示される", "画面操作で確認")])
    b.req("proxy", domain="app", kind="機能", title="代理承認", body="承認者が不在のとき、あらかじめ指名された代理者が承認できる。",
          evidence=[b.E("rule", "あらかじめ指名された代理者が承認できる")], scope="次回以降",
          scope_reason="範囲の確認が必要なため", decider="山本", status="保留", open_items="代理の範囲が未確認")
    b.req("audit", domain="app", kind="非機能", title="申請と承認の操作履歴を残す", body="申請・承認・取消の操作履歴を残し、7年間保存する。",
          evidence=[b.E("rule", "申請と承認の記録は7年間保存する")], nfr_tags=["audit", "retention"],
          priority="高", scope="今回必須", scope_reason="規程の要件のため", confirm_with="田中", status="確認待ち")
    b.req("role", domain="app", kind="機能", title="役割ごとの権限", body="申請者・承認者・経理担当の権限を分ける。", nfr_tags=["authz"],
          priority="中", scope="今回必須", confirm_with="田中", status="下書き")
    b.req("simple", domain="app", kind="画面・帳票", title="承認の画面は簡単にする", body="承認の画面はなるべく簡単にする。",
          evidence=[b.E("memo", "承認の画面はなるべく簡単にしたい")], priority="中", scope="今回できれば", confirm_with="佐藤", status="下書き")
    p["requirements"][-1]["internal_note"] = "現場の不満が強い点。社外資料には出さないこと。"

    c = b.ai_prepared("extract", [
        {"kind": "要望", "text": "承認後でも金額を訂正できるようにしたい", "detail": "佐藤の発言。精算後までは求めていない。", "ask": "",
         "evidence": [{"source_id": b.s["minutes"], "unit_id": "", "quote": "承認後でも金額を訂正できるようにしたい"}]},
        {"kind": "制約", "text": "直接変更は認めない", "detail": "田中の発言。変更履歴があっても認めないという条件つき。", "ask": "",
         "evidence": [{"source_id": b.s["minutes"], "unit_id": "", "quote": "変更履歴があっても直接変更は認めない"}]},
        {"kind": "決定", "text": "金額の訂正は再申請で進める", "detail": "話者は未確認。判断は確認メールで記録する。", "ask": "",
         "evidence": [{"source_id": b.s["mtg2"], "unit_id": "", "quote": "金額の訂正は再申請で進めます"}]},
        {"kind": "要件", "text": "訂正の上限は5回までとする", "detail": "AIの推測。資料に記載なし。", "ask": "", "evidence": []},
    ], source_ids=[b.s["minutes"]], recording_ids=[b.s["mtg2"]])
    b.resolve_candidate(c[0], "修正して採用", b.r["resubmit"])
    b.resolve_candidate(c[1], "採用", b.r["immut"])
    b.resolve_candidate(c[2], "採用", b.r["resubmit"])
    b.resolve_candidate(c[3], "却下")

    issue(p, "承認後の金額訂正の方式",
          [{"who": "佐藤（営業部）", "nature": "業務上の希望", "text": "承認後でも金額を訂正できるようにしたい", "evidence": b.E("minutes", "承認後でも金額を訂正できるようにしたい")},
           {"who": "田中（経理課）", "nature": "業務上の希望", "text": "承認後に金額を直接変更できると監査で説明できない", "evidence": b.E("minutes", "承認後に金額を直接変更できると監査で説明できない")},
           {"who": "鈴木（情報システム課）", "nature": "技術制約", "text": "3案とも実現方式の候補であり決定ではない", "evidence": b.E("minutes", "いずれも現時点では提案であり、決定ではない")}],
          "誤った金額を正しく精算し、監査で説明できる状態を保つ", "記録の連続性と訂正の手間が対立する",
          ["直接変更", "再承認", "再申請"], "山本", "山本", [b.E("minutes", "承認後でも金額を訂正できるようにしたい")], b.R("immut", "resubmit"),
          state="結論あり", conclusion="再申請を採用（DEC-001）")

    before = pj.get(p, "requirements", b.r["immut"])["body"]
    pj.update_requirement(p, b.r["immut"], {"body": "承認済みの申請は直接変更できない。金額の誤りは再申請で訂正する。"},
                          reason="DEC-001 により訂正の手順を追記", actor="デモ担当者")
    b.decide("method", "承認後の金額訂正の方式", [
        opt("A", "直接変更", "現場の手間が少ない", "変更履歴が残っても監査で説明できないと経理が判断"),
        opt("B", "再承認", "承認の記録は続く", "今回の再承認案では元の金額を保持しない"),
        opt("C", "再申請", "元の記録が残り、監査で説明できると経理が確認", "現場の入力の手間が増える")],
        "C", "元の記録が残り監査で説明できること、内容を引き継げば現場の手間も受け入れられることから再申請を採用した。",
        {"A": "この案件では、変更履歴が残る直接変更も監査で説明できないと経理が判断したため", "B": "今回の再承認案では元の金額を保持しないため"},
        "山本", "田中", "2026-09-15",
        [b.E("mtg2", "元の記録が残るので監査で説明できます"), b.E("mtg2", "元の内容を引き継げるなら受け入れます"), b.E("mail", "金額の訂正は再申請とする方式を承認します")],
        b.R("immut", "resubmit"))
    pj.get(p, "decisions", b.d["method"])["confirmation"] = "第2回の山本の発言は話者が未確認のため根拠にせず、判断は本人の確認メール（2026-09-15）で記録した。"
    b.decide("rule", "再申請に適用する規程上の基準", [opt("A", "規程の基準をそのまま適用", "規程と運用が一致する", None)], "A",
             "経費申請規程の第6条（金額基準）と第8条（精算後の取消不可）に合わせるため。", {}, "山本", "田中", "2026-09-15",
             [b.E("rule", "10万円以上の申請は部長の承認を必要とする"), b.E("rule", "精算後の申請は取り消せない"), b.E("mtg2", "再申請でも金額の基準は同じです")],
             b.R("limit", "settled"))
    ag.record_history(p, b.r["immut"], "採用", "第2回打ち合わせの論点", decision_id=b.d["method"], before=before,
                      after="承認済みの申請は直接変更できない。金額の誤りは再申請で訂正する。", meeting_date="2026-09-15",
                      proposed_on="2026-09-08", decided_on="2026-09-15", applied_on="2026-09-16",
                      options=["直接変更", "再承認", "再申請"], rationale=pj.get(p, "decisions", b.d["method"])["rationale"],
                      decider="山本", confirmer="田中", evidence=pj.get(p, "decisions", b.d["method"])["evidence"])
    b.agree("immut", "resubmit", "limit", "settled")
    b.decide("proxy", "代理承認の扱い", [opt("A", "今回対応", "不在時も止まらない", "範囲の確認が必要"), opt("B", "次回に検討", "今回の範囲を守れる", "不在時は手作業")],
             None, None, {}, "山本", None, None, [b.E("mail", "代理承認は今回は保留とします")], b.R("proxy"),
             state="保留", hold="代理の範囲の確認が済んでいないため")
    pj.get(p, "decisions", b.d["proxy"])["internal_note"] = "担当者間で意見が分かれている。"

    scenario(p, "通常の申請と承認", "通常", "申請者が申請を提出する", ["申請者が提出", "承認者が確認", "承認", "精算連携"], "精算連携が完了する", None, b.R("limit"), "申請者・承認者")
    scenario(p, "差し戻し", "例外", "承認者が内容に問題を見つける", ["承認者が差し戻す", "申請者が修正", "再提出"], "再提出される", "差し戻しの理由がない場合は実行できない", b.R("role"))
    scenario(p, "金額誤りの再申請", "例外", "承認後に金額の誤りが見つかる", ["申請者が再申請を開始", "元の申請を取消", "内容を引き継いだ下書きを修正", "再度承認"], "新しい申請が承認される", "精算後は実行できない", b.R("resubmit", "immut", "settled"))
    scenario(p, "二重操作", "例外", "同じ申請を2人が同時に操作する", ["先の操作を確定", "後の操作は最新の状態を表示して中止"], "どちらか一方のみ確定する", "後の操作者へ理由を表示", b.R("audit"))
    scenario(p, "承認者の不在と期限", "例外", "期限までに承認されない", ["未承認を通知", "代理の扱いは未決"], "未定", "代理承認が保留のため未決", b.R("proxy"))

    risk(p, "再申請の手間で現場が使わなくなる", "事実に基づく", "再申請の入力が多い場合", "訂正が遅れる", "発生頻度は月に数件という発言のみ", "内容の引き継ぎ", "佐藤",
         [b.E("minutes", "月に数件ある")], b.R("resubmit"))
    risk(p, "代理承認が未決のまま運用が始まる", "一般論", "承認者の不在時", "申請が滞る", "規程の確認が未了", "次回の範囲で再検討", "田中", [], b.R("proxy"))
    action(p, "代理承認の範囲を規程で確認する", None, None, b.R("proxy"))
    b.nfr(audit=("確認済み", "規程の7年保存を確認"), retention=("確認済み", "7年"), authz=("未確認", None))
    b.snapshot_baseline("第2回打ち合わせ後の合意版")
    doc = b.issue_doc("meeting", "第2回打ち合わせ確認資料")
    share.record_response(p, doc["id"], b.r["resubmit"], "再申請の方式で問題ありません。", "田中", "2026-09-18")


def step3(b):
    p = b.p
    b.paste("req3", "追加要望メール", "経理担当者から：承認済みの申請の金額を、経理担当者が直接訂正できるようにしたい。\n"
            "理由：月末は再申請を待つと締めに間に合わないことがある。\n"
            "申請者から：領収書の画像を添付できるようにしたい。", "要望", "2026-10-02")
    chg = ag.receive_change(p, "承認済みの申請の金額を、経理担当者が直接訂正できるようにしたい", "経理担当者", "月末は再申請を待つと締めに間に合わないことがある。",
                            [b.E("req3", "承認済みの申請の金額を、経理担当者が直接訂正できるようにしたい")], "2026-10-31", "2026-10-02", b.R("immut", "resubmit"))
    b.c["edit"] = chg["id"]
    chg2 = ag.receive_change(p, "領収書の画像を添付できるようにしたい", "申請者", None, [b.E("req3", "領収書の画像を添付できるようにしたい")], None, "2026-10-02")
    b.c["receipt"] = chg2["id"]
    chg.update(status="調査中", classification="矛盾候補")
    chg2.update(status="判断待ち", classification="新規")
    for imp in checks.related_impacts(p, b.R("immut", "resubmit")):
        ag.add_impact(p, chg["id"], imp["area"], imp["target"], imp["note"], imp["basis"])
    ag.add_impact(p, chg["id"], "権限", b.r["role"], "経理担当者に更新権限を与えることになる", "確認済み")
    ag.add_impact(p, chg["id"], "性能", None, "影響なし", "影響なし（確認済み）")
    c = b.ai_prepared("impact", [
        {"kind": "影響候補", "text": "監査で説明できない状態に戻る可能性", "detail": "過去の判断 DEC-001 の採用理由と衝突する。", "ask": "過去の判断",
         "evidence": [{"source_id": b.s["mtg2"], "unit_id": "", "quote": "元の記録が残るので監査で説明できます"}]},
        {"kind": "影響候補", "text": "履歴の保存対象が増える", "detail": "", "ask": "データ", "evidence": []},
    ], source_ids=[b.s["req3"]], recording_ids=[b.s["mtg2"]])
    b.resolve_candidate(c[0], "採用")
    ag.add_impact(p, chg["id"], "データ", b.r["audit"], "履歴の保存対象が増える可能性（AI候補）", "AI候補")
    b.scan_and_adopt()
    for x in p["conflicts"]:
        if x["state"] == "未確認":
            x["applicability"] = "承認後・精算前の申請で両立するか確認が必要"


def step4(b):
    p = b.p
    b.paste("mtg3", "第3回打ち合わせメモ", "田中：月末の締めに間に合わない問題は、再申請の下書きを経理が代行作成できれば解決する。\n"
            "山本：直接訂正は認めない。経理の代行で進める。\n"
            "山本：領収書の添付は次回の開発で検討する。", "議事録", "2026-10-09")
    dec = b.decide("edit", "経理担当者による直接訂正の要望", [
        opt("A", "経理の直接訂正", "締めに間に合う", "変更履歴が残っても監査で説明できないとした過去の判断に反する"),
        opt("B", "経理が再申請の下書きを代行", "記録が残り締めにも間に合う", "経理の作業が増える")],
        "B", "直接訂正は過去の判断（監査で説明できること）に反する。代行作成なら記録を保ったまま締めの問題を解決できる。",
        {"A": "変更履歴があっても監査で説明できないとする DEC-001 の判断と矛盾するため"},
        "山本", "田中", "2026-10-09",
        [b.E("mtg3", "再申請の下書きを経理が代行作成できれば解決する"), b.E("mtg3", "直接訂正は認めない")], b.R("resubmit"), changes=[b.c["edit"]])
    ag.apply_change(p, b.c["edit"], dec, {b.r["resubmit"]: {
        "body": "承認後に金額の誤りが見つかったときは、元の申請を取り消し、内容を引き継いだ再申請で訂正する。再申請の下書きは経理担当者が代行作成できる。"}},
        "human", applied_on="2026-10-12", actor="デモ担当者")
    pj.set_requirement_status(p, b.r["resubmit"], "合意済み", "human", "デモ担当者")
    ag.record_history(p, b.r["resubmit"], "却下", f"追加要望 {b.c['edit']}（直接訂正）", change_id=b.c["edit"], decision_id=dec,
                      proposed_on="2026-10-02", decided_on="2026-10-09", options=["経理の直接訂正", "経理が再申請の下書きを代行"],
                      rationale="変更履歴があっても監査で説明できないとする過去の判断と矛盾するため却下した。", decider="山本", confirmer="田中")
    for x in p["conflicts"]:
        if b.c["edit"] in (x["a"], x["b"]):
            x["state"] = "解消"
            x["resolution"] = "直接訂正を却下し解消（" + dec + "）"
    new = b.req("receipt", domain="app", kind="機能", title="領収書の画像添付", body="申請に領収書の画像を添付できる。",
                evidence=[b.E("req3", "領収書の画像を添付できるようにしたい")], scope="次回以降", scope_reason="今回の範囲を守るため", scope_decider="山本",
                scope_decided_at="2026-10-09", decider="山本", status="提案")
    pj.require(p, "changes", b.c["receipt"]).update(status="反映済み", related_requirements=[new])
    ag.record_history(p, new, "保留", f"追加要望 {b.c['receipt']}", change_id=b.c["receipt"], proposed_on="2026-10-02", decided_on="2026-10-09",
                      rationale="今回の範囲を守るため次回の開発で検討する。", decider="山本", evidence=[b.E("mtg3", "領収書の添付は次回の開発で検討する")])
    b.issue_doc("meeting", "第3回打ち合わせ確認資料")
    b.issue_doc("change", "追加要望確認資料", b.c["edit"])
    b.issue_doc("spec", "要件定義書")


STEPS = [step1, step2, step3, step4]
