#!/usr/bin/env python3
"""PostToolUse hook: タスク定義書 (.claude/tasks/*.md) の Write/Edit を検知して2つを行う。

1. フォーマットチェック: ~/.claude/tasks/_TEMPLATE.md の必須節が揃っているかを機械的に検査し、
   欠落があれば具体的に指摘する。(feedback_task_workflow.md「タスク定義は必ず _TEMPLATE.md から
   起こす（毎回抜ける最重要ミス）」への機械的な歯止め。人間の注意力に依存させない。)
2. design-review を実行するか AskUserQuestion で確認するよう指示する。

対象はタスク定義書のみ（コード実装は対象外）。
規約・索引など「タスク定義書ではない .md」は、ファイル先頭付近に
    <!-- taskdef-format: skip -->
を書けばフォーマットチェックを除外できる（design-review の確認だけ残る）。
"""
import json
import os
import re
import sys

# _TEMPLATE.md の必須節。(表示名, 見出しにマッチする正規表現)
# 「## 8. 検証プロトコル」「## 変更対象ファイル一覧（並列実行計画）」のような
# 採番・補足つきの見出しにも当たるよう緩めに書く。
REQUIRED_SECTIONS = [
    ("## ステータス", r"^#{2,3}\s*(?:\d+[.．]\s*)?ステータス"),
    ("## 再開手順", r"^#{2,3}\s*(?:\d+[.．]\s*)?再開手順"),
    ("## 目的", r"^#{2,3}\s*(?:\d+[.．]\s*)?目的"),
    ("## 前提", r"^#{2,3}\s*(?:\d+[.．]\s*)?前提"),
    ("## 作業内容", r"^#{2,3}\s*(?:\d+[.．]\s*)?作業内容"),
    ("## 懸念点・確認事項", r"^#{2,3}\s*(?:\d+[.．]\s*)?懸念点|^#{2,3}\s*(?:\d+[.．]\s*)?確認事項"),
    ("## 変更対象ファイル一覧（並列実行計画）", r"^#{2,3}\s*(?:\d+[.．]\s*)?変更対象ファイル一覧"),
    ("## 検証プロトコル", r"^#{2,3}\s*(?:\d+[.．]\s*)?検証プロトコル"),
]

# 委任体制は「変更対象ファイル一覧（並列実行計画）」節の中身でもよいので、
# 見出しか本文のどちらかに現れていればよいものとして別扱いにする。
DELEGATION_HINT = r"ワーカー|Worker|並列|タスク管理エージェント"


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""

    if not re.search(r"/\.claude/tasks/.*\.md$", file_path):
        return

    messages = []

    # --- 1. フォーマットチェック ---
    # done/ 配下は完了済みなので検査しない。
    is_done = "/.claude/tasks/done/" in file_path
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except Exception:
        content = ""

    skip_marker = "<!-- taskdef-format: skip -->" in content

    if content and not is_done and not skip_marker:
        missing = [
            label
            for label, pattern in REQUIRED_SECTIONS
            if not re.search(pattern, content, re.MULTILINE)
        ]
        if not re.search(DELEGATION_HINT, content):
            missing.append("委任体制・並列実行計画（ワーカー構成／並列不要ならその理由）")

        if missing:
            messages.append(
                "⚠️ タスク定義書のフォーマット不備: " + file_path + "\n"
                "次の節が見つかりません。`~/.claude/tasks/_TEMPLATE.md` の全節を残すルールです"
                "（内容が薄くても節見出しごと残す。並列不要なら「ワーカー1本・順次・理由」を明記）:\n"
                + "\n".join("  - " + m for m in missing)
                + "\n→ ユーザーに承認を求める前に埋めること。"
                "\n→ この .md がタスク定義書ではない（規約・索引・調査記録など）場合は、"
                "ファイル先頭に `<!-- taskdef-format: skip -->` を追記して検査対象から外すこと。"
            )

    # --- 2. design-review の確認 ---
    messages.append(
        "📋 タスク定義書を編集しました: " + file_path + "\n"
        "→ この更新に design-review（設計レビュー）が必要か、AskUserQuestion でユーザーに1問確認すること。"
        "（軽微・事務的な更新などレビュー不要なケースもあるため、毎回は実行しない＝オーバーヘッド回避。）\n"
        "→ ユーザーが「実行する」を選んだら、design-review スキルでこの task-def を対象に、"
        "別のレビューエージェントで設計レビューを回すこと。"
        "**レビュー基準には `~/.claude/notes/design_review_rubric.md` と `design_philosophy.md` に加え、"
        "着手プロジェクトの開発ガイドライン（u1-web なら `docs/dev-guidelines.md`）を必ず含めること。**\n"
        "→ 返ってきた指摘は全件反映せず、(a)事実誤り=直す (b)要件内=直す (c)要件外・範囲外=ユーザーに諮る、"
        "の3分類で取捨選択すること（`feedback_task_workflow.md`「レビュー指摘の取捨選択はレビューを受けた側の責任」）。"
    )

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": "\n\n".join(messages),
                }
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
    sys.exit(0)
