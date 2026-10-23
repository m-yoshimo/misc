#!/usr/bin/env python3
"""`rm` の deny（SAFE-09）と、ユーザー発言による許可（`rm_grant.py`）の検証。

**実際にファイルを消すテストは1つも書かない。** フックの判定だけを見る。
許可の記録先は一時ディレクトリに差し替えるので、本物の
`~/.claude/state/rm_grant/` は触らない。
"""

import io
import json
import os
import sys
import contextlib
import tempfile

HOOKS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS)

import rule_guard  # noqa: E402
import rm_grant  # noqa: E402

SESSION = "sess-1234"


def guard(cmd: str, session_id: str = SESSION):
    """rule_guard を通し、(deny したか, 理由文) を返す。"""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            rule_guard.check_rm(cmd, {"session_id": session_id})
        except SystemExit:
            pass
    text = out.getvalue()
    if not text.strip():
        return False, ""
    payload = json.loads(text)["hookSpecificOutput"]
    return payload.get("permissionDecision") == "deny", payload.get(
        "permissionDecisionReason", ""
    )


def submit(prompt: str, session_id: str = SESSION) -> None:
    """UserPromptSubmit フックに発言を流す。"""
    stdin = io.StringIO(json.dumps({"prompt": prompt, "session_id": session_id}))
    old = sys.stdin
    sys.stdin = stdin
    try:
        rm_grant.main()
    except SystemExit:
        pass
    finally:
        sys.stdin = old


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- ルール読み込みを省く許可（2026-10-22 ユーザー指示）--------------------------
# `build_prompt.py research --no-rules` が見る記録。**記録できるのはユーザーの発言だけ。**


@case
def test_no_rules_grant_recorded_from_user_words(failures):
    for prompt in (
        "ルールは不要なので、admingraph の Mutation を列挙して",
        "ルール読まなくて良いから、さっと調べて",
        "ルール抜きで調査して",
        "メモリの読み込みは不要",
    ):
        submit(prompt)
        if not os.path.isfile(rm_grant.state_path(SESSION, rm_grant.NO_RULES_DIR)):
            failures.append(f"許可が記録されていない: {prompt}")


@case
def test_no_rules_grant_absent_without_user_words(failures):
    submit("ルールは必ず守らせて調査して")
    if os.path.isfile(rm_grant.state_path(SESSION, rm_grant.NO_RULES_DIR)):
        failures.append("ルール不要と言っていないのに許可が記録されている")


@case
def test_no_rules_grant_expires_next_turn(failures):
    submit("ルールは不要なので調べて")
    submit("ありがとう、次はこれを見て")
    if os.path.isfile(rm_grant.state_path(SESSION, rm_grant.NO_RULES_DIR)):
        failures.append("次のターンで失効していない")


# --- 許可が無いとき ------------------------------------------------------------


@case
def test_blocks_rm_without_grant(failures):
    for cmd in (
        "rm apps/api/main.go",
        "rm -rf apps/front/src/features/DailyKuji",
        "rmdir .claude/notes/old",
        "unlink /home/m-yoshimo/work/foo.txt",
        "sudo rm -rf /etc/hosts",
        "find apps -name '*.log' -delete",
    ):
        denied, reason = guard(cmd)
        if not denied:
            failures.append(f"止めていない: {cmd}")
        elif "SAFE-09" not in reason:
            failures.append(f"理由に SAFE-09 が無い: {cmd}")


@case
def test_blocks_rm_inside_pipeline_and_chain(failures):
    for cmd in (
        "cd apps && rm -rf dist",
        "echo start; rm -f out.log",
        "make build && rm -rf node_modules",
    ):
        denied, _ = guard(cmd)
        if not denied:
            failures.append(f"連結されたコマンドの中の rm を見逃した: {cmd}")


@case
def test_does_not_block_mentions_of_rm(failures):
    """コマンドではなく文字列として rm が出るだけのものは止めない。"""
    for cmd in (
        'echo "rm -rf は危険"',
        "grep -n 'rm -rf' docs/guide.md",
        "cat .claude/notes/rm-policy.md",
    ):
        denied, _ = guard(cmd)
        if denied:
            failures.append(f"表示だけなのに止めた: {cmd}")


