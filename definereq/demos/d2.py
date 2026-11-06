"""デモ2：集計アプリのクラウド移行（業務アプリ＋インフラ）。強み：事前準備、非機能、アプリと基盤の境界。"""
from __future__ import annotations

from .. import project as pj
from ..export import share
from ..logic import agreement as ag
from ..logic import checks
from .builder import accept, action, issue, measure, opt, risk, scenario

ID = "d2"
NAME = "拠点売上集計の自動化とクラウド移行"
DOMAINS = ["app", "infra"]
TRAITS = ["data", "deadline", "platform", "integration"]
LEAD = "「毎朝すぐ」「データを失いたくない」を、測れる条件とアプリ・基盤の境界に分解する。"
STRENGTH = "事前準備・非機能・アプリと基盤の境界"
SUMMARY = "12拠点のExcelを手作業でまとめている売上集計を自動化し、クラウド移行も検討する案件です。"
SITUATION = "経営企画は毎朝すぐに数字を見たいのですが、「すぐ」や「失いたくない」の具体的な条件が決まっていません。"
HIGHLIGHTS = ["曖昧な要望を、完了時刻や復旧条件などに具体化する", "アプリと基盤の担当範囲を整理する"]
TOUR = [
    {"stage": 1, "page": "sources", "title": "PowerPointとExcelを読み込む", "input": "移行計画案と処理量の表", "ai": "なし", "human": "発表者ノートは対象外のまま。図の内容は人が補足", "result": "スライド別の抽出結果と未理解の図"},
    {"stage": 1, "page": "prep", "title": "分野別に質問を準備する", "input": "対象分野：業務アプリ＋インフラ", "ai": "質問候補（準備済み）", "human": "重複をまとめて確認相手を決める", "result": "共通・分野別の質問"},
    {"stage": 2, "page": "refine", "title": "曖昧な言葉を具体化する", "input": "「毎朝すぐ」「失いたくない」", "ai": "質問と受入条件案（準備済み）", "human": "数値を確認して登録する", "result": "RTO・RPO・計画停止を分けた条件"},
    {"stage": 2, "page": "nfr", "title": "非機能を確認する", "input": "要件と確認項目", "ai": "なし", "human": "未確認の項目を残す", "result": "バックアップだけでは達成としない表示"},
    {"stage": 2, "page": "issues", "title": "無停止の希望を調整する", "input": "業務の希望と基盤の条件", "ai": "なし", "human": "判断者が月1回の計画停止を判断", "result": "意見の違いと結論"},
    {"stage": 3, "page": "conflicts", "title": "締め後固定と再集計の矛盾", "input": "拠点からの再集計の要望", "ai": "なし（文型の照合）", "human": "適用範囲を確認する", "result": "矛盾の候補と調査範囲"},
    {"stage": 4, "page": "why", "title": "復旧条件の理由を聞く", "input": "「なぜ復旧は4時間以内なのか」", "ai": "なし", "human": "引用を確認", "result": "理由と根拠。保存期間は「理由の記録がありません」"},
    {"stage": 4, "page": "share", "title": "要件定義書を出力する", "input": "案件データ", "ai": "なし", "human": "未決を含めて確認待ちを明示", "result": "アプリと基盤を分けた要件定義書"},
]


