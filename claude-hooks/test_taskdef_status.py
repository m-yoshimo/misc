#!/usr/bin/env python3
"""`taskdef_status.py`（FLOW-23）の検証。

**git は一度も呼ばない。** `taskdef_status.git` を差し替えて、決め打ちの出力を返させる。
理由は 2 つ:
  - `git init` は SAFE-01 の allowlist に無い（テストのためでも実行しない）
  - 実リポジトリに依存すると、ブランチを切り替えただけでテストの結果が変わる

`rule_guard.check_taskdef_phase`（設計完了のまま実装に入ったら deny）も、
同じ差し替えでここから検証する。
"""

import io
import json
import os
import sys
import time
import contextlib
import tempfile

HOOKS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS)

import taskdef_status as ts  # noqa: E402
import rule_guard  # noqa: E402

BRANCH = "feat/GID-9999/sample_work"
SESSION = "sess-under-test"

TASKDEF = """# サンプル

## ステータス

- [ ] **{phase}**（2026-09-14）

### 検証ゲートの最新状態

| ゲート | コマンド | 結果 | 実行時刻 |
|---|---|---|---|
| Go テスト全件 | `make test` | ✅ ok | 09-14 11:03 |

## 懸念点・確認事項

- Q1 Worker A が `DecideRank` の引数を変えた。承認するか差し戻すか
- Q2 辞書のキー名を定義書と変えた。承認するか差し戻すか

## 読むもの

- なし
"""


def build(tmp: str, phase: str) -> str:
    """タスク定義書を 1 つ持つ、リポジトリに見える木を作る。"""
    d = os.path.join(tmp, ".claude", "tasks", "GID-9000-parent")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "GID-9999-sample.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(TASKDEF.format(phase=phase))
    # done/ 配下は探索対象外であることを見るための囮
    done = os.path.join(tmp, ".claude", "tasks", "done")
    os.makedirs(done, exist_ok=True)
    with open(os.path.join(done, "GID-9999-old.md"), "w", encoding="utf-8") as fh:
        fh.write("# 済み\n\n## ステータス\n\n### 検証ゲートの最新状態\n\n- [x] **完了**\n")
    # 🔴 2026-10-16 以降、判定に使うのは**セッションが開いた定義書**（ブランチ名では当てない）。
    # 定義書を 1 つ作ったら、既定のセッション（SESSION）が開いた状態にしておく。
    ts.SESSION_TASKDEF_DIR = os.path.join(tmp, "state", "session_taskdef")
    ts.record_session_taskdef(SESSION, path)
    return path


def fake_git(tmp: str, porcelain: str = ""):
    def _git(cwd, *args):
        if args[:2] == ("rev-parse", "--show-toplevel"):
            return tmp + "\n"
        if args[:2] == ("rev-parse", "--abbrev-ref"):
            return BRANCH + "\n"
        if args[:1] == ("status",):
            return porcelain
        return ""
    return _git


def run(fn, data: dict):
    """モードを呼び、(終了コード, stdout, stderr) を返す。"""
    data = {"session_id": SESSION, **data}
    out, err = io.StringIO(), io.StringIO()
    code = None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            fn(data)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def touch(path: str, offset: float) -> None:
    now = time.time() + offset
    os.utime(path, (now, now))


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- 読み取り部分 --------------------------------------------------------------


@case
def test_finds_taskdef_and_skips_done(tmp, failures):
    path = build(tmp, "実装中")
    found = ts.find_taskdef(tmp, "GID-9999")
    if found != path:
        failures.append(f"タスク定義書の特定に失敗: {found}")
    if "done" in found:
        failures.append("done/ 配下を拾っている")


@case
def test_phase_detection(tmp, failures):
    for phase in ts.PHASES:
        path = build(tmp, phase)
        got = ts.phase_of(path)
        if got != phase:
            failures.append(f"状態の判定が違う: 期待 {phase} / 実際 {got}")


@case
def test_phase_unknown_word(tmp, failures):
    path = build(tmp, "進行中")  # 6 つに無い語
    if ts.phase_of(path) != "":
        failures.append("6 つに無い状態名を受け入れている")


@case
def test_pending_questions(tmp, failures):
    """実装中に拾うのは進捗ではなく、**ユーザーの判断待ち**（2026-09-14 ユーザー確認）。"""
    path = build(tmp, "実装中")
    questions = ts.pending_questions(path)
    if len(questions) != 2 or "Worker A" not in questions[0]:
        failures.append(f"判断待ちの確認事項が取れていない: {questions}")


