#!/usr/bin/env python3
"""`delegate_guard.py`（委任の指示文の発行印の検査）の検証。

発行記録は一時ファイルに差し替えるので、本物の `~/.claude/state/delegate/` は触らない。
"""

import contextlib
import io
import json
import os
import sys
import tempfile

HOOKS = os.path.dirname(os.path.abspath(__file__))
_TMP = tempfile.mkdtemp(prefix="delegate-guard-test-")
os.environ["DELEGATE_ISSUED_LOG"] = os.path.join(_TMP, "issued.jsonl")
sys.path.insert(0, HOOKS)

import delegate_guard  # noqa: E402


def record(stamp: str, **extra) -> None:
    with open(delegate_guard.ISSUED_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": stamp, "label": extra.pop("label", stamp), **extra}) + "\n")


def signed(body: str, **extra) -> str:
    stamp = delegate_guard.fingerprint(body)
    record(stamp, **extra)
    return f"{body}\n[delegate:{stamp}]\n"


def call(payload: dict, argv=()) -> str:
    stdin = io.StringIO(json.dumps(payload))
    out = io.StringIO()
    old_stdin, old_argv = sys.stdin, sys.argv
    sys.stdin, sys.argv = stdin, ["delegate_guard.py", *argv]
    try:
        with contextlib.redirect_stdout(out):
            try:
                delegate_guard.main()
            except SystemExit:
                pass
    finally:
        sys.stdin, sys.argv = old_stdin, old_argv
    return out.getvalue()


def run(tool: str, prompt: str, subagent_type=None, session="s1", background=True):
    """フックを通し、(deny したか, 理由文) を返す。"""
    tool_input = {"prompt": prompt}
    if background is not None:
        tool_input["run_in_background"] = background
    if subagent_type:
        tool_input["subagent_type"] = subagent_type
    text = call({"tool_name": tool, "tool_input": tool_input, "session_id": session})
    if not text.strip():
        return False, ""
    payload = json.loads(text)["hookSpecificOutput"]
    return payload.get("permissionDecision") == "deny", payload.get("permissionDecisionReason", "")


def run_stop(session: str, active=False):
    """Stop フックを通し、(止めたか, 理由文) を返す。"""
    text = call({"session_id": session, "stop_hook_active": active}, argv=["--stop"])
    if not text.strip():
        return False, ""
    payload = json.loads(text)
    return payload.get("decision") == "block", payload.get("reason", "")


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- ファイル渡し（2026-10-22 ユーザー決定）------------------------------------
# `prompt` に指示文の本文を入れず、ファイルのパスだけを渡す形。
# 照合は「渡されたパスの中身の指紋 == 発行印」で行う（ファイル名も発行印）。


def prompt_file(body: str, stamp=None, **extra) -> tuple:
    real = delegate_guard.fingerprint(body + "\n")
    stamp = stamp or real
    record(stamp, **extra)
    path = os.path.join(_TMP, "prompts", f"{stamp}.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"{body}\n\n[delegate:{stamp}]\n")
    return path, stamp


def launch(path: str, stamp: str) -> str:
    return f"次のファイルを全文読み、指示に従ってください。\n{path}\n\n[delegate:{stamp}]\n"


@case
def passes_prompt_file():
    path, stamp = prompt_file("ファイルで渡した指示文。")
    denied, _ = run("Agent", launch(path, stamp))
    return not denied


@case
def denies_missing_prompt_file():
    stamp = delegate_guard.fingerprint("存在しないファイル\n")
    record(stamp)
    denied, reason = run("Agent", launch(os.path.join(_TMP, "prompts", f"{stamp}.md"), stamp))
    return denied and "ファイルが無い" in reason


@case
def denies_tampered_prompt_file():
    path, stamp = prompt_file("元の指示文。")
    with open(path, "w", encoding="utf-8") as fh:  # 発行印はそのまま、本文だけ差し替える
        fh.write(f"書き換えた指示文。\n\n[delegate:{stamp}]\n")
    denied, reason = run("Agent", launch(path, stamp))
    return denied and "変わっている" in reason


@case
def denies_pointing_at_other_delegation():
    path, stamp = prompt_file("本物の指示文。")
    other, other_stamp = prompt_file("別の委任の指示文。")
    denied, _ = run("Agent", launch(other, stamp))  # パスは別物、発行印は本物
    return denied and stamp != other_stamp


@case
def denies_prompt_file_in_foreground():
    path, stamp = prompt_file("前景では起動させない。")
    denied, reason = run("Agent", launch(path, stamp), background=False)
    return denied and "背景" in reason


@case
def passes_issued_prompt():
    denied, _ = run("Agent", signed("差分を読んでレビューしてください。"))
    return not denied


@case
def passes_task_tool_name():
    denied, _ = run("Task", signed("旧ツール名でも同じ検査を通る。"))
    return not denied


@case
def denies_without_marker():
    denied, reason = run("Agent", "手で書いた指示文")
    return denied and "発行印" in reason


@case
def denies_appended_text():
    prompt = signed("元の指示文。")
    tampered = prompt.replace("元の指示文。", "元の指示文。特に〜を重点的に見てください。")
    denied, reason = run("Agent", tampered)
    return denied and "変わっている" in reason


@case
def denies_removed_text():
    prompt = signed("一行目。\n二行目。")
    denied, _ = run("Agent", prompt.replace("二行目。", ""))
    return denied


@case
def denies_unknown_stamp():
    body = "記録に無い発行印。"
    stamp = delegate_guard.fingerprint(body)  # 記録しない
    denied, reason = run("Agent", f"{body}\n[delegate:{stamp}]")
    return denied and "発行記録に無い" in reason


@case
def tolerates_whitespace_changes():
    prompt = signed("一行目。\n\n二行目。")
    denied, _ = run("Agent", prompt.replace("\n\n", "\n").replace("一行目。", "一行目。  "))
    return not denied


@case
def ignores_other_tools():
    denied, _ = run("Bash", "手で書いた文字列")
    return not denied


@case
def deny_reason_tells_how_to_fix():
    _, reason = run("Agent", "手で書いた指示文")
    return "build_prompt.py" in reason and "相談" in reason


@case
def denies_foreground_launch():
    prompt = signed("背景で起動すべき指示文。", agent="general-purpose")
    denied_false, reason = run("Agent", prompt, background=False)
    denied_missing, _ = run("Agent", prompt, background=None)
    return denied_false and denied_missing and "run_in_background" in reason


@case
def denies_other_subagent_type():
    prompt = signed("汎用エージェント用の指示文。", agent="general-purpose")
    denied, reason = run("Agent", prompt, subagent_type="review-security")
    return denied and "general-purpose" in reason


@case
def omitted_subagent_type_is_general():
    denied, _ = run("Agent", signed("省略時は汎用。", agent="general-purpose"))
    return not denied


@case
def no_agent_in_record_skips_type_check():
    denied, _ = run("Agent", signed("調査役。種類は問わない。"), subagent_type="Explore")
    return not denied


@case
def stop_blocks_partial_group_once():
    a = signed("組の 1 体目。", group="g1", label="review-logic")
    signed("組の 2 体目。", group="g1", label="review-security")
    run("Agent", a, session="s-partial")
    first, reason = run_stop("s-partial")
    second, _ = run_stop("s-partial")
    return first and "review-security" in reason and "review-logic" not in reason and not second


@case
def stop_passes_full_group():
    a = signed("全員起動 1。", group="g2", label="a")
    b = signed("全員起動 2。", group="g2", label="b")
    run("Agent", a, session="s-full")
    run("Agent", b, session="s-full")
    blocked, _ = run_stop("s-full")
    return not blocked


@case
def stop_ignores_group_started_in_other_session():
    a = signed("別セッション 1。", group="g3", label="a")
    signed("別セッション 2。", group="g3", label="b")
    run("Agent", a, session="s-other")
    blocked, _ = run_stop("s-mine")
    return not blocked


def make_task(name: str, active: bool):
    """`<proj>/.claude/tasks/<name>.md` と、その一時ディレクトリの delegate/ を作って登録する。"""
    proj = os.path.join(_TMP, f"proj-{name}")
    tasks = os.path.join(proj, ".claude", "tasks")
    os.makedirs(os.path.join(tasks, "done"), exist_ok=True)
    td = os.path.join(tasks, f"{name}.md")
    with open(td if active else os.path.join(tasks, "done", f"{name}.md"), "w", encoding="utf-8") as fh:
        fh.write("x\n")
    root = os.path.join(proj, ".claude", "tmp", name, "delegate")
    os.makedirs(os.path.join(root, "20261006-110000-research-aaaaaa"), exist_ok=True)
    delegate_guard.append_jsonl(delegate_guard.WORKDIR_REGISTRY, {"dir": root, "taskdef": td})
    return proj, root


@case
def sweep_removes_delegate_files_of_completed_tasks_only():
    _, active_root = make_task("GID-1-active", active=True)
    done_proj, done_root = make_task("GID-2-done", active=False)
    other_file = os.path.join(done_proj, ".claude", "tmp", "GID-2-done", "note.txt")
    with open(other_file, "w", encoding="utf-8") as fh:
        fh.write("delegate/ 以外は META-01 の扱い\n")
    call({"session_id": "s-sweep"}, argv=["--sweep"])
    registry = delegate_guard.read_jsonl(delegate_guard.WORKDIR_REGISTRY)
    return (os.path.isdir(active_root) and not os.path.exists(done_root) and os.path.isfile(other_file)
            and all(e["dir"] != done_root for e in registry) and any(e["dir"] == active_root for e in registry))


@case
def sweep_removes_external_pr_diff_only_if_unchanged():
    proj, root = make_task("GID-3-done", active=False)
    repo_a = os.path.join(_TMP, "repo-a")
    repo_b = os.path.join(_TMP, "repo-b")
    for repo, text in ((repo_a, "このチケットの差分\n"), (repo_b, "このチケットの差分\n")):
        os.makedirs(repo, exist_ok=True)
        with open(os.path.join(repo, "pr-diff.txt"), "w", encoding="utf-8") as fh:
            fh.write(text)
        with open(os.path.join(repo, "findings-logic.json"), "w", encoding="utf-8") as fh:
            fh.write("{}")
        delegate_guard.append_jsonl(os.path.join(root, "external.jsonl"), {
            "path": os.path.join(repo, "pr-diff.txt"),
            "digest": delegate_guard.file_digest(os.path.join(repo, "pr-diff.txt")),
        })
    # repo_b は別のセッションのレビューに書き換わった
    with open(os.path.join(repo_b, "pr-diff.txt"), "w", encoding="utf-8") as fh:
        fh.write("別のセッションの差分\n")
    call({"session_id": "s-sweep2"}, argv=["--sweep"])
    return (not os.path.exists(os.path.join(repo_a, "pr-diff.txt"))
            and not os.path.exists(os.path.join(repo_a, "findings-logic.json"))
            and os.path.exists(os.path.join(repo_b, "pr-diff.txt"))
            and os.path.exists(os.path.join(repo_b, "findings-logic.json")))


@case
def stop_also_sweeps():
    _, root = make_task("GID-4-done", active=False)
    run_stop("s-stop-sweep")
    return not os.path.exists(root)


@case
def stop_respects_stop_hook_active():
    a = signed("ループ防止 1。", group="g4", label="a")
    signed("ループ防止 2。", group="g4", label="b")
    run("Agent", a, session="s-active")
    blocked, _ = run_stop("s-active", active=True)
    return not blocked


def main() -> None:
    failures = []
    for fn in CASES:
        try:
            ok = fn()
        except Exception as err:  # noqa: BLE001
            ok = False
            print(f"  例外 {fn.__name__}: {err!r}")
        if not ok:
            failures.append(fn.__name__)
    print(f"ケース数: {len(CASES)}")
    for name in failures:
        print(f"  NG {name}")
    print(f"不一致: {len(failures)} 件")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
