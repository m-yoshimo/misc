#!/usr/bin/env python3
"""エージェントへの委任を、`delegate` skill が組み立てた指示文だけに限る PreToolUse フック。

## なぜ要るか（2026-10-05）

2026-08-26〜10-02 の苛立ち 229 件のうち、ユーザーが時間・トークンの浪費を明言した深刻な 13 場面の
5 場面が「委任先への渡し方を Claude が推測で決めた」ことによる:
ルールを渡さないワーカーが要件を変えて全面やり直し（9/11）、レビューに定義書を渡した（9/24）、
誤った入力のレビュアーに 25 万トークン（9/30）、「終わったら消す」と書いて成果物を消させた（9/17）、
レビューに PRD を渡さなかった（9/03）。

委任プロンプトに何を入れるかは FLOW-22 / FLOW-16 で文章のルールにしていたが、守られなかった。
skill にしても、Claude が手順を迂回したりテンプレートを書き換えたりすれば同じことが起きる
（local-review のテンプレートを書き換えた・自作プロンプトでレビューした実例がある）。
そこで **指示文はスクリプトだけが組み立て、Claude は書き換えられない** 形にする。

## 仕組み

- `~/.claude/skills/delegate/build_prompt.py` が指示文を組み立て、末尾に発行印 `[delegate:<12桁>]` を付ける。
  発行印は本文の指紋（空白を除いた本文の SHA-256 の先頭 12 桁）で、発行記録に残す
- このフックは Agent / Task の `prompt` を見て、次のどれかなら deny する
  - 末尾に発行印が無い
  - 本文の指紋が発行印と合わない（発行後に書き換えた・書き足した・削った）
  - 発行記録に無い発行印
- 指紋は空白を除いてから計算する。指示文を書き写すときの改行・空白の揺れでは止めず、
  文字の変更だけを止めるため
- `run_in_background: true` が付いていなければ deny する（2026-10-07 ユーザー指示）。前景で起動すると、エージェントが
  終わるまでメインのセッションが塞がり、ユーザーのメッセージに答えられないため
- 発行記録に `agent` があれば、Agent ツールの `subagent_type` と照合して違えば deny する（2026-10-05）。
  pointpf-api のレビュー用の指示文を汎用以外のエージェントに渡す、などの取り違えを止めるため
- `--stop`（Stop フック）: 同時に発行した指示文の組（`group`）のうち、このセッションで一部だけ起動して
  残りを起動していなければ、1 度だけ止める。pointpf-api の 5 体・design-review-v2 の 9 体の一部しか
  起動しないと、レビューの次元が黙って欠けるため。組を 1 体も起動していない場合は対象外

- `--sweep`（SessionStart フック。`--stop` のときも先に同じ処理を行う）: 委任のファイルは、タスク定義書が宣言した
  一時ディレクトリの `delegate/` に置かれる（`build_prompt.py` が `workdirs.jsonl` に持ち主と一緒に記録する）。
  持ち主のタスク定義書が無くなった（`done/` に移った・消された）ものを消す。外に書いたファイル（pointpf-api の
  `pr-diff.txt`）は、中身が書いたときのままなら、同じ場所の `findings-*.json` と一緒に消す。
  要件（2026-10-06 ユーザー）: 遅くともチケットの完了時には必ず消えていること・どのチケットのファイルか分かること。
  完了の処理（`done/` への移動）をしたターンの終わりの Stop で消える

## 対象外（このフックでは止まらないもの）

- 起動後のエージェントへの追加指示（SendMessage）
- Workflow ツールのスクリプトから起動されるエージェント
"""

import glob
import hashlib
import json
import os
import re
import shutil
import sys

ISSUED_LOG = os.environ.get("DELEGATE_ISSUED_LOG") or os.path.join(
    os.path.expanduser("~"), ".claude", "state", "delegate", "issued.jsonl"
)
STATE_DIR = os.path.dirname(ISSUED_LOG)
USED_LOG = os.path.join(STATE_DIR, "used.jsonl")
NOTIFIED_LOG = os.path.join(STATE_DIR, "notified.jsonl")
MARKER = re.compile(r"\[delegate:([0-9a-f]{12})\]\s*$")
DEFAULT_AGENT = "general-purpose"
WORKDIR_REGISTRY = os.path.join(STATE_DIR, "workdirs.jsonl")
WHITESPACE = re.compile(r"\s+")

HOWTO = (
    "\nエージェントへの指示文は `python3 ~/.claude/skills/delegate/build_prompt.py <種類> ...` で組み立て、"
    "出力をそのまま `prompt` に渡すこと（使い方は ~/.claude/skills/delegate/SKILL.md）。"
    "\nユーザーが明示的にこの委任を指示していた場合は、黙って諦めずに"
    "「フックに止められた。どうするか」と報告して相談すること。"
)


def fingerprint(body: str) -> str:
    """本文の指紋。空白の揺れは無視し、文字の変更だけを検出する。"""
    return hashlib.sha256(WHITESPACE.sub("", body).encode("utf-8")).hexdigest()[:12]


# 🔴 2026-10-22 ユーザー決定。指示文は `prompt` に入れず、**ファイルで渡す**。
# `prompt` に書くのは「このファイルを読め」＋発行印だけ。
# 照合は**ファイルの中身の指紋 == 発行印**で行う（ファイル名も発行印なので、
# 別の内容のファイルを指しても通らない。後から書き換えても指紋が合わなくなる）。
PROMPT_REF = re.compile(r"^(?P<path>/[^\s]+/(?P<stamp>[0-9a-f]{12})\.md)$", re.M)


