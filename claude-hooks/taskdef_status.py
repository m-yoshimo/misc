#!/usr/bin/env python3
"""タスク定義書の `## ステータス` を、更新漏れが起きても復元できる形で運ぶフック。

2つのモードを持つ（配線は `~/.claude/settings.json`）。

| モード | フックイベント | 何をするか |
|---|---|---|
| `--session-start` | SessionStart | いまのブランチのタスク定義書のステータス節を注入する |
| `--stop` | Stop | コードを触ったのに定義書を触っていないセッションを 1 度だけ止める |

## なぜこの2つなのか（2026-09-14 に `cli.js` 2.1.81 の実装を読んで確定）

- **`SessionStart` は `source: "compact"` でも発火する**（取りうる値は
  `startup` / `resume` / `clear` / `compact`）。`additionalContext` は圧縮後のコンテキストに入る。
  **これがディスクの実物を運べる唯一の経路。** ただし
  **ファイルが古ければ古い内容が載るだけ**なので、「そもそも古くしない」側は
  `rule_guard.py` の deny（設計完了のまま実装に入らせない）と `--stop` が受け持つ。
- **`Stop` には `stop_hook_active` がある**ので、止めても無限ループにならない。

## `PreCompact` / `PostCompact` を使わない理由（2026-09-16 にユーザー判断で `--precompact` を削除）

- **`PreCompact` は compaction を止められない。** フック実行関数の戻り値は
  `{newCustomInstructions, userDisplayMessage}` の 2 つだけで、中断を伝える経路が無い。
- **`PreCompact` の標準出力は「要約を作るモデルへの指示」にしかならない。**
  圧縮後の Claude が受け取るのは**要約の本文**であって、この指示文ではない。
  要約の出力上限は 20,000 トークン固定なので、「これを残せ」と足せばその分ほかが落ちる。
  **しかも、残ってほしいものの大半（定義書のパス・現在地）は
  `--session-start` がディスクから確実に注入するので重複していた。**
- **`PostCompact` は使えない。** 戻り値が `userDisplayMessage` だけで、画面に出るだけ。
  コンテキストには入らない。
"""

import json
import os
import re
import subprocess
import sys
import time

# FLOW-23 の 6 状態。**この並びが唯一の正**で、他のファイルに書き写さない。
PHASES = ("未着手", "設計中", "設計完了", "実装中", "実装完了", "完了")

STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", "taskdef_status")
STATE_TTL_DAYS = 7

TICKET = re.compile(r"([A-Za-z]{2,}-\d+)")
STATUS_HEAD = re.compile(r"^##\s+ステータス\s*$")
# 「懸念点・確認事項」のように前置きが付く書き方も拾う
QUESTIONS_HEAD = re.compile(r"^##\s+.*確認事項")
ANY_HEAD = re.compile(r"^##\s+")
CHECKBOX = re.compile(r"^\s*-\s*\[( |x|X)\]\s*(.+)$")

MAX_INJECT = 3000


def git(cwd: str, *args) -> str:
    """read-only な git だけを呼ぶ（SAFE-01 の allowlist の範囲）。"""
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout if out.returncode == 0 else ""


def repo_root(cwd: str) -> str:
    return git(cwd, "rev-parse", "--show-toplevel").strip()


def ticket_of(cwd: str) -> str:
    """ブランチ名からチケット番号を取る（`feat/GID-1856/...` → `GID-1856`）。"""
    branch = git(cwd, "rev-parse", "--abbrev-ref", "HEAD").strip()
    match = TICKET.search(branch)
    return match.group(1).upper() if match else ""


def find_taskdef(root: str, ticket: str) -> str:
    """`.claude/tasks/` 配下（`done/` は除く）で、ファイル名にチケット番号を含む .md を探す。

    見つからなければ空文字。**推測で別のファイルを当てない** — 間違ったファイルの
    ステータスを注入すると、無いより悪い（VERIFY-02 と同じ理由）。
    """
    if not root or not ticket:
        return ""
    base = os.path.join(root, ".claude", "tasks")
    if not os.path.isdir(base):
        return ""
    hits = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d != "done"]
        for name in filenames:
            if name.endswith(".md") and ticket.lower() in name.lower():
                hits.append(os.path.join(dirpath, name))
    return sorted(hits)[0] if hits else ""


def section(path: str, head: re.Pattern) -> list:
    """`head` に当たる `##` 見出しから、次の `##` 見出しまでの行を返す。"""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
    except OSError:
        return []
    out, inside = [], False
    for line in lines:
        if ANY_HEAD.match(line):
            if inside:
                break
            inside = bool(head.match(line))
            continue
        if inside:
            out.append(line)
    return out