@case
def test_pending_questions_skips_settled(tmp, failures):
    """決着済みの残骸（`- [x]`）を判断待ちに数えないこと。"""
    path = build(tmp, "実装中")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    text = text.replace("- Q1 Worker A", "- [x] Q1 Worker A")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    questions = ts.pending_questions(path)
    if any("Worker A" in q for q in questions):
        failures.append("決着済みの項目を判断待ちに数えている")


@case
def test_no_ticket_no_taskdef(tmp, failures):
    build(tmp, "実装中")
    if ts.find_taskdef(tmp, "") != "":
        failures.append("チケット番号が無いのにファイルを当てている")
    if ts.find_taskdef(tmp, "GID-0001") != "":
        failures.append("該当しないチケットでファイルを当てている")


# --- --session-start ----------------------------------------------------------


OVERVIEW = """# サンプル — overview

## ステータス

- [ ] **設計中**（2026-10-20）

## 基本方針

- 採った案: 管理画面から操作する
- 採らなかった案と理由: 利用者で完結する案は悪用の可能性があるため

## サブタスク間で共有する決め事

| 決め事 | 内容 | 理由 |
|---|---|---|
| コードの置き場 | 専用テーブルを新設する | 有効期限が違う |

## 読むもの（実装者・レビュアー共通）

- PRD: `docs/prd.md`
"""

RELEASE_PLAN = """<!-- taskdef-format: skip -->
# サンプル リリース計画・タスク管理

## この資料で扱うもの

- 進捗はこの資料だけが持つ

## タスク一覧

| 順 | ID | 種類 | タスク | 前提 | 担当 | 状態 |
|---|---|---|---|---|---|---|
| 1 | S-1 | 実装 | 送信 API | なし | Claude | 作業中 |
| ― | R-1 | 実装以外 | フラグを ON にする | S-1 | ユーザー | 未着手 |

## R-1 フラグを ON にする

- 手順はここに書く
"""


def build_siblings(tmp: str) -> None:
    """作業中の定義書と同じディレクトリに overview / release-plan を置く。"""
    d = os.path.join(tmp, ".claude", "tasks", "GID-9000-parent")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "overview.md"), "w", encoding="utf-8") as fh:
        fh.write(OVERVIEW)
    with open(os.path.join(d, "release-plan.md"), "w", encoding="utf-8") as fh:
        fh.write(RELEASE_PLAN)


@case
def test_session_start_injects_siblings(tmp, failures):
    """🔴 同じディレクトリの overview / release-plan の必要な節も入ること（2026-10-20）。"""
    build(tmp, "実装中")
    build_siblings(tmp)
    ts.git = fake_git(tmp)
    code, out, _ = run(ts.mode_session_start, {"cwd": tmp})
    if code != 0:
        failures.append(f"終了コードが {code}")
        return
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    for expect in ("release-plan.md", "S-1", "R-1", "採らなかった案", "専用テーブル"):
        if expect not in ctx:
            failures.append(f"注入内容に {expect} が無い")
    # 量の大きい `## 読むもの` は入れない
    if "docs/prd.md" in ctx:
        failures.append("`## 読むもの` を注入している（量が大きいので入れない）")
    # release-plan の手順（`## R-n`）も入れない
    if "手順はここに書く" in ctx:
        failures.append("`## R-n` の手順を注入している（入れない）")


@case
def test_session_start_without_siblings(tmp, failures):
    """overview / release-plan が無いタスクでも、今までどおり動くこと。"""
    build(tmp, "実装中")
    ts.git = fake_git(tmp)
    code, out, _ = run(ts.mode_session_start, {"cwd": tmp})
    if code != 0:
        failures.append(f"終了コードが {code}")
        return
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    if "GID-9999-sample.md" not in ctx or "実装中" not in ctx:
        failures.append("作業中の定義書の注入が壊れている")


@case
def test_session_start_overview_itself(tmp, failures):
    """overview を開いているセッションでは、overview を二重に注入しないこと。"""
    build(tmp, "実装中")
    build_siblings(tmp)
    overview = os.path.join(tmp, ".claude", "tasks", "GID-9000-parent", "overview.md")
    ts.SESSION_TASKDEF_DIR = os.path.join(tmp, "state", "session_taskdef")
    ts.record_session_taskdef(SESSION, overview)
    ts.git = fake_git(tmp)
    code, out, _ = run(ts.mode_session_start, {"cwd": tmp})
    if code != 0:
        failures.append(f"終了コードが {code}")
        return
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    if ctx.count("悪用の可能性") != 1:
        failures.append(f"overview の節が重複して入っている（{ctx.count('悪用の可能性')} 回）")
    if "S-1" not in ctx:
        failures.append("release-plan のタスク一覧が入っていない")


