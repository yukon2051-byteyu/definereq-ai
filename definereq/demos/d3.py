"""デモ3：拠点ネットワークと遠隔保守（ネットワーク）。強み：録画根拠、ネットワーク条件、調整、変更影響。"""
from __future__ import annotations

from .. import project as pj
from ..export import share
from ..logic import agreement as ag
from ..logic import checks
from .builder import accept, action, issue, measure, opt, risk, scenario

ID = "d3"
NAME = "拠点ネットワーク更新と遠隔保守"
DOMAINS = ["network"]
TRAITS = ["comms", "confidential"]
LEAD = "録画の発言を根拠に、外部接続の禁止と遠隔保守の要望を調整する。提案は提案のまま扱う。"
STRENGTH = "録画根拠・ネットワーク条件・調整・変更影響"
SUMMARY = "大阪拠点のネットワークを更新し、障害時の保守の進め方も見直す案件です。"
SITUATION = "保守会社は障害対応を早めるために遠隔保守を提案していますが、社内規程では外部からの接続が禁止されています。"
HIGHLIGHTS = ["録画の発言を根拠として確認する", "提案・制約・合意を区別し、調整事項を整理する"]
VIDEO = "d3_拠点ネットワーク定例.mp4"
TOUR = [
    {"stage": 1, "page": "sources", "title": "通信一覧と構成図を読み込む", "input": "通信一覧、構成説明、規程抜粋", "ai": "なし", "human": "線のつながりは人が補足する", "result": "ポートは未確認のまま。図は未理解と表示"},
    {"stage": 2, "page": "recordings", "title": "録画の発言を確認する", "input": "架空の音声付き録画（MP4）", "ai": "準備済みの文字起こし", "human": "話者を確認する", "result": "時刻付きの発言。提案と決定を区別"},
    {"stage": 2, "page": "refine", "title": "「速く、止まりにくく」を具体化する", "input": "拠点長の発言", "ai": "質問候補（準備済み）", "human": "未計測は未計測のまま登録", "result": "通信量と切替時間は未計測"},
    {"stage": 2, "page": "decisions", "title": "提案を合意にしない", "input": "保守担当の遠隔保守の提案", "ai": "なし", "human": "状態は確認待ちのまま", "result": "発言だけでは合意にならない"},
    {"stage": 3, "page": "changes", "title": "追加要望の影響を調べる", "input": "常時接続の要望", "ai": "影響候補（準備済み）", "human": "受付のみ", "result": "分離・認証・責任分界への影響"},
    {"stage": 4, "page": "issues", "title": "方式を比較して判断する", "input": "3つの保守方式", "ai": "なし", "human": "セキュリティ責任者が判断", "result": "今回は現地対応。時間限定の接続は次回"},
    {"stage": 4, "page": "why", "title": "遠隔保守の扱いを聞く", "input": "「なぜ遠隔保守を今回やらないのか」", "ai": "なし", "human": "引用の時刻を確認", "result": "理由と時刻付きの引用"},
    {"stage": 4, "page": "share", "title": "確認資料を出力する", "input": "案件データ", "ai": "なし", "human": "録画の全文は載せない", "result": "選んだ引用だけの資料"},
]