def status_line(path: str) -> str:
    """ステータス節の**最初のチェックボックス行**＝現在地の 1 行。"""
    for line in section(path, STATUS_HEAD):
        match = CHECKBOX.match(line)
        if match:
            return line.strip()
    return ""


def phase_of(path: str) -> str:
    """現在地の 1 行に現れる状態を返す。6 つのどれでもなければ空文字。"""
    line = status_line(path)
    # 「実装完了」は「完了」を含むので、長い方から当てる
    for phase in sorted(PHASES, key=len, reverse=True):
        if phase in line:
            return phase
    return ""


def pending_questions(path: str, limit: int = 5) -> list:
    """`## 確認事項` に残っている項目（＝ユーザーの判断待ち）を先頭から拾う。

    **実装中に記録すべきものはここだけ**（2026-09-14 ユーザー確認）。
    実装の進捗そのものは追わない —「タスク定義書どおりに実装している限り、
    途中経過に報告する中身は無い」。消えると困るのは、**ワーカーからの
    「定義書と違う実装にした」という申告と、それに対する承認／差し戻し**で、
    これは会話の中にしか無いので compaction で飛ぶ（FLOW-15 / FLOW-22 / FLOW-23）。
    """
    out = []
    for line in section(path, QUESTIONS_HEAD):
        body = line.strip()
        if not body.startswith("- "):
            continue
        match = CHECKBOX.match(line)
        if match:
            if match.group(1) != " ":
                continue  # 決着済みの残骸は数えない（本来は削除されているはず）
            body = "- " + match.group(2).strip()
        out.append(body[:160])
        if len(out) >= limit:
            break
    return out


def locate(cwd: str):
    """(タスク定義書の絶対パス, リポジトリルート) を返す。無ければ ("", "")。"""
    root = repo_root(cwd)
    if not root:
        return "", ""
    path = find_taskdef(root, ticket_of(cwd))
    return path, root


# --- セッションが対象としているタスク定義書 -------------------------------------
# 🔴 **ブランチ名からチケット番号を取る方式をやめた**（2026-10-16 ユーザー指示
# 「ブランチで判断しないで欲しい／編集先のレポジトリやセッションが対象としているタスクで判断して欲しい」）。
#
# なぜ: 1つのワークツリーを複数セッションが共有するので、**他セッションがブランチを切り替えると
# `ticket_of(cwd)` の戻り値が変わり、無関係な定義書で判定していた**。
# 2026-10-16 10:26:59 に私がこのリポジトリを `feat/GID-1679/...` → `feat/GID-1714/...` へ
# 切り替えた直後、GID-1859 を作業していた別セッションの Edit が GID-1714 の定義書（設計完了のまま）で
# 止められ、約 70 分動けなくなった（`git log -g` で確認）。
#
# いまは**そのセッションが実際に開いた（Read / Write / Edit した）定義書**だけを見る。
# 記録が無ければ判定しない（止めない）。推測で別の定義書を当てない（VERIFY-02 と同じ理由）。
SESSION_TASKDEF_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", "session_taskdef")
TASKDEF_FILE = re.compile(r"[/\\]\.claude[/\\]tasks[/\\](?!done[/\\])[^\0]*\.md$")