def read_jsonl(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except (OSError, ValueError):
        return []


def append_jsonl(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def file_digest(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def sweep() -> list:
    """持ち主のタスク定義書が無くなった委任のファイルを消し、消したディレクトリを返す。"""
    entries = read_jsonl(WORKDIR_REGISTRY)
    if not entries:
        return []
    keep, removed = [], []
    for entry in entries:
        root, taskdef = entry.get("dir"), entry.get("taskdef")
        if not root or not taskdef:
            continue
        if os.path.isfile(taskdef):
            if entry not in keep:
                keep.append(entry)
            continue
        for ext in read_jsonl(os.path.join(root, "external.jsonl")):
            path = ext.get("path")
            try:
                same = path and os.path.isfile(path) and file_digest(path) == ext.get("digest")
            except OSError:
                same = False
            if same:
                # 中身が書いたときのままなら、このチケットのレビューのもの（別のセッションのものは中身が違う）
                for leftover in [path] + glob.glob(os.path.join(os.path.dirname(path), "findings-*.json")):
                    try:
                        os.remove(leftover)
                    except OSError:
                        pass
        if os.path.basename(root) == "delegate" and os.path.isdir(root):
            shutil.rmtree(root, ignore_errors=True)
            removed.append(root)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(WORKDIR_REGISTRY, "w", encoding="utf-8") as fh:
        for entry in keep:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return removed


def issued_records() -> dict:
    return {r["id"]: r for r in read_jsonl(ISSUED_LOG) if "id" in r}


def issued_ids() -> set:
    return set(issued_records())


def deny(detail: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"[delegate] {detail}{HOWTO}",
                }
            },
            ensure_ascii=False,
        )
    )
    sys.exit(0)


def check(prompt: str, subagent_type=None, run_in_background=True) -> dict:
    """通してよければ発行記録を返す。止めるときは deny して終わる。"""
    text = prompt.rstrip()
    match = MARKER.search(text)
    if not match:
        deny("指示文の末尾に発行印 `[delegate:...]` が無い（スクリプトを通さずに書いた指示文）")
    body = text[: match.start()]
    stamp = match.group(1)
    ref = PROMPT_REF.search(body)
    if ref and ref.group("stamp") == stamp:
        # ファイル渡し。読むのは起動の直前なので、**これからエージェントが読む中身**を照合できる
        path = ref.group("path")
        if not os.path.isfile(path):
            deny(f"指示文のファイルが無い: {path}（`build_prompt.py` を実行し直すこと）")
        try:
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
        except OSError as err:
            deny(f"指示文のファイルを読めない: {path}（{err}）")
        inner = MARKER.search(content.rstrip())
        if not inner or inner.group(1) != stamp:
            deny(f"{path} の発行印が、prompt の発行印と合わない（別の委任のファイルを指している）")
        if fingerprint(content.rstrip()[: inner.start()]) != stamp:
            deny(f"{path} の中身が、発行印を付けたときから変わっている（書き換え・書き足し・削除）")
    elif fingerprint(body) != stamp:
        deny("指示文の本文が、発行印を付けたときから変わっている（書き換え・書き足し・削除）")
    record = issued_records().get(match.group(1))
    if record is None:
        deny("発行記録に無い発行印（スクリプトが発行したものではない）")
    if not run_in_background:
        # 前景で起動すると、エージェントが終わるまでメインのセッションがツールの結果待ちで塞がり、
        # ユーザーのメッセージに答えられない（2026-10-07 GID-1859 のセッションで実装ワーカーが前景で動き続けた）
        deny(
            "委任のエージェントは背景で起動すること（Agent ツールに `run_in_background: true` を付ける）。"
            "前景で起動すると、終わるまでユーザーのメッセージに答えられなくなる。結果は完了の通知で届く"
        )
    expected = record.get("agent")
    actual = subagent_type or DEFAULT_AGENT
    if expected and actual != expected:
        deny(
            f"この指示文は subagent_type `{expected}` 用に発行されたが、`{actual}` で起動しようとしている。"
            "スクリプトの出力に書かれた subagent_type で起動すること"
        )
    return record


def stop(data: dict) -> None:
    if data.get("stop_hook_active"):
        sys.exit(0)
    session = data.get("session_id") or ""
    used = [u for u in read_jsonl(USED_LOG) if u.get("session_id") == session]
    used_ids = {u["id"] for u in used}
    started = {u["group"] for u in used if u.get("group")}
    notified = {n["group"] for n in read_jsonl(NOTIFIED_LOG) if n.get("session_id") == session}
    records = issued_records().values()
    lines = []
    for group in sorted(started - notified):
        missing = [r["label"] for r in records if r.get("group") == group and r["id"] not in used_ids]
        if missing:
            lines.append(f"- 未起動: {', '.join(missing)}")
            append_jsonl(NOTIFIED_LOG, {"group": group, "session_id": session})
    if lines:
        print(json.dumps({
            "decision": "block",
            "reason": "[delegate] 同時に発行した指示文の組のうち、起動していないエージェントがある。"
                      "全員を起動すること（起動しない理由があるなら、ユーザーに報告して相談すること）:\n"
                      + "\n".join(lines),
        }, ensure_ascii=False))
    sys.exit(0)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)
    if "--stop" in sys.argv[1:]:
        sweep()
        stop(data)
    if "--sweep" in sys.argv[1:]:
        sweep()
        sys.exit(0)
    if data.get("tool_name") not in ("Agent", "Task"):
        sys.exit(0)
    tool_input = data.get("tool_input") or {}
    record = check(tool_input.get("prompt") or "", tool_input.get("subagent_type"),
                   tool_input.get("run_in_background") is True)
    append_jsonl(USED_LOG, {"id": record["id"], "group": record.get("group"),
                            "session_id": data.get("session_id") or ""})
    sys.exit(0)


if __name__ == "__main__":
    main()