def step1(b):
    p = b.p
    b.profile({"problem": "仮説", "current": "確認済み"},
              background="大阪拠点のネットワーク更新を検討している。",
              purpose="受発注の業務が止まりにくい通信環境にする。",
              problem="朝の時間帯に画面が遅くなると現場が申告している（通信量は未計測）。",
              request="回線を速く、止まりにくくしてほしい。保守会社から遠隔保守の提案がある。",
              scope_in="大阪拠点と本社の間の通信",
              current="拠点間は主回線1本で接続している。障害時は保守会社の担当者が拠点へ出向いて対応している。",
              constraints="社外から社内ネットワークへの外部接続は規程で禁止。")
    b.stake("中村", "情報システム課", "担当", "要件の取りまとめ")
    b.stake("小林", "大阪拠点", "拠点長", "業務条件の判断")
    b.stake("岡田", "保守会社", "保守担当", "保守の提案（判断権限なし）", certainty="本人申告")
    b.stake("森", "情報セキュリティ", "責任者", "例外の承認", certainty="未確認", note="第2回から参加予定")
    b.term("切戻し", "切替に失敗したときに元の状態へ戻すこと")
    b.src("flow", "d3_通信一覧.xlsx", "構成・運用", date="2026-09-01")
    s = b.src("topo", "d3_構成説明.pptx", "構成・運用", date="2026-09-01")
    s["supplement"] = "図の線は、大阪拠点と本社、本社と保守会社の接続を示す想定（人の補足。未確認）。"
    b.src("rule", "d3_情報セキュリティ規程抜粋.txt", "制約", visibility="社内のみ", date="2026-04-01")
    b.paste("mnt", "保守の現状メモ", "障害時は保守会社の担当者が大阪拠点へ出向いて対応している。\n現地に到着するまで時間がかかるため、障害対応に時間がかかっている。", "構成・運用", "2026-09-01")
    p["prep"].update(
        understanding="回線の速度と止まりにくさの要望があるが、通信量と切替時間は未計測である。遠隔保守は外部接続の禁止に関わる。",
        purpose="業務の条件と、遠隔保守の扱いを確認する。",
        gaps=["通信量", "ピークの時間帯", "切替時間", "停止の許容時間"],
        materials=["通信量の計測結果", "障害履歴"],
        agenda=["通信の用途", "障害時の業務", "遠隔保守の提案"],
        decide_today=["計測する項目"])
    b.fill_prep_questions(8)
    cands = b.ai_prepared("prep", [
        {"kind": "質問", "text": "外部接続の禁止に例外の手続きはありますか。", "detail": "規程の第13条に例外の記載がある。", "ask": "情報セキュリティ責任者",
         "evidence": [{"source_id": b.s["rule"], "unit_id": "", "quote": "事前承認により例外を認めることがある"}]},
        {"kind": "不足情報", "text": "通信のポートが未確認です", "detail": "通信一覧のポート欄が未確認。創作しないこと。", "ask": "ネットワーク担当",
         "evidence": [{"source_id": b.s["flow"], "unit_id": "", "quote": "未確認"}]},
    ], source_ids=[b.s["flow"], b.s["rule"]])
    for c in cands:
        b.resolve_candidate(c, "採用")