@case
def test_does_not_block_other_commands(failures):
    for cmd in ("ls -la", "git status", "mv a.md .claude/tasks/done/a.md"):
        denied, _ = guard(cmd)
        if denied:
            failures.append(f"rm でないのに止めた: {cmd}")


# --- ルールが削除を命じている場所（許可が要らない）--------------------------------


@case
def test_allows_self_owned_paths(failures):
    """`.claude/tmp/` と `~/.claude/state/` は META-01 が削除を命じている（軸0）。"""
    for cmd in (
        "rm -rf .claude/tmp/GID-1856",
        "rm .claude/tmp/GID-1856/out.log",
        "rm -f /home/m-yoshimo/.claude/state/rm_grant/old.json",
    ):
        denied, _ = guard(cmd)
        if denied:
            failures.append(f"自分の作業ファイルの掃除を止めた: {cmd}")


@case
def test_mixed_targets_still_blocked(failures):
    """作業ファイルに紛れて別の場所を消そうとしたら止める。"""
    denied, _ = guard("rm -rf .claude/tmp/GID-1856 apps/api/main.go")
    if not denied:
        failures.append("作業ファイル以外が混ざっているのに通した")


# --- ユーザーの発言による許可 ---------------------------------------------------


@case
def test_grant_from_user_message(failures):
    submit("さっきの一時ファイル、消しておいて")
    denied, _ = guard("rm apps/api/tmp.txt")
    if denied:
        failures.append("ユーザーが「消しておいて」と言ったのに止めた")


@case
def test_grant_words(failures):
    for prompt in (
        "この dir 削除して",
        "rm しちゃって",
        "使ってないやつ捨てていいよ",
        "クリーンアップして",
    ):
        submit(prompt)
        denied, _ = guard("rm -rf build")
        if denied:
            failures.append(f"許可として扱われなかった: {prompt}")


@case
def test_grant_expires_on_next_message(failures):
    submit("消しておいて")
    denied, _ = guard("rm apps/api/tmp.txt")
    if denied:
        failures.append("許可したターンで止めた")
    submit("ありがとう、次はテスト流して")
    denied, _ = guard("rm apps/api/tmp.txt")
    if not denied:
        failures.append("次のターンでも許可が残っている（そのターン限りのはず）")


@case
def test_grant_is_per_session(failures):
    submit("消しておいて", session_id="sess-A")
    denied, _ = guard("rm foo.txt", session_id="sess-B")
    if not denied:
        failures.append("別セッションの許可で通してしまった")


@case
def test_claude_cannot_grant_itself(failures):
    """Claude の出力ではなく、**ユーザーの発言**だけが許可になることの確認。

    `rm_grant.py` が読むのは `UserPromptSubmit` の `prompt`（ユーザーの発言）だけで、
    Claude 側から書き込む経路はこのフックには無い。
    """
    submit("テストを流して")  # 削除に触れていない
    denied, _ = guard("rm -rf apps")
    if not denied:
        failures.append("許可が無いのに通した")


def main() -> None:
    failures = []
    original = rm_grant.STATE_DIR
    original_no_rules = rm_grant.NO_RULES_DIR
    with tempfile.TemporaryDirectory() as tmp:
        rm_grant.STATE_DIR = os.path.join(tmp, "rm_grant")
        # 本物の `~/.claude/state/no_rules_grant/` を触らない
        rm_grant.NO_RULES_DIR = os.path.join(tmp, "no_rules_grant")
        rule_guard.RM_GRANT_DIR = rm_grant.STATE_DIR
        for fn in CASES:
            before = len(failures)
            try:
                fn(failures)
            except Exception as exc:
                failures.append(f"{fn.__name__}: 例外 {exc!r}")
            for i in range(before, len(failures)):
                failures[i] = f"{fn.__name__}: {failures[i]}"
    rm_grant.STATE_DIR = original
    rm_grant.NO_RULES_DIR = original_no_rules

    print(f"ケース数: {len(CASES)}")
    for f in failures:
        print(f"  NG {f}")
    print(f"不一致: {len(failures)} 件")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