def _session_taskdef_file(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")
    return os.path.join(SESSION_TASKDEF_DIR, f"{safe}.json")


def record_session_taskdef(session_id: str, path: str) -> None:
    """定義書を開いたら、そのセッションの対象として記録する。"""
    if not session_id or not path or not TASKDEF_FILE.search(path):
        return
    try:
        os.makedirs(SESSION_TASKDEF_DIR, exist_ok=True)
        limit = time.time() - STATE_TTL_DAYS * 86400
        for name in os.listdir(SESSION_TASKDEF_DIR):
            stale = os.path.join(SESSION_TASKDEF_DIR, name)
            if os.path.isfile(stale) and os.path.getmtime(stale) < limit:
                os.remove(stale)
        with open(_session_taskdef_file(session_id), "w", encoding="utf-8") as fh:
            json.dump({"path": os.path.abspath(path), "at": time.time()}, fh, ensure_ascii=False)
    except OSError:
        pass


def locate_for_session(session_id: str):
    """(そのセッションが対象としている定義書, リポジトリルート)。無ければ ("", "")。"""
    try:
        with open(_session_taskdef_file(session_id), encoding="utf-8") as fh:
            path = (json.load(fh) or {}).get("path") or ""
    except (OSError, ValueError):
        return "", ""
    if not path or not os.path.isfile(path):
        return "", ""
    return path, repo_root(os.path.dirname(path))


# --- --session-start ----------------------------------------------------------


# 🔴 同じディレクトリの overview / release-plan からも入れる（2026-10-20 ユーザー決定）。
#
# なぜ: `--session-start` が入れるのは**作業中の定義書 1 枚**だけだった。
# 2026-10-20 の構成（1タスク＝1ディレクトリ。overview＋詳細設計＋release-plan）では、
# 圧縮後に**他のサブタスクと実装以外の作業（R-n）の状態が見えず**、
# **サブタスクをまたぐ決め事も失われる**（失うと、他サブタスクと食い違う実装をする）。
#
# 入れるのは次の3つだけ。**量の少ないものを優先する** — この注入は上限（MAX_INJECT）に
# 当たると後半が落ちるので、`## 読むもの`（パスの列挙で量が大きい）は入れない。
SIBLINGS = (
    ("release-plan.md", re.compile(r"^##\s+タスク一覧"), "全タスクの順番と状態"),
    ("overview.md", re.compile(r"^##\s+基本方針"), "方針（採った案・採らなかった案・リリースの区切り）"),
    ("overview.md", re.compile(r"^##\s+サブタスク間で共有する決め事"), "サブタスクをまたぐ決め事"),
)
MAX_SIBLING = 1500


def sibling_blocks(path: str, root: str) -> list:
    """作業中の定義書と同じディレクトリの overview / release-plan から、必要な節だけ返す。"""
    directory = os.path.dirname(path)
    out = []
    for name, head, label in SIBLINGS:
        target = os.path.join(directory, name)
        # 作業中の定義書が overview 自身でも入れる。上の本体が入れるのは
        # ステータス節・表・確認事項だけで、`## 基本方針` などは入らないため（重複しない）。
        if not os.path.isfile(target):
            continue
        body = "\n".join(section(target, head)).strip()
        if not body:
            continue
        if len(body) > MAX_SIBLING:
            body = body[:MAX_SIBLING] + "\n…（以降は省略。全文はファイルを開く）"
        rel = os.path.relpath(target, root) if root else target
        out += ["", f"**{label}**（`{rel}`）", "", body]
    return out


def mode_session_start(data: dict) -> None:
    """圧縮後・再開後のコンテキストへ、**ディスクの実物**を入れる。

    ステータス節をそのまま貼らない。実運用の定義書では、この節に決定の履歴が
    積み上がっていることがあり（実測: GID-1856 は節の大半が履歴）、
    **上限に当たって肝心の表が落ちる**。
    そこで「現在地の 1 行」と「`###` の表」だけを拾い、履歴は捨てる。
    """
    # ブランチ名から当てない（上の `locate_for_session` のコメント参照）。
    # 圧縮・再開では session_id が変わらないので、同じセッションが開いた定義書が残っている。
    path, root = locate_for_session(data.get("session_id") or "")
    if not path:
        sys.exit(0)
    rel = os.path.relpath(path, root) if root else path
    lines = section(path, STATUS_HEAD)

    # `###` の小見出しと、その直後に続く表の行だけを拾う。
    # 表が終わって別の文章（＝履歴や注記）が始まったら、そこで打ち切る。
    tables, keep = [], False
    for line in lines:
        if line.startswith("### "):
            keep = True
            tables.append(line)
            continue
        if not keep:
            continue
        if line.strip() == "" or line.lstrip().startswith("|"):
            tables.append(line)
        else:
            keep = False
    block = "\n".join(tables).strip()
    if len(block) > MAX_INJECT:
        block = block[:MAX_INJECT] + "\n…（以降は省略。全文はファイルを開く）"

    parts = [
        f"📌 作業中のタスク定義書: `{rel}`（このファイルが唯一の真実 — COMM-10）",
        "",
        f"**現在地**: {status_line(path) or '（ステータス行が無い。FLOW-23 違反）'}",
    ]
    if block:
        parts += ["", "**並列に動いているものの最新状態**（履歴は省いた）", "", block]

    questions = pending_questions(path)
    if questions:
        parts += ["", "**ユーザーの判断待ち（`## 確認事項` に残っているもの・先頭5件）**", ""]
        parts += questions

    parts += sibling_blocks(path, root)

    parts += [
        "",
        "⚠️ **この内容が実態と食い違っていたら、それは更新漏れ。作業を進める前に直す**（FLOW-23）。",
    ]
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "\n".join(parts),
                }
            },
            ensure_ascii=False,
        )
    )
    sys.exit(0)


# --- --stop -------------------------------------------------------------------