def step2(b):
    p = b.p
    b.rec("video", "拠点ネットワーク定例（録画）", "d3_準備済み文字起こし.vtt", "prepared", "2026-09-10", note=f"元動画：{VIDEO}（架空の合成音声）")
    rec = pj.get(p, "recordings", b.s["video"])
    rec["video_file"] = VIDEO
    b.confirm_speakers("video", {"中村": "中村", "小林": "小林", "岡田": "岡田"})
    for s, k in zip(rec["segments"], ["その他", "要望", "制約", "提案", "制約", "提案", "要望", "保留"]):
        s["kind"] = k
    b.paste("m2", "第2回定例メモ", "小林：受発注の停止は30分までなら紙の伝票で対応できる。\n"
            "小林：朝9時の受発注の画面は3秒以内で開いてほしい。\n"
            "中村：通信量の計測は10月に1週間行う。\n"
            "森：外部接続の例外は、接続者、時間、作業内容のログがそろう場合に検討できる。\n"
            "岡田：回線が切れた場合の代替回線の切替時間はまだ測定していない。\n", "議事録", "2026-09-24")

    b.req("resp", domain="network", kind="性能", title="受発注の画面は3秒以内に開く", body="朝9時の受発注の時間帯に、受発注の画面が3秒以内に開く。",
          evidence=[b.E("video", "朝九時の受発注の時間帯に画面が遅くなります"), b.E("m2", "朝9時の受発注の画面は3秒以内で開いてほしい")],
          measures=[measure("画面の表示時間", 3, "秒以内", "必要条件", "平日9時台、大阪拠点の端末", "第2回定例", "確認待ち", origin="関係者が提示"),
                    measure("ピーク時の通信量", None, "Mbps", "現状の計測値", "平日9時台", "未計測", "未計測", origin="未確認")],
          priority="高", scope="今回必須", scope_reason="業務の中心のため", decider="小林", due="2026-10-30", status="確認待ち",
          acceptance=[accept("平日9時台", "受発注の画面を開く", "3秒以内に表示される", "計測の結果で確認")])
    b.req("flowlist", domain="network", kind="通信", title="受発注の通信を確保する", body="大阪拠点の端末から本社の受発注サーバーへの通信を確保する。ポートは未確認。",
          evidence=[b.E("flow", "本社の受発注サーバー"), b.E("flow", "受発注")], priority="高", scope="今回必須", confirm_with="中村", status="確認待ち")
    b.req("fail", domain="network", kind="障害", title="回線断のとき受発注を続ける", body="回線が切れたときも受発注だけは続ける。代替の方式は未決。停止の許容は30分まで。",
          evidence=[b.E("video", "回線が切れたときは、受発注だけでも続けたいです"), b.E("m2", "受発注の停止は30分までなら紙の伝票で対応できる")],
          measures=[measure("許容停止時間", 30, "分まで", "必要条件", "受発注、平日", "第2回定例", "確認待ち", origin="関係者が提示"),
                    measure("代替回線への切替時間", None, "分", "現状の計測値", None, "未計測", "未計測", origin="未確認")],
          nfr_tags=["failure", "availability"], priority="高", scope="今回必須", scope_reason="業務の継続のため", decider="小林", due="2026-10-30",
          open_area="代替経路の方式が未決", status="確認待ち",
          acceptance=[accept("主回線が切れた", "切替または紙の伝票へ移行", "30分以内に受発注を再開する", "切替試験で確認")])
    b.req("redund", domain="network", kind="接続", title="回線を二重化する", body="拠点間の回線を二重化する（実現方式の候補）。", evidence=[b.E("topo", "代替回線はない")],
          nfr_tags=["availability"], priority="中", scope="判断待ち", confirm_with="中村", status="提案",
          measures=[measure("回線の二重化", None, None, "実現方式の候補", None, "候補であり決定ではない", "確認待ち", origin="未確認")])
    b.req("noext", domain="network", kind="分離", title="外部からの接続は禁止する", body="社外から社内ネットワークへの外部接続は禁止する。",
          evidence=[b.E("rule", "社外から社内ネットワークへの外部接続は禁止する"), b.E("video", "当社の規程では外部からの接続は禁止です")], nfr_tags=["auth"],
          priority="高", scope="今回必須", scope_reason="規程のため", decider="森", due="2026-10-15", status="提案")
    b.req("remote", domain="network", kind="認証", title="保守会社の遠隔保守", body="保守会社が遠隔保守を行う（提案）。接続者、時間、作業内容のログと承認者の条件は未確認。",
          evidence=[b.E("video", "外部からの遠隔保守を提案します"), b.E("video", "接続時間を限定して、承認者が都度許可する方式なら運用できると思います")],
          nfr_tags=["auth", "audit", "maintenance"], priority="中", scope="判断待ち", decider="森", due="2026-10-15", status="提案", open_area="責任分界と承認者が未決")
    b.req("log", domain="network", kind="運用", title="例外接続のログを保存する", body="例外の接続は、接続者、時間、作業内容のログを保存する。", evidence=[b.E("rule", "接続者、時間、作業内容のログを保存する")],
          nfr_tags=["audit"], priority="高", scope="今回必須", decider="森", status="提案")
    b.req("cut", domain="network", kind="障害", title="工事の切戻し", body="工事に失敗したときは元の回線へ切り戻す。判断基準は未決。", nfr_tags=["migration"], priority="高", scope="今回必須", open_area="切戻しの判断基準が未決", confirm_with="小林", status="下書き")
    pj.get(p, "requirements", b.r["redund"])["internal_note"] = "保守会社には費用の話をまだしない。"

    c = b.ai_prepared("refine", [
        {"kind": "質問", "text": "「速い」は、どの画面が、何秒以内なら満たしますか。", "detail": "", "ask": "小林",
         "evidence": [{"source_id": b.s["video"], "unit_id": "", "quote": "現場の要望は、速くて止まりにくい回線です"}]},
        {"kind": "質問", "text": "「止まりにくい」は、どの障害で、何分の停止まで許容しますか。", "detail": "", "ask": "小林",
         "evidence": [{"source_id": b.s["video"], "unit_id": "", "quote": "停止が何分まで許容できるかは持ち帰ります"}]},
    ], recording_ids=[b.s["video"]])
    b.resolve_candidate(c[0], "採用", b.r["resp"])
    b.resolve_candidate(c[1], "採用", b.r["fail"])
    c2 = b.ai_prepared("extract", [
        {"kind": "要件", "text": "遠隔保守を採用する", "detail": "岡田の発言。提案であり、決定ではない。", "ask": "",
         "evidence": [{"source_id": b.s["video"], "unit_id": "", "quote": "外部からの遠隔保守を提案します"}]},
        {"kind": "保留", "text": "遠隔保守はまだ提案の段階", "detail": "中村の発言。", "ask": "",
         "evidence": [{"source_id": b.s["video"], "unit_id": "", "quote": "遠隔保守はまだ提案の段階で、決定ではありません"}]},
    ], recording_ids=[b.s["video"]])
    b.resolve_candidate(c2[0], "却下")
    b.resolve_candidate(c2[1], "採用", b.r["remote"])

    issue(p, "外部接続の禁止と遠隔保守",
          [{"who": "岡田（保守会社）", "nature": "業務上の希望", "text": "障害対応を早くするために遠隔保守を提案", "evidence": b.E("video", "障害対応を早くするために、外部からの遠隔保守を提案します")},
           {"who": "中村（情報システム課）", "nature": "技術制約", "text": "規程では外部からの接続は禁止", "evidence": b.E("video", "当社の規程では外部からの接続は禁止です")},
           {"who": "森（情報セキュリティ）", "nature": "運用負担", "text": "ログがそろう場合に例外を検討できる", "evidence": b.E("m2", "接続者、時間、作業内容のログがそろう場合に検討できる")}],
          "障害時に業務を早く再開する", "外部接続の禁止と、遠隔からの保守作業が両立するか", ["常時の遠隔接続", "時間限定・都度承認の接続", "現地対応"],
          "森", "森", [b.E("m2", "接続者、時間、作業内容のログがそろう場合に検討できる")], b.R("noext", "remote"), state="判断待ち",
          extra_questions=["承認者は誰か", "接続の時間帯はいつか", "ログは誰が確認するか"])
    b.decide("remote", "遠隔保守の扱い", [
        opt("A", "常時の遠隔接続", "障害対応が早い", "規程の例外の条件を満たしにくい"),
        opt("B", "時間限定・都度承認の接続", "ログと承認を残せる", "承認者の運用負担、責任分界が未決"),
        opt("C", "現地対応", "外部接続が不要", "到着までの時間がかかる")],
        None, None, {}, "森", None, None, [b.E("video", "外部からの遠隔保守を提案します")], b.R("remote"), state="確認待ち")
    scenario(p, "通常の受発注", "通常", "拠点の端末が受発注の画面を開く", ["端末から本社へ接続", "受発注を入力"], "受発注が完了", None, b.R("resp", "flowlist"))
    scenario(p, "回線断", "例外", "主回線が切れる", ["切断を検知", "代替手段へ移行（方式は未決）", "紙の伝票で受発注", "復旧後に入力"], "受発注を再開", "代替回線がない場合は紙の伝票", b.R("fail"))
    scenario(p, "認証失敗", "例外", "利用者の認証に失敗する", ["失敗を通知", "問い合わせ先へ連絡"], "認証が復旧", "認証基盤の障害時の扱いは未決", b.R("noext"))
    scenario(p, "工事の切戻し", "例外", "工事で通信を確認できない", ["判断基準に照らす（未決）", "元の回線へ切り戻す"], "元の通信を確認", "判断者が未決", b.R("cut"))
    risk(p, "通信量が未計測のまま帯域の条件を決めてしまう", "事実に基づく", "計測前に回線を選定した場合", "朝の遅さが解消しない可能性", "実測がない", "10月に1週間計測する", "中村", [b.E("video", "通信量はまだ計測していません")], b.R("resp"))
    risk(p, "切替時間が未計測のまま30分以内と判断してしまう", "事実に基づく", "回線断の発生時", "受発注の停止が長引く", "切替時間は未測定", "切替試験を行う", "岡田", [b.E("m2", "代替回線の切替時間はまだ測定していない")], b.R("fail"))
    action(p, "通信量を1週間計測する", "中村", None, b.R("resp"))
    action(p, "例外接続の承認者を確認する", None, None, b.R("remote"))
    b.nfr(performance=("未確認", "3秒以内の要望。実測なし"), availability=("未確認", "30分までの停止。切替時間は未計測"), audit=("確認済み", "規程でログの保存を確認"), monitoring=("未確認", None))
    b.snapshot_baseline("第2回定例後の版")
    b.issue_doc("meeting", "第2回定例 確認資料")


