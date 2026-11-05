"""デモ用のサンプル資料を生成する（開発時に1回だけ実行。全て架空のデータ）。

生成先：definereq/demos/files/
- 録画は Windows の音声合成（Microsoft Haruka）で作った架空の会議音声に、静止画の映像を合わせたもの
- reportlab と音声合成は開発時のみ必要で、公開環境には不要
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import wave
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "definereq" / "demos" / "files"
OUT.mkdir(parents=True, exist_ok=True)


# ---- デモ1：申請・承認アプリ ----
D1_MEMO = """経費申請アプリの要望メモ（架空の会社：サンプル工業）
背景：紙とExcelの申請で、承認までの状況が見えない。
目的：申請から精算までを一つのアプリで追えるようにする。
要望：申請、承認、差し戻し、精算連携を画面で行いたい。
要望：承認後の申請は変更できないようにしたい。監査で説明できる状態を保ちたい。
要望：承認の画面はなるべく簡単にしたい。
制約：次の決算期までに利用を開始したい。
"""

D1_RULES = [
    "経費申請規程（架空）",
    "第5条 承認された申請の内容は変更できない。",
    "第6条 10万円以上の申請は部長の承認を必要とする。",
    "第7条 承認者が不在のときは、あらかじめ指名された代理者が承認できる。",
    "第8条 精算後の申請は取り消せない。",
    "第9条 申請と承認の記録は7年間保存する。",
]

D1_VTT = """WEBVTT

00:00:03.000 --> 00:00:11.000
<v 佐藤>再申請なら元の申請を取り消して新しく作るということですね。元の内容を引き継げるなら受け入れます。

00:00:12.000 --> 00:00:21.000
<v 田中>再申請であれば元の記録が残るので監査で説明できます。精算後の申請は対象外にしてください。

00:00:22.000 --> 00:00:28.000
<v 鈴木>10万円以上は再申請でも部長の承認が必要という理解でよいでしょうか。

00:00:29.000 --> 00:00:33.000
<v 田中>はい、再申請でも金額の基準は同じです。

