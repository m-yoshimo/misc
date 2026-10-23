#!/usr/bin/env python3
"""`~/.claude/memory/feedback_*.md` の**全文**を、SessionStart フックで注入するために分割して出す。

## なぜ必要か（2026-09-11 に実測）

フック1本が返せる出力にはサイズ上限がある。超えるとファイルに退避され、
Claude には**先頭 2KB のプレビューしか届かない**（しかもエラーにならないので気づけない）。

  - 19,561 B（MEMORY.md）: 通る
  - 33,851 B / 74,762 B / 115,893 B: 落ちる

ルール本文は合計 190KB あるので、1本では絶対に入らない。**上限はフック1本ごとに掛かる**ので、
本数を増やせば合計量は増やせる。それをやるのがこのスクリプト。

### 「読め」と指示する方式は失敗した（この方式を選んだ理由）

一度、フックでは本文を流さず「セッション開始時に9ファイルを全部 Read しろ」という指示だけを
出す形にした。指示は確かに注入されたが、**新セッションは1ファイルも読まずに即答した**
（2026-09-11 18:26 のセッションで実測。Read の呼び出し 0 回）。
指示には強制力が無く、ツールを使わずテキストで返す経路はフックでは止められない。
**だから注入で押し込む。** 私の意思を介在させないことが、この方式の唯一の利点。

## 使い方

    python3 ~/.claude/hooks/session_rules.py <index> <configured_total>
    python3 ~/.claude/hooks/session_rules.py --count

`<index>` は 1 始まり。`settings.json` の SessionStart に `<configured_total>` 本ぶん並べる。
実際のチャンク数が `<configured_total>` を超えた場合（ルールが増えたとき）、
最後の1本に**警告と、届いていないルール ID の一覧**を付ける。黙って欠落させないため。

## 設計上の制約

**ルールの文言をこのファイルに持たない。** 持つのは分割の条件だけ。
コピーを持つと同期が切れる（META-04 と同じ構造）。
分割は `## <ID>:` のセクション境界でのみ行うので、**1つのルールが途中で切れることはない**。
"""

import json
import os
import re
import sys

MEMORY_DIR = os.path.join(os.path.expanduser("~"), ".claude", "memory")

# 1本あたりの上限。実測で 19,561 B は通り 33,851 B は落ちるので、通る側に余裕を持たせる。
# JSON エスケープでバイト数が増える分もここで吸収する。
MAX_BYTES = 16000

RULE_HEAD = re.compile(r"^## ([A-Z]+-\d+):")


def rule_files() -> list:
    return sorted(
        f for f in os.listdir(MEMORY_DIR)
        if f.startswith("feedback_") and f.endswith(".md")
    )


def units() -> list:
    """ファイル群を「1ルール = 1単位」に割る。戻り値は (ファイル名, ルールID, 本文) の列。

    最初の `## ` より前（frontmatter と「この場面」の説明）は、そのファイルの
    ルール ID が `None` の単位として先頭に置く。
    """
    out = []
    for fname in rule_files():
        with open(os.path.join(MEMORY_DIR, fname), encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        current, rule_id = [], None
        for line in lines:
            match = RULE_HEAD.match(line)
            if match:
                if current:
                    out.append((fname, rule_id, "\n".join(current) + "\n"))
                current, rule_id = [line], match.group(1)
                continue
            current.append(line)
        if current:
            out.append((fname, rule_id, "\n".join(current)))
    return out


def chunks() -> list:
    """単位を、1チャンクが MAX_BYTES を超えないように詰める。

    1単位だけで MAX_BYTES を超える場合は、その単位だけで1チャンクにする
    （途中で切るよりは、1本落ちる方が検出できる。`--count` が警告する）。
    """
    packed, current, size, last_file = [], [], 0, None
    for fname, rule_id, body in units():
        header = f"--- {fname} ---\n" if fname != last_file else ""
        piece = header + body
        cost = len(piece.encode("utf-8"))
        if current and size + cost > MAX_BYTES:
            packed.append(current)
            current, size, last_file = [], 0, None
            header = f"--- {fname} ---\n"
            piece = header + body
            cost = len(piece.encode("utf-8"))
        current.append((fname, rule_id, piece))
        size += cost
        last_file = fname
    if current:
        packed.append(current)
    return packed


def render(packed: list, index: int, total: int) -> str:
    body = "".join(piece for _, _, piece in packed[index - 1])
    text = f"=== ルール本文 ({index}/{len(packed)}) ===\n{body}"
    if index == total and len(packed) > total:
        missing = [
            rule_id
            for chunk in packed[total:]
            for _, rule_id, _ in chunk
            if rule_id
        ]
        text += (
            "\n\n🔴 警告: ルールが増えてチャンク数が "
            f"{len(packed)} になったが、settings.json には {total} 本しか配線されていない。"
            "次のルールはコンテキストに届いていない: " + " / ".join(missing) +
            "\n`python3 ~/.claude/hooks/session_rules.py --count` を実行し、"
            "SessionStart のフックを増やすこと。"
        )
    return text


def main() -> None:
    packed = chunks()

    if "--count" in sys.argv:
        print(f"チャンク数: {len(packed)}（1本あたり上限 {MAX_BYTES} バイト）")
        for i, chunk in enumerate(packed, 1):
            size = sum(len(p.encode("utf-8")) for _, _, p in chunk)
            ids = [r for _, r, _ in chunk if r]
            flag = "  ⚠️上限超過" if size > MAX_BYTES else ""
            print(f"  {i}: {size} バイト / {len(ids)} ルール / {' '.join(ids)}{flag}")
        total_rules = sum(1 for chunk in packed for _, r, _ in chunk if r)
        print(f"ルール総数: {total_rules}")
        sys.exit(0)

    try:
        index, total = int(sys.argv[1]), int(sys.argv[2])
    except (IndexError, ValueError):
        sys.exit(0)

    if index < 1 or index > len(packed):
        sys.exit(0)  # ルールが減ってチャンクが余った。何も出さない

    print(json.dumps(
        {"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": render(packed, index, total),
        }},
        ensure_ascii=False,
    ))
    sys.exit(0)


if __name__ == "__main__":
    main()