def step3(b):
    p = b.p
    b.paste("req3", "保守会社からの要望", "保守会社から：障害時に備えて、常時接続の遠隔保守を設定させてほしい。\n", "要望", "2026-10-05")
    chg = ag.receive_change(p, "障害時に備えて、常時接続の遠隔保守を設定したい", "保守会社（岡田）", "障害対応の時間を短くするため。", [b.E("req3", "常時接続の遠隔保守を設定させてほしい")], None, "2026-10-05", b.R("remote", "noext"))
    b.c["always"] = chg["id"]
    chg.update(status="調査中", classification="矛盾候補")
    for imp in checks.related_impacts(p, b.R("remote", "noext")):
        ag.add_impact(p, chg["id"], imp["area"], imp["target"], imp["note"], imp["basis"])
    ag.add_impact(p, chg["id"], "分離", b.r["noext"], "外部接続の禁止と衝突する", "確認済み")
    ag.add_impact(p, chg["id"], "責任分界", None, "接続の管理者が未決", "未調査")
    c = b.ai_prepared("impact", [
        {"kind": "影響候補", "text": "常時接続ではログの確認の負担が増える", "detail": "規程の第14条に関連。", "ask": "運用",
         "evidence": [{"source_id": b.s["rule"], "unit_id": "", "quote": "接続者、時間、作業内容のログを保存する"}]},
    ], source_ids=[b.s["rule"], b.s["req3"]])
    b.resolve_candidate(c[0], "採用")
    ag.add_impact(p, chg["id"], "運用", b.r["log"], "常時接続ではログの確認の負担が増える", "AI候補")
    b.scan_and_adopt()


