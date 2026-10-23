#!/usr/bin/env python3
"""memory_lint.py が「壊れた状態」を実際に検出できるかの検証。

本物の ~/.claude/memory/ は触らない。一時ディレクトリへコピーし、そこを壊して検査させる。
memory_lint.py は MEMORY_DIR を参照するので、HOME を差し替えて実行する。

## 置き場所について（2026-09-14）

以前は `idpf-api/.claude/tmp/feedback-inventory/` に置いていたが、**そこは一時ファイルの場所**で
META-01 の掃除対象。実際に 2026-09-14 の掃除で消えた。**フックと同じ寿命のものはフックの隣に置く。**
消えた版はセッションのトランスクリプトから復元した（正常 1 + 壊し 10）。
"""

import os
import shutil
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory_lint.py")
REAL = os.path.join(os.path.expanduser("~"), ".claude", "memory")


def run_in(home: str) -> tuple:
    env = dict(os.environ, HOME=home)
    proc = subprocess.run(
        [sys.executable, HOOK], capture_output=True, text=True, env=env
    )
    return proc.returncode, proc.stdout


def make_sandbox(tmp: str) -> str:
    home = os.path.join(tmp, "home")
    dest = os.path.join(home, ".claude", "memory")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copytree(REAL, dest)
    return home


def edit(home: str, fname: str, old: str, new: str) -> None:
    path = os.path.join(home, ".claude", "memory", fname)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert old in text, f"仕込み対象が見つからない: {fname} / {old[:40]}"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace(old, new, 1))


# (説明, 壊し方, 検出されてほしい語)
BREAKAGES = [
    (
        "本文の要約だけ直して早見表を直し忘れた",
        # 要約の文言そのものに依存しないよう、行の先頭だけで狙う（2026-10-02 に SAFE-01 の要約を変えて壊れた）
        lambda h: edit(h, "feedback_03_commands.md",
                       "- **要約**: 実行してよい git は",
                       "- **要約**: 変更後の文言に差し替えた。実行してよい git は"),
        "要約が本文と一致しない",
    ),
    (
        "早見表から1行消した",
        # 表のセルのパディングに依存しないよう ID だけで狙う（2026-10-01 に整形で壊れた）
        lambda h: edit(h, "MEMORY.md",
                       "**SAFE-13**", "**SAFE-99**"),
        "早見表に無い",
    ),
    (
        "本文に無い ID を早見表に書いた",
        lambda h: edit(h, "MEMORY.md",
                       "**COMM-06**", "**COMM-77**"),
        "本文に存在しない",
    ),
    (
        "フィールドを1つ落とした",
        lambda h: edit(h, "feedback_03_commands.md",
                       "- **判定**: リソース定義を手で書いたら違反",
                       "- リソース定義を手で書いたら違反"),
        "フィールドが無い",
    ),
    (
        "重要度を規定外の値にした",
        lambda h: edit(h, "feedback_04_editing.md",
                       "- **重要度**: major", "- **重要度**: high"),
        "重要度が規定外",
    ),
    (
        "重要度を変えて早見表の件数とずらした",
        lambda h: edit(h, "feedback_04_editing.md",
                       "- **重要度**: major", "- **重要度**: minor"),
        "実際は",
    ),
    (
        "name をファイル名から導出できない値にした（META-04）",
        lambda h: edit(h, "feedback_03_commands.md",
                       "name: feedback-03-commands", "name: コマンド実行のルール"),
        "一致しない",
    ),
    (
        "解決しない wikilink を書いた",
        lambda h: edit(h, "feedback_03_commands.md",
                       "[[feedback-09-after-mistake]]", "[[feedback-nonexistent]]"),
        "解決しない",
    ),
    (
        "存在しない ID を本文から参照した",
        lambda h: edit(h, "feedback_03_commands.md",
                       "SAFE-07（`terraform apply` は事前確認）",
                       "SAFE-42（`terraform apply` は事前確認）"),
        "存在しない",
    ),
    (
        "ID を重複させた",
        lambda h: edit(h, "feedback_03_commands.md",
                       "## TECH-05:", "## TECH-02:"),
        "重複",
    ),
]


def main() -> None:
    failures = []

    # 1. 壊していない状態では OK になること
    with tempfile.TemporaryDirectory() as tmp:
        home = make_sandbox(tmp)
        code, out = run_in(home)
        if code != 0:
            failures.append(f"壊していない状態で不一致が出た:\n{out}")

    # 2. 壊した状態では必ず検出されること
    for label, breaker, expect in BREAKAGES:
        with tempfile.TemporaryDirectory() as tmp:
            home = make_sandbox(tmp)
            breaker(home)
            code, out = run_in(home)
            if code == 0:
                failures.append(f"検出できなかった: {label}")
            elif expect not in out:
                failures.append(
                    f"検出はしたが内容が違う: {label}\n    期待に含む語: {expect}\n    実際:\n{out}"
                )

    print(f"ケース数: {len(BREAKAGES) + 1}（正常 1 + 壊し {len(BREAKAGES)}）")
    for f in failures:
        print(f"  NG {f}")
    print(f"不一致: {len(failures)} 件")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