def _state_path(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")
    return os.path.join(STATE_DIR, f"{safe}.json")


def _sweep_state() -> None:
    """自分が作った状態ファイルだけを掃除する（META-01 と同じ考え方）。"""
    limit = time.time() - STATE_TTL_DAYS * 86400
    try:
        names = os.listdir(STATE_DIR)
    except OSError:
        return
    for name in names:
        path = os.path.join(STATE_DIR, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < limit:
                os.remove(path)
        except OSError:
            continue


def _changed_paths(root: str) -> list:
    """`git status --porcelain` から、作業ツリーで変更された実ファイルを返す。"""
    out = []
    for line in git(root, "status", "--porcelain").split("\n"):
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:  # リネーム
            path = path.split(" -> ", 1)[1]
        path = path.strip().strip('"')
        if path.startswith(".claude/"):
            continue  # タスク定義書・作業メモ自体は「コードを触った」に数えない
        full = os.path.join(root, path)
        if os.path.isfile(full):
            out.append(full)
    return out


def _newest_mtime(paths: list) -> float:
    newest = 0.0
    for path in paths:
        try:
            newest = max(newest, os.path.getmtime(path))
        except OSError:
            continue
    return newest


def mode_stop(data: dict) -> None:
    """コードを触ったのに、タスク定義書をそのあと一度も触っていないなら止める。

    止める条件は「**定義書の更新時刻より新しい変更が、コード側にある**」こと。
    判定は時刻の比較だけで、内容は見ない（内容の正否は機械には当てられない）。

    2 重の歯止めを置く:
      1. `stop_hook_active` が立っていれば何もしない（同じターンで繰り返さない）
      2. 一度止めたら、そのときのコード側の最新時刻を記録する。
         **それより新しい変更が出るまで、二度と止めない**（毎ターン止まるのを防ぐ）
    """
    if data.get("stop_hook_active"):
        sys.exit(0)
    cwd = data.get("cwd") or os.getcwd()
    # ブランチ名から当てない（`locate_for_session` のコメント参照）
    path, root = locate_for_session(data.get("session_id") or "")
    if not path or not root:
        sys.exit(0)
    try:
        taskdef_mtime = os.path.getmtime(path)
    except OSError:
        sys.exit(0)

    changed = _changed_paths(root)
    newest = _newest_mtime(changed)
    if newest <= taskdef_mtime:
        sys.exit(0)

    _sweep_state()
    os.makedirs(STATE_DIR, exist_ok=True)
    state_file = _state_path(data.get("session_id") or "")
    notified = 0.0
    try:
        with open(state_file, encoding="utf-8") as fh:
            notified = float(json.load(fh).get("notified_mtime") or 0.0)
    except (OSError, ValueError, json.JSONDecodeError):
        notified = 0.0
    if newest <= notified:
        sys.exit(0)

    try:
        with open(state_file, "w", encoding="utf-8") as fh:
            json.dump({"notified_mtime": newest}, fh)
    except OSError:
        pass

    rel = os.path.relpath(path, root)
    newest_rel = ""
    for candidate in changed:
        try:
            if os.path.getmtime(candidate) == newest:
                newest_rel = os.path.relpath(candidate, root)
                break
        except OSError:
            continue
    sys.stderr.write(
        "[FLOW-23] タスク定義書を更新せずに終わろうとしている。\n"
        f"  定義書: {rel}（最終更新はコードより古い）\n"
        f"  現在地: {status_line(path) or '(ステータス行が無い)'}\n"
        f"  定義書より新しいコードの変更: {newest_rel or '(不明)'}\n"
        "次をこの場でやること。**やったうえで終わる。**\n"
        "  1. 定義書と違う実装をした／ワーカーがそう申告したなら、"
        "`## 確認事項` に1件ずつ起こす（会話に置かない。ここが消えると承認も差し戻しもできない）\n"
        "  2. 状態が変わっていれば現在地の1行を書き換える"
        f"（{' → '.join(PHASES)}）\n"
        "  3. 検証ゲート・レビューを回したなら、その表を最新の結果で上書きする\n"
        "更新が不要だと判断したなら、その理由を1行添えてそのまま終えてよい"
        "（この確認は同じ変更に対して二度は出ない）。\n"
    )
    sys.exit(2)


MODES = {
    "--session-start": mode_session_start,
    "--stop": mode_stop,
}


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in MODES:
        sys.stderr.write(f"usage: taskdef_status.py [{' | '.join(MODES)}]\n")
        sys.exit(1)
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        data = {}
    MODES[mode](data)


if __name__ == "__main__":
    main()
