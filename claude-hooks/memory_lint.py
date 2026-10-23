#!/usr/bin/env python3
"""`~/.claude/memory/` のルールと早見表（MEMORY.md）の整合を検査する。

## なぜ必要か

早見表は各ルールの `要約` からの転記で、**転記されたかを誰も検査していなかった**。
そのため本文を直しても早見表が追従せず、実際に次の食い違いが残っていた（2026-09-10 の棚卸しで発覚）:

  - `MEMORY.md` に「prettier が Edit/Write 後に自動実行」が残っていた。
    本文（TECH-03）は「その記憶を持ち込んで誤報告した」と、まさにそれを禁じていた。
  - 当時 `feedback_auto_execute.md`（現 `feedback_03_commands.md`）で最も分量が多く「最重要」と書かれていた SAFE-13
    （裏に回った処理が終わるまで回答を返さない）が、早見表に1行も無かった。

同じ構造の事故は design-review v1 でも起きている（rubric と philosophy の同期が
「誰の仕事でもなかった」ため切れた）。**要約を二次情報のまま人手で保つと必ず切れる**ので、
機械で照合する。

## 使い方

  python3 ~/.claude/hooks/memory_lint.py            # 人が読む形で出力・不一致があれば exit 1
  python3 ~/.claude/hooks/memory_lint.py --hook     # PostToolUse フック用（JSON を出す）

フックとして使う場合、不一致が無ければ**何も出力しない**（ノイズを出さない）。

## 設計上の制約

**ルールの文言をこのファイルに持たない。** 持つのは「構造の条件」だけ（ID の形・必須フィールド名・
接頭辞の集合）。文言のコピーを持つと、それ自体が同期切れの原因になる（この検査が防ぎたいもの）。
"""

import json
import os
import re
import sys

MEMORY_DIR = os.path.join(os.path.expanduser("~"), ".claude", "memory")
INDEX = "MEMORY.md"

PREFIXES = {"SAFE", "FLOW", "COMM", "VERIFY", "TECH", "META"}
SEVERITIES = ["blocker", "major", "minor"]
FIELDS = ["重要度", "要約", "いつ", "判定", "やること", "なぜ", "由来", "関連"]

RULE_HEAD = re.compile(r"^## ([A-Z]+-\d+): (.+)$")
FIELD_LINE = re.compile(r"^- \*\*(" + "|".join(FIELDS) + r")\*\*: ?(.*)$")
# 索引の行。ID セルは先頭とは限らない（2026-09-11 に重要度マーカーの列を先頭へ足した）ので、
# 「`**ID**` だけのセルがある」ことで判定し、要約は**その次のセル**から取る。
INDEX_ROW = re.compile(r"\|\s*\*\*([A-Z]+-\d+)\*\*\s*\|")
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
ID_REF = re.compile(r"\b(?:" + "|".join(PREFIXES) + r")-\d+\b")
# 宣言件数。旧: `## blocker（34件）` 見出し。新: 冒頭の `` `blocker` 34件 `` という記述
COUNT_IN_HEADING = re.compile(r"`(blocker|major|minor)`\s*(\d+)\s*件")


def rule_files() -> list:
    return sorted(
        f for f in os.listdir(MEMORY_DIR)
        if f.startswith("feedback_") and f.endswith(".md")
    )


def parse_rules() -> tuple:
    """各 feedback_*.md からルールを読む。戻り値は (rules, problems)。"""
    rules, problems = {}, []
    for fname in rule_files():
        path = os.path.join(MEMORY_DIR, fname)
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")

        # frontmatter: name はファイル名から機械導出できる値であること（META-04）
        expected_name = fname[:-3].replace("_", "-")
        head = "\n".join(lines[:8])
        actual = re.search(r"^name: *(.+)$", head, re.M)
        if not actual:
            problems.append(f"{fname}: frontmatter に `name:` が無い")
        elif actual.group(1).strip() != expected_name:
            problems.append(
                f"{fname}: `name:` が「{actual.group(1).strip()}」。"
                f"ファイル名からの導出値「{expected_name}」と一致しない"
            )
        if not re.search(r"^metadata:", head, re.M):
            problems.append(f"{fname}: frontmatter が `metadata:` 形式でない")

        current, seen = None, {}
        for line in lines:
            head_match = RULE_HEAD.match(line)
            if head_match:
                if current:
                    rules[current["id"]] = current
                rule_id, title = head_match.group(1), head_match.group(2)
                prefix = rule_id.split("-")[0]
                if prefix not in PREFIXES:
                    problems.append(f"{fname}: {rule_id} の接頭辞が規定外（{prefix}）")
                if rule_id in rules or rule_id in seen:
                    problems.append(f"{fname}: ID {rule_id} が重複している")
                seen[rule_id] = True
                current = {"id": rule_id, "title": title, "file": fname, "fields": {}}
                continue
            if current:
                field_match = FIELD_LINE.match(line)
                if field_match:
                    current["fields"][field_match.group(1)] = field_match.group(2).strip()
        if current:
            rules[current["id"]] = current

    for rule_id, rule in rules.items():
        missing = [f for f in FIELDS if f not in rule["fields"]]
        if missing:
            problems.append(f"{rule['file']}: {rule_id} にフィールドが無い: {' / '.join(missing)}")
        sev = rule["fields"].get("重要度", "")
        if sev and sev not in SEVERITIES:
            problems.append(f"{rule['file']}: {rule_id} の重要度が規定外（{sev}）")
    return rules, problems