def step1(b):
    p = b.p
    b.profile({"problem": "確認済み", "outcome": "仮説"},
              background="12拠点のExcelを本社の2名が毎朝手作業で統合している。現行サーバーの保守と障害対応は情報システム課だけで担っており、クラウドへの移行も検討している。",
              purpose="集計を自動化し、クラウドへ移行する。",
              problem="手作業の集計に約90分かかり、提出の遅延や重複も手で直している。",
              outcome="毎朝すぐに本社が集計結果を確認できる状態。",
              request="拠点Excelの集計の自動化とクラウド移行。",
              scope_in="売上集計の自動化と基盤の移行",
              scope_out="拠点のExcel様式の変更",
              current="拠点がExcelを提出し、本社が手作業で統合。現行サーバーは社内設置。",
              constraints="現行の月次報告の様式は変えない。")
    b.stake("高橋", "経営企画", "利用者代表", "業務条件の判断")
    b.stake("渡部", "経理", "集計業務の担当", "業務手順の確認")
    b.stake("伊藤", "情報システム課", "基盤担当", "基盤の条件の確認")
    b.stake("ベンダーA", "クラウド事業者", "基盤の保守", "保守範囲の確認", certainty="未確認", note="契約範囲は未確認")
    b.term("RTO", "目標復旧時間。障害から何時間以内に復旧するか")
    b.term("RPO", "許容データ損失。障害時に、どこまでのデータ損失を許容するか")
    pptx = b.src("plan", "d2_移行計画案.pptx", "構成・運用", date="2026-08-28")
    pptx["supplement"] = "スライド3の矢印は、拠点から自動集計への流れを示す（人の補足）。"
    b.src("load", "d2_現状の処理量.xlsx", "計測・調査", date="2026-08-31")
    b.src("ops", "d2_運用メモ.txt", "構成・運用", date="2026-08-31")
    p["prep"].update(
        understanding="集計の自動化と基盤の移行の2つが同時に動く。アプリと基盤の担当範囲の境界が未確認。",
        purpose="「毎朝すぐ」と「データを失いたくない」を確認できる条件にする。",
        gaps=["データの増加率", "障害の一次受付の担当", "復旧の手順の有無"],
        materials=["現行のバックアップ設定", "復旧手順", "障害履歴"],
        agenda=["朝の完了時刻", "復旧とデータ損失", "移行時の停止", "責任分界"],
        decide_today=["確認する数値の種類（RTO・RPO・停止時間）"])
    b.fill_prep_questions(8)
    b.question("データの増加率はどのくらいですか。", "容量の見積もりに必要なため。", "基盤担当", "高", evidence=[b.E("load", "データ増加率")])
    cands = b.ai_prepared("prep", [
        {"kind": "不足情報", "text": "データ増加率が未計測です", "detail": "処理量の表で未計測となっている。", "ask": "基盤担当",
         "evidence": [{"source_id": b.s["load"], "unit_id": "", "quote": "データ増加率"}]},
        {"kind": "質問", "text": "障害の一次受付は誰が担当しますか。", "detail": "運用メモで未定。", "ask": "プロジェクト責任者",
         "evidence": [{"source_id": b.s["ops"], "unit_id": "", "quote": "障害の一次受付の担当は未定である"}]},
    ], source_ids=[b.s["load"], b.s["ops"]])
    for c in cands:
        b.resolve_candidate(c, "採用")