00:00:34.000 --> 00:00:42.000
<v 山本>金額の訂正は再申請で進めます。代理承認は今回は保留にしましょう。
"""


def make_d1():
    (OUT / "d1_要望メモ.txt").write_text(D1_MEMO, encoding="utf-8")
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    c = canvas.Canvas(str(OUT / "d1_経費申請規程.pdf"))
    y = 780
    for i, line in enumerate(D1_RULES):
        c.setFont("HeiseiKakuGo-W5", 15 if i == 0 else 11)
        c.drawString(60, y, line)
        y -= 30
    c.showPage()
    c.save()

    from docx import Document

    d = Document()
    d.add_heading("第1回打ち合わせ議事録（架空）", 0)
    d.add_paragraph("開催日：2026-09-08")
    d.add_heading("出席者", 1)
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "氏名", "所属"
    for n, o in (("佐藤", "営業部（申請者の代表）"), ("田中", "経理課長"), ("鈴木", "情報システム課"), ("山本", "管理部長")):
        cells = t.add_row().cells
        cells[0].text, cells[1].text = n, o
    d.add_heading("発言要旨", 1)
    for line in ("佐藤：金額を1桁間違えたまま承認されることが月に数件ある。承認後でも金額を訂正できるようにしたい。",
                 "田中：承認後に金額を直接変更できると監査で説明できない。変更履歴があっても直接変更は認めない。",
                 "鈴木：直接変更、再承認、再申請の3案が考えられる。いずれも現時点では提案であり、決定ではない。",
                 "佐藤：精算が終わった申請まで直したいわけではない。",
                 "田中：代理承認の範囲は規程の確認が必要である。"):
        d.add_paragraph(line)
    d.add_heading("宿題", 1)
    d.add_paragraph("鈴木：3案の比較を次回までに用意する。")
    d.save(OUT / "d1_第1回議事録.docx")
    (OUT / "d1_第2回字幕.vtt").write_text(D1_VTT, encoding="utf-8")


# ---- デモ2：集計アプリのクラウド移行 ----
def make_d2():
    from io import BytesIO

    from PIL import Image, ImageDraw
    from pptx import Presentation
    from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
    from pptx.util import Cm, Pt

    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "拠点売上集計の自動化とクラウド移行（架空）"
    s.placeholders[1].text = "第1回検討資料"

    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "現状の集計業務"
    tb = s.shapes.add_table(4, 3, Cm(1.5), Cm(4), Cm(22), Cm(5)).table
    rows = [("項目", "現状", "備考"), ("拠点数", "12拠点", "各拠点がExcelを提出"), ("集計担当", "本社2名", "毎朝手作業で統合"),
            ("集計時間", "約90分", "2026年8月の担当者の記録")]
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            tb.cell(r, c).text = v
    s.notes_slide.notes_text_frame.text = "社内メモ：担当者の異動の話は外部に出さないこと。"

    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "想定する処理の流れ"
    a = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Cm(2), Cm(6), Cm(6), Cm(2.5))
    a.text_frame.text = "拠点のExcel提出"
    b = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Cm(13), Cm(6), Cm(6), Cm(2.5))
    b.text_frame.text = "クラウドで自動集計"
    s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Cm(8), Cm(7.2), Cm(13), Cm(7.2))
    grp = s.shapes.add_group_shape()
    g1 = grp.shapes.add_textbox(Cm(2), Cm(10), Cm(8), Cm(1))
    g1.text_frame.text = "毎朝すぐに本社が集計結果を確認する"
    g2 = grp.shapes.add_textbox(Cm(2), Cm(11), Cm(8), Cm(1))
    g2.text_frame.text = "締め後の数字は固定する"
    img = Image.new("RGB", (480, 200), "#EEF0F3")
    ImageDraw.Draw(img).rectangle((40, 60, 200, 140), outline="#555555", width=3)
    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    s.shapes.add_picture(buf, Cm(14), Cm(10), Cm(9), Cm(3.5))
    prs.save(OUT / "d2_移行計画案.pptx")

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "現状の処理量"
    ws.append(["項目", "値", "単位", "測定条件", "根拠"])
    ws.append(["1日の提出ファイル数", 12, "件", "2026年8月の平日", "担当者の記録"])
    ws.append(["1ファイルの行数", 3000, "行", "最大の拠点", "2026年8月のファイルで確認"])
    ws.append(["手作業の集計時間", 90, "分", "2026年8月の平均", "担当者の記録"])
    ws.append(["データ増加率", None, "％/年", "未計測", "未確認"])
    ws2 = wb.create_sheet("提出の実績")
    ws2.append(["拠点", "締切の順守", "備考"])
    ws2.append(["大阪", "遅延あり", "月に2回ほど9時を過ぎる"])
    ws2.append(["福岡", "未提出あり", "担当者不在の日に未提出"])
    ws2.append(["札幌", "重複あり", "同じファイルを2回提出した"])
    wb.save(OUT / "d2_現状の処理量.xlsx")

    from docx import Document

    d = Document()
    d.add_heading("第1回打ち合わせ議事録（架空）", 0)
    d.add_paragraph("開催日：2026-09-03")
    d.add_heading("発言要旨", 1)
    for line in ("高橋（経営企画）：毎朝すぐに売上の数字を見たい。",
                 "高橋（経営企画）：データを失いたくない。集計データは絶対に守ってほしい。",
                 "伊藤（基盤担当）：現行サーバーのバックアップは日次で、夜間に取得している。",
                 "伊藤（基盤担当）：移行のときは切替の作業で停止が必要になる可能性がある。",
                 "高橋（経営企画）：朝の集計は止めないでほしい。",
                 "渡部（業務担当）：締め後の数字は固定してほしい。月次報告と合わなくなるからだ。",
                 "渡部（業務担当）：ただし遅れて届いた拠点の訂正は再集計したいという声がある。",
                 "伊藤（基盤担当）：復旧を試験したことはない。"):
        d.add_paragraph(line)
    d.save(OUT / "d2_第1回議事録.docx")
    (OUT / "d2_運用メモ.txt").write_text(
        "運用メモ（架空）\n"
        "アプリの保守は情報システム課、クラウド基盤の保守はベンダーが担当する想定である。\n"
        "障害の一次受付の担当は未定である。\n"
        "保守のための計画停止は月1回の日曜夜を候補にしている。\n", encoding="utf-8")


# ---- デモ3：拠点ネットワークと遠隔保守 ----
D3_LINES = [
    ("中村", 1.00, "本日は大阪拠点のネットワーク更新について確認します。"),
    ("小林", 0.93, "現場の要望は、速くて止まりにくい回線です。朝九時の受発注の時間帯に画面が遅くなります。"),
    ("中村", 1.00, "通信量はまだ計測していません。切替時間も未計測です。"),
    ("岡田", 1.08, "保守担当としては、障害対応を早くするために、外部からの遠隔保守を提案します。"),
    ("中村", 1.00, "当社の規程では外部からの接続は禁止です。例外の手続きがあるかは確認が必要です。"),
    ("岡田", 1.08, "接続時間を限定して、承認者が都度許可する方式なら運用できると思います。"),
    ("小林", 0.93, "回線が切れたときは、受発注だけでも続けたいです。停止が何分まで許容できるかは持ち帰ります。"),
    ("中村", 1.00, "遠隔保守はまだ提案の段階で、決定ではありません。次回までに情報セキュリティ担当に確認します。"),
]


def tts(lines, workdir: Path) -> list[Path]:
    """Windows の音声合成で1行ずつ WAV にする。"""
    script = workdir / "tts.ps1"
    data = workdir / "lines.json"
    data.write_text(json.dumps([t for _, _, t in lines], ensure_ascii=False), encoding="utf-8")
    script.write_text(
        "Add-Type -AssemblyName System.Speech\n"
        f"$lines = Get-Content -Raw -Encoding UTF8 '{data}' | ConvertFrom-Json\n"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "$s.SelectVoice('Microsoft Haruka Desktop')\n"
        "$s.Rate = 1\n"
        "$i = 0\n"
        f"foreach ($l in $lines) {{ $s.SetOutputToWaveFile('{workdir}\\line' + $i + '.wav'); $s.Speak($l); $i++ }}\n"
        "$s.Dispose()\n", encoding="utf-8-sig")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], check=True)
    return [workdir / f"line{i}.wav" for i in range(len(lines))]


def make_d3():
    import av
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    rate = 22050
    with tempfile.TemporaryDirectory() as td:
        wavs = tts(D3_LINES, Path(td))
        pcm, cues = [], []
        t = 2.0
        pcm.append(np.zeros(int(rate * t)))
        for (speaker, pitch, text), path in zip(D3_LINES, wavs):
            with wave.open(str(path), "rb") as w:
                sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
                raw = w.readframes(w.getnframes())
            assert width == 2
            x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
            if ch > 1:
                x = x[::ch]
            n = int(len(x) * rate / sr / pitch)  # 話者ごとに声の高さを少し変える
            x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
            pcm.append(x)
            start, end = t, t + n / rate
            cues.append((start, end, speaker, text))
            t = end + 0.7
            pcm.append(np.zeros(int(rate * 0.7)))
    audio = np.concatenate(pcm)

    font_big = ImageFont.truetype("C:/Windows/Fonts/meiryob.ttc", 34)
    font = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 20)

    def card(speaker: str | None) -> np.ndarray:
        img = Image.new("RGB", (640, 360), "#16161A")
        d = ImageDraw.Draw(img)
        d.text((36, 40), "拠点ネットワーク更新 定例（架空）", font=font, fill="#FFFFFF")
        d.text((36, 150), speaker or "開始", font=font_big, fill="#FF7A1A")
        d.text((36, 300), "デモ用の合成音声です", font=font, fill="#9A9CA3")
        return np.array(img)

    frames = {c[2]: card(c[2]) for c in cues}
    blank = card(None)
    path = OUT / "d3_拠点ネットワーク定例.mp4"
    with av.open(str(path), "w") as c:
        vs = c.add_stream("libx264", rate=2)
        vs.width, vs.height, vs.pix_fmt = 640, 360, "yuv420p"
        vs.options = {"crf": "30", "preset": "veryfast"}
        ast = c.add_stream("aac", rate=rate)
        ast.layout = "mono"
        total = len(audio) / rate
        for i in range(int(total * 2) + 1):
            now = i / 2
            cue = next((q for q in cues if q[0] <= now <= q[1] + 0.7), None)
            arr = frames[cue[2]] if cue else blank
            frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
            frame.pts, frame.time_base = i, Fraction(1, 2)
            for pkt in vs.encode(frame):
                c.mux(pkt)
        for pkt in vs.encode():
            c.mux(pkt)
        ints = (audio * 32767).astype(np.int16)
        pos = 0
        while pos < len(ints):
            piece = ints[pos:pos + 1024].reshape(1, -1)
            frame = av.AudioFrame.from_ndarray(piece, format="s16", layout="mono")
            frame.sample_rate, frame.pts, frame.time_base = rate, pos, Fraction(1, rate)
            for pkt in ast.encode(frame):
                c.mux(pkt)
            pos += 1024
        for pkt in ast.encode():
            c.mux(pkt)

    def stamp(s: float) -> str:
        return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:06.3f}"

    vtt = "WEBVTT\n\n" + "\n".join(f"{stamp(a)} --> {stamp(b)}\n<v {sp}>{tx}\n" for a, b, sp, tx in cues)
    (OUT / "d3_準備済み文字起こし.vtt").write_text(vtt, encoding="utf-8")

    from pptx import Presentation
    from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
    from pptx.util import Cm

    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "大阪拠点の構成（架空）"
    for label, x in (("大阪拠点", 2), ("本社", 10), ("保守会社", 18)):
        box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Cm(x), Cm(7), Cm(5), Cm(2.5))
        box.text_frame.text = label
    s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Cm(7), Cm(8.2), Cm(10), Cm(8.2))
    s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Cm(15), Cm(8.2), Cm(18), Cm(8.2))
    tx = s.shapes.add_textbox(Cm(2), Cm(11), Cm(20), Cm(1.5))
    tx.text_frame.text = "拠点間は主回線1本で接続している。代替回線はない。"
    s.notes_slide.notes_text_frame.text = "社内メモ：回線の契約更新は来年3月。"
    prs.save(OUT / "d3_構成説明.pptx")

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "通信一覧"
    ws.append(["通信ID", "通信元", "通信先", "方向", "用途", "時間帯", "ポート", "状態"])
    ws.append(["F01", "大阪拠点の端末", "本社の受発注サーバー", "拠点→本社", "受発注", "平日8時から18時", "未確認", "利用中"])
    ws.append(["F02", "大阪拠点の端末", "本社のファイルサーバー", "拠点→本社", "図面の参照", "平日", "未確認", "利用中"])
    ws.append(["F03", "保守会社", "大阪拠点のネットワーク機器", "外部→拠点", "遠隔保守（提案）", "未確認", "未確認", "提案のみ"])
    ws2 = wb.create_sheet("拠点")
    ws2.append(["拠点", "利用者数", "用途", "計測"])
    ws2.append(["大阪拠点", 60, "受発注・図面参照", "通信量は未計測"])
    wb.save(OUT / "d3_通信一覧.xlsx")
    (OUT / "d3_情報セキュリティ規程抜粋.txt").write_text(
        "情報セキュリティ規程 抜粋（架空）\n"
        "第12条 社外から社内ネットワークへの外部接続は禁止する。\n"
        "第13条 業務上必要な場合は、情報セキュリティ責任者の事前承認により例外を認めることがある。\n"
        "第14条 例外の接続は、接続者、時間、作業内容のログを保存する。\n", encoding="utf-8")


if __name__ == "__main__":
    which = sys.argv[1:] or ["1", "2", "3"]
    if "1" in which:
        make_d1()
    if "2" in which:
        make_d2()
    if "3" in which:
        make_d3()
    print("生成しました:", sorted(p.name for p in OUT.iterdir()))
