"""データの種類・状態の定義（案件JSONの形式もここで決める）。

このファイルは「何という状態があるか」だけを持ち、処理は書かない。
画面と業務ロジックが同じ定義を参照することで、表記ゆれを防ぐ。
"""
from __future__ import annotations

FORMAT_VERSION = 1
APP_ID = "DefineReq_AI"

# 値が「未設定」(None) と「該当なし」(NA) は意味が違うため区別する
NA = "__該当なし__"

DOMAINS = {"app": "業務アプリ", "infra": "インフラ", "network": "ネットワーク"}

# 案件・関係者の情報がどの程度確かか
CERTAINTY = ["確認済み", "本人申告", "仮説", "未確認"]

# 要件・決定に共通の状態
AGREEMENT_STATES = ["下書き", "提案", "確認待ち", "合意済み", "保留", "却下", "廃止"]
# 合意済みにするときに人の操作を必須とする状態
HUMAN_ONLY_STATES = {"合意済み"}

REQ_KINDS = ["業務", "機能", "データ", "画面・帳票", "連携", "非機能", "サービス条件",
             "性能", "容量", "可用性", "復旧", "運用", "配置制約", "接続", "通信", "分離", "認証", "障害", "移行"]

SCOPE_CHOICES = ["今回必須", "今回できれば", "次回以降", "対象外", "判断待ち"]
PRIORITIES = ["高", "中", "低"]

# 境界の区別（必要条件・計測値・仮定・実現方式候補・人が確定した設計制約）
MEASURE_KINDS = ["必要条件", "現状の計測値", "仮定・見積もり", "実現方式の候補", "人が確定した設計制約"]
MEASURE_STATUS = ["未計測", "計測済み", "確認待ち", "該当なし"]

# 資料
SOURCE_KINDS = ["要望", "手順", "議事録", "既存仕様", "構成・運用", "計測・調査", "制約", "その他"]
VISIBILITY = ["社内のみ", "関係者限定", "社外共有可"]

# 発言の性質
UTTERANCE_KINDS = ["要望", "質問", "提案", "決定", "保留", "推測", "制約", "引用", "その他"]
SPEAKER_CONFIRM = ["未確認", "確認済み"]
CONTENT_CONFIRM = ["未確認", "確認済み", "要聞き直し"]

# 会議後の候補
CANDIDATE_KINDS = ["要点", "要望", "要件", "決定", "保留", "未回答", "意見の違い", "制約", "リスク", "次の行動"]
CANDIDATE_STATES = ["候補", "採用", "修正して採用", "却下"]

# 追加要望
CHANGE_STATES = ["受付", "調査中", "判断待ち", "反映済み", "却下", "保留", "取り下げ"]
CHANGE_CLASSES = ["未分類", "新規", "変更", "重複", "補足", "矛盾候補", "対象外", "判断不能"]
IMPACT_AREAS = ["要件", "シナリオ", "データ", "権限", "例外", "性能", "復旧", "通信", "分離",
                "運用", "移行", "責任分界", "受入条件", "過去の判断", "成果物"]
IMPACT_BASIS = ["確認済み", "登録関係", "AI候補", "未調査", "影響なし（確認済み）"]

# 矛盾と不確かさの区別
CONFLICT_KINDS = ["明確な矛盾", "前提確認が必要な候補", "登録関係からの影響", "AI推測", "未調査"]
CONFLICT_STATES = ["未確認", "確認中", "解消", "矛盾なしと確認", "保留"]

RISK_STATES = ["未対応", "対応中", "対応済み", "受容", "取り下げ"]
RISK_NATURE = ["事実に基づく", "一般論", "AI候補"]

ACTION_STATES = ["未着手", "対応中", "完了", "取り下げ"]

QUESTION_STATES = ["未質問", "回答待ち", "回答済み", "取り下げ"]

ISSUE_STATES = ["未調整", "調整中", "判断待ち", "結論あり"]
OPINION_NATURE = ["業務上の希望", "技術制約", "運用負担", "その他"]

HISTORY_OUTCOMES = ["採用", "却下", "保留", "取り下げ"]

DOC_TYPES = {"meeting": "打ち合わせ確認資料", "change": "追加要望確認資料", "spec": "要件定義書"}

# 案件JSONの中の一覧（収録先名 → ID接頭語）
COLLECTIONS = {
    "stakeholders": "STK", "glossary": "TRM", "sources": "SRC", "recordings": "REC",
    "questions": "QST", "candidates": "CAN", "requirements": "REQ", "issues": "ISU",
    "scenarios": "SCN", "decisions": "DEC", "changes": "CHG", "conflicts": "CNF",
    "risks": "RSK", "actions": "ACT", "history": "HIS", "baselines": "BSL",
    "shared_docs": "DOC", "responses": "RES", "ai_runs": "AIR",
}