@case
def test_session_start_injects_disk_truth(tmp, failures):
    build(tmp, "実装中")
    ts.git = fake_git(tmp)
    code, out, _ = run(ts.mode_session_start, {"cwd": tmp})
    if code != 0:
        failures.append(f"session-start の終了コードが {code}")
        return
    payload = json.loads(out)["hookSpecificOutput"]
    if payload["hookEventName"] != "SessionStart":
        failures.append("hookEventName が SessionStart でない")
    ctx = payload["additionalContext"]
    for expect in ("GID-9999-sample.md", "実装中", "Worker A", "判断待ち"):
        if expect not in ctx:
            failures.append(f"注入内容に {expect} が無い")


@case
def test_session_start_drops_history_keeps_tables(tmp, failures):
    """ステータス節に決定の履歴が積まれていても、表が落ちないこと。

    実測（GID-1856）で、節の大半が履歴になっている定義書があった。
    そのまま貼ると上限に当たり、**肝心の表が落ちる**。
    """
    path = build(tmp, "実装完了")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    history = "\n".join(f"- 2026-09-0{i % 9} 決定の履歴 " + "あ" * 200 for i in range(40))
    marker = "## 懸念点・確認事項"
    if marker not in text:
        failures.append("テストの仕込み位置が見つからない（テスト自体が古い）")
        return
    text = text.replace(marker, history + "\n\n" + marker)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)

    ts.git = fake_git(tmp)
    _, out, _ = run(ts.mode_session_start, {"cwd": tmp})
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    if "Go テスト全件" not in ctx:
        failures.append("履歴に押し出されて検証ゲートの表が落ちている")
    if "決定の履歴" in ctx:
        failures.append("履歴を注入している（現在地と表だけでよい）")
    if "実装完了" not in ctx:
        failures.append("現在地の 1 行が落ちている")


@case
def test_session_start_never_asks_for_progress_checklist(tmp, failures):
    """進捗のチェックリストを要求しないこと（2026-09-14 に廃止した）。"""
    path = build(tmp, "実装中")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    text = text.replace("## 懸念点・確認事項", "## 変更対象ファイル一覧")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)

    ts.git = fake_git(tmp)
    _, out, _ = run(ts.mode_session_start, {"cwd": tmp})
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    if "実装ステップ" in ctx:
        failures.append("廃止した実装ステップを要求している")
    if "実装中" not in ctx:
        failures.append("現在地が落ちている")


@case
def test_session_start_silent_without_taskdef(tmp, failures):
    ts.git = fake_git(tmp)  # タスク定義書を作らない
    code, out, _ = run(ts.mode_session_start, {"cwd": tmp})
    if code != 0 or out.strip():
        failures.append("タスク定義書が無いのに何か出力している")


# --- モードの一覧 --------------------------------------------------------------


@case
def test_precompact_mode_is_gone(tmp, failures):
    """`--precompact` を復活させないための歯止め（2026-09-16 ユーザー判断で削除）。

    削除理由: PreCompact の標準出力は**要約を作るモデルへの指示**にしかならず、
    圧縮後の Claude には要約の本文しか届かない。しかも残したかったもの
    （定義書のパス・現在地）は `--session-start` がディスクから確実に注入するので重複していた。
    """
    if "--precompact" in ts.MODES or hasattr(ts, "mode_precompact"):
        failures.append("--precompact が残っている")


# --- --stop -------------------------------------------------------------------


def stop_env(tmp, porcelain=" M apps/api/main.go\n"):
    src = os.path.join(tmp, "apps", "api")
    os.makedirs(src, exist_ok=True)
    path = os.path.join(src, "main.go")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("package main\n")
    ts.git = fake_git(tmp, porcelain)
    ts.STATE_DIR = os.path.join(tmp, "state")
    return path


@case
def test_stop_blocks_when_code_is_newer(tmp, failures):
    taskdef = build(tmp, "実装中")
    src = stop_env(tmp)
    touch(taskdef, -600)
    touch(src, 0)
    code, _, err = run(ts.mode_stop, {"cwd": tmp, "session_id": SESSION})
    if code != 2:
        failures.append(f"コードの方が新しいのに止めていない（終了コード {code}）")
    if "FLOW-23" not in err:
        failures.append("止めた理由に FLOW-23 が無い")
    if "main.go" not in err:
        failures.append("どのファイルが新しいかを示していない")