def parse_index() -> tuple:
    """MEMORY.md の表から ID → 要約 を読む。戻り値は (index, declared_counts)。"""
    path = os.path.join(MEMORY_DIR, INDEX)
    index, counts = {}, {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            for sev, num in COUNT_IN_HEADING.findall(line):
                counts[sev] = int(num)
            if not INDEX_ROW.search(line):
                continue
            # 要約セル内のエスケープされた `|` を保護してから分割する
            cells = [c.strip() for c in line.replace(r"\|", "\x00").split("|")]
            # `**ID**` だけのセルを探し、その**次のセル**を要約とする。
            # 先頭に重要度マーカーの列があっても効くようにするため、位置を固定しない。
            for i, cell in enumerate(cells[:-1]):
                m = re.fullmatch(r"\*\*([A-Z]+-\d+)\*\*", cell)
                if m:
                    index[m.group(1)] = cells[i + 1].replace("\x00", r"\|")
                    break
    return index, counts


def check() -> list:
    rules, problems = parse_rules()
    index, declared = parse_index()

    only_body = sorted(set(rules) - set(index))
    only_index = sorted(set(index) - set(rules))
    for rule_id in only_body:
        problems.append(f"{INDEX}: {rule_id}（{rules[rule_id]['file']}）が早見表に無い")
    for rule_id in only_index:
        problems.append(f"{INDEX}: {rule_id} が早見表にあるが、本文に存在しない")

    for rule_id in sorted(set(rules) & set(index)):
        body = rules[rule_id]["fields"].get("要約", "")
        if body != index[rule_id]:
            problems.append(
                f"{INDEX}: {rule_id} の要約が本文と一致しない\n"
                f"    本文: {body}\n"
                f"    索引: {index[rule_id]}"
            )

    actual = {s: 0 for s in SEVERITIES}
    for rule in rules.values():
        sev = rule["fields"].get("重要度")
        if sev in actual:
            actual[sev] += 1
    for sev, want in declared.items():
        if actual.get(sev) != want:
            problems.append(
                f"{INDEX}: 「## {sev}（{want}件）」だが、実際は {actual.get(sev)} 件"
            )

    names = {f[:-3].replace("_", "-") for f in rule_files()}
    for fname in rule_files() + [INDEX]:
        with open(os.path.join(MEMORY_DIR, fname), encoding="utf-8") as fh:
            text = fh.read()
        for target in set(WIKILINK.findall(text)):
            if target == "...":
                continue  # 記法の説明に使うプレースホルダ（META-04 の本文）
            if target not in names:
                problems.append(f"{fname}: [[{target}]] が解決しない")
        for ref in set(ID_REF.findall(text)):
            if ref not in rules:
                problems.append(f"{fname}: 本文中の {ref} が存在しない")
    return problems


def main() -> None:
    as_hook = "--hook" in sys.argv
    problems = check()

    if as_hook:
        if problems:
            body = "⚠️ メモリの整合が崩れています（`python3 ~/.claude/hooks/memory_lint.py` で再確認できます）\n"
            body += "\n".join(f"  - {p}" for p in problems)
            body += (
                "\n\n早見表は各ルールの `要約` からの転記です（META-04）。"
                "本文を直したら早見表も直してください。直している途中ならこの警告は無視して構いません。"
            )
            print(json.dumps(
                {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": body}},
                ensure_ascii=False,
            ))
        sys.exit(0)

    if problems:
        print(f"不一致: {len(problems)} 件")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    rules, _ = parse_rules()
    print(f"OK: {len(rules)} ルール。早見表・フィールド・参照すべて整合しています。")
    sys.exit(0)


if __name__ == "__main__":
    main()
