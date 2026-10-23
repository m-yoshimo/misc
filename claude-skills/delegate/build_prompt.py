#!/usr/bin/env python3
"""エージェントに渡す指示文を組み立て、発行印を付けて出力する。

指示文の中身はこのスクリプトとテンプレートだけが決める。Claude は出力をそのまま Agent ツールに渡す。
発行印の無い・書き換えた指示文は `~/.claude/hooks/delegate_guard.py` が止める（背景はそちらの冒頭）。

使い方は `~/.claude/skills/delegate/SKILL.md`。
"""

import argparse
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid

HOME = os.path.expanduser("~")
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(SKILL_DIR, "templates")
DESIGN_REVIEW_DIR = os.path.join(HOME, ".claude", "skills", "design-review-v2")
RUBRIC_DIR = "~/.claude/notes/design-review-v2/"

sys.path.insert(0, os.path.join(HOME, ".claude", "hooks"))
from delegate_guard import ISSUED_LOG, WORKDIR_REGISTRY, append_jsonl, fingerprint, file_digest  # noqa: E402

# 未追跡ファイルのうち、ここに入るものは常にレビュー対象から外す（2026-10-05 ユーザー決定）。
# 追跡済みの差分は `.claude/` 以下も対象にする（GitHub で管理されるため）。
UNTRACKED_EXCLUDED_PREFIX = ".claude/"

# 調査の依頼文にこれらが入っていたら組み立てない。9/17 に「終わったら消す」と書いて成果物を消させたため。
RESEARCH_FORBIDDEN = re.compile(
    r"削除|消す|消して|消去|上書き|書き込|rm\s|rmdir|unlink|truncate"
    r"|git\s+(?:push|reset|restore|clean|stash|checkout|commit|add|rebase|merge|switch)"
)

# 調査役を使って、リポジトリ専用のレビュー skill を迂回した自前のレビューをさせないため（2026-10-05）。
# 言い換えれば通るので、完全には止まらない。
RESEARCH_REVIEW_WORDS = re.compile(r"レビュー|観点|指摘|review", re.I)

# 汎用エージェント。Agent ツールで subagent_type を省いたときもこれになる。
GENERAL = "general-purpose"

# pointpf-api のレビュアー定義はパスを付けずにファイルを読み書きさせる。エージェントはセッションの
# 作業ディレクトリで動くので、セッションが別のリポジトリにあると別の場所を読み書きしてしまう。
POINTPF_FILES = re.compile(r"(?<![\w/.-])(pr-diff\.txt|pr-summary\.txt|findings-[a-z]+\.json)")


MEMORY_DIR = os.path.join(HOME, ".claude", "memory")

# コマンドの実行役（`command`）に渡してよい、Makefile 以外のコマンド。ファイルを編集しないと分かっているものだけ。
# Makefile のターゲットはすべて許す（2026-10-05 ユーザー指示「Makefile に定義されているコマンドは、ルールなしで実行できて良い」）。
# 列挙に無いものは通さない（SAFE-08: 列挙の外は禁止側）。
COMMAND_ALLOWED = [
    ("go", "test"), ("go", "build"), ("go", "vet"),
    ("golangci-lint", "run"),
    ("pnpm", "run", "test"), ("pnpm", "run", "lint"), ("pnpm", "run", "typecheck"),
]
# 出力先の指定・連結・置換で、ファイルの書き換えを紛れ込ませないため
COMMAND_FORBIDDEN_CHARS = re.compile(r"[<>|;&$`()\n\\]")
MAKE_TARGET_LINE = re.compile(r"^([A-Za-z0-9_.\-/%]+(?:\s+[A-Za-z0-9_.\-/%]+)*)\s*:(?!=)", re.M)
MAKE_INCLUDE_LINE = re.compile(r"^-?include\s+(.+)$", re.M)
COMMAND_TIMEOUT = 590

# エージェントの中でもフックは動く。止められたときに中断して報告すると、委任をやり直すことになる（2026-10-06 ユーザー要件）。
HOOK_DENIED = (
    "## フックに止められたとき\n\n"
    "ツールの実行がフックに止められても、**作業を中断しないでください。** 止めた理由の文に直し方が書かれているので、"
    "そのとおりに形を直して実行し直し、作業を続けてください。\n"
    "直し方が書かれていない・直しても止められる場合だけ、その操作を飛ばして残りの作業を続け、"
    "最後の報告に「止めたフックの理由文」と「飛ばした操作」をそのまま書いてください。"
)


def scratch_note(workdir) -> str:
    if workdir:
        return (f"コマンドの出力をファイルに保存する必要があるときは、次のディレクトリの中にだけ置いてください"
                f"（`.claude/tmp/` の他の場所に新しいディレクトリを作ると、フックに止められます）: {workdir}")
    return ("一時ファイルを作らないでください（置き場所がありません）。コマンドの出力は `| head` / `| tail` で切らずに、"
            "そのまま全文を読んでください。")


class BuildError(Exception):
    pass


def rule_files() -> list:
    """委任先に全文を読ませる作業ルールのファイル。ファイルが増えても漏れないよう、毎回ディレクトリから集める。

    コードレビュー（`review`）とコマンドの実行役（`command`）以外の委任では、ルールを必ず守らせる（2026-10-05 ユーザー指示）。
    """
    paths = [os.path.join(MEMORY_DIR, "MEMORY.md")] + sorted(glob.glob(os.path.join(MEMORY_DIR, "feedback_*.md")))
    missing = [p for p in paths if not os.path.isfile(p)]
    if missing or len(paths) < 2:
        raise BuildError(f"作業ルールのファイルが見つからない: {', '.join(missing) or MEMORY_DIR}")
    return ["~/" + os.path.relpath(p, HOME) for p in paths]


def rule_list_text(indent: str) -> str:
    return "\n".join(f"{indent}- {p}" for p in rule_files())


# --- 発行 -------------------------------------------------------------------

# 🔴 2026-10-22 ユーザー決定。指示文はファイルで渡し、`prompt` には本文を入れない。
# そのため**依頼した側（メインのセッション）は、自分が何を指示したかを起動時に見ない**。
# それを補うため、**結果の冒頭に指示文の全文を転記させる**。
# 受け入れ検査（FLOW-22）は、転記された指示文と成果物を突き合わせて行う。
TRANSCRIBE_NOTE = (
    "\n\n## 受け取った指示文の転記（必須）\n\n"
    "**結果の冒頭に、いま読んだこの指示文の全文をそのまま転記してください。**\n"
    "- 結果をファイルに書く指示があるなら、そのファイルの冒頭に転記する\n"
    "- ファイルに書く指示が無いなら、最後の報告の冒頭に転記する\n"
    "- 要約せず、1 文字も変えずに写してください（依頼した側が、何を指示したかを確認するために使います）"
)


