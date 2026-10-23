#!/usr/bin/env python3
"""`build_prompt.py` の検証。

一時ディレクトリに git リポジトリを作って使う。本物のリポジトリ・発行記録は触らない。
"""

import io
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

SKILL = os.path.dirname(os.path.abspath(__file__))
_TMP = tempfile.mkdtemp(prefix="delegate-build-test-")
os.environ["DELEGATE_ISSUED_LOG"] = os.path.join(_TMP, "state", "issued.jsonl")
sys.path.insert(0, SKILL)
sys.path.insert(0, os.path.join(os.path.expanduser("~"), ".claude", "hooks"))

import build_prompt  # noqa: E402
import delegate_guard  # noqa: E402

REPOS = "/home/m-yoshimo/work/genda/repositories"
LOCAL_REVIEW = f"{REPOS}/idpf-api/.claude/skills/local-review/SKILL.md"
POINTPF = f"{REPOS}/pointpf-api/.claude"
POINTPF_AGENTS = ["review-security", "review-logic", "review-design", "review-performance", "review-testability"]
TASK_TMP = "T-1-work"


def sh(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def make_repo(flavor: str = "idpf") -> str:
    """flavor: idpf（local-review）/ pointpf（code-review-local と 5 体の定義）/ none / both"""
    repo = tempfile.mkdtemp(prefix="repo-", dir=_TMP)
    sh(repo, "init", "-q", "-b", "feature/x")
    sh(repo, "config", "user.email", "t@example.com")
    sh(repo, "config", "user.name", "t")
    if flavor in ("idpf", "both"):
        os.makedirs(os.path.join(repo, ".claude", "skills", "local-review"))
        shutil.copyfile(LOCAL_REVIEW, os.path.join(repo, ".claude", "skills", "local-review", "SKILL.md"))
    if flavor in ("pointpf", "both"):
        os.makedirs(os.path.join(repo, ".claude", "skills", "code-review-local"))
        shutil.copyfile(f"{POINTPF}/skills/code-review-local/SKILL.md",
                        os.path.join(repo, ".claude", "skills", "code-review-local", "SKILL.md"))
        os.makedirs(os.path.join(repo, ".claude", "agents"))
        for name in POINTPF_AGENTS:
            shutil.copyfile(f"{POINTPF}/agents/{name}.md", os.path.join(repo, ".claude", "agents", f"{name}.md"))
    write(repo, "tracked.go", "package a\n")
    write(repo, ".claude/rules/rule.md", "rule\n")
    sh(repo, "add", ".")
    sh(repo, "commit", "-q", "-m", "init")
    write(repo, "tracked.go", "package a\n\nfunc staged() {}\n")
    sh(repo, "add", "tracked.go")
    write(repo, "tracked.go", "package a\n\nfunc staged() {}\n\nfunc unstaged() {}\n")
    write(repo, ".claude/rules/rule.md", "rule changed\n")  # 追跡済みの .claude/ 以下（対象に入る）
    write(repo, "new.go", "package a\n\nfunc untracked() {}\n")  # 未追跡（--untracked で入る）
    write(repo, ".claude/tasks/t.md", "task\n")  # 未追跡の .claude/ 以下（常に除外）
    return repo


def write(repo, rel, text):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = build_prompt.main(argv)
    return code, out.getvalue(), err.getvalue()


def diff_of(repo, *flags):
    args = build_prompt.parse(["review", "--repo", repo, *flags])
    return build_prompt.build_diff(repo, args)


WORKER_PLAN = (
    "## 変更対象ファイル一覧（並列実行計画）\n\n"
    "### Worker A（テスト）\n\n- 担当ファイル:\n  1. `tracked.go`\n- 読むもの:\n  - `.claude/rules/rule.md`\n\n"
    "- **タスク管理エージェント（background）**: 監視\n"
)


def taskdef(repo, branch="feature/x", rel=".claude/tasks/t.md", tmp=TASK_TMP, plan=WORKER_PLAN):
    tmp_line = f"- 一時ディレクトリ: `.claude/tmp/{tmp}/`\n" if tmp else "- 一時ディレクトリ: なし\n"
    write(repo, rel,
          f"# t\n## ステータス\n- [ ] 実装中\n- 作業ブランチ: `{branch}`\n{tmp_line}"
          "## 読むもの\n| 種別 | 記入 |\n|---|---|\n| 規約 | `.claude/rules/rule.md` |\n## 目的\nx\n" + plan)
    return os.path.join(repo, rel)


def review(repo, *flags):
    return run(["review", "--repo", repo, "--taskdef", taskdef(repo), *flags])


def command(repo, *commands, extra=()):
    argv = ["command", "--repo", repo, "--taskdef", taskdef(repo), *extra]
    for c in commands:
        argv += ["--command", c]
    return run(argv)


def task_delegate_dir(repo):
    return os.path.join(repo, ".claude", "tmp", TASK_TMP, "delegate")


def signed_ok(prompt: str) -> bool:
    body, stamp = prompt.rstrip().rsplit("[delegate:", 1)
    stamp = stamp.rstrip("]")
    return delegate_guard.fingerprint(body) == stamp and stamp in delegate_guard.issued_ids()


def prompt_files(stdout: str) -> list:
    return [line.split()[0] for line in stdout.splitlines() if line.strip().split(" ")[0].endswith(".txt")]


def prompt_of(stdout: str) -> str:
    return stdout.split("---\n", 1)[1].rsplit("---\n", 1)[0]


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def requires_repo():
    repo = make_repo()
    code, _, err = run(["review", "--taskdef", taskdef(repo), "--worktree"])
    return code == 1 and "--repo" in err and "セッションの作業ディレクトリは使わない" in err


def make_repo_with_origin() -> str:
    """origin/main（= 最初のコミット）から分かれ、ブランチでコミットを 1 つ積んだリポジトリ。"""
    repo = make_repo("idpf")
    sh(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    sh(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    write(repo, "committed.go", "package a\n\nfunc committedOnBranch() {}\n")
    sh(repo, "add", "committed.go")
    sh(repo, "commit", "-q", "-m", "branch commit")
    return repo


@case
def default_diff_is_everything_the_pr_will_carry():
    """取り方の指定が無ければ「PR に載る変更の全部」（2026-10-07 ユーザー指示「既定値は作って」）。"""
    repo = make_repo_with_origin()
    args = build_prompt.parse(["review", "--repo", repo])
    text, summary = build_prompt.build_diff(repo, args)
    return ("committedOnBranch" in text and "func staged" in text and "func unstaged" in text
            and "func untracked" in text and ".claude/tasks/t.md" not in text
            and "既定" in summary and "origin/main" in summary)


@case
def default_diff_ignores_commits_added_to_origin_main_after_branching():
    """fetch で origin/main が先に進んでも、main 側の新しいコミットは既定の差分に入らない（起点は分かれた地点のまま）。"""
    repo = make_repo_with_origin()
    branch_head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    sh(repo, "stash", "-u")  # 作業ツリーを空にして main 側のコミットを作る（テスト用の一時リポジトリ）
    sh(repo, "checkout", "-q", "refs/remotes/origin/main")
    write(repo, "main_only.go", "package a\n\nfunc onlyOnMain() {}\n")
    sh(repo, "add", "main_only.go")
    sh(repo, "commit", "-q", "-m", "main advanced")
    sh(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    sh(repo, "checkout", "-q", "feature/x")
    sh(repo, "stash", "pop")
    args = build_prompt.parse(["review", "--repo", repo])
    text, _ = build_prompt.build_diff(repo, args)
    current = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return current == branch_head and "committedOnBranch" in text and "onlyOnMain" not in text


@case
def default_diff_after_rebase_onto_advanced_origin_main():
    """origin/main が進んだ後に `git rebase origin/main` しても、main 側の変更は既定の差分に入らない。

    rebase 後はブランチのコミットが新しい origin/main の上に載るので、分かれた地点 = 新しい origin/main の先端になる。
    """
    repo = make_repo_with_origin()
    sh(repo, "stash", "-u")  # テスト用の一時リポジトリ
    sh(repo, "checkout", "-q", "refs/remotes/origin/main")
    write(repo, "main_only.go", "package a\n\nfunc onlyOnMain() {}\n")
    sh(repo, "add", "main_only.go")
    sh(repo, "commit", "-q", "-m", "main advanced")
    sh(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    sh(repo, "checkout", "-q", "feature/x")
    sh(repo, "rebase", "-q", "origin/main")
    sh(repo, "stash", "pop")
    advanced = subprocess.run(["git", "-C", repo, "rev-parse", "origin/main"], capture_output=True, text=True).stdout.strip()
    base = build_prompt.default_base(repo)[1]
    args = build_prompt.parse(["review", "--repo", repo])
    text, _ = build_prompt.build_diff(repo, args)
    has_main_file = os.path.isfile(os.path.join(repo, "main_only.go"))  # rebase で main 側のファイルは作業ツリーにある
    return base == advanced and has_main_file and "committedOnBranch" in text and "onlyOnMain" not in text


@case
def default_diff_uses_taskdef_base_branch_and_shows_commit_count():
    """別の作業ブランチから切ったブランチは、定義書のベースブランチで起点を決める（元のブランチの変更を入れない）。"""
    repo = make_repo_with_origin()           # feature/x: origin/main + committedOnBranch
    sh(repo, "update-ref", "refs/remotes/origin/feature/x", "HEAD")
    sh(repo, "stash", "-u")
    sh(repo, "checkout", "-q", "-b", "feature/y")
    write(repo, "stacked.go", "package a\n\nfunc stackedOnly() {}\n")
    sh(repo, "add", "stacked.go")
    sh(repo, "commit", "-q", "-m", "stacked")
    sh(repo, "stash", "pop")
    plain = build_prompt.parse(["review", "--repo", repo])
    text_plain, summary_plain = build_prompt.build_diff(repo, plain)
    td = taskdef(repo, branch="feature/y")
    with open(td, encoding="utf-8") as fh:
        body = fh.read()
    with open(td, "w", encoding="utf-8") as fh:
        fh.write(body.replace("- 作業ブランチ:", "- ベースブランチ: `origin/feature/x`\n- 作業ブランチ:"))
    based = build_prompt.parse(["review", "--repo", repo, "--taskdef", td])
    text_based, summary_based = build_prompt.build_diff(repo, based)
    return ("committedOnBranch" in text_plain and "コミット 2 件" in summary_plain
            and "committedOnBranch" not in text_based and "stackedOnly" in text_based
            and "コミット 1 件" in summary_based and "タスク定義書のベースブランチ origin/feature/x" in summary_based)


@case
def default_diff_without_origin_asks_for_mode():
    code, _, err = review(make_repo())  # origin が無いリポジトリ
    return code == 1 and "指定すること" in err


@case
def rejects_two_diff_modes():
    code, _, _ = review(make_repo(), "--cached", "--worktree")
    return code == 1


@case
def cached_has_only_staged():
    text, summary = diff_of(make_repo(), "--cached")
    return "staged" in text and "unstaged" not in text and "git diff --cached" in summary


@case
def worktree_has_unstaged_and_tracked_claude():
    text, _ = diff_of(make_repo(), "--worktree")
    return "unstaged" in text and ".claude/rules/rule.md" in text and "new.go" not in text


@case
def untracked_adds_new_files_but_not_claude():
    text, summary = diff_of(make_repo(), "--worktree", "--untracked")
    return ("func untracked" in text and ".claude/tasks/t.md" not in text
            and "未追跡 1 件" in summary)


@case
def head_has_both():
    text, _ = diff_of(make_repo(), "--head")
    return "staged" in text and "unstaged" in text


@case
def review_picks_local_review_and_signs():
    repo = make_repo("idpf")
    code, out, _ = review(repo, "--worktree", "--untracked")
    prompt = prompt_of(out)
    return (code == 0 and "レビュー: リポジトリの skill" in out and "local-review/SKILL.md" in out
            and "subagent_type: general-purpose" in out
            and "IDPF プロジェクトのコード変更について" in prompt
            and "{diff}" not in prompt and "target.diff" in prompt and signed_ok(prompt))


@case
def review_picks_code_review_local_with_five_embedded_reviewers():
    repo = make_repo("pointpf")
    code, out, _ = review(repo, "--head")
    paths = prompt_files(out)
    if code != 0 or "code-review-local/SKILL.md" not in out or len(paths) != 5:
        return False
    if not os.path.isfile(os.path.join(repo, "pr-diff.txt")):
        return False
    for name, path in zip(POINTPF_AGENTS, sorted(paths, key=lambda p: POINTPF_AGENTS.index(os.path.basename(p)[:-4]))):
        with open(path, encoding="utf-8") as fh:
            prompt = fh.read()
        short = name.split("-", 1)[1]
        if not signed_ok(prompt):
            return False
        # 定義の本文が入り、ファイル名が対象リポジトリの絶対パスになっている
        if f"`{os.path.join(repo, 'pr-diff.txt')}` を読み込んでください" not in prompt:
            return False
        if os.path.join(repo, f"findings-{short}.json") not in prompt or "restrictedTools" in prompt:
            return False
        if "所定のfindingsファイルに書き出してください" not in prompt:
            return False
    records = [r for r in delegate_guard.issued_records().values() if r.get("label") in POINTPF_AGENTS]
    groups = {r.get("group") for r in records[-5:]}
    return len(groups) == 1 and None not in groups and all(r.get("agent") == "general-purpose" for r in records[-5:])


@case
def review_pointpf_refuses_leftover_findings():
    repo = make_repo("pointpf")
    write(repo, "findings-logic.json", "{}")
    code, _, err = review(repo, "--head")
    return code == 1 and "findings-logic.json" in err


@case
def review_pointpf_refuses_existing_pr_diff():
    repo = make_repo("pointpf")
    write(repo, "pr-diff.txt", "別のセッションのレビュー中\n")
    code, _, err = review(repo, "--head")
    with open(os.path.join(repo, "pr-diff.txt"), encoding="utf-8") as fh:
        kept = fh.read() == "別のセッションのレビュー中\n"
    return code == 1 and "pr-diff.txt" in err and kept


def write_action(repo, name="claude-code-review.yml", prompt="Review ONLY the changes.\n## Review focus areas:\n- Security\n"):
    body = "\n".join("            " + line for line in prompt.splitlines())
    write(repo, f".github/workflows/{name}",
          "name: Claude Code Review\non:\n  pull_request:\njobs:\n  claude-review:\n    runs-on: ubuntu-latest\n"
          "    steps:\n      - uses: actions/checkout@v6\n      - name: Run\n        uses: anthropics/claude-code-action@v1\n"
          f"        with:\n          prompt: |\n{body}\n")


@case
def review_with_both_skill_shapes_asks_user():
    code, _, err = review(make_repo("both"), "--head")
    return code == 1 and "2 つ以上" in err


@case
def review_finds_repo_skill_by_shape_not_name():
    repo = make_repo("none")
    # 名前に review を含まない skill でも、{diff} の差し込み口を持つテンプレートなら使う
    write(repo, ".claude/skills/team-cr/SKILL.md",
          "---\nname: team-cr\ndescription: チームの確認\n---\n## 手順\n```\n次の差分を見てください。\n{diff}\n```\n")
    code, out, _ = review(repo, "--head")
    prompt = prompt_of(out)
    return code == 0 and "team-cr" in out and "次の差分を見てください。" in prompt and "{diff}" not in prompt


@case
def review_stops_on_unreadable_review_skill():
    repo = make_repo("none")
    write(repo, ".claude/skills/push-and-review/SKILL.md", "---\nname: push-and-review\ndescription: push 後にレビュー\n---\n手順だけ\n")
    write_action(repo)
    code, _, err = review(repo, "--head")
    return code == 1 and "push-and-review" in err and "ユーザーに聞く" in err


@case
def review_uses_github_actions_prompt_when_no_skill():
    repo = make_repo("none")
    write_action(repo)
    write_action(repo, name="claude.yml", prompt="")  # prompt の無い定義（メンション用など）は数えない
    write(repo, ".github/workflows/govulncheck-autofix.yml",  # レビュー以外に同じ action を使う定義も数えない
          "name: autofix\non: push\njobs:\n  fix:\n    runs-on: ubuntu-latest\n    steps:\n"
          "      - uses: anthropics/claude-code-action@v1\n        with:\n          prompt: |\n            Fix vulns\n")
    code, out, _ = review(repo, "--head")
    prompt = prompt_of(out)
    return (code == 0 and "GitHub Actions の定義" in out and "claude-code-review.yml" in out
            and "Review ONLY the changes." in prompt and "gh pr diff" in prompt and "target.diff" in prompt
            and "PR にコメントしないでください" in prompt and signed_ok(prompt))


@case
def review_stops_on_two_github_actions_prompts():
    repo = make_repo("none")
    write_action(repo)
    write_action(repo, name="another-review.yml")
    code, _, err = review(repo, "--head")
    return code == 1 and "2 つ以上" in err


@case
def review_falls_back_to_design_review_v2():
    repo = make_repo("none")
    code, out, _ = review(repo, "--head")
    paths = prompt_files(out)
    if code != 0 or "design-review-v2" not in out or len(paths) != 9:
        return False
    with open(paths[0], encoding="utf-8") as fh:
        return "レビュー種別: code" in fh.read()


@case
def review_checks_taskdef_branch():
    repo = make_repo("idpf")
    other = make_repo("idpf")
    ok, out, _ = review(repo, "--head")
    bad, _, err = run(["review", "--repo", repo, "--taskdef", taskdef(other, branch="feature/other"), "--head"])
    return ok == 0 and "作業ブランチと一致" in out and bad == 1 and "feature/other" in err


# --- 置き場所（タスク定義書の一時ディレクトリ） --------------------------------

@case
def files_go_into_declared_task_tmpdir():
    repo = make_repo("idpf")
    code, out, _ = review(repo, "--head")
    root = task_delegate_dir(repo)
    made = os.listdir(root)
    registry = delegate_guard.read_jsonl(delegate_guard.WORKDIR_REGISTRY)
    return (code == 0 and len(made) == 1 and made[0].startswith(tuple("0123456789")) and "-review-" in made[0]
            and not os.path.exists(os.path.join(repo, ".claude", "tmp", "delegate"))
            and {"dir": root, "taskdef": os.path.join(repo, ".claude/tasks/t.md")} in registry)


@case
def file_making_kinds_require_taskdef_and_declaration():
    repo = make_repo("idpf")
    no_td, _, err1 = run(["review", "--repo", repo, "--head"])
    td = taskdef(repo, tmp=None)
    no_decl, _, err2 = run(["review", "--repo", repo, "--taskdef", td, "--head"])
    return no_td == 1 and "--taskdef" in err1 and no_decl == 1 and "一時ディレクトリ" in err2


@case
def workdirs_never_collide_in_same_second():
    repo = make_repo()
    td = taskdef(repo)
    paths = {build_prompt.make_workdir(td, "review") for _ in range(20)}
    return len(paths) == 20


@case
def pointpf_records_pr_diff_as_external():
    repo = make_repo("pointpf")
    code, _, _ = review(repo, "--head")
    entries = delegate_guard.read_jsonl(os.path.join(task_delegate_dir(repo), "external.jsonl"))
    pr = os.path.join(repo, "pr-diff.txt")
    return code == 0 and entries == [{"path": pr, "digest": delegate_guard.file_digest(pr)}]


# --- ルール ------------------------------------------------------------------

RULES = os.path.join(os.path.expanduser("~"), ".claude", "memory")


def has_all_rules(prompt: str) -> bool:
    import glob as _glob
    names = ["MEMORY.md"] + [os.path.basename(p) for p in _glob.glob(os.path.join(RULES, "feedback_*.md"))]
    return len(names) >= 2 and all(f"~/.claude/memory/{n}" in prompt for n in names)


@case
def research_and_worker_list_all_rule_files():
    code, out, _ = run(["research", "--question", "handler 層で認可を見ている箇所を一覧にして"])
    research = prompt_of(out)
    repo = make_repo()
    code2, out2, _ = run(["worker", "--repo", repo, "--taskdef", taskdef(repo), "--assign", "Worker A", "--fixed-sections", "## 設計"])
    worker = prompt_of(out2)
    return (code == 0 and code2 == 0 and has_all_rules(research) and has_all_rules(worker)
            and "8. 読んだ作業ルールのファイルの一覧" in worker and "{RULE_FILES}" not in worker + research)


@case
def design_review_v2_lists_all_rule_files():
    repo = make_repo()
    code, out, _ = run(["review-design-v2", "--repo", repo, "--taskdef", taskdef(repo), "--design"])
    paths = prompt_files(out)
    if code != 0 or not paths:
        return False
    with open(paths[0], encoding="utf-8") as fh:
        prompt = fh.read()
    return has_all_rules(prompt) and "{RULE_FILES}" not in prompt and paths[0].startswith(task_delegate_dir(repo))


@case
def review_has_no_rule_files():
    code, out, _ = review(make_repo("idpf"), "--head")
    return code == 0 and "~/.claude/memory/feedback_" not in prompt_of(out)


# --- コマンドの実行役 ---------------------------------------------------------

def write_makefile(repo):
    write(repo, "Makefile", "test:\n\tgo test ./...\n.PHONY: lint\nlint fmt:\n\techo\nVAR := 1\n-include Makefile.local\n")
    write(repo, "Makefile.local", "local-only:\n\techo\n")


@case
def command_accepts_make_targets_and_allowed_commands():
    repo = make_repo()
    write_makefile(repo)
    code, out, _ = command(repo, "make test", "make lint fmt VERBOSE=1", "make local-only", "go vet ./...")
    prompt = prompt_of(out)
    return (code == 0 and "`make test`" in prompt and "command-4.log" in prompt
            and task_delegate_dir(repo) in prompt
            and "subagent_type: general-purpose" in out and "~/.claude/memory/" not in prompt and signed_ok(prompt))


HOOKS = os.path.join(os.path.expanduser("~"), ".claude", "hooks")
HEAVY_GUARD = f"{REPOS}/idpf-api/.claude/heavy-command-guard.local.py"


def hook_denies(script: str, command_line: str, cwd: str) -> bool:
    proc = subprocess.run([sys.executable, script], input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command_line}}),
                          capture_output=True, text=True, cwd=cwd)
    out = proc.stdout.strip()
    return bool(out) and json.loads(out).get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


@case
def command_lines_pass_the_real_hooks():
    """エージェントが「実行する行」をそのまま実行したとき、フックに止められない（2026-10-06 ユーザー要件）。"""
    repo = make_repo()
    write_makefile(repo)
    code, out, _ = command(repo, "make test", "go test ./...", "go vet ./...")
    prompt = prompt_of(out)
    lines = [l.split("実行する行: `", 1)[1].rsplit("`", 1)[0] for l in prompt.splitlines() if "実行する行: `" in l]
    if code != 0 or len(lines) != 3 or not all("timeout 590 " in l for l in lines):
        return False
    for line in lines:
        for script in (os.path.join(HOOKS, "rule_guard.py"), HEAVY_GUARD):
            if hook_denies(script, line, repo):
                print(f"    止められた: {os.path.basename(script)}: {line}")
                return False
    # 形を崩すと止まることも確かめる（検査そのものが効いていること）
    return hook_denies(HEAVY_GUARD, "make test > x.log 2>&1", repo)


def agent_hook_denial(script: str, prompt: str, subagent_type: str):
    """Agent ツールの呼び出しとしてフックに通し、止めた理由文を返す（通れば None）。"""
    tool_input = {"prompt": prompt, "run_in_background": True}
    if subagent_type:
        tool_input["subagent_type"] = subagent_type
    proc = subprocess.run([sys.executable, script], input=json.dumps({"tool_name": "Agent", "tool_input": tool_input}),
                          capture_output=True, text=True, cwd=_TMP)
    out = proc.stdout.strip()
    if not out:
        return None
    data = json.loads(out).get("hookSpecificOutput", {})
    return data.get("permissionDecisionReason") if data.get("permissionDecision") == "deny" else None


@case
def every_kind_passes_the_real_agent_hooks():
    """組み立てた指示文を、そのまま Agent ツールに渡したときに止められない（2026-10-07 GID-1859 の件）。"""
    repo = make_repo("idpf")
    write_makefile(repo)
    td = taskdef(repo, rel=".claude/tasks/P-1/t.md")
    write(repo, ".claude/tasks/P-1/overview.md", "overview")  # 補助資料に .claude/tasks/ のパスが載る
    with open(td, encoding="utf-8") as fh:
        text = fh.read()
    with open(td, "w", encoding="utf-8") as fh:
        fh.write(text.replace("| 規約 | `.claude/rules/rule.md` |", "| 規約 | `.claude/rules/rule.md`、`overview.md` |"))
    outs = {
        "worker": run(["worker", "--repo", repo, "--taskdef", td, "--assign", "Worker A", "--fixed-sections", "## 設計"])[1],
        "research": run(["research", "--taskdef", td, "--question", f"{td} の前提を調べて"])[1],
        "command": run(["command", "--repo", repo, "--taskdef", td, "--command", "make test"])[1],
        "review": run(["review", "--repo", repo, "--taskdef", td, "--head"])[1],
    }
    prompts = [(k, prompt_of(o), "general-purpose") for k, o in outs.items()]
    design = run(["review-design-v2", "--repo", repo, "--taskdef", td, "--design"])[1]
    for path in prompt_files(design):
        with open(path, encoding="utf-8") as fh:
            prompts.append(("review-design-v2", fh.read(), "general-purpose"))
    if len(prompts) != 13 or not any(".claude/tasks/P-1/overview.md" in p for k, p, _ in prompts if k == "review-design-v2"):
        return False
    for kind, prompt, agent in prompts:
        for script in (os.path.join(HOOKS, "rule_guard.py"), os.path.join(HOOKS, "delegate_guard.py")):
            reason = agent_hook_denial(script, prompt, agent)
            if reason:
                print(f"    {kind} が {os.path.basename(script)} に止められた: {reason[:120]}")
                return False
    return True


@case
def prompts_tell_agents_not_to_abort_on_hook_denial():
    repo = make_repo()
    write_makefile(repo)
    td = taskdef(repo)
    outs = [
        command(repo, "make test")[1],
        run(["research", "--taskdef", td, "--question", "認可を見ている箇所を一覧にして"])[1],
        run(["worker", "--repo", repo, "--taskdef", td, "--assign", "Worker A", "--fixed-sections", "## 設計"])[1],
    ]
    prompts = [prompt_of(o) for o in outs]
    return all("作業を中断しないでください" in p and "{HOOK_DENIED}" not in p and "{SCRATCH}" not in p for p in prompts) \
        and task_delegate_dir(repo) in prompts[2] and "subagent_type: general-purpose" in outs[1]


@case
def command_rejects_unknown_or_editing_commands():
    repo = make_repo()
    write_makefile(repo)
    cases = [
        ("make deploy", "定義されていない"),
        ("make -C apps test", "--cwd"),
        ("make test > out.log", "リダイレクト"),
        ("make test && make lint", "リダイレクト"),
        ("sed -i s/a/b/ x.go", "worker"),
        ("go build -o bin/app .", "-o"),
    ]
    for c, word in cases:
        code, _, err = command(repo, c)
        if code != 1 or word not in err:
            print(f"    {c}: {err.strip()}")
            return False
    return True


@case
def command_cwd_must_stay_in_repo():
    repo = make_repo()
    code, _, err = command(repo, "go vet ./...", extra=("--cwd", "../.."))
    return code == 1 and "--cwd" in err


# --- 調査役 -------------------------------------------------------------------

@case
def research_with_taskdef_writes_result_into_task_tmpdir():
    repo = make_repo()
    td = taskdef(repo)
    _, out1, _ = run(["research", "--taskdef", td, "--question", "認可を見ている箇所を一覧にして"])
    _, out2, _ = run(["research", "--taskdef", td, "--question", "認可を見ている箇所を一覧にして"])
    p1, p2 = prompt_of(out1), prompt_of(out2)
    r1 = [l.strip() for l in p1.splitlines() if l.strip().endswith("result.md")]
    r2 = [l.strip() for l in p2.splitlines() if l.strip().endswith("result.md")]
    return (r1 and r2 and r1[0] != r2[0] and r1[0].startswith(task_delegate_dir(repo))
            and os.path.isdir(os.path.dirname(r1[0])) and "{REPORT}" not in p1)


@case
def research_without_taskdef_returns_by_message():
    code, out, _ = run(["research", "--question", "認可を見ている箇所を一覧にして"])
    prompt = prompt_of(out)
    return code == 0 and "最後のメッセージにだけ" in prompt and "result.md" not in prompt and "作業ディレクトリ" not in out


@case
def research_rejects_review_words():
    code, _, err = run(["research", "--question", "この差分をセキュリティの観点で見て"])
    return code == 1 and "review" in err


@case
def research_rejects_destructive_words():
    code, _, err = run(["research", "--question", "調べ終わったら一時ファイルを削除して"])
    return code == 1 and "削除" in err


@case
def research_accepts_read_only_question():
    code, out, _ = run(["research", "--question", "handler 層で認可を見ている箇所を一覧にして"])
    return code == 0 and "読み取りだけ" in prompt_of(out)


# --- 実装ワーカー・design-review-v2 ------------------------------------------

@case
def worker_requires_all_args():
    code, _, err = run(["worker", "--taskdef", "x.md"])
    return code == 1 and "--assign" in err


TWO_WORKERS = (
    "## 変更対象ファイル一覧（並列実行計画）\n\n"
    "### Worker A（API）\n\n- 担当ファイル:\n  1. `a.go`\n- 読むもの:\n  - `.claude/rules/rule.md`\n"
    "  - `docs/missing.md`\n  - https://example.com/spec\n\n"
    "### Worker B（画面）\n\n- 担当ファイル:\n  1. `b.tsx`\n- 読むもの:\n  - `only-b.md`\n\n"
    "- **タスク管理エージェント（background）**: 監視\n"
)


@case
def worker_gets_only_its_own_read_list():
    """担当の節の「読むもの」だけを渡す（2026-10-07 GID-1859 のワーカーが 1MB 超の資料を読み飛ばした件）。"""
    repo = make_repo()
    write(repo, "only-b.md", "b")
    td = taskdef(repo, plan=TWO_WORKERS)
    code, out, _ = run(["worker", "--repo", repo, "--taskdef", td, "--assign", "Worker A", "--fixed-sections", "## 設計"])
    a = prompt_of(out)
    code_b, out_b, _ = run(["worker", "--repo", repo, "--taskdef", td, "--assign", "Worker B", "--fixed-sections", "## 設計"])
    b = prompt_of(out_b)
    return (code == 0 and code_b == 0 and "無断改変として扱います" in a
            and ".claude/rules/rule.md" in a and "docs/missing.md（読めず" in a and "https://example.com/spec" in a
            and "only-b.md" not in a and "### Worker A" in a
            and "only-b.md" in b and ".claude/rules/rule.md" not in b.split("作業ルールの全ファイル")[0])


@case
def worker_requires_its_section_and_read_list():
    repo = make_repo()
    no_section, _, err1 = run(["worker", "--repo", repo, "--taskdef", taskdef(repo), "--assign", "Worker Z",
                               "--fixed-sections", "## 設計"])
    no_list_plan = "## 変更対象ファイル一覧\n\n### Worker A\n\n- 担当ファイル:\n  1. `a.go`\n"
    no_list, _, err2 = run(["worker", "--repo", repo, "--taskdef", taskdef(repo, plan=no_list_plan), "--assign", "Worker A",
                            "--fixed-sections", "## 設計"])
    # 見出しの書き方の揺れ（コロン区切り）でも節を見つける。「Worker A」で「Worker AB」は拾わない
    colon_plan = ("## 変更対象ファイル一覧\n\n### Worker AB: 別\n\n- 読むもの:\n  - `nope.md`\n\n"
                  "### Worker A: `api`\n\n- 読むもの:\n  - `.claude/rules/rule.md`\n")
    colon, out, _ = run(["worker", "--repo", repo, "--taskdef", taskdef(repo, plan=colon_plan), "--assign", "Worker A",
                         "--fixed-sections", "## 設計"])
    return (no_section == 1 and "### Worker Z" in err1 and no_list == 1 and "読むもの" in err2
            and colon == 0 and "nope.md" not in prompt_of(out) and ".claude/rules/rule.md" in prompt_of(out))


@case
def worker_rejects_whole_repo_and_oversized_read_list():
    repo = make_repo()
    other = make_repo("none")
    whole = f"## 変更対象ファイル一覧\n\n### Worker A\n\n- 読むもの:\n  - `{other}/`\n"
    code1, _, err1 = run(["worker", "--repo", repo, "--taskdef", taskdef(repo, plan=whole), "--assign", "Worker A",
                          "--fixed-sections", "## 設計"])
    write(repo, "docs/big.md", "x" * (build_prompt.WORKER_READ_LIMIT + 1))
    write(repo, "docs/shot.png", "x" * (build_prompt.WORKER_READ_LIMIT + 1))
    big = "## 変更対象ファイル一覧\n\n### Worker A\n\n- 読むもの:\n  - `docs/big.md`\n"
    code2, _, err2 = run(["worker", "--repo", repo, "--taskdef", taskdef(repo, plan=big), "--assign", "Worker A",
                          "--fixed-sections", "## 設計"])
    image = "## 変更対象ファイル一覧\n\n### Worker A\n\n- 読むもの:\n  - `docs/shot.png`\n"
    code3, _, _ = run(["worker", "--repo", repo, "--taskdef", taskdef(repo, plan=image), "--assign", "Worker A",
                       "--fixed-sections", "## 設計"])
    return (code1 == 1 and "リポジトリ丸ごと" in err1
            and code2 == 1 and "上限" in err2 and "docs/big.md" in err2
            and code3 == 0)  # 画像は合計に数えない


@case
def design_review_v2_builds_nine_signed_prompts():
    repo = make_repo()
    code, out, _ = run(["review-design-v2", "--repo", repo, "--taskdef", taskdef(repo), "--design"])
    paths = prompt_files(out)
    if code != 0 or len(paths) != 9:
        return False
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            prompt = fh.read()
        body, stamp = prompt.rstrip().rsplit("[delegate:", 1)
        if delegate_guard.fingerprint(body) != stamp.rstrip("]"):
            return False
        if "~/.claude/memory/MEMORY.md" not in prompt or "{" + "LABEL}" in prompt:
            return False
        if "レビュー種別: design" not in prompt or "rule.md" not in prompt:
            return False
    return any("R1-layering.txt" in p for p in paths) and any("free.txt" in p for p in paths)


@case
def read_list_resolves_from_taskdef_dir_then_its_repo_then_target_repo():
    """定義書と修正対象が別のリポジトリにあるとき（2026-10-07 の GID-1859 の件）。"""
    home = make_repo("idpf")   # 定義書があるリポジトリ
    target = make_repo("none")  # 修正対象（--repo）
    write(home, ".claude/tasks/P-1/design/a.png", "png")
    write(home, ".claude/prds/prd.md", "prd")
    write(home, "apps/api/x.go", "package x")
    write(target, "package.json", "{}")
    write(home, "package.json", "{}")  # 同名がある場合も、定義書側（1・2 番目）が先に当たる
    write(home, ".claude/tasks/P-1/t.md",
          "# t\n## 読むもの\n- `design/a.png`\n- [PRD](../../prds/prd.md)\n- `apps/api/x.go`\n"
          "- `package.json`\n- `only-target.ts`\n- `missing.md`\n## 目的\nx\n")
    write(target, "only-target.ts", "x")
    items = dict((s.split("（")[0], a) for s, a in build_prompt.read_list(os.path.join(home, ".claude/tasks/P-1/t.md"), target))
    return (items["design/a.png"] == os.path.join(home, ".claude/tasks/P-1/design/a.png")
            and items["../../prds/prd.md"] == os.path.join(home, ".claude/prds/prd.md")
            and items["apps/api/x.go"] == os.path.join(home, "apps/api/x.go")
            and items["package.json"] == os.path.join(home, "package.json")
            and items["only-target.ts"] == os.path.join(target, "only-target.ts")
            and items["missing.md"] is None)


@case
def read_list_same_repo_keeps_previous_resolution():
    repo = make_repo("idpf")
    write(repo, ".claude/tasks/t.md", "# t\n## 読むもの\n- `.claude/rules/rule.md`\n- `nope.md`\n## 目的\nx\n")
    items = build_prompt.read_list(os.path.join(repo, ".claude/tasks/t.md"), repo)
    return (items[0][1] == os.path.join(repo, ".claude/rules/rule.md")
            and items[1] == ("nope.md（読めず: 存在しない）", None))


@case
def read_list_requires_section():
    repo = make_repo()
    write(repo, ".claude/tasks/u.md", "# u\n## 目的\nx\n")
    try:
        build_prompt.read_list(os.path.join(repo, ".claude/tasks/u.md"), repo)
    except build_prompt.BuildError:
        return True
    return False


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
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