@case
def test_stop_passes_when_taskdef_is_newer(tmp, failures):
    taskdef = build(tmp, "実装中")
    src = stop_env(tmp)
    touch(src, -600)
    touch(taskdef, 0)
    code, _, _ = run(ts.mode_stop, {"cwd": tmp, "session_id": SESSION})
    if code not in (0, None):
        failures.append(f"定義書の方が新しいのに止めている（終了コード {code}）")


@case
def test_stop_does_not_repeat_for_same_change(tmp, failures):
    taskdef = build(tmp, "実装中")
    src = stop_env(tmp)
    touch(taskdef, -600)
    touch(src, 0)
    first, _, _ = run(ts.mode_stop, {"cwd": tmp, "session_id": SESSION})
    second, _, _ = run(ts.mode_stop, {"cwd": tmp, "session_id": SESSION})
    if first != 2:
        failures.append("1 回目で止まっていない")
    if second == 2:
        failures.append("同じ変更に対して 2 回止めている（毎ターン止まる）")


@case
def test_stop_blocks_again_for_new_change(tmp, failures):
    taskdef = build(tmp, "実装中")
    src = stop_env(tmp)
    touch(taskdef, -600)
    touch(src, -300)
    run(ts.mode_stop, {"cwd": tmp, "session_id": SESSION})
    touch(src, 0)  # さらに新しい変更
    code, _, _ = run(ts.mode_stop, {"cwd": tmp, "session_id": SESSION})
    if code != 2:
        failures.append("通知後に新しい変更が出ても止めていない")


@case
def test_stop_respects_stop_hook_active(tmp, failures):
    taskdef = build(tmp, "実装中")
    src = stop_env(tmp)
    touch(taskdef, -600)
    touch(src, 0)
    code, _, _ = run(
        ts.mode_stop, {"cwd": tmp, "session_id": SESSION, "stop_hook_active": True}
    )
    if code == 2:
        failures.append("stop_hook_active が立っているのに止めている（無限ループになる）")


@case
def test_stop_ignores_claude_dir_changes(tmp, failures):
    taskdef = build(tmp, "実装中")
    stop_env(tmp, porcelain=" M .claude/tasks/GID-9000-parent/GID-9999-sample.md\n")
    touch(taskdef, 0)
    code, _, _ = run(ts.mode_stop, {"cwd": tmp, "session_id": SESSION})
    if code == 2:
        failures.append(".claude/ 配下の変更を「コードを触った」に数えている")


@case
def test_stop_silent_without_taskdef(tmp, failures):
    stop_env(tmp)  # タスク定義書を作らない
    code, _, err = run(ts.mode_stop, {"cwd": tmp, "session_id": SESSION})
    if code == 2 or err.strip():
        failures.append("タスク定義書が無いのに止めている")


# --- rule_guard の FLOW-23 deny ------------------------------------------------


def guard(tmp, data, tool, tool_input):
    ts.git = fake_git(tmp)
    out = io.StringIO()
    code = None
    with contextlib.redirect_stdout(out):
        try:
            rule_guard.check_taskdef_phase(
                {"session_id": SESSION, **data, "cwd": tmp}, tool, tool_input
            )
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue()


@case
def test_guard_denies_impl_edit_while_design_done(tmp, failures):
    build(tmp, "設計完了")
    _, out = guard(tmp, {}, "Edit", {"file_path": os.path.join(tmp, "apps/api/main.go")})
    if "deny" not in out or "FLOW-23" not in out:
        failures.append("設計完了のまま実装ファイルを編集しようとしたのに止めていない")


@case
def test_guard_allows_taskdef_edit(tmp, failures):
    path = build(tmp, "設計完了")
    _, out = guard(tmp, {}, "Edit", {"file_path": path})
    if out.strip():
        failures.append("タスク定義書自体の編集を止めている（ステータスを直せなくなる）")


@case
def test_guard_allows_when_phase_is_impl(tmp, failures):
    build(tmp, "実装中")
    _, out = guard(tmp, {}, "Edit", {"file_path": os.path.join(tmp, "apps/api/main.go")})
    if out.strip():
        failures.append("実装中なのに止めている")


@case
def test_guard_denies_delegation_while_design_done(tmp, failures):
    build(tmp, "設計完了")
    _, out = guard(
        tmp, {}, "Agent",
        {"prompt": "`.claude/tasks/GID-9999-sample.md` のとおり実装して。無断改変として扱う。"},
    )
    if "deny" not in out:
        failures.append("設計完了のままワーカーを起動しようとしたのに止めていない")


@case
def test_guard_skips_subagent(tmp, failures):
    build(tmp, "設計完了")
    _, out = guard(
        tmp, {"agent_id": "agent_123"}, "Edit",
        {"file_path": os.path.join(tmp, "apps/api/main.go")},
    )
    if out.strip():
        failures.append("サブエージェントを止めている（ステータスの持ち主ではない）")