def step4(b):
    p = b.p
    b.paste("m3", "第3回定例メモ", "森：常時接続は認めない。\n"
            "森：今回は現地対応とし、時間限定の接続は次回以降に検討する。規程の例外の条件がそろっていないためだ。\n"
            "小林：現地対応でも紙の伝票で30分はしのげるので受け入れる。\n", "議事録", "2026-10-12")
    d = pj.get(p, "decisions", b.d["remote"])
    d.update(adopted="C", rationale="規程の例外の条件（ログ、承認者）がそろっていないため。業務は紙の伝票で30分はしのげる。",
             rejected_reasons={"A": "常時接続は認めないと判断したため", "B": "承認者とログの運用が未決のため次回以降に検討する"},
             confirmer="小林", decided_on="2026-10-12", related_changes=[b.c["always"]],
             evidence=d["evidence"] + [b.E("m3", "今回は現地対応とし、時間限定の接続は次回以降に検討する"), b.E("m3", "紙の伝票で30分はしのげる")])
    ag.set_state(p, d["id"], "合意済み", "human", "デモ担当者")
    ag.apply_change(p, b.c["always"], d["id"], {b.r["remote"]: {
        "title": "保守は現地対応とする", "body": "今回の保守は現地対応とする。時間限定の遠隔接続は次回以降に検討する。",
        "scope": "今回必須", "scope_reason": "規程の例外の条件がそろっていないため", "scope_decider": "森", "scope_decided_at": "2026-10-12"}},
        "human", applied_on="2026-10-13", actor="デモ担当者")
    pj.set_requirement_status(p, b.r["remote"], "合意済み", "human", "デモ担当者")
    ag.record_history(p, b.r["remote"], "却下", f"追加要望 {b.c['always']}（常時接続）", change_id=b.c["always"], decision_id=d["id"], proposed_on="2026-10-05", decided_on="2026-10-12",
                      rationale="常時接続は認めないと判断したため。", decider="森", evidence=[b.E("m3", "常時接続は認めない")])
    for x in p["conflicts"]:
        if b.c["always"] in (x["a"], x["b"]):
            x["state"] = "解消"
            x["resolution"] = f"現地対応を採用（{d['id']}）"
    i = p["issues"][0]
    i.update(state="結論あり", conclusion=f"今回は現地対応。時間限定の接続は次回以降に検討（{d['id']}）")
    new = b.req("limited", domain="network", kind="認証", title="時間限定の遠隔接続", body="時間を限定し、承認者が都度許可する遠隔接続を検討する。",
                evidence=[b.E("video", "接続時間を限定して、承認者が都度許可する方式なら運用できると思います"), b.E("m3", "時間限定の接続は次回以降に検討する")],
                scope="次回以降", scope_reason="承認者とログの運用が未決のため", scope_decider="森", scope_decided_at="2026-10-12", decider="森", status="提案", split_from=b.r["remote"])
    pj.require(p, "requirements", b.r["remote"]).setdefault("replaced_by", []).append(new)
    b.scan_and_adopt()
    for x in p["conflicts"]:
        if x["state"] == "未確認" and b.r["remote"] in (x["a"], x["b"]):
            x["state"] = "矛盾なしと確認"
            x["applicability"] = "今回は現地対応のため外部接続は発生しない。時間限定の接続は次回の検討で再確認する。"
    b.issue_doc("meeting", "第3回定例 確認資料")
    b.issue_doc("change", "追加要望確認資料", b.c["always"])
    b.issue_doc("spec", "要件定義書")


STEPS = [step1, step2, step3, step4]