def step2(b):
    p = b.p
    b.src("m1", "d2_第1回議事録.docx", "議事録", date="2026-09-03")
    b.paste("m2", "第2回打ち合わせメモ", "高橋：毎朝8時30分までに前日分の集計が終わっていればよい。朝9時の部門会議に使うためだ。\n"
            "高橋：復旧は4時間以内を目標にする。午後の報告に間に合わせるためだ。\n"
            "高橋：失ってよいのは直前の1日分の入力までとする。拠点のExcelから再取込できるからだ。\n"
            "伊藤：保守の計画停止は月1回の日曜夜に限る案で調整したい。\n"
            "高橋：日曜夜の計画停止は受け入れる。朝の集計が止まらなければよい。\n"
            "渡部：締め後の数字は翌月に訂正版を作り、元の数字は残す。\n"
            "高橋：集計データの保存期間は3年とする。\n", "議事録", "2026-09-17")
    for q in p["questions"]:
        if "許容できる停止時間" in q["text"]:
            q.update(status="回答済み", answer="日曜夜の計画停止は受け入れる。", evidence=[b.E("m2", "日曜夜の計画停止は受け入れる")])
        if "目標復旧時間" in q["text"]:
            q.update(status="回答済み", answer="RTOは4時間以内、RPOは1日分まで。", evidence=[b.E("m2", "復旧は4時間以内を目標にする")])

    b.req("auto", domain="app", kind="機能", title="拠点Excelの自動集計", body="12拠点のExcelを取り込み、自動で集計する。",
          evidence=[b.E("plan", "毎朝すぐに本社が集計結果を確認する"), b.E("load", "1日の提出ファイル数")], priority="高", scope="今回必須",
          scope_reason="取り組みの目的のため", decider="高橋", due="2026-09-30", status="提案",
          data_io="入力：拠点のExcel（最大3000行）／出力：集計結果", related=[],
          measures=[measure("1ファイルの行数", 3000, "行", "現状の計測値", "最大の拠点", "2026年8月のファイル", "計測済み", origin="資料に記載"),
                    measure("データ増加率", None, "％/年", "現状の計測値", None, "未確認", "未計測", origin="未確認")],
          acceptance=[accept("12拠点のファイルが提出済み", "集計を実行", "全拠点の合計が手作業の結果と一致する", "2026年8月分で比較")])
    b.req("morning", domain="app", kind="性能", title="毎朝8時30分までに前日分の集計を終える", body="毎朝8時30分までに前日分の集計を完了する。",
          evidence=[b.E("m1", "毎朝すぐに売上の数字を見たい"), b.E("m2", "毎朝8時30分までに前日分の集計が終わっていればよい")],
          measures=[measure("集計の完了時刻", "8:30", "まで", "必要条件", "平日、前日分、12拠点が提出済み", "第2回打ち合わせ", "確認待ち", origin="関係者が提示", verify="本番相当の測定：未実施"),
                    measure("手作業の集計時間", 90, "分", "現状の計測値", "2026年8月の平均", "担当者の記録", "計測済み", origin="資料に記載")],
          priority="高", scope="今回必須", scope_reason="部門会議に使うため", decider="高橋", due="2026-09-30", status="提案",
          acceptance=[accept("12拠点が提出済み", "朝の集計を実行", "8時30分までに完了する", "本番相当のデータで3日間測定")])
    b.req("exc", domain="app", kind="業務", title="未提出・重複・遅延の扱い", body="未提出の拠点を一覧で示し、重複ファイルは取り込まない。遅延は後から追加取込できる。",
          evidence=[b.E("load", "担当者不在の日に未提出"), b.E("load", "同じファイルを2回提出した"), b.E("load", "月に2回ほど9時を過ぎる")],
          exceptions="未提出、重複、遅延", priority="高", scope="今回必須", confirm_with="渡部", status="確認待ち")
    b.req("freeze", domain="app", kind="データ", title="締め後の数字は固定する", body="締め後の数字は固定し、訂正は翌月の訂正版として作る。元の数字は残す。",
          evidence=[b.E("m1", "締め後の数字は固定してほしい"), b.E("m2", "締め後の数字は翌月に訂正版を作り、元の数字は残す")],
          priority="高", scope="今回必須", scope_reason="月次報告と合わせるため", decider="渡部", status="提案",
          acceptance=[accept("締め後の月", "数字の変更を試みる", "変更できず、訂正版の作成へ案内される", "画面操作で確認")])
    b.req("rto", domain="infra", kind="復旧", title="障害時は4時間以内に集計を再開する", body="障害時は4時間以内に集計を再開する。",
          evidence=[b.E("m2", "復旧は4時間以内を目標にする")], nfr_tags=["recovery"],
          measures=[measure("目標復旧時間（RTO）", 4, "時間以内", "必要条件", "基盤障害時", "第2回打ち合わせ", "確認待ち", origin="関係者が提示", verify="復旧試験：未実施")],
          priority="高", scope="今回必須", scope_reason="午後の報告に間に合わせるため", decider="高橋", due="2026-10-15", status="提案",
          open_area="復旧の試験をしたことがない", confirm_with="伊藤",
          acceptance=[accept("バックアップから復旧する", "復旧試験を実施", "4時間以内に集計を再開できる", "移行前に1回試験")])
    b.req("rpo", domain="infra", kind="復旧", title="失ってよいデータは直前の1日分まで", body="障害時に失ってよいデータは直前の1日分までとする。",
          evidence=[b.E("m1", "データを失いたくない"), b.E("m2", "失ってよいのは直前の1日分の入力までとする")], nfr_tags=["backup", "recovery"],
          measures=[measure("許容データ損失（RPO）", 1, "日分", "必要条件", "基盤障害時", "第2回打ち合わせ", "確認待ち", origin="関係者が提示", verify="復旧試験：未実施"),
                    measure("バックアップの間隔", 1, "日", "現状の計測値", "現行サーバー", "第1回打ち合わせの発言", "確認待ち", origin="関係者が提示", verify="現行の設定は資料で未確認")],
          priority="高", scope="今回必須", scope_reason="拠点のExcelから再取込できるため", decider="高橋", due="2026-10-15", status="提案",
          acceptance=[accept("前日のバックアップがある", "復旧と再取込を実施", "前日分までの集計が再現できる", "移行前に1回試験")])
    b.req("downtime", domain="infra", kind="可用性", title="計画停止は月1回の日曜夜に限る", body="保守の計画停止は月1回の日曜夜に限る。朝の集計は止めない。",
          evidence=[b.E("m1", "朝の集計は止めないでほしい"), b.E("m2", "保守の計画停止は月1回の日曜夜に限る案で調整したい")], nfr_tags=["availability", "maintenance"],
          measures=[measure("計画停止の頻度", 1, "回/月", "必要条件", "日曜夜", "第2回打ち合わせ", "確認待ち", origin="関係者が提示", verify="対象外（運用の取り決め）")],
          priority="高", scope="今回必須", decider="高橋", status="提案", related=[])
    b.req("backup", domain="infra", kind="運用", title="日次バックアップを取得する", body="集計データのバックアップを日次で取得する。",
          evidence=[b.E("m1", "現行サーバーのバックアップは日次で")], nfr_tags=["backup"], priority="中", scope="今回必須", confirm_with="伊藤", status="確認待ち")
    b.req("resp", domain="infra", kind="運用", title="アプリと基盤の責任分界", body="アプリの保守は情報システム課、クラウド基盤の保守はベンダーが担当する。障害の一次受付は未定。",
          evidence=[b.E("ops", "アプリの保守は情報システム課、クラウド基盤の保守はベンダーが担当する想定である"), b.E("ops", "障害の一次受付の担当は未定である")],
          nfr_tags=["operation", "maintenance"], priority="高", scope="今回必須", open_area="障害の一次受付が未決", confirm_with="高橋", status="下書き")
    b.req("retain", domain="app", kind="データ", title="集計データの保存期間は3年とする", body="集計データの保存期間は3年とする。",
          evidence=[b.E("m2", "集計データの保存期間は3年とする")], nfr_tags=["retention"], priority="中", scope="今回必須", decider="高橋", status="提案")
    b.req("migrate", domain="infra", kind="移行", title="移行時の切替と切戻し", body="現行の手作業と自動集計を並行運用してから切り替える。切戻しの条件は未決。",
          evidence=[b.E("m1", "切替の作業で停止が必要になる可能性がある")], nfr_tags=["migration"], priority="高", scope="今回必須",
          open_area="切戻しの条件が未決", confirm_with="伊藤", status="下書き")
    r = pj.get(p, "requirements", b.r["rpo"])
    r["related"] = b.R("backup", "rto")
    pj.get(p, "requirements", b.r["freeze"])["internal_note"] = "渡部さんの負担が大きい。社外には出さない。"

    c = b.ai_prepared("refine", [
        {"kind": "質問", "text": "「毎朝すぐ」は何時までに、どの状態なら満たしますか。", "detail": "完了時刻と対象範囲が未確認。", "ask": "高橋",
         "evidence": [{"source_id": b.s["m1"], "unit_id": "", "quote": "毎朝すぐに売上の数字を見たい"}]},
        {"kind": "質問", "text": "「失いたくない」は、どの時点まで戻せればよいですか。", "detail": "許容データ損失と復旧時間は別に確認する。", "ask": "高橋",
         "evidence": [{"source_id": b.s["m1"], "unit_id": "", "quote": "データを失いたくない"}]},
        {"kind": "受入条件案", "text": "12拠点が提出済みのとき、要確認の時刻までに集計が完了する", "detail": "時刻は資料にないため要確認。", "ask": "高橋", "evidence": []},
    ], source_ids=[b.s["m1"]])
    for x in c:
        b.resolve_candidate(x, "採用", b.r["morning"])

    issue(p, "朝の集計を止めたくない希望と保守の停止",
          [{"who": "高橋（経営企画）", "nature": "業務上の希望", "text": "朝の集計は止めないでほしい", "evidence": b.E("m1", "朝の集計は止めないでほしい")},
           {"who": "伊藤（基盤担当）", "nature": "技術制約", "text": "移行のときは切替の作業で停止が必要になる可能性がある", "evidence": b.E("m1", "切替の作業で停止が必要になる可能性がある")},
           {"who": "伊藤（基盤担当）", "nature": "運用負担", "text": "保守の計画停止は月1回の日曜夜に限る案", "evidence": b.E("m2", "保守の計画停止は月1回の日曜夜に限る案で調整したい")}],
          "朝の部門会議までに集計結果を出す", "完全な無停止と、保守・移行の作業が両立しない可能性がある",
          ["完全無停止", "日曜夜の計画停止"], "高橋", "伊藤", [b.E("m2", "日曜夜の計画停止は受け入れる")], b.R("downtime"),
          state="結論あり", conclusion="朝の集計を止めないことを条件に、月1回の日曜夜の計画停止を採用", extra_questions=["移行の切替も日曜夜で収まるか"])
    issue(p, "障害の一次受付の担当", [{"who": "運用メモ", "nature": "運用負担", "text": "担当は未定", "evidence": b.E("ops", "障害の一次受付の担当は未定である")}],
          "障害時の連絡先を一本にする", "アプリと基盤のどちらの障害か最初に判別できない", ["情報システム課", "ベンダー"], "高橋", "伊藤", [], b.R("resp"), state="未調整")

    b.decide("recovery", "復旧の条件", [
        opt("A", "RTO 4時間・RPO 1日分", "現行の日次バックアップの運用に近い", "直近の入力は再取込が必要"),
        opt("B", "RTO 1時間・RPO 0", "業務への影響が小さい", "実現方式の変更が必要で、費用は未確認")],
        "A", "午後の報告に間に合えば業務上問題がなく、失ったデータは拠点のExcelから再取込できるため。",
        {"B": "業務上そこまで短い復旧を必要としていないため"}, "高橋", "伊藤", "2026-09-17",
        [b.E("m2", "復旧は4時間以内を目標にする"), b.E("m2", "拠点のExcelから再取込できるからだ")], b.R("rto", "rpo"))
    b.decide("stop", "計画停止の扱い", [opt("A", "完全無停止", "停止がない", "保守・移行の方式が限定される"), opt("B", "月1回の日曜夜に計画停止", "朝の集計に影響しない", "日曜夜は処理できない")],
             "B", "朝の集計が止まらなければ業務上問題がないため。", {"A": "保守と移行の作業を行えなくなる可能性があるため"}, "高橋", "伊藤", "2026-09-17",
             [b.E("m2", "日曜夜の計画停止は受け入れる")], b.R("downtime"))
    b.decide("fix", "締め後の数字の扱い", [opt("A", "固定し、翌月に訂正版", "月次報告と一致する", "訂正の手間がある")], "A", "月次報告と合わなくなるのを防ぐため。", {}, "渡部", "高橋", "2026-09-17",
             [b.E("m1", "月次報告と合わなくなるからだ"), b.E("m2", "締め後の数字は翌月に訂正版を作り、元の数字は残す")], b.R("freeze"))
    b.decide("store", "保存期間", [opt("A", "3年", None, None)], "A", None, {}, "高橋", None, "2026-09-17", [b.E("m2", "集計データの保存期間は3年とする")], b.R("retain"))
    for key, dkey in (("rto", "recovery"), ("rpo", "recovery"), ("downtime", "stop"), ("freeze", "fix")):
        d = pj.get(p, "decisions", b.d[dkey])
        ag.record_history(p, b.r[key], "採用", "第2回打ち合わせ", decision_id=d["id"], after=pj.get(p, "requirements", b.r[key])["body"], meeting_date="2026-09-17",
                          decided_on=d["decided_on"], options=[o["label"] for o in d["options"]], rationale=d["rationale"], decider=d["decider"], confirmer=d["confirmer"], evidence=d["evidence"])
    b.agree("rto", "rpo", "downtime", "freeze", "retain")

    scenario(p, "朝の自動集計", "通常", "拠点が前日分を提出", ["提出の確認", "自動集計", "本社が確認"], "8時30分までに完了", None, b.R("auto", "morning"))
    scenario(p, "未提出", "例外", "締切までに未提出の拠点がある", ["未提出を一覧表示", "担当者へ連絡", "遅れて追加取込"], "全拠点が反映される", "未提出のまま確定はしない", b.R("exc"))
    scenario(p, "重複提出", "例外", "同じファイルが2回提出される", ["重複を検出", "取り込まず通知"], "重複は反映されない", None, b.R("exc"))
    scenario(p, "基盤障害からの復旧", "例外", "基盤障害が発生", ["一次受付（未決）", "バックアップから復旧", "拠点のExcelを再取込", "集計を再開"], "4時間以内に再開", "切替失敗時の手順は未決", b.R("rto", "rpo", "resp"))
    scenario(p, "移行の切替失敗", "例外", "切替後に集計が失敗", ["切戻しの判断", "手作業へ戻す"], "朝の報告を手作業で実施", "切戻しの条件が未決", b.R("migrate"))

    risk(p, "復旧の試験をしたことがないため、4時間以内の復旧を確認できていない", "事実に基づく", "基盤障害の発生時", "午後の報告に間に合わない可能性", "復旧時間は未計測", "移行前に復旧試験を行う", "伊藤",
         [b.E("m1", "復旧を試験したことはない")], b.R("rto"))
    risk(p, "データ増加率が未計測で容量の見通しが立たない", "事実に基づく", "拠点や行数が増えた場合", "処理時間の増加", "増加率が未計測", "計測する", "伊藤", [b.E("load", "データ増加率")], b.R("auto"))
    action(p, "データ増加率を計測する", "伊藤", None, b.R("auto"))
    action(p, "障害の一次受付の担当を決める", None, None, b.R("resp"))
    b.nfr(performance=("未確認", "8時30分までの完了は関係者が提示した条件。実測は未実施"), throughput=("確認済み", "12ファイル・最大3000行"), availability=("確認済み", "日曜夜の計画停止"),
          recovery=("未確認", "RTO・RPOの要求値は合意済み。達成できるかは復旧試験が未実施のため未検証"), backup=("未確認", "現行は日次。クラウド側の設定は未確認"), monitoring=("未確認", None))
    b.snapshot_baseline("第2回打ち合わせ後の合意版")
    doc = b.issue_doc("meeting", "第2回打ち合わせ確認資料")
    share.record_response(p, doc["id"], b.r["rto"], "4時間以内で問題ありません。", "高橋", "2026-09-22")