def issue(body: str, kind: str, label: str, agent=None, group=None, repo=None) -> str:
    """発行印を付ける。agent は起動してよい subagent_type（None なら照合しない）。

    group は同時に発行した指示文の組。組の全員を起動したかを Stop フックが確かめる。
    """
    body = body.rstrip() + TRANSCRIBE_NOTE + "\n"
    stamp = fingerprint(body)
    os.makedirs(os.path.dirname(ISSUED_LOG), exist_ok=True)
    record = {
        "id": stamp,
        "kind": kind,
        "label": label,
        "issued_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    if agent:
        record["agent"] = agent
    if group:
        record["group"] = group
    if repo:
        record["repo"] = repo
    with open(ISSUED_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return f"{body}\n[delegate:{stamp}]\n"


def new_group() -> str:
    return uuid.uuid4().hex[:12]


# --- git ---------------------------------------------------------------------

def git(repo: str, *args: str, ok_codes=(0,)) -> str:
    proc = subprocess.run(
        ["git", "-C", repo, *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode not in ok_codes:
        raise BuildError(f"git {' '.join(args)} が失敗した: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout.decode("utf-8", "replace")


def target_repo(args) -> str:
    """対象リポジトリ。セッションの作業ディレクトリは使わない（2026-10-05 ユーザー要件）。

    タスク定義書や会話が修正対象とは別のリポジトリにあっても、修正対象の実装に合わせて選ぶため。
    """
    if not args.repo:
        raise BuildError(
            "--repo で修正対象の実装があるリポジトリ（worktree）を指定すること。"
            "セッションの作業ディレクトリは使わない。どれか分からなければ、推測せずにユーザーに聞くこと"
        )
    return git(os.path.expanduser(args.repo), "rev-parse", "--show-toplevel").strip()


def taskdef_branch(taskdef: str):
    with open(taskdef, encoding="utf-8") as fh:
        match = re.search(r"^- 作業ブランチ:\s*`([^`]+)`", fh.read(), re.M)
    return match.group(1) if match else None


def check_branch(repo: str, taskdef: str) -> str:
    """タスク定義書の作業ブランチと、対象リポジトリの今のブランチが一致することを確かめる。"""
    current = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    expected = taskdef_branch(taskdef)
    if not expected:
        raise BuildError(f"{taskdef} の `## ステータス` に `- 作業ブランチ: \\`...\\`` が無い。リポジトリを照合できない")
    if expected != current:
        raise BuildError(
            f"タスク定義書の作業ブランチ `{expected}` と、{repo} の今のブランチ `{current}` が違う。"
            "--repo の指定（リポジトリ・worktree）を取り違えていないか確かめること"
        )
    return current


def repo_line(repo: str, args, check: bool) -> str:
    if check and args.taskdef:
        branch = check_branch(repo, os.path.abspath(os.path.expanduser(args.taskdef)))
        return f"対象: {repo}（ブランチ `{branch}`。タスク定義書の作業ブランチと一致）"
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    return f"対象: {repo}（ブランチ `{branch}`）"


TASKDEF_BASE_LINE = re.compile(r"^- ベースブランチ:\s*`([^`]+)`", re.M)


def taskdef_base_branch(taskdef):
    if not taskdef:
        return None
    path = os.path.abspath(os.path.expanduser(taskdef))
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        match = TASKDEF_BASE_LINE.search(fh.read())
    return match.group(1) if match else None


def default_base(repo: str, taskdef=None) -> tuple:
    """既定の取り方の起点: ベースブランチと今の HEAD が分かれた地点。

    ベースブランチは、タスク定義書の `- ベースブランチ:` の行があればそれ、無ければリポジトリの既定のブランチ（origin/HEAD）。
    別の作業ブランチから切ったブランチ・マージ先が main 以外の PR では、行を書かないと元のブランチの変更まで入るため（2026-10-07）。
    """
    branch = taskdef_base_branch(taskdef)
    if not branch:
        try:
            branch = git(repo, "rev-parse", "--abbrev-ref", "origin/HEAD").strip()
        except BuildError:
            branch = "origin/main"
    try:
        base = git(repo, "merge-base", branch, "HEAD").strip()
    except BuildError:
        raise BuildError(
            f"既定の差分の起点（{branch} と HEAD の分かれた地点）を求められない。"
            "取り方（--cached / --worktree / --head / --range A..B）を指定すること"
        )
    return branch, base


def diff_args(args, repo: str) -> tuple:
    """(git diff の引数, 表示用の名前) を返す。

    指定が無ければ既定の取り方「PR に載る変更の全部」にする（2026-10-07 ユーザー指示「既定値は作って」。
    それまでは既定値を持たせず毎回聞いていたため、レビューのたびに聞き返していた）:
    既定のブランチから分かれた地点と作業ツリーの差分（コミット済み・ステージ済み・未ステージ）＋未追跡ファイル。
    """
    chosen = [m for m in ("cached", "worktree", "head") if getattr(args, m)]
    if args.range:
        chosen.append("range")
    if len(chosen) > 1:
        raise BuildError("差分の取り方は 1 つだけ指定すること（--cached / --worktree / --head / --range A..B）")
    if not chosen:
        branch, base = default_base(repo, getattr(args, "taskdef", None))
        args.untracked = True
        commits = git(repo, "rev-list", "--count", f"{base}..HEAD").strip()
        source = "タスク定義書のベースブランチ" if taskdef_base_branch(getattr(args, "taskdef", None)) else "既定のブランチ"
        return [base], (f"既定: git diff $(git merge-base {branch} HEAD)（起点 {base[:9]}・{source} {branch}・"
                        f"起点から積まれたコミット {commits} 件。コミット済み・ステージ済み・未ステージ）")
    mode = chosen[0]
    if mode == "cached":
        return ["--cached"], "git diff --cached"
    if mode == "worktree":
        return [], "git diff"
    if mode == "head":
        return ["HEAD"], "git diff HEAD"
    return [args.range], f"git diff {args.range}"


def build_diff(repo: str, args) -> tuple:
    """(差分の本文, 1 行の説明) を返す。"""
    extra, label = diff_args(args, repo)
    text = git(repo, "diff", *extra)
    files = [f for f in git(repo, "diff", "--name-only", *extra).splitlines() if f]
    untracked = []
    if args.untracked:
        listed = git(repo, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
        for path in sorted(p for p in listed if p and not p.startswith(UNTRACKED_EXCLUDED_PREFIX)):
            # 差分があると終了コード 1 を返す
            text += git(repo, "diff", "--no-index", "--", "/dev/null", path, ok_codes=(0, 1))
            untracked.append(path)
    if not text.strip():
        raise BuildError(f"レビュー対象なし（{label}{' ＋ 未追跡' if args.untracked else ''} が空）")
    summary = f"差分: `{label}`"
    if args.untracked:
        summary += f" ＋ 未追跡 {len(untracked)} 件"
    summary += f"（{len(files) + len(untracked)} ファイル）"
    return text, summary


# --- 作業ディレクトリ ---------------------------------------------------------

TASKDEF_TMP_LINE = re.compile(r"^\s*-?\s*一時ディレクトリ[:：](.*)$", re.M)
TASKDEF_TMP_NAME = re.compile(r"`(?:\./)?\.claude/tmp/([^/`\s]+)/?`")


def require_taskdef(args, why: str) -> str:
    if not args.taskdef:
        raise BuildError(
            f"--taskdef が必要（{why}）。タスク定義書が無い作業なら、作業ファイルを作る委任はできないので、ユーザーに聞くこと"
        )
    taskdef = os.path.abspath(os.path.expanduser(args.taskdef))
    if not os.path.isfile(taskdef):
        raise BuildError(f"タスク定義書が無い: {taskdef}")
    return taskdef


def task_tmpdir(taskdef: str) -> str:
    """タスク定義書の `## ステータス` で宣言された一時ディレクトリ（META-01）。

    委任のファイルは作業ごとのこのディレクトリに置く。共用のディレクトリを作らないのは、
    どのチケットのファイルか分からなくなり、消し忘れるため（2026-10-06 ユーザー要件「tmp 以下はセッションごとに持ってほしい」）。
    """
    parts = taskdef.split(os.sep)
    try:
        index = len(parts) - 1 - parts[::-1].index("tasks")
    except ValueError:
        index = -1
    if index < 1 or parts[index - 1] != ".claude":
        raise BuildError(f"{taskdef} は `.claude/tasks/` の下に無い。一時ディレクトリの場所を決められない")
    claude_root = os.sep.join(parts[:index])
    with open(taskdef, encoding="utf-8") as fh:
        text = fh.read()
    names = [n for line in TASKDEF_TMP_LINE.findall(text) for n in TASKDEF_TMP_NAME.findall(line)]
    if len(names) != 1:
        raise BuildError(
            f"{taskdef} の `## ステータス` に「一時ディレクトリ: `.claude/tmp/<名前>/`」の行が 1 つも無い（または複数ある）。"
            "先に宣言すること（META-01）"
        )
    return os.path.join(claude_root, "tmp", names[0])


def make_workdir(taskdef: str, kind: str) -> str:
    """`<一時ディレクトリ>/delegate/<日時>-<種類>-<ランダム>/` を作り、持ち主のタスク定義書と結びつけて記録する。

    名前の末尾にランダムな文字列を付け、既にあればエラーにする。複数のセッションが同じ秒に組み立てても、
    別の委任のファイルを上書きしないため。持ち主のタスク定義書が `.claude/tasks/` から無くなったら
    （`done/` に移ったら）、`delegate_guard.py` が消す。
    """
    now = datetime.datetime.now()
    root = os.path.join(task_tmpdir(taskdef), "delegate")
    path = os.path.join(root, f"{now.strftime('%Y%m%d-%H%M%S')}-{kind}-{uuid.uuid4().hex[:6]}")
    os.makedirs(path)
    append_jsonl(WORKDIR_REGISTRY, {"dir": root, "taskdef": taskdef})
    return path


def record_external(workdir: str, path: str) -> None:
    """一時ディレクトリの外に書いたファイル（pointpf-api の `pr-diff.txt`）を、完了時に消せるよう記録する。"""
    append_jsonl(os.path.join(os.path.dirname(workdir), "external.jsonl"), {"path": path, "digest": file_digest(path)})


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# --- タスク定義書の `## 読むもの` ---------------------------------------------

PATH_IN_BACKTICKS = re.compile(r"`([^`\s]+)`")
PATH_IN_LINK = re.compile(r"\]\(([^)\s]+)\)")
URL = re.compile(r"https?://[^\s)`|]+")


def git_root_of(path: str):
    """path から上にたどって `.git`（ディレクトリ、または worktree のファイル）がある場所を返す。"""
    current = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def resolve_relative(candidate: str, bases: list):
    """bases の順に試し、最初に実在したものを返す。どれにも無ければ None。"""
    for base in bases:
        absolute = os.path.normpath(os.path.join(base, candidate))
        if os.path.exists(absolute):
            return absolute
    return None


def read_list(taskdef: str, repo: str) -> list:
    """`## 読むもの` 節に書かれたパスと URL を、書かれた順に重複なく返す。

    返すのは (表示用の文字列, 実在するローカルファイルの絶対パス or None) の組。
    取捨選択はしない。読めないものは読めない旨を付けて残す（黙って落とさない）。

    相対パスは、次の順に試して最初に実在したものを使う（2026-10-07。定義書と修正対象が別のリポジトリにあると、
    --repo 基準だけでは定義書のリンクがほとんど解決できなかったため）:
      1. 定義書のディレクトリ（Markdown のリンクの慣習）
      2. 定義書が属する git リポジトリの直下
      3. --repo（以前からの基準）
    解決できたものは、表示に絶対パスを添える。相対パスのままだと、委任先がどこを基準に読むか分からないため。
    """
    with open(taskdef, encoding="utf-8") as fh:
        text = fh.read()
    match = re.search(r"^## 読むもの[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not match:
        raise BuildError(f"{taskdef} に `## 読むもの` 節が無い")
    return [(r["shown"], r["path"] if r["kind"] == "file" else None) for r in refs_in(match.group(1), taskdef, repo)]


def refs_in(section: str, taskdef: str, repo: str) -> list:
    """節の本文に書かれたパスと URL を、書かれた順に重複なく返す。

    返すのは {shown: 表示用の文字列, path: 絶対パス or None, kind: url / file / dir / pattern / missing} の並び。
    """
    bases = [os.path.dirname(os.path.abspath(taskdef))]
    for base in (git_root_of(taskdef), repo):
        if base and base not in bases:
            bases.append(base)

    found, seen = [], set()
    for candidate in URL.findall(section) + PATH_IN_LINK.findall(section) + PATH_IN_BACKTICKS.findall(section):
        candidate = candidate.split("#L")[0].rstrip(".,、。")
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.startswith("http"):
            found.append({"shown": candidate, "path": None, "kind": "url"})
            continue
        if "/" not in candidate and not re.search(r"\.\w+$", candidate):
            continue  # コマンド名・識別子などパスでないもの
        if candidate.startswith("~"):
            absolute = os.path.expanduser(candidate)
        elif os.path.isabs(candidate):
            absolute = candidate
        else:
            absolute = resolve_relative(candidate, bases) or os.path.join(repo, candidate)
        where = "" if absolute == candidate else f"（{absolute}）"
        if os.path.isfile(absolute):
            found.append({"shown": f"{candidate}{where}", "path": absolute, "kind": "file"})
        elif os.path.isdir(absolute):
            found.append({"shown": f"{candidate}{where}（ディレクトリ。配下の全ファイルを読むこと）",
                          "path": absolute, "kind": "dir"})
        elif "*" in candidate:
            found.append({"shown": f"{candidate}（パターン。該当する全ファイルを読むこと）", "path": None, "kind": "pattern"})
        else:
            found.append({"shown": f"{candidate}（読めず: 存在しない）", "path": None, "kind": "missing"})
    return found


# ワーカーに渡す資料（定義書を含む）の合計の上限。ルール本文は別枠（全委任で同じ量を読むため）。
# 2026-10-07 に GID-1859 のワーカーが、渡された 1MB 超の資料を読み切れずに自分の判断で読み飛ばした。
# 500KB は Claude が決めた初期値（量の検査はユーザーが承認したが、数字そのものはユーザー未確認）。
WORKER_READ_LIMIT = 500_000
# 画像は読むときの重さがバイト数に比例しないので、合計に数えない
NON_TEXT = re.compile(r"\.(?:png|jpe?g|gif|webp|svg|pdf|ico)$", re.I)
SKIP_DIRS = {".git", "node_modules", ".next", "dist", "build", "vendor"}


def text_bytes(path: str) -> int:
    return 0 if NON_TEXT.search(path) else os.path.getsize(path)


def dir_files(path: str) -> list:
    files = []
    for root, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        files.extend(os.path.join(root, n) for n in names)
    return files


def worker_read_list(taskdef: str, repo: str, assign: str) -> list:
    """`## 変更対象ファイル一覧` の `### <assign>` 節にある「読むもの」を返す（2026-10-07 ユーザー承認）。

    タスク全体の `## 読むもの` は、担当の違うワーカー全員の資料を合わせたもので、1 体には読み切れない量になる。
    何を読ませるかは定義書の時点で決め、ワーカーにも Claude にも選ばせない。
    """
    with open(taskdef, encoding="utf-8") as fh:
        text = fh.read()
    plan = re.search(r"^## 変更対象ファイル一覧[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not plan:
        raise BuildError(f"{taskdef} に `## 変更対象ファイル一覧` 節が無い")
    # 名前の後ろは「（範囲）」「: 範囲」「 — 範囲」など書き方が揃わないので、英数字が続かないことだけを見る
    section = re.search(rf"^### {re.escape(assign)}(?![\w-])[^\n]*\n(.*?)(?=^### |^## |\Z)", plan.group(1), re.S | re.M)
    if not section:
        raise BuildError(
            f"{taskdef} の `## 変更対象ファイル一覧` に `### {assign}` の節が無い。"
            "テンプレート（~/.claude/tasks/_TEMPLATE.md）の形でワーカーごとの節を立てること"
        )
    block = re.search(r"^- 読むもの[^\n]*\n((?:[ \t]+[^\n]*\n?|\n)*)", section.group(1), re.M)
    if not block or not block.group(1).strip():
        raise BuildError(
            f"{taskdef} の `### {assign}` に「- 読むもの:」の列挙が無い。"
            "このワーカーが読む資料を、`## 読むもの` から選んでファイル単位で書くこと"
        )
    refs = refs_in(block.group(1), taskdef, repo)
    repo_dirs = [r["shown"] for r in refs if r["kind"] == "dir" and os.path.exists(os.path.join(r["path"], ".git"))]
    if repo_dirs:
        raise BuildError(f"`### {assign}` の「読むもの」にリポジトリ丸ごとのディレクトリがある: {', '.join(repo_dirs)}。ファイル単位に直すこと")
    sizes = [(text_bytes(taskdef), "タスク定義書")]
    for r in refs:
        if r["kind"] == "file":
            sizes.append((text_bytes(r["path"]), r["shown"]))
        elif r["kind"] == "dir":
            files = dir_files(r["path"])
            sizes.append((sum(text_bytes(f) for f in files), r["shown"]))
            r["shown"] = r["shown"].replace("（ディレクトリ。", f"（ディレクトリ。{len(files)} ファイル。")
    total = sum(s for s, _ in sizes)
    if total > WORKER_READ_LIMIT:
        biggest = "、".join(f"{name}（{size // 1000}KB）" for size, name in sorted(sizes, reverse=True)[:5])
        raise BuildError(
            f"`### {assign}` で渡す資料が定義書と合わせて {total // 1000}KB あり、上限 {WORKER_READ_LIMIT // 1000}KB を超える"
            f"（大きい順: {biggest}）。ワーカーが読み切れず、自分の判断で読み飛ばすことになる。"
            "定義書の「読むもの」を絞るか、担当を分けること"
        )
    return [(r["shown"], r["path"] if r["kind"] == "file" else None) for r in refs], total


# --- コードレビュー -----------------------------------------------------------

FENCED_BLOCK = re.compile(r"^```[^\n]*\n(.*?)\n```[ \t]*$", re.S | re.M)
AGENT_LINE = re.compile(r"^- (review-[\w-]+)[ \t]*$", re.M)
SUBAGENT_SENTENCE = re.compile(r"各サブエージェントには「(.+?)」と指示してください")
REVIEW_WORD = re.compile(r"レビュー|review", re.I)
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def skill_files(repo: str) -> list:
    root = os.path.join(repo, ".claude", "skills")
    return sorted(glob.glob(os.path.join(root, "*", "SKILL.md")) + glob.glob(os.path.join(root, "*.md")))


def classify_skill(path: str, repo: str):
    """スクリプトが指示文を組み立てられるコードレビューの skill か、中身の形で判定する（名前は見ない）。

    返すのは ("template", テンプレート本文) / ("agents", None) / None。
    """
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for block in FENCED_BLOCK.findall(text):
        if "{diff}" in block:
            return ("template", block)
    agents = AGENT_LINE.findall(text)
    if agents and SUBAGENT_SENTENCE.search(text) and all(
            os.path.isfile(os.path.join(repo, ".claude", "agents", f"{a}.md")) for a in agents):
        return ("agents", None)
    return None


def mentions_review(path: str) -> bool:
    """名前・説明・ファイル名に「レビュー」「review」を含むか（形の合わないレビューの skill を見落とさないため）。"""
    with open(path, encoding="utf-8") as fh:
        head = FRONTMATTER.match(fh.read())
    names = os.path.relpath(path, os.path.dirname(os.path.dirname(path)))
    return bool(REVIEW_WORD.search(names) or (head and REVIEW_WORD.search(head.group(1))))


def action_review_prompts(repo: str) -> list:
    """GitHub Actions で `anthropics/claude-code-action` に `prompt:` を渡している、レビューの定義を返す。

    同じ action はレビュー以外（脆弱性の自動修正など）にも使われるので、ファイル名・ワークフロー名・ジョブ名の
    どれかに「レビュー」「review」を含むものだけを数える（pointpf-api の govulncheck-autofix.yml を拾わないため）。
    """
    import yaml

    found = []
    for path in sorted(glob.glob(os.path.join(repo, ".github", "workflows", "*.y*ml"))):
        try:
            with open(path, encoding="utf-8") as fh:
                doc = yaml.safe_load(fh) or {}
        except (OSError, yaml.YAMLError):
            continue
        for job_key, job in (doc.get("jobs") or {}).items():
            names = " ".join(str(x) for x in (os.path.basename(path), doc.get("name"), job_key, (job or {}).get("name")))
            if not REVIEW_WORD.search(names):
                continue
            for step in (job or {}).get("steps") or []:
                uses = str((step or {}).get("uses") or "")
                prompt = ((step or {}).get("with") or {}).get("prompt")
                if uses.startswith("anthropics/claude-code-action") and isinstance(prompt, str) and prompt.strip():
                    found.append((path, prompt))
    return found


def build_review(args) -> dict:
    """コードレビューに使うものを、対象リポジトリの中身から決める。Claude は選ばない（2026-10-07 ユーザー決定）。

    1. リポジトリのコードレビューの skill（名前ではなく中身の形で見分ける）
    2. 無ければ、GitHub Actions の Claude コードレビューの定義（`prompt:`）
    3. どちらも無ければ、design-review-v2（差分を対象にしたコードレビュー）
    形の合うものが 2 つ以上あって決まらないとき、形の合わない「レビュー」の skill があるときは、止めてユーザーに聞く。
    """
    taskdef = require_taskdef(args, "差分・指示文をタスク定義書の一時ディレクトリに置くため")
    repo = target_repo(args)
    head = repo_line(repo, args, check=True)

    files = skill_files(repo)
    matched = [(path, classify_skill(path, repo)) for path in files]
    matched = [(path, kind) for path, kind in matched if kind]
    if len(matched) > 1:
        raise BuildError(
            "コードレビューの skill として使える形のものが 2 つ以上ある: "
            + "、".join(p for p, _ in matched) + "。どれを使うか、ユーザーに聞くこと"
        )
    if matched:
        path, (kind, template) = matched[0]
        if kind == "template":
            result = review_local(repo, path, template, args, taskdef)
        else:
            result = review_pointpf(repo, path, args, taskdef)
        result["summary"] = f"{head}\n■ レビュー: リポジトリの skill {path}\n■ {result['summary']}"
        return result

    unknown = [p for p in files if mentions_review(p)]
    if unknown:
        raise BuildError(
            f"名前か説明にレビューを含む skill があるが、スクリプトが組み立てられる形ではない: {'、'.join(unknown)}。"
            "チームのレビューの skill かもしれないので、黙って他のレビューに切り替えない。ユーザーに聞くこと"
        )

    actions = action_review_prompts(repo)
    if len(actions) > 1:
        raise BuildError(
            "GitHub Actions に Claude のレビューの定義が 2 つ以上ある: "
            + "、".join(p for p, _ in actions) + "。どれを使うか、ユーザーに聞くこと"
        )
    if actions:
        path, prompt = actions[0]
        result = review_actions(repo, path, prompt, args, taskdef)
        result["summary"] = f"{head}\n■ レビュー: GitHub Actions の定義 {path}\n■ {result['summary']}"
        return result

    result = build_review_design_v2(args)
    result["summary"] = ("■ レビュー: design-review-v2（リポジトリにコードレビューの skill も GitHub Actions の定義も無いため）\n"
                         f"{result['summary']}")
    return result


ACTIONS_PREFACE = (
    "これはローカルの差分のレビューです（PR はまだありません）。以下の指示は、このリポジトリの GitHub Actions"
    "（{workflow}）で PR のレビューに使っているものです。次の点だけ読み替えてください。\n"
    "- `gh pr diff` などの `gh` コマンドは使わず、差分は次のファイルを Read ツールで最後まで読んでください: {diff}\n"
    "- PR にコメントしないでください。レビュー結果は最後のメッセージに書いてください。\n"
    "- ファイルを作成・編集・削除しないでください。\n\n---\n\n"
)


def review_actions(repo: str, workflow: str, prompt: str, args, taskdef: str) -> dict:
    text, summary = build_diff(repo, args)
    workdir = make_workdir(taskdef, "review")
    diff_path = os.path.join(workdir, "target.diff")
    write(diff_path, text)
    body = ACTIONS_PREFACE.format(workflow=workflow, diff=diff_path) + prompt.strip()
    prompt_text = issue(body, "review", "actions-review", agent=GENERAL, repo=repo)
    return {"summary": summary, "workdir": workdir, "prompts": [("actions-review", GENERAL, prompt_text)]}


def review_local(repo: str, skill: str, template: str, args, taskdef: str) -> dict:
    text, summary = build_diff(repo, args)
    workdir = make_workdir(taskdef, "review")
    diff_path = os.path.join(workdir, "target.diff")
    write(diff_path, text)
    untracked_note = (
        "なし（未追跡の新規ファイルは、上の差分ファイルに新規追加の差分として含めてある）"
        if args.untracked else "なし（今回は未追跡ファイルをレビュー対象に含めていない）"
    )
    body = template.replace(
        "{diff}", f"差分の本文はファイルに保存してある。Read ツールで最後まで読むこと: {diff_path}"
    ).replace("{untracked_files}", untracked_note)
    label = os.path.basename(os.path.dirname(skill)) if skill.endswith("SKILL.md") else os.path.basename(skill)[:-3]
    prompt = issue(body, "review", label, agent=GENERAL, repo=repo)
    return {"summary": summary, "workdir": workdir, "prompts": [(label, GENERAL, prompt)]}


def agent_body(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    match = re.match(r"---\n.*?\n---\n", text, re.S)
    return text[match.end():] if match else text


def review_pointpf(repo: str, skill: str, args, taskdef: str) -> dict:
    with open(skill, encoding="utf-8") as fh:
        skill_text = fh.read()
    sentence = SUBAGENT_SENTENCE.search(skill_text)
    agents = AGENT_LINE.findall(skill_text)
    if not sentence or not agents:
        raise BuildError(f"{skill} から指示文・レビュアー一覧を読み取れない（skill の形が変わった可能性がある）")
    definitions = {name: os.path.join(repo, ".claude", "agents", f"{name}.md") for name in agents}
    missing = [p for p in definitions.values() if not os.path.isfile(p)]
    if missing:
        raise BuildError(f"レビュアーの定義ファイルが無い: {', '.join(missing)}")
    # pr-diff.txt と findings-*.json は skill が決めた固定の名前で、リポジトリに 1 組しか置けない。
    # 残っていれば、前回の消し忘れか、別のセッションのレビューが進行中なので上書きしない（2026-10-06）。
    leftovers = sorted(glob.glob(os.path.join(repo, "findings-*.json")))
    if os.path.exists(os.path.join(repo, "pr-diff.txt")):
        leftovers.insert(0, os.path.join(repo, "pr-diff.txt"))
    if leftovers:
        raise BuildError(
            f"前回のレビューのファイルが残っている（{', '.join(leftovers)}）。別のセッションのレビューが進行中かもしれない。"
            "進行中でないことを確かめてから、code-review-local の片付け手順のとおり削除して組み立て直すこと"
        )

    text, summary = build_diff(repo, args)
    workdir = make_workdir(taskdef, "review")
    pr_diff = os.path.join(repo, "pr-diff.txt")
    write(pr_diff, text)  # skill が決めている置き場所
    record_external(workdir, pr_diff)

    def absolute(src: str) -> str:
        return POINTPF_FILES.sub(lambda m: os.path.join(repo, m.group(1)), src)

    group = new_group()
    prompts = []
    for name, path in definitions.items():
        # 定義ファイルの subagent_type は、セッションが pointpf-api に無いと起動できない。
        # どこからでも同じに動かすため、定義の本文を指示文に入れて汎用エージェントで起動する。
        body = (
            f"あなたは code-review-local skill のレビュアー `{name}` です。"
            f"以下は {path} の本文です。この定義に従ってください。"
            "（ファイル名は、対象リポジトリ直下の絶対パスに置き換えてあります）\n\n"
            f"{absolute(agent_body(path)).strip()}\n\n---\n\n{absolute(sentence.group(1))}"
        )
        prompts.append((name, GENERAL, issue(body, "review", name, agent=GENERAL, group=group, repo=repo)))
    return {
        "summary": summary + f"。`{os.path.join(repo, 'pr-diff.txt')}` に保存。レビュアー {len(prompts)} 体（全員を並列で起動すること）",
        "workdir": workdir,
        "prompts": prompts,
    }


# --- design-review-v2 --------------------------------------------------------

def conventions(repo: str) -> list:
    """design-review-v2 の Step 1（規約の所在）。存在するものを機械的に集める。"""
    patterns = [
        "CLAUDE.md", "*/CLAUDE.md", "apps/*/CLAUDE.md",
        "docs/*.md", ".claude/rules/**/*.md", ".claude/agents/review-*.md",
    ]
    found = []
    for pattern in patterns:
        for path in sorted(glob.glob(os.path.join(repo, pattern), recursive=True)):
            rel = os.path.relpath(path, repo)
            if rel not in found:
                found.append(rel)
    return [os.path.join(repo, p) for p in found]


def build_review_design_v2(args) -> dict:
    taskdef = require_taskdef(args, "design-review-v2 はタスク定義書の `## 読むもの` から資料を集め、一時ディレクトリに置く")
    repo = target_repo(args)
    head = repo_line(repo, args, check=not args.design)
    skill = os.path.join(DESIGN_REVIEW_DIR, "SKILL.md")
    with open(os.path.join(DESIGN_REVIEW_DIR, "reviewer_prompt.md"), encoding="utf-8") as fh:
        template = fh.read()
    with open(skill, encoding="utf-8") as fh:
        skill_text = fh.read()
    reviewers = re.findall(r"^\| `review:([^`]+)` \| `([^`]+)`", skill_text, re.M)
    if len(reviewers) != 9:
        raise BuildError(f"{skill} からレビュアー 9 体を読み取れない（{len(reviewers)} 体）")

    workdir = make_workdir(taskdef, "review-design-v2")
    if args.design:
        if any(getattr(args, m) for m in ("cached", "worktree", "head")) or args.range:
            raise BuildError("--design と差分の取り方は同時に指定できない")
        target = os.path.join(workdir, "target.md")
        shutil.copyfile(taskdef, target)
        review_type, summary = "design", f"対象: タスク定義書 {taskdef}"
    else:
        text, summary = build_diff(repo, args)
        target = os.path.join(workdir, "target.diff")
        write(target, text)
        review_type = "code"

    context_lines = []
    context_dir = os.path.join(workdir, "context")
    for shown, absolute in read_list(taskdef, repo):
        if absolute:
            copied = os.path.join(context_dir, absolute.replace(os.sep, "__").lstrip("_"))
            os.makedirs(context_dir, exist_ok=True)
            shutil.copyfile(absolute, copied)
            context_lines.append(f"- {copied}（元: {shown}）")
        else:
            context_lines.append(f"- {shown}")
    conv = conventions(repo)
    rules = rule_list_text("   ")

    group = new_group()
    prompts = []
    for label, rule_file in reviewers:
        rule = f"{RUBRIC_DIR}{rule_file}" if not rule_file.startswith("~") else rule_file
        body = (template
                .replace("{WORKDIR}", workdir)
                .replace("{RULE_FILES}", rules)
                .replace("{RULE_FILE}", rule)
                .replace("{CONVENTIONS}", "\n".join(f"- {p}" for p in conv) or "なし")
                .replace("{TARGET}", target)
                .replace("{REVIEW_TYPE}", review_type)
                .replace("{CONTEXT}", "\n".join(context_lines) or "なし")
                .replace("{LABEL}", label))
        prompts.append((label, GENERAL, issue(body, "review-design-v2", label, agent=GENERAL, group=group, repo=repo)))
    return {"summary": f"{head}\n■ {summary}。補助資料 {len(context_lines)} 件・規約 {len(conv)} 件",
            "workdir": workdir, "prompts": prompts}


# --- 実装ワーカー・調査 -------------------------------------------------------

def build_worker(args) -> dict:
    if not (args.taskdef and args.assign and args.fixed_sections):
        raise BuildError("worker には --taskdef・--assign・--fixed-sections がすべて必要")
    taskdef = os.path.abspath(os.path.expanduser(args.taskdef))
    repo = target_repo(args)
    head = repo_line(repo, args, check=True)
    items, total = worker_read_list(taskdef, repo, args.assign)
    # 一時ディレクトリを宣言している定義書なら、ワーカー用の置き場所を作って渡す。渡さないと、ワーカーが
    # ルールどおり出力を `.claude/tmp/` に保存しようとして、宣言の無いディレクトリとしてフックに止められるため
    try:
        workdir = make_workdir(taskdef, "worker")
    except BuildError:
        workdir = None
    with open(os.path.join(TEMPLATES, "worker.md"), encoding="utf-8") as fh:
        body = (fh.read()
                .replace("{TASKDEF}", taskdef)
                .replace("{READ_LIST}", "\n".join(f"   - {shown}" for shown, _ in items) or "   - なし")
                .replace("{RULE_FILES}", rule_list_text("   "))
                .replace("{ASSIGN}", args.assign)
                .replace("{SCRATCH}", scratch_note(workdir))
                .replace("{HOOK_DENIED}", HOOK_DENIED)
                .replace("{FIXED_SECTIONS}", "、".join(f"`{s}`" for s in args.fixed_sections)))
    prompt = issue(body, "worker", args.assign, agent=GENERAL, repo=repo)
    return {"summary": f"{head}\n■ タスク定義書 {taskdef}・担当 {args.assign}・読むもの {len(items)} 件"
                       f"（定義書と合わせて {total // 1000}KB／上限 {WORKER_READ_LIMIT // 1000}KB）",
            "workdir": workdir, "prompts": [("worker", GENERAL, prompt)]}


# 🔴 2026-10-22 ユーザー指示「research に省くオプションを付けろ、ただしこのオプションが
# 僕が明示的にルール不要といった時だけ使えるようにしろ」。
# 許可を記録するのは `rm_grant.py`（UserPromptSubmit）で、材料はユーザーの発言そのもの。
# **Claude 側から許可を書く経路は無い**（自己例外化の禁止・SAFE-07）。
NO_RULES_GRANT_DIR = os.path.join(HOME, ".claude", "state", "no_rules_grant")


def no_rules_granted() -> bool:
    """ユーザーがこのターンで「ルールは不要」と言ったか。

    スクリプトには session_id が渡らないので、記録の**どれかが直近 15 分以内**なら許可とみなす。
    許可はユーザーの発言でしか作られないので、セッションをまたいで効く点だけが緩さとして残る。
    """
    try:
        names = os.listdir(NO_RULES_GRANT_DIR)
    except OSError:
        return False
    limit = time.time() - 15 * 60
    for name in names:
        path = os.path.join(NO_RULES_GRANT_DIR, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) >= limit:
                return True
        except OSError:
            continue
    return False


def research_rules_section(args) -> str:
    """調査役にルール本文を読ませる節。`--no-rules` が許可されているときだけ省く。"""
    if not getattr(args, "no_rules", False):
        return (
            "## 最初に読むもの\n\n"
            "作業ルールの全ファイル（**全文を読み、調査中はこれに従ってください**。"
            "あなたにはルールが自動では渡らないため、ここで読みます）:\n"
            f"{rule_list_text('')}\n\n"
            "ルールとこの指示文が食い違うときは、どちらかを自分で選ばず、報告に書いてください。"
        )
    if not no_rules_granted():
        raise BuildError(
            "--no-rules は、ユーザーが「ルールは不要」と明示したターンでしか使えない"
            "（記録が無い）。ルールを読ませる形で組み立て直すか、ユーザーに確認すること"
        )
    return (
        "## 作業ルール\n\n"
        "**このタスクでは作業ルールの読み込みを省いています**（ユーザーが「ルールは不要」と明示したため）。\n"
        "下の「制約」と「報告」に書かれていることだけを守ってください。"
    )


def build_research(args) -> dict:
    if not args.question:
        raise BuildError("research には --question が必要")
    hit = RESEARCH_FORBIDDEN.search(args.question)
    if hit:
        raise BuildError(f"調べる内容に、読み取り以外の操作を指す語「{hit.group(0)}」が入っている。調査役には読み取りだけを任せる")
    hit = RESEARCH_REVIEW_WORDS.search(args.question)
    if hit:
        raise BuildError(
            f"調べる内容に「{hit.group(0)}」が入っている。コードレビューは `review`、"
            "設計レビューは `review-design-v2` を使うこと（調査役でレビューの代わりをしない）"
        )
    # タスク定義書があれば、結果はその一時ディレクトリのファイル 1 つに書かせる（2026-10-06 ユーザー決定）。
    # 設計時の調査は結果が大きく、メッセージで返すと Claude のコンテキストを圧迫し、要約で細部が失われるため。
    # 書き出し先を Claude が指定できると上書きの経路になるので、毎回新しく作るディレクトリに固定する。
    # タスク定義書が無い作業では一時ディレクトリを作らない（META-01）ので、メッセージで返させる。
    if args.taskdef:
        workdir = make_workdir(require_taskdef(args, ""), "research")
        result = os.path.join(workdir, "result.md")
        report = (
            "調べた結果は、**次のファイル 1 つにだけ**書き出してください。他の場所には書かないでください。\n\n"
            f"{result}\n\n最後のメッセージには、書き終えたことと、上のファイルのパスだけを書いてください。"
        )
        summary = f"調査（読み取りのみ）。結果の書き出し先: {result}"
        # 書き込みのツールを持たないエージェント（Explore など）では結果を書けず、途中で失敗するため汎用に固定する
        agent = GENERAL
    else:
        workdir, report = None, "調べた結果は、**最後のメッセージにだけ**書いてください。ファイルに書き出さないでください。"
        summary = "調査（読み取りのみ）。タスク定義書の指定が無いので、結果はメッセージで返る"
        agent = None
    with open(os.path.join(TEMPLATES, "research.md"), encoding="utf-8") as fh:
        body = (fh.read()
                .replace("{RULES_SECTION}", research_rules_section(args))
                .replace("{REPORT}", report)
                .replace("{SCRATCH}", scratch_note(workdir))
                .replace("{HOOK_DENIED}", HOOK_DENIED)
                .replace("{QUESTION}", args.question.strip()))
    return {"summary": summary, "workdir": workdir,
            "prompts": [("research", agent, issue(body, "research", "research", agent=agent))]}


def make_targets(makefile: str, seen=None) -> set:
    """Makefile（と include したファイル）に書かれたターゲット名。make は実行しない（$(shell) を評価させないため）。"""
    seen = seen if seen is not None else set()
    if makefile in seen or not os.path.isfile(makefile):
        return set()
    seen.add(makefile)
    with open(makefile, encoding="utf-8") as fh:
        text = fh.read()
    targets = set()
    for line in MAKE_TARGET_LINE.findall(text):
        targets.update(t for t in line.split() if not t.startswith(".") and "%" not in t)
    for include in MAKE_INCLUDE_LINE.findall(text):
        for name in include.split():
            targets |= make_targets(os.path.join(os.path.dirname(makefile), name), seen)
    return targets


def check_command(command: str, cwd: str) -> None:
    hit = COMMAND_FORBIDDEN_CHARS.search(command)
    if hit:
        raise BuildError(f"コマンド `{command}` に `{hit.group(0)}` が入っている。リダイレクト・連結・置換は使えない（出力の保存先はスクリプトが決める）")
    words = command.split()
    if not words:
        raise BuildError("空のコマンドは渡せない")
    if words[0] == "make":
        if any(w in ("-C", "-f", "--file", "--directory") or w.startswith(("--file=", "--directory=")) for w in words[1:]):
            raise BuildError("make の -C / -f は使えない。実行する場所は --cwd で指定すること")
        wanted = [w for w in words[1:] if not w.startswith("-") and "=" not in w]
        targets = make_targets(os.path.join(cwd, "Makefile"))
        unknown = [t for t in wanted if t not in targets]
        if not wanted or unknown:
            raise BuildError(f"{os.path.join(cwd, 'Makefile')} に定義されていないターゲット: {', '.join(unknown) or '（指定なし）'}")
        return
    if "-o" in words:
        raise BuildError(f"`{command}` は -o でファイルを書き出す。コマンドの実行役には渡せない")
    if not any(tuple(words[:len(prefix)]) == prefix for prefix in COMMAND_ALLOWED):
        allowed = "、".join(" ".join(p) for p in COMMAND_ALLOWED)
        raise BuildError(
            f"`{command}` はファイルを編集しないと確かめられていない（許可しているのは Makefile のターゲットと {allowed}）。"
            "ファイルの編集を含む作業は `worker` を使うか、ユーザーに聞くこと"
        )


def build_command(args) -> dict:
    if not args.command:
        raise BuildError("command には --command が必要（複数指定できる）")
    taskdef = require_taskdef(args, "コマンドのログをタスク定義書の一時ディレクトリに置くため")
    repo = target_repo(args)
    head = repo_line(repo, args, check=True)
    cwd = os.path.normpath(os.path.join(repo, args.cwd or "."))
    if not (cwd == repo or cwd.startswith(repo + os.sep)) or not os.path.isdir(cwd):
        raise BuildError(f"--cwd は {repo} の中の既存ディレクトリを指定すること: {cwd}")
    for command in args.command:
        check_command(command, cwd)
    workdir = make_workdir(taskdef, "command")
    # 実行する行はスクリプトが組み立てて、そのまま実行させる。エージェントの中でもフック
    # （idpf-api の heavy-command-guard: GNU timeout 必須・1 回に 1 つ、rule_guard の SAFE-12）が動くので、
    # 形が違うと途中で止められてやり直しになるため（2026-10-06 ユーザー要件）。
    # timeout を Bash ツールの上限（600 秒）より短くするのは、超えると裏に回ってエージェントが待てなくなるため（SAFE-13）。
    lines = []
    for i, command in enumerate(args.command, 1):
        log = os.path.join(workdir, f"command-{i}.log")
        lines.append(
            f"{i}. `{command}`\n"
            f"   実行する行: `cd {cwd} && timeout {COMMAND_TIMEOUT} {command} > {log} 2>&1; echo \"exit=$?\"`\n"
            f"   出力の保存先: {log}"
        )
    with open(os.path.join(TEMPLATES, "command.md"), encoding="utf-8") as fh:
        body = (fh.read().replace("{CWD}", cwd).replace("{COMMANDS}", "\n".join(lines))
                .replace("{TIMEOUT}", str(COMMAND_TIMEOUT)).replace("{HOOK_DENIED}", HOOK_DENIED))
    prompt = issue(body, "command", "command", agent=GENERAL, repo=repo)
    return {"summary": f"{head}\n■ コマンド {len(args.command)} 件（実行する場所: {cwd}）",
            "workdir": workdir, "prompts": [("command", GENERAL, prompt)]}


BUILDERS = {
    "review": build_review,
    "review-design-v2": build_review_design_v2,
    "worker": build_worker,
    "research": build_research,
    "command": build_command,
}


def parse(argv):
    p = argparse.ArgumentParser(description="エージェントへの指示文を組み立てる")
    p.add_argument("kind", choices=sorted(BUILDERS))
    p.add_argument("--repo", help="修正対象の実装があるリポジトリ（worktree）。既定値なし")
    p.add_argument("--cached", action="store_true", help="git diff --cached")
    p.add_argument("--worktree", action="store_true", help="git diff")
    p.add_argument("--head", action="store_true", help="git diff HEAD")
    p.add_argument("--range", help="git diff <A..B>")
    p.add_argument("--untracked", action="store_true", help="未追跡ファイル（.claude/ 以下を除く）を差分として含める")
    p.add_argument("--design", action="store_true", help="review-design-v2: タスク定義書そのものをレビューする")
    p.add_argument("--taskdef", help="タスク定義書のパス（作業ブランチを --repo と照合する）")
    p.add_argument("--assign", help="worker: 担当の節の名前（`## 変更対象ファイル一覧` の `### Worker A` なら `Worker A`）")
    p.add_argument("--fixed-sections", nargs="+", help="worker: 改変禁止の節の名前")
    p.add_argument("--question", help="research: 調べる内容")
    p.add_argument("--no-rules", action="store_true",
                   help="research: 作業ルールの読み込みを省く（ユーザーが「ルールは不要」と明示したターンだけ使える）")
    p.add_argument("--command", action="append", help="command: 実行するコマンド（複数指定できる。書いた順に実行）")
    p.add_argument("--cwd", help="command: 実行する場所（--repo からの相対パス。既定: リポジトリ直下）")
    return p.parse_args(argv)


def agent_note(agent) -> str:
    return f"subagent_type: {agent}" if agent else "subagent_type: 指定なし（読み取りのみの調査役）"


# 🔴 2026-10-22 ユーザー決定。**指示文は `prompt` に入れず、ファイルで渡す。**
#
# なぜ: 指示文は 1 体あたり約 10,000 文字で、`prompt` に渡すにはメインのセッションが
# その全文を出力として書き出すことになる。実測（2026-10-20〜21 の GID-1474）では
# **9 体の起動に 1 体 30〜45 秒・合計約 4〜5 分**かかり、出力は 9 体で約 94,000 文字だった。
# ファイルで渡せば `prompt` は 3 行で済み、起動はツール呼び出しの時間だけになる。
PROMPT_DIR_FALLBACK = os.path.join(HOME, ".claude", "state", "delegate", "prompts")
MARKER = re.compile(r"\[delegate:([0-9a-f]{12})\]\s*$")


def prompt_path(result, stamp: str) -> str:
    """指示文を置く場所。タスクの一時ディレクトリ配下に置き、無ければ state 側に置く。

    ファイル名は発行印そのもの。`delegate_guard.py` が「渡されたパスの中身の指紋 == 発行印」で
    照合するので、**名前とファイルの中身が結びつく**（別の内容を指しても通らない）。
    """
    base = os.path.join(result["workdir"], "prompts") if result["workdir"] else PROMPT_DIR_FALLBACK
    return os.path.join(base, f"{stamp}.md")


def launch_prompt(path: str, stamp: str) -> str:
    return (
        "次のファイルを全文読み、そこに書かれた指示に従って作業してください。"
        "**この prompt には指示の本文は含まれていません。**\n"
        f"{path}\n"
        f"\n[delegate:{stamp}]\n"
    )


def main(argv=None) -> int:
    args = parse(argv)
    try:
        result = BUILDERS[args.kind](args)
    except BuildError as err:
        print(f"エラー: {err}", file=sys.stderr)
        return 1
    print(f"■ {result['summary']}")
    if result["workdir"]:
        print(f"■ 作業ディレクトリ: {result['workdir']}")

    written = []
    for label, agent, prompt in result["prompts"]:
        match = MARKER.search(prompt.rstrip())
        if not match:
            print("エラー: 発行印の無い指示文が組み立てられた（スクリプトの不具合）", file=sys.stderr)
            return 1
        stamp = match.group(1)
        path = prompt_path(result, stamp)
        if os.path.exists(path):
            print(f"エラー: {path} が既にある（上書きしない）", file=sys.stderr)
            return 1
        write(path, prompt)
        os.chmod(path, 0o444)  # うっかり上書きの防止（所有者は戻せるので、歯止めは rule_guard.py 側）
        written.append((label, agent, path))

    print(f"■ 指示文 {len(written)} 件をファイルに書き出した。"
          "**全員を背景で（run_in_background: true）起動すること**"
          "（一部だけの起動は Stop フックが、前景での起動は delegate_guard.py が止める）")
    print("■ 以下の prompt を**そのまま**渡すこと（ファイルを開いて貼り直す必要はない）")
    for label, agent, path in written:
        stamp = os.path.basename(path)[: -len(".md")]
        print(f"\n--- {label}（{agent_note(agent)}）")
        print(launch_prompt(path, stamp), end="")
    print("---")
    print("\n■ 何を指示したかは、エージェントの結果の冒頭に全文が転記される（受け入れ検査はそれと成果物を突き合わせる）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