@case
def test_guard_ignores_other_sessions_taskdef(tmp, failures):
    """🔴 他セッションが開いた定義書で止めないこと（2026-10-16 の事故）。

    1つのワークツリーを複数セッションが共有していて、別セッションがブランチを
    `feat/GID-1714/...` へ切り替えた瞬間、GID-1859 を作業していたセッションの Edit が
    GID-1714（設計完了のまま）で止められ、約 70 分動けなくなった。
    """
    build(tmp, "設計完了")  # 記録されるのは SESSION
    _, out = guard(
        tmp, {"session_id": "another-session"}, "Edit",
        {"file_path": os.path.join(tmp, "apps/api/main.go")},
    )
    if out.strip():
        failures.append("自分が開いていない定義書で止めている")


@case
def test_guard_ignores_branch_name(tmp, failures):
    """ブランチ名が別チケットに切り替わっても、判定は開いた定義書のまま。"""
    build(tmp, "設計完了")
    ts.git = lambda cwd, *a: (
        tmp + "\n" if a[:2] == ("rev-parse", "--show-toplevel")
        else "feat/GID-1234/other-work\n" if a[:2] == ("rev-parse", "--abbrev-ref") else ""
    )
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            rule_guard.check_taskdef_phase(
                {"session_id": SESSION, "cwd": tmp}, "Edit",
                {"file_path": os.path.join(tmp, "apps/api/main.go")},
            )
        except SystemExit:
            pass
    if "FLOW-23" not in out.getvalue():
        failures.append("ブランチ名が変わると判定できなくなっている")


@case
def test_guard_denies_edit_in_other_repository(tmp, failures):
    """定義書と別リポジトリのファイルでも、同じタスクなら判定する。

    GID-1859 のように、idpf-api のタスク定義書で idpf-admin-frontend を直す作業がある。
    """
    build(tmp, "設計完了")
    other = os.path.join(tmp, "..", "other-repo", "app", "Form.tsx")
    _, out = guard(tmp, {}, "Edit", {"file_path": os.path.abspath(other)})
    if "FLOW-23" not in out:
        failures.append("別リポジトリのファイルだと判定していない")


@case
def test_guard_silent_when_taskdef_was_removed(tmp, failures):
    """記録した定義書が消えていたら判定しない（推測で別のものを当てない）。"""
    path = build(tmp, "設計完了")
    os.remove(path)
    _, out = guard(tmp, {}, "Edit", {"file_path": os.path.join(tmp, "apps/api/main.go")})
    if out.strip():
        failures.append("記録先が消えているのに止めている")


@case
def test_record_only_taskdef_paths(tmp, failures):
    """`.claude/tasks/` 配下の .md 以外は記録しない（done/ も対象外）。"""
    ts.SESSION_TASKDEF_DIR = os.path.join(tmp, "state", "session_taskdef")
    for path in (
        os.path.join(tmp, "apps", "api", "main.go"),
        os.path.join(tmp, ".claude", "tmp", "GID-1/x.md"),
        os.path.join(tmp, ".claude", "tasks", "done", "GID-2-old.md"),
    ):
        ts.record_session_taskdef("sess-x", path)
        got, _ = ts.locate_for_session("sess-x")
        if got:
            failures.append(f"記録すべきでないパスを記録した: {path}")


@case
def test_guard_silent_outside_repo(tmp, failures):
    build(tmp, "設計完了")
    ts.git = lambda cwd, *a: ""  # リポジトリではない
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            rule_guard.check_taskdef_phase({"cwd": tmp}, "Edit", {"file_path": "/x/y.go"})
        except SystemExit:
            pass
    if out.getvalue().strip():
        failures.append("リポジトリ外なのに止めている")


def main() -> None:
    failures = []
    original_git, original_state = ts.git, ts.STATE_DIR
    original_session_dir = ts.SESSION_TASKDEF_DIR
    for fn in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            before = len(failures)
            try:
                fn(tmp, failures)
            except Exception as exc:  # テスト自身の落ち方も失敗として出す
                failures.append(f"{fn.__name__}: 例外 {exc!r}")
            for i in range(before, len(failures)):
                failures[i] = f"{fn.__name__}: {failures[i]}"
            ts.git, ts.STATE_DIR = original_git, original_state
            ts.SESSION_TASKDEF_DIR = original_session_dir

    print(f"ケース数: {len(CASES)}")
    for f in failures:
        print(f"  NG {f}")
    print(f"不一致: {len(failures)} 件")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