def step3(b):
    p = b.p
    b.paste("req3", "拠点からの要望", "福岡拠点から：締め後でも当月の数字を再集計したい。遅れて届いた訂正を当月に反映したい。\n"
            "経営企画から：拠点別の予実グラフも欲しい。\n", "要望", "2026-10-06")
    chg = ag.receive_change(p, "締め後でも当月の数字を再集計したい", "福岡拠点", "遅れて届いた訂正を当月に反映したい。", [b.E("req3", "締め後でも当月の数字を再集計したい")], None, "2026-10-06", b.R("freeze"))
    b.c["recalc"] = chg["id"]
    chg2 = ag.receive_change(p, "拠点別の予実グラフも欲しい", "経営企画", None, [b.E("req3", "拠点別の予実グラフも欲しい")], None, "2026-10-06")
    b.c["graph"] = chg2["id"]
    chg.update(status="調査中", classification="矛盾候補")
    chg2.update(status="判断待ち", classification="新規")
    for imp in checks.related_impacts(p, b.R("freeze")):
        ag.add_impact(p, chg["id"], imp["area"], imp["target"], imp["note"], imp["basis"])
    ag.add_impact(p, chg["id"], "データ", b.r["freeze"], "月次報告の数字と集計の数字が一致しなくなる可能性", "確認済み")
    ag.add_impact(p, chg["id"], "性能", b.r["morning"], "再集計の処理が朝の集計と重なる可能性（未計測）", "AI候補")
    ag.add_impact(p, chg["id"], "運用", None, "再集計の実施者が未決", "未調査")
    b.scan_and_adopt()


def step4(b):
    p = b.p
    b.paste("m3", "第3回打ち合わせメモ", "高橋：当月の再集計は認めない。訂正版で対応する。月次報告との一致を優先する。\n"
            "渡部：訂正版の作成は翌営業日までに行う。\n"
            "高橋：予実グラフは次回以降にする。\n", "議事録", "2026-10-13")
    dec = b.decide("recalc", "締め後の再集計の要望", [
        opt("A", "当月の再集計を認める", "数字がすぐ直る", "月次報告と合わなくなる"),
        opt("B", "翌月の訂正版で対応（現行どおり）", "月次報告と一致する", "反映が遅れる"),
        opt("C", "訂正版を翌営業日までに作成", "月次報告と一致し、反映も早い", "渡部の作業が増える")],
        "C", "月次報告との一致を優先しつつ、反映の遅れを小さくするため。", {"A": "月次報告との一致を優先するため", "B": "反映の遅れを短縮できるため"},
        "高橋", "渡部", "2026-10-13", [b.E("m3", "当月の再集計は認めない"), b.E("m3", "訂正版の作成は翌営業日までに行う")], b.R("freeze"), changes=[b.c["recalc"]])
    ag.apply_change(p, b.c["recalc"], dec, {b.r["freeze"]: {
        "body": "締め後の数字は固定し、訂正は訂正版として翌営業日までに作る。元の数字は残す。"}}, "human", applied_on="2026-10-14", actor="デモ担当者")
    pj.set_requirement_status(p, b.r["freeze"], "合意済み", "human", "デモ担当者")
    for x in p["conflicts"]:
        if b.c["recalc"] in (x["a"], x["b"]):
            x["state"] = "解消"
            x["resolution"] = f"当月の再集計は認めず訂正版で対応（{dec}）"
    new = b.req("graph", domain="app", kind="画面・帳票", title="拠点別の予実グラフ", body="拠点別の予実グラフを表示する。", evidence=[b.E("req3", "拠点別の予実グラフも欲しい")],
                scope="次回以降", scope_reason="今回の範囲を守るため", scope_decider="高橋", scope_decided_at="2026-10-13", decider="高橋", status="提案")
    pj.require(p, "changes", b.c["graph"]).update(status="反映済み", related_requirements=[new])
    ag.record_history(p, new, "保留", f"追加要望 {b.c['graph']}", change_id=b.c["graph"], decided_on="2026-10-13", rationale="今回の範囲を守るため次回以降に検討する。", decider="高橋",
                      evidence=[b.E("m3", "予実グラフは次回以降にする")])
    b.issue_doc("meeting", "第3回打ち合わせ確認資料")
    b.issue_doc("change", "追加要望確認資料", b.c["recalc"])
    b.issue_doc("spec", "要件定義書")


STEPS = [step1, step2, step3, step4]
