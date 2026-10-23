#!/usr/bin/env python3
"""`~/.claude/memory/` のルールのうち、**機械的に判定でき、かつ例外が無いもの**だけを
実行前に止める PreToolUse フック。

## 設計方針（2026-09-10 にユーザーと合意）

1. **`ask` は使わない。** 返すのは `deny` と `additionalContext` だけ。
   `deny` の `permissionDecisionReason` は Claude にのみ返り、Claude はそれを読んで書き直すか
   ユーザーに報告する（`heavy-command-guard.local.py` が同じ形で動いているのを実測して確認した）。
   **`ask` / `allow` を返したときに何が起きるかは未検証。** 検証していない挙動に依存しないため、
   この2つは使わない。「`ask` はダイアログを出す」と断定しないこと（2026-09-11 の rule-audit で
   VERIFY-02 違反として検出された。読んだ実装にあったのは `deny` だけだった）。

2. **`deny` してよいのは「ルールに、ユーザーの判断が要る例外が書かれていない」ものだけ。**
   例外があるルールをフックで止めると、**相談すべきケースを握りつぶす**。
   この基準で 7 候補から 4 件に絞った。除外したもの:
     - SAFE-10（ルート再帰 grep）: 「どうしても必要なら目的を添えて事前に確認する（許可制）」
     - META-01（`/tmp` 書き込み）: 「ユーザーが明示的に `/tmp` を指定したときだけ使う」
   この 2 件は additionalContext（実行は止めず警告のみ）で扱う。

   **2026-09-11 追記: 警告段には強制力が無いことが実測で分かった。**
   SAFE-12 を警告で配線した当日に、警告を読んだうえで 6 回破った（うち 1 回は保存側を `head -24` で
   切っている）。**そこで SAFE-12 は「ルール本文の例外を機械が当てられる形に書き換えて」deny へ移した** —
   「出力量が確実に小さいと分かっている場合」という Claude の主観を、「パイプラインの先頭が許可列挙に
   あるか」に変えた。**ルールを分かりやすくするのではなく、判定をフックへ移せる形にするのが効く。**
   SAFE-10 / META-01 に同じ書き換えを広げるかは未決（2026-09-11 時点）。

3. **ルールの文言をコピーしない。** 条件（正規表現）だけをここに持ち、説明文は
   `~/.claude/memory/` の該当ルールの `要約` を実行時に読んで返す。
   コピーを持つと同期が切れる（2026-09-10 に v1 ルーブリック参照と早見表の prettier 前提で実際に発生）。

4. **理由文には必ず「ユーザーの明示指示なら報告して相談する」を添える。**
   deny を「できません」で終わらせると、それ自体が握りつぶしになる。
"""

import json
import os
import re
import sys

MEMORY_DIR = os.path.join(os.path.expanduser("~"), ".claude", "memory")

# ルール ID → 定義ファイルの対応表は**持たない**。
# 2026-09-11 にルールファイルを場面別へ再編した際、この対応表が丸ごと陳腐化した。
# ID は主題に紐づいてファイル名から独立しているので、表を持つと再編のたびに古くなる
# （「コピーを持つと同期が切れる」の同じ失敗。設計方針 3 と同根）。
# 代わりに `feedback_*.md` を走査して `## <ID>:` を持つファイルを実行時に見つける。

FOLLOWUP = (
    "\nユーザーが明示的にこの操作を指示していた場合は、黙って諦めずに"
    "「フックに止められた。ルール上はこうだが、指示なのでどうするか」と報告して相談すること。"
)


def locate(rule_id: str):
    """`## <rule_id>:` を持つファイルを探し、(ファイル名, 要約) を返す。

    対応表を持たずに毎回走査する。ルールを別ファイルへ移しても追従するため。
    ファイル数は 10 未満・合計 100KB 程度なので、走査コストは無視できる。
    """
    try:
        names = sorted(
            f for f in os.listdir(MEMORY_DIR)
            if f.startswith("feedback_") and f.endswith(".md")
        )
    except OSError:
        return "", ""
    for name in names:
        try:
            with open(os.path.join(MEMORY_DIR, name), encoding="utf-8") as fh:
                in_rule = False
                for line in fh:
                    if line.startswith("## "):
                        if in_rule:
                            break  # 要約が無いまま次のルールへ来た
                        in_rule = line.startswith(f"## {rule_id}:")
                        continue
                    if in_rule and line.startswith("- **要約**:"):
                        return name, line.split(":", 1)[1].strip()
        except OSError:
            continue
    return "", ""


def summary_of(rule_id: str) -> str:
    return locate(rule_id)[1] or "(要約を取得できませんでした)"


def deny(rule_id: str, detail: str) -> None:
    name, summary = locate(rule_id)
    reason = (
        f"[{rule_id}] {summary or '(要約を取得できませんでした)'}\n"
        f"検出: {detail}\n"
        f"定義: ~/.claude/memory/{name or '(ファイル不明)'} の `## {rule_id}`"
        f"{FOLLOWUP}"
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )
    sys.exit(0)


# --- SAFE-01: git は allowlist（read-only）以外すべてユーザー -------------------
# ルール本文の allowlist と、要許可（checkout / switch）を反映。
# checkout / switch は「目的を伝えて同意を得れば Claude が実行してよい」ので **止めない**。
GIT_READONLY = {
    "status", "diff", "log", "show", "blame",
    "ls-files", "rev-parse",

    # 共通の祖先のコミットを表示するだけ（2026-10-16 ユーザー承認）。
    # 「なぜこの PR に別チケットの変更が入っているのか」の調査で使う
    "merge-base",
}
# `config` は 2026-10-05 に `GIT_READONLY` から外した（ユーザー承認）。
# サブコマンド名しか見ていなかったので、**`git config user.name "x"` のような書き込みも素通りしていた**。
# 読み取り（`--get` / `--list` / 値を指定しない形）だけ通し、値を書く形は deny する。
GIT_CONFIG_WRITE_FLAG = re.compile(
    r"(?<![\w-])(?:--add|--unset(?:-all)?|--replace-all|--rename-section"
    r"|--remove-section|--edit|-e)(?=\s|$)"
)
GIT_CONFIG_READ_FLAG = re.compile(
    r"(?<![\w-])(?:--get(?:-all|-regexp|-urlmatch)?|--list|-l)(?=\s|$)"
)
GIT_ALLOWED_WITH_PERMISSION = {"checkout", "switch"}

# `git branch` は**表示だけなら通す**（2026-10-16 ユーザー承認）。
# それまで `--list` を含む形しか通しておらず、`git branch` / `-a` / `--show-current` のような
# 同じ「表示するだけ」の形を止めていた。
# 止めるのは、ブランチを**消す・改名する・作る・上流を書き換える**形。
GIT_BRANCH_WRITE_FLAG = re.compile(
    r"(?<![\w-])(?:-d|-D|--delete|-m|-M|--move|-c|-C|--copy|-u|--set-upstream-to"
    r"|--unset-upstream|--edit-description|-f|--force)(?=\s|=|$)"
)
# 値を取る表示系のフラグ。この直後の語は「作成するブランチ名」ではない
GIT_BRANCH_VALUE_FLAG = {
    "--list", "--contains", "--no-contains", "--merged", "--no-merged",
    "--points-at", "--sort", "--format", "--color", "--column",
}

# `git remote` は**表示だけ通す**（2026-10-16 ユーザー承認。本文は元から `git remote -v` に限定）。
# `add` / `remove` / `rename` / `set-url` は `.git/config` を書き換え、`prune` は追跡ブランチを削除する。
GIT_REMOTE_WRITE_SUB = {"add", "remove", "rm", "rename", "set-url", "set-head", "set-branches", "prune", "update"}
# `git fetch` は read-only ではない（`.git/` のリモート追跡ブランチ・`FETCH_HEAD` を書き換える）。
# それでも通すのは、**FLOW-19 が `git log origin/main --not HEAD` で main の先行を見ることを要求していて、
# `origin/main` が古いままだとその判定が成立しない**ため（2026-10-02 ユーザー承認）。
# ただし **`--prune` 系は除外** — ローカルのリモート追跡ブランチを削除するので、取り返しがつかない側に入る。
GIT_FETCH_PRUNE = re.compile(r"(?<![\w-])(?:--prune\S*|-p)(?=\s|$)")
# 実際に git が「実行される」形だけを見る。断片の**先頭**に来ているものだけが対象。
# `chk DENY 'git restore foo.go'` や `echo "git add"` のように、引数・文字列として
# git が現れるだけのものを止めないため（SAFE-05 で同じ誤検知を直したのと同じ考え方）。
GIT_AT_HEAD = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+|sudo\s+|time\s+|command\s+|nohup\s+)*"
    r"git\s+(?:-[^\s]+\s+)*([a-z][a-z0-9-]*)"
)
# コマンド置換・サブシェルの中も実行される
SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|\n]|\$\(|`|\(|\{")


def check_git_config(segment: str) -> None:
    """`git config` のうち、設定を書き換える形だけを止める。

    判定は 2 つ。
      1. 書き込み専用のフラグ（`--add` / `--unset` / `--edit` など）があれば deny
      2. フラグを除いた引数が **2 つ以上**あれば deny（`<name> <value>` ＝ 値の代入）
         `git config user.name`（1 つ）は読み取りなので通す
    """
    if GIT_CONFIG_WRITE_FLAG.search(segment):
        deny("SAFE-01", "`git config` の書き込み系フラグ（設定を書き換える）")
    if GIT_CONFIG_READ_FLAG.search(segment):
        return
    # `git` と `config` を落とし、オプションでないトークンだけ数える
    tokens = [t for t in segment.split() if not t.startswith("-")]
    try:
        operands = tokens[tokens.index("config") + 1:]
    except ValueError:
        return
    if len(operands) >= 2:
        deny(
            "SAFE-01",
            f"`git config {operands[0]} {operands[1]}` は設定を書き換える。"
            "読み取りなら値を付けずに `git config <name>` か `git config --get <name>` を使うこと",
        )


def check_git(cmd: str) -> None:
    for segment in SEGMENT_SPLIT.split(cmd):
        match = GIT_AT_HEAD.match(segment)
        if not match:
            continue
        sub = match.group(1)
        if sub == "fetch":
            if GIT_FETCH_PRUNE.search(segment):
                deny(
                    "SAFE-01",
                    "`git fetch --prune` はローカルのリモート追跡ブランチを削除する。"
                    "`--prune` を外した `git fetch` なら実行してよい",
                )
            continue
        if sub == "config":
            check_git_config(segment)
            continue
        if sub in GIT_READONLY or sub in GIT_ALLOWED_WITH_PERMISSION:
            continue
        if sub == "stash" and re.match(r"\s*git\s+stash\s+list", segment):
            continue
        if sub == "branch":
            check_git_branch(segment)
            continue
        if sub == "remote":
            check_git_remote(segment)
            continue
        deny("SAFE-01", f"`git {sub}` は read-only の allowlist に無い")


def _git_operands(segment: str, sub: str) -> list:
    """`git <sub>` より後ろの、フラグでない語を返す（`--opt=値` の値は含めない）。"""
    tokens = segment.split()
    try:
        rest = tokens[tokens.index(sub) + 1:]
    except ValueError:
        return []
    operands, skip = [], False
    for token in rest:
        if skip:
            skip = False
            continue
        if token.startswith("-"):
            if token in GIT_BRANCH_VALUE_FLAG:
                skip = True  # 次の語はこのフラグの値
            continue
        operands.append(token)
    return operands


def check_git_branch(segment: str) -> None:
    """`git branch` は表示だけ通す。消す・改名する・作る・上流を書き換える形は止める。"""
    if GIT_BRANCH_WRITE_FLAG.search(segment):
        deny(
            "SAFE-01",
            "`git branch` の変更系（削除 `-d`/`-D`・改名 `-m`/`-M`・複製 `-c`/`-C`・"
            "上流の書き換え `-u`/`--set-upstream-to`）。表示だけなら `git branch` / `-a` / "
            "`--list <pattern>` / `--show-current` を使うこと",
        )
    operands = _git_operands(segment, "branch")
    if operands:
        deny(
            "SAFE-01",
            f"`git branch {operands[0]}` は**ブランチを作る**（作成はユーザーが行う）。"
            "表示したいなら `git branch --list <pattern>` を使うこと",
        )


def check_git_remote(segment: str) -> None:
    """`git remote` は表示だけ通す（`-v` / `show` / `get-url`）。"""
    operands = _git_operands(segment, "remote")
    if operands and operands[0] in GIT_REMOTE_WRITE_SUB:
        deny(
            "SAFE-01",
            f"`git remote {operands[0]}` はリモートの設定を書き換える"
            "（`prune` は追跡ブランチを削除する）。表示なら `git remote -v` / `show` / `get-url`",
        )


# --- SAFE-05: スクリプトでのファイル書き換えは一律禁止（例外なしと本文に明記）------
# 誤検知で正当な読み取りを止めないよう、**書き換えが確実な形だけ**に絞る。
SCRIPT_EDIT = [
    (re.compile(r"(?<![\w./-])sed\s+(?:-[^\s]*\s+)*-[a-zA-Z]*i"), "sed -i によるファイル書き換え"),
    (re.compile(r"(?<![\w./-])perl\s+(?:-[^\s]*\s+)*-[a-zA-Z]*i"), "perl -i によるファイル書き換え"),
    (re.compile(r"(?<![\w./-])(?:python3?|ruby)\b[^\n]*\.(?:write|writelines)\("), "スクリプトからのファイル書き込み"),
    # 書き込みモードが明示されている open だけを見る。読み取りの open(...) は対象外。
    (re.compile(r"(?<![\w./-])python3?\b[^\n]*open\([^)]*,[^)]*['\"][wax]"), "python の open(..., 'w'/'a'/'x') によるファイル書き込み"),
    # ヒアドキュメントでの上書き。auto mode が「heredoc で編集せよ」と案内してくるので必ず要る。
    # 消費側を cat / tee に限定する。`python3 - > out.txt <<PY`（解析結果の保存）は書き換えではないので
    # 対象外にしないと、SAFE-12 が求める「出力をファイルに保存してから読む」を潰してしまう。
    (re.compile(r"(?<![\w./-])(?:cat\s*>>?\s*\S+|tee\s+(?:-a\s+)?\S+)[^\n]*<<"), "ヒアドキュメントによるファイル上書き"),
]

# `echo "sed -i ..."` のように、コマンドではなく**文字列を表示するだけ**のものを判定から外す。
# heavy-command-guard.local.py の SAFE_HEAD と同じ考え方。
DISPLAY_ONLY_HEAD = re.compile(r"^\s*(echo|printf|cat|grep|rg|jq|less|head|tail|wc)\b")


HEREDOC_WRITE = SCRIPT_EDIT[-1][0]


# --- SAFE-12: `| head` / `| tail` はパイプラインの先頭が許可列挙のときだけ ----------
# 2026-09-11 に警告段から deny へ移した。ルール本文の `判定` を「出力量が確実に小さいか」という
# Claude の主観から「許可列挙にあるか」に書き換えたことで、機械的に当てられるようになったため。
#
# **判定するのはパイプラインの先頭**（出力を生み出す側）。
# `make test | grep FAIL | head -5` は、直前が grep でも先頭が make なので違反。
#
# 列挙の基準は「出力量」ではなく「**やり直しのコストが誰に出るか**」。
# すでにある状態を読むだけで、もう一度打っても副作用が無いものだけを入れる。
# 2026-10-16 にユーザー承認で拡大（`timeout` 接頭辞・読み取りの git / gh / docker・
# バージョン表示）。`make` / `go build` / `go test` / `npm` / `pnpm` / `docker compose up` /
# `terraform` / `curl` / `aws` と、`gh pr create` のように副作用が残るものは入れない。
LOW_COST_ORIGIN = re.compile(
    # 接頭辞は読み飛ばす。**`timeout <秒>` は SAFE-13 が要求している形**なので必ず入れる
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+|sudo\s+|time\s+|command\s+"
    r"|timeout\s+[0-9]+[smhd]?\s+|nohup\s+)*"
    r"(?:"
    r"cat|grep|rg|sed|awk|sort|uniq|jq|wc|nl|cut|tr|column|diff|head|tail|od|xxd|strings"
    r"|ls|find|pwd|date|env|echo|printf|seq|df|du|ps|which|type"
    r"|stat|file|realpath|readlink|basename|dirname|tree"
    # 読み取りの git。`git fetch` は 2026-10-02 / 2026-10-16 にユーザー承認（SAFE-01 と同じ範囲）
    r"|git\s+(?:status|log|diff|show|branch|rev-parse|ls-files|blame"
    r"|merge-base|remote|config|describe|show-ref|rev-list|cat-file|stash\s+list|fetch)"
    # 出力を読むだけの gh。`gh pr create` / `merge` は入れない（やり直すと PR が増える）
    r"|gh\s+(?:pr|issue|run|release|repo|workflow)\s+(?:list|view|diff|checks|status)"
    r"|gh\s+auth\s+status"
    # `gh api` は既定が GET。書き込みメソッドを明示しているものは通さない
    r"|gh\s+api(?![^|;&\n]*(?:-X|--method)\s*(?:POST|PUT|PATCH|DELETE))"
    # 状態を表示するだけの docker（`up` / `build` / `exec` は入れない）
    r"|docker\s+(?:ps|images|version|compose\s+(?:ps|version|config))"
    # バージョン・設定の表示だけ。`go build` / `go test` は入れない
    r"|go\s+(?:version|env)\b|node\s+--version|python3?\s+--version"
    r")\b"
)
PIPE_TRUNC_STAGE = re.compile(r"^\s*(?:head|tail)\b")

# 文の区切りと**コマンド置換の開き**で切る。`|` では切らない（パイプラインの段が壊れる）。
# `$(` を切らないと `L=$(grep -n foo bar | head -1)` の先頭が `L=$(grep` ではなく
# 代入扱いにならず止まる。中は独立したパイプラインとして判定する。
PIPELINE_SPLIT = re.compile(r"&&|\|\||[;\n]|\$\(|`")


def check_output_trunc(cmd: str) -> None:
    for command in PIPELINE_SPLIT.split(cmd):
        stages = command.split("|")
        if len(stages) < 2:
            continue
        if not any(PIPE_TRUNC_STAGE.search(s) for s in stages[1:]):
            continue
        if LOW_COST_ORIGIN.search(stages[0]):
            continue
        origin = stages[0].strip()[:60]
        deny(
            "SAFE-12",
            f"パイプラインの先頭 `{origin}` が許可列挙に無いのに `| head` / `| tail` で切っている。"
            "`<cmd> > .claude/tmp/{task}/out.log 2>&1; echo \"exit=$?\"` で保存してから読むこと",
        )


def check_script_edit(cmd: str) -> None:
    for segment in re.split(r"&&|\|\||;|\n|\|", cmd):
        # `cat > file <<EOF` は DISPLAY_ONLY_HEAD（cat 始まり）に当たってしまうので、
        # 表示扱いで飛ばす前にヒアドキュメント書き込みかどうかを先に見る。
        if DISPLAY_ONLY_HEAD.search(segment) and not HEREDOC_WRITE.search(segment):
            continue
        for pattern, detail in SCRIPT_EDIT:
            if pattern.search(segment):
                deny("SAFE-05", detail)


# --- TECH-02: コード生成系は Claude が実行しない（例外なし）----------------------
CODEGEN = [
    (re.compile(r"make\s+(?:-C\s+\S+\s+)?openapi_generate"), "OpenAPI コード生成"),
    (re.compile(r"(?<![\w./-])(?:gomockhandler|mockgen)\b"), "モック再生成"),
    (re.compile(r"go\s+run\s+\S*cmd/migration_apply"), "スキーマ適用"),
    (re.compile(r"go\s+run\s+\S*cmd/generate_models"), "データモデル生成"),
]


def check_codegen(cmd: str) -> None:
    for pattern, detail in CODEGEN:
        if pattern.search(cmd):
            deny("TECH-02", f"{detail}（ユーザーに実行を依頼する）")


# --- FLOW-22: 委任プロンプトにルールの参照が無ければ止める（例外なし）-------------
# 2026-09-11 に実測: ルールを注入している UserPromptSubmit / SessionStart フックは
# **メインセッションにしか発火しない**。サブエージェント8体のトランスクリプトを全件調べたところ、
# 索引・Tier 0・ルール本文の出現は 0 件だった。つまり委任先は、ツール入力だけで機械判定できる数件を除き
# **ルールを何も知らない状態で動く**。実際にワーカーが確定要件を保留して報告する事故が起きた。
#
# ここで見るのは FLOW-22 の8点のうち、**機械で当てられる 2 点だけ**:
#
#   (a) 実装の委任なら、「無断改変として扱う」の宣言があるか。
#       実装の委任かどうかは **プロンプトがタスク定義書（`.claude/tasks/`）を指しているか**で判定する。
#       read-only の調査役・レビュアーは定義書を指さないことが多く、そこまで縛ると誤検知になるため。
#
#   (b) `design-review-v2` の判定者への委任なら、`~/.claude/memory/MEMORY.md` を読ませているか。
#       判定者かどうかは **プロンプトがルーブリック（`~/.claude/notes/design-review-v2/`）を指しているか**で判定する。
#       これが捕まえるのは「**skill のテンプレートから MEMORY.md の1行だけ落とした**」場合（FLOW-16 が禁じる改変）。
#       **ルーブリックすら渡していない自作のレビュー依頼は、design-review と判別できないので捕まえられない。**
#
# 2026-09-14 に削除した条件: 「ルール本文（`feedback_*.md`）を読ませる指示があるか」。
#   全委任に掛けていたため、**「テストを実行して失敗一覧を返して」のような委任まで deny していた**。
#   通すには 197,071 バイト（9ファイル）を読ませる必要があり、釣り合わない。
#   そもそも deny 段（SAFE-01 / SAFE-05 / SAFE-12 / TECH-02 / META-08）は
#   **サブエージェントでもこのフックが機械的に止める**ので、読ませなくても安全は担保される。
#   ルール本文を読ませるのは `design-review-v2` の判定者だけ（FLOW-22 の1点目）。
#   ただし「その委任が design-review-v2 か」は文字列では当てられないので、deny にはしない。
#
# 残り（`## 読むもの` の全項目・担当範囲・改変禁止の節指定・報告8項目の中身）も、
# **文字列では正しさを当てられない**ので deny にしない。書いたかどうかは自分で担保する。
#
# 2026-10-07: `delegate` skill の指示文（末尾に発行印 `[delegate:<12桁>]`）は、発行の記録の種類で
#   実装の委任かどうかを決める。`worker` だけが実装の委任。レビュー・調査・コマンドの実行役の指示文は、
#   補助資料や結果の置き場所として `.claude/tasks/` のパスを含むことがあり、文字列で判定すると
#   「宣言の無い実装の委任」として止めてしまっていた（GID-1859 のセッションで発覚）。
#   発行印の無い指示文は、これまでどおり文字列で判定する（そもそも delegate_guard.py が止める）。
TASKDEF_REF = re.compile(r"\.claude/tasks/")
# delegate の worker テンプレートは「無断改変として扱います。」と書く（2026-10-07 に「扱う」だけだった一致を広げた）
UNREPORTED_DECL = re.compile(r"無断改変として扱(?:う|います)")
RUBRIC_REF = re.compile(r"\.claude/notes/design-review-v2/")
MEMORY_REF = re.compile(r"(?:~|\$HOME|/home/[^/\s]+)?/?\.claude/memory/MEMORY\.md")
DELEGATE_STAMP = re.compile(r"\[delegate:([0-9a-f]{12})\]\s*$")


def delegate_kind(prompt: str):
    """`delegate` skill が発行した指示文なら、その種類（`worker` など）を返す。それ以外は None。"""
    match = DELEGATE_STAMP.search(prompt.rstrip())
    if not match:
        return None
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import delegate_guard

        return (delegate_guard.issued_records().get(match.group(1)) or {}).get("kind")
    except Exception:  # noqa: BLE001 — 読めなければ文字列での判定に戻る
        return None


def is_impl_delegation(prompt: str) -> bool:
    kind = delegate_kind(prompt)
    if kind:
        return kind == "worker"
    return bool(TASKDEF_REF.search(prompt))


def check_delegation(tool_input: dict) -> None:
    """実装の委任に無断改変の宣言があるか、design-review の判定者にルールを渡しているかを見る。"""
    prompt = tool_input.get("prompt") or ""
    if not prompt.strip():
        return
    if is_impl_delegation(prompt) and not UNREPORTED_DECL.search(prompt):
        deny(
            "FLOW-22",
            "実装の委任（タスク定義書を指している）なのに、報告に"
            "「申告しなかった差異は無断改変として扱う」の宣言が無い"
            "（宣言が無いとワーカーに申告の動機が働かず、定義書に無い実装が黙って混ざる）",
        )
    if RUBRIC_REF.search(prompt) and not MEMORY_REF.search(prompt):
        deny(
            "FLOW-22",
            "`design-review-v2` の判定者への委任（ルーブリックを指している）なのに、"
            "`~/.claude/memory/MEMORY.md` を読ませる指示が無い"
            "（skill のテンプレートには入っている。落としたなら FLOW-16 のテンプレ改変にも当たる）",
        )


# --- META-08: v1 ルーブリックへの追記・削除の禁止（例外なし）---------------------
V1_FILES = ("design_review_rubric.md", "design_philosophy.md")
V1_WRITE_CMD = re.compile(r">>?|(?<![\w./-])(?:rm|mv|cp|tee|truncate|install)\b")


def check_v1_paths(text: str, is_command: bool) -> None:
    """v1 ルーブリック 2 ファイルへの書き込み・削除を止める。

    ファイル名だけで見る（`~/` / `$HOME` / 相対パスのどれでも効かせるため）。
    読み取り（`cat` / `grep` など）は対象外なので、書き換え系の語が同じコマンドに
    出ているときだけ止める。
    """
    for target in V1_FILES:
        if target not in text:
            continue
        if is_command and not V1_WRITE_CMD.search(text):
            continue  # 読み取りは対象外
        deny("META-08", f"{target} への書き込み・削除")


# --- META-01: `.claude/tmp/` の持ち主をタスク定義書で判定する ------------------------
# 2026-09-14 追加。ルール本文（「不要になったら自分で消す」）は 2026-08-26 から正しく書かれていたが、
# 3日にわたって守らなかった。**文言では直らない**ことは SAFE-12 で確認済み（警告を配線した当日に6回破った）。
# そこで掃除を「思い出したらやること」から「**次の作業を始める前提条件**」に変えた。
#
# 2026-10-05 に判定を「日付」から「タスク定義書の宣言」に変えた。日付で判定すると、ブランチを
# 切り替えて並行している作業の一時ファイルまで、日付をまたいだだけで残骸扱いになり、新しい作業を始められなかった。
# 持ち主は、タスク定義書の `## ステータス` にある `一時ディレクトリ:` の行で宣言する（リンクにしない）。
#   - 新しく作るディレクトリが、未完了（done/ 以外）の定義書で宣言されていなければ止める。
#     タスク定義書を作らない作業では一時ディレクトリを作らせない（2026-10-05 ユーザー決定）。
#   - 既存のディレクトリのうち、未完了の定義書で宣言されていないもの
#     （done/ に移ったタスクのもの・持ち主不明のもの）が残っていれば止める。
#
# 判定するのは「**新しい作業ディレクトリを作ろうとしたか**」。既存ディレクトリへの追記は止めない
# （作業の途中で詰まると、掃除ではなく作業そのものが壊れるため）。
TMP_DIR_PATH = re.compile(r"(?:^|[\s'\"=])((?:[^\s'\"=]*/)?\.claude/tmp)/([^/\s'\"]+)/")
TASKDEF_TMP_LINE = re.compile(r"^\s*-?\s*一時ディレクトリ[:：](.*)$", re.MULTILINE)
TASKDEF_TMP_NAME = re.compile(r"`(?:\./)?\.claude/tmp/([^/`\s]+)/?`")
# `~/.claude/tasks/` の定義書（リポジトリをまたぐ作業）も、プロジェクトの `.claude/tmp/` を持つことがある。
# 2026-10-05 に、ここを見ていなかったため持ち主のいるディレクトリを残骸と判定し、別セッションの作業データ（529 ファイル）を消させた。
# プロジェクトのパスを付けた宣言（`~/work/.../idpf-api/.claude/tmp/<名前>/`）は、そのプロジェクトの `.claude/tmp` とだけ照合する。
# パスの無い宣言はどのプロジェクトか決まらないので、名前だけで持ち主ありとみなす（消させない側に倒す）。
GLOBAL_TASKS_ROOT = os.path.join(os.path.expanduser("~"), ".claude", "tasks")
TASKDEF_TMP_PATH = re.compile(r"`([^`\s]*?)\.claude/tmp/([^/`\s]+)/?`")
# design-review-v2 は実行中だけ `design-review/<日時>/` を作り、最後に自分で消す（SKILL.md Step 0 / 7）。
# delegate skill の作業ファイルは、タスク定義書が宣言した一時ディレクトリの中（`<名前>/delegate/`）に置くので対象外にしない
# （2026-10-06 ユーザー要件「tmp 以下はセッションごとに持ってほしい」）。
TMP_EXEMPT = ("design-review",)


# ワイルドカードを含むパスは判定しない（2026-10-23）。`ls -d */.claude/tmp/*/…` の
# ような一覧で、`*` という名前のディレクトリを宣言した定義書が無いと判定して止めていた。
TMP_GLOB = re.compile(r"[*?\[\]]")


def _project_root(cwd: str) -> str:
    """`.claude/tasks` を持つ、cwd から最も近い上位ディレクトリを返す。無ければ空文字。

    2026-10-23 に判明: フックが受け取る cwd は、`cd` を含むコマンドを実行した後
    そのディレクトリに残る。`.claude/tmp/<名前>/` という書き方は「このプロジェクトの」
    という意味なので、cwd をそのまま基準にすると
    `<サブディレクトリ>/.claude/tmp` という存在しない場所を見てしまい、
    `<サブディレクトリ>/.claude/tasks` にも宣言が無いので
    「宣言している定義書が無い」と、原因と無関係な理由で止まっていた。
    """
    path = os.path.realpath(cwd or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(path, ".claude", "tasks")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return ""
        path = parent


def _real_owner(name: str) -> bool:
    """テンプレートのプレースホルダを持ち主として数えない（2026-10-23）。

    `~/.claude/tasks/_TEMPLATE*.md` の宣言行から `{チケット番号}-{内容}` を拾い、
    実在する持ち主として owners に入っていた。
    """
    return "{" not in name and "}" not in name


def _abs(path: str, cwd: str) -> str:
    """コマンド文字列から拾った相対パスを、ツールを呼んだ側の cwd で解決する。

    フックプロセスの cwd は Claude の作業ディレクトリと一致しない。`cd x && …` の
    `cd` も PreToolUse の時点では効いていないので、os.path.isdir() などをそのまま
    呼ぶと別の場所を見る。2026-10-07 に `.claude/tmp/GID-1857/` への書き込みが
    「宣言が無い」と誤って止められたのはこれが原因（cwd が apps/api だったため
    apps/api/.claude/tasks を探していた）。
    """
    if os.path.isabs(path):
        return path
    return os.path.join(cwd or os.getcwd(), path)


def _active_tmp_lines(tasks_root: str) -> list:
    """未完了（done/ 以外）のタスク定義書にある「一時ディレクトリ:」の行を返す。"""
    lines = []
    for root, dirs, files in os.walk(tasks_root):
        if os.path.relpath(root, tasks_root).split(os.sep)[0] == "done":
            dirs[:] = []
            continue
        for f in files:
            if not f.endswith(".md"):
                continue
            try:
                with open(os.path.join(root, f), encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                continue
            lines.extend(TASKDEF_TMP_LINE.findall(text))
    return lines


def _active_tmp_owners(tasks_root: str, tmp_root: str) -> set:
    """`tmp_root` の中で、未完了のタスク定義書が宣言している一時ディレクトリ名を返す。"""
    owners = set()
    for line in _active_tmp_lines(tasks_root):
        owners.update(n for n in TASKDEF_TMP_NAME.findall(line) if _real_owner(n))
    if os.path.realpath(tasks_root) == os.path.realpath(GLOBAL_TASKS_ROOT):
        return owners
    target_root = os.path.realpath(tmp_root)
    for line in _active_tmp_lines(GLOBAL_TASKS_ROOT):
        for prefix, name in TASKDEF_TMP_PATH.findall(line):
            if not _real_owner(name):
                continue
            if prefix in ("", "./"):
                owners.add(name)
            elif os.path.realpath(os.path.expanduser(prefix + ".claude/tmp")) == target_root:
                owners.add(name)
    return owners


MV_TO_DONE = re.compile(
    r"\bmv\b[^\n;&|]*?((?:[^\s'\"]*/)?\.claude/tasks)/(?:[^\s'\"]+/)?done/"
)


def check_done_leftover_tmp(cmd: str, cwd: str) -> None:
    """`done/` へ移すとき、同名の一時ディレクトリが残っていたら知らせる。

    META-01 の「不要になったら自分で消す」は、done 化がまさにその瞬間なのに
    3 回続けて守れなかった（2026-08-26 の `/tmp` 放置 ／ 2026-09-14 の
    feedback-inventory を 3 日放置 ／ 2026-10-13 に GID-1857 の 28MB を 1 週間放置）。
    毎回ユーザーが `.claude/tmp/` を自分で見て見つけている。

    deny にしないのは、done 化は「確認なしで即実行する合図」（FLOW-08）で、
    止めると今度はそちらのルールを破ることになるため。消すのは Claude の判断。
    """
    for match in MV_TO_DONE.finditer(cmd):
        tasks_root = _abs(match.group(1), cwd)
        tmp_root = os.path.join(os.path.dirname(tasks_root), "tmp")
        if not os.path.isdir(tmp_root):
            continue
        owners = _active_tmp_owners(tasks_root, tmp_root)
        try:
            names = sorted(os.listdir(tmp_root))
        except OSError:
            continue
        leftovers = [
            n for n in names
            if os.path.isdir(os.path.join(tmp_root, n))
            and n not in owners
            and n not in TMP_EXEMPT
        ]
        if leftovers:
            warn([(
                "META-01",
                f"`{tmp_root}/` に、未完了のタスク定義書が宣言していないディレクトリが残っている: "
                f"{', '.join(leftovers)}\n"
                f"  done 化はこれを消す瞬間。消す場合はユーザーに消してよいか聞く"
                f"（`rm` はユーザーがそのターンで削除に触れていないと deny される・SAFE-09）。"
                f"残す場合は「何を・なぜ残しているか」をユーザーに伝える",
            )])
        return


def check_tmp_housekeeping(text: str, cwd: str) -> None:
    """`.claude/tmp/<新しい名前>/` を作ろうとしたとき、持ち主の宣言と残骸を確かめる。"""
    for match in TMP_DIR_PATH.finditer(text):
        shown, target = match.group(1), match.group(2)
        if TMP_GLOB.search(shown) or TMP_GLOB.search(target):
            continue  # ワイルドカードは特定のディレクトリを指さない（一覧・検索）
        if shown in (".claude/tmp", "./.claude/tmp"):
            # プロジェクトを指定しない書き方は「このプロジェクトの」という意味なので、
            # cwd ではなく `.claude/tasks` を持つ上位ディレクトリを基準にする。
            root = _project_root(cwd)
            if not root:
                continue  # プロジェクトのルートが分からない。判定材料が無いので止めない
            tmp_root = os.path.join(root, ".claude", "tmp")
        else:
            tmp_root = _abs(shown, cwd)
        if target in TMP_EXEMPT or os.path.isdir(os.path.join(tmp_root, target)):
            continue  # skill が管理するもの / 既存ディレクトリへの追記は対象外
        tasks_root = os.path.join(os.path.dirname(tmp_root), "tasks")
        # `.claude/tasks` が無い場所は素通りさせない。タスク定義書が 1 つも無い
        # プロジェクトで一時ディレクトリを作るのは、META-01 が禁じている側。
        # 「どこを見ればよいか分からない」場合の逃げ道は、上の `_project_root` が
        # 空を返したときだけに限る。
        # どこを見て判定したかを必ず添える。2026-10-23 まで、解決先がずれていても
        # 「宣言が無い」としか出なかったため、原因の切り分けができなかった。
        where = f"（判定した場所: `{tmp_root}/` ／ フックが見ている cwd: `{cwd or '(無し)'}`）"
        owners = _active_tmp_owners(tasks_root, tmp_root)
        if target not in owners:
            deny(
                "META-01",
                f"`{shown}/{target}/` を宣言している未完了のタスク定義書が無い。{where}\n"
                f"先にタスク定義書の `## ステータス` に「一時ディレクトリ: `.claude/tmp/{target}/`」の行を書くこと（リンクにしない。"
                "`~/.claude/tasks/` の定義書なら `~/<プロジェクトのパス>/.claude/tmp/<名前>/` のようにプロジェクトのパスを付ける）。"
                "タスク定義書が無い作業なら、なぜ一時ファイルが必要かを説明して、タスク定義書の作成の許可をユーザーに得る。\n"
                "判定した場所が意図と違うなら、コマンドのパスを絶対パスで書き直して実行し直すこと",
            )
        try:
            names = sorted(os.listdir(tmp_root))
        except OSError:
            names = []
        orphans = [
            n for n in names
            if os.path.isdir(os.path.join(tmp_root, n)) and n not in owners and n not in TMP_EXEMPT
        ]
        if orphans:
            deny(
                "META-01",
                f"`{shown}/` に、未完了のタスク定義書（プロジェクトの `.claude/tasks/` と `~/.claude/tasks/`）で宣言されていないディレクトリがある: {' / '.join(orphans)}{where}\n"
                "完了済みタスクのもの、または持ち主の分からないもの。新しい作業ディレクトリを作る前に消すこと。"
                "消さずに残す必要があるなら、何を・なぜ残すのかをユーザーに伝えて判断を仰ぐ",
            )


# --- SAFE-09: ユーザーが削除に触れていないターンの `rm` を止める ------------------
# 2026-09-17 追加。**別セッションのワーカーがエージェント経由で `rm` を実行した**のが発端。
# SAFE-09 は「取り返しがつかないものは実行しない」と定めているが、**文言だけで歯止めが無かった**。
# サブエージェントにはルール本文が届かない（FLOW-22）ので、ワーカーには何の縛りも無かった。
#
# 例外（ユーザーの事前許可）は `rm_grant.py`（UserPromptSubmit）が記録する。
# 🔴 **Claude は許可を書けない。** 書けるのはユーザーの発言だけ（自己例外化の禁止・SAFE-07）。
#
# 許可が要らないもの ＝ **ルールが削除を命じている場所**（SAFE-09 の軸0）:
#   - `.claude/tmp/` 配下（META-01「不要になったら自分で消す」）
#   - `~/.claude/state/` 配下（フックが自分で作った記録）
RM_AT_HEAD = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+|sudo\s+|time\s+|command\s+|nohup\s+|xargs\s+(?:-[^\s]+\s+)*)*"
    r"(rm|rmdir|unlink)\b"
)
FIND_DELETE = re.compile(r"(?<![\w./-])find\b[^|;&\n]*\s-delete\b")
SELF_OWNED = ("/.claude/tmp/", ".claude/tmp/", "/.claude/state/", ".claude/state/")
RM_GRANT_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", "rm_grant")


def _rm_targets(segment: str) -> list:
    """削除対象に見えるトークン（オプションでないもの）を返す。"""
    tokens = segment.split()
    return [t for t in tokens[1:] if not t.startswith("-")]


def _all_self_owned(targets: list) -> bool:
    return bool(targets) and all(
        any(marker in t for marker in SELF_OWNED) for t in targets
    )


def _rm_granted(session_id: str) -> bool:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")
    return os.path.isfile(os.path.join(RM_GRANT_DIR, f"{safe}.json"))


def check_rm(cmd: str, data: dict) -> None:
    for segment in SEGMENT_SPLIT.split(cmd):
        if DISPLAY_ONLY_HEAD.search(segment):
            continue  # `echo "rm -rf ..."` のような表示だけのもの
        match = RM_AT_HEAD.match(segment)
        found = match.group(1) if match else ("find ... -delete" if FIND_DELETE.search(segment) else "")
        if not found:
            continue
        if match and _all_self_owned(_rm_targets(segment)):
            continue  # ルールが削除を命じている場所（軸0）
        if _rm_granted(data.get("session_id") or ""):
            continue  # ユーザーがこのターンで削除に触れている
        deny(
            "SAFE-09",
            f"`{found}` を実行しようとしたが、**ユーザーはこのターンで削除に触れていない**。\n"
            "消したものを取り戻す方法が無いので実行しない。"
            "必要なら、何をなぜ消すのかを伝えて指示を仰ぐこと"
            "（ユーザーが「消して」「削除して」等と言ったターンでは、このフックは止めない）",
        )


# --- FLOW-23: 「設計完了」のまま実装に入らせない（例外なし）----------------------
# 2026-09-14 追加。ステータスが古いまま compaction が起きると、残るのは `git diff` だけになり、
# 「この差分はどのステップまでを表すのか」を推測で当てることになる（FLOW-09 の再開可能性が壊れる）。
#
# 6 状態のうち、**機械的に当てられる遷移は「設計完了 → 実装中」だけ**なのでそこだけ止める。
#   - 設計完了かどうか: タスク定義書の現在地の 1 行に「設計完了」があるか
#   - 実装に入ったか: `.claude/` の外のファイルを書き換えようとしたか／
#                     タスク定義書を指す委任を起動しようとしたか
#
# **サブエージェントには掛けない。** 共通入力の `agent_id` は
# 「サブエージェント内から発火したときだけ存在し、メインスレッドでは存在しない」と
# 実装に明記されている（2026-09-14 に `cli.js` 2.1.81 で確認）。
# ステータスを持っているのは委任した側なので、ワーカーを止めても直せない。
IMPL_FILE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def _taskdef_helper():
    """`taskdef_status.py` を同じディレクトリから読む。無ければ None（機能を落とすだけ）。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import taskdef_status

        return taskdef_status
    except ImportError:
        return None


def check_taskdef_phase(data: dict, tool: str, tool_input: dict) -> None:
    if data.get("agent_id"):
        return  # サブエージェント。ステータスの持ち主ではない
    helper = _taskdef_helper()
    if helper is None:
        return

    if tool in IMPL_FILE_TOOLS:
        target = tool_input.get("file_path") or ""
        if not target or f"{os.sep}.claude{os.sep}" in target or target.startswith(".claude/"):
            return  # タスク定義書・作業メモ自体の編集は「実装」ではない
        what = f"`{target}` を書き換えようとした"
    elif tool in ("Agent", "Task"):
        prompt = tool_input.get("prompt") or ""
        if not is_impl_delegation(prompt):
            return  # 実装の委任ではない
        what = "タスク定義書を指す委任を起動しようとした"
    else:
        return

    # 🔴 判定に使うのは**このセッションが開いた定義書**だけ（2026-10-16 ユーザー指示）。
    # ブランチ名から当てていたため、ワークツリーを共有する他セッションの切り替えで
    # 無関係な定義書で止めていた。記録が無ければ判定しない。
    path, root = helper.locate_for_session(data.get("session_id") or "")
    if not path or helper.phase_of(path) != "設計完了":
        return
    deny(
        "FLOW-23",
        f"{os.path.relpath(path, root) if root else path} のステータスが「設計完了」のままなのに、{what}。\n"
        f"（判定に使った定義書＝このセッションが開いた `{path}`。別のタスクの定義書なら、"
        "そのタスクの定義書を開いてから作業すること）\n"
        "先に現在地の 1 行を「実装中」へ書き換えること"
        "（この 1 行が無いと、compaction 後に残るのは `git diff` だけになり、"
        "どのステップまで終わったのかを推測で当てることになる）",
    )


# --- 警告のみ（実行は止めない）------------------------------------------------
# ルール本文に「ユーザーの判断が要る例外」が書かれているもの。deny すると例外を握りつぶすので、
# additionalContext で Claude に気づかせるだけにする。`permissionDecision` を返さないので実行は続く。

# SAFE-10: リポジトリルートでの再帰 grep。例外＝「どうしても必要なら目的を添えて事前に確認する（許可制）」
# `grep` は再帰指定が無いとディレクトリを読まないので、`.` は**パターン**でしかない
# （`grep -c . file` が誤検知していた）。よって grep 側は -r/-R/--recursive を必須にする。
# `rg` / `ugrep` は既定で再帰するので、末尾の `.` だけで見る。
ROOT_GREP = re.compile(
    # `-rn` のような結合フラグも拾えるよう、r/R の前後に他のフラグ文字を許す
    r"(?<![\w./-])grep\s+(?:-[^\s]*\s+)*-[a-zA-Z]*[rR][a-zA-Z]*\b[^|;&\n]*\s(?:\.|\./)(?:\s|$)"
    r"|(?<![\w./-])grep\s+(?:-[^\s]*\s+)*--recursive\b[^|;&\n]*\s(?:\.|\./)(?:\s|$)"
    r"|(?<![\w./-])(?:rg|ugrep)\s+(?:-[^\s]*\s+)*[^|;&\n]*\s(?:\.|\./)(?:\s|$)"
)

# SAFE-12 は 2026-09-11 に deny へ移した（`check_output_trunc`）。ここには無い。

# META-01: /tmp への書き込み。例外＝「ユーザーが明示的に /tmp を指定したときだけ」
TMP_WRITE = re.compile(r">>?\s*/tmp/|(?<![\w./-])(?:tee|mkdir|touch|cp|mv|install)\s[^|;&\n]*\s/tmp/")

WARN_RULES = [
    ("SAFE-10", ROOT_GREP, "リポジトリルートへの再帰 grep に見える"),
]

# --- FLOW-22: 委任の指示文のファイルは、スクリプト以外が触らない ------------------
# 🔴 2026-10-22 ユーザー決定。指示文は `build_prompt.py` が書き、エージェントが読むだけ。
# **私（Claude）が書き換える経路を塞ぐ。** `chmod 0444` は所有者が自分で戻せるので歯止めにならない
# （2026-10-22 に実測）。止めるのはここ。
DELEGATE_PROMPT_PATH = re.compile(r"(?:/\.claude/state/delegate/|/delegate/[^/]*/prompts/|/delegate/prompts/)")
DELEGATE_PROMPT_WRITE = re.compile(
    r">>?\s*\S*(?:/\.claude/state/delegate/|/delegate/prompts/|/delegate/[^/\s]*/prompts/)"
    r"|(?<![\w./-])(?:tee|cp|mv|install|truncate|chmod|chown|ln)\s[^|;&\n]*"
    r"(?:/\.claude/state/delegate/|/delegate/prompts/|/delegate/[^/\s]*/prompts/)"
    r"|(?<![\w./-])(?:sed|perl)\s+(?:-[^\s]*\s+)*-[a-zA-Z]*i[^|;&\n]*"
    r"(?:/\.claude/state/delegate/|/delegate/prompts/|/delegate/[^/\s]*/prompts/)"
)


def check_delegate_prompt(text: str, what: str) -> None:
    """委任の指示文のファイルを、私が書き換え・移動・権限変更するのを止める。"""
    if not text:
        return
    hit = (DELEGATE_PROMPT_WRITE if what == "コマンド" else DELEGATE_PROMPT_PATH).search(text)
    if hit:
        deny(
            "FLOW-22",
            f"{what}が委任の指示文のファイルを変更しようとしている。"
            "指示文は `build_prompt.py` だけが書く（読むのは Read で可）。"
            "内容を変えたいなら、スクリプトを引数を変えて実行し直すこと（新しいファイルとして発行される）",
        )


# 🔴 2026-10-16 ユーザー指示「/tmp への保存をエージェント含めて禁止しろ」。
# 警告では止まらなかった（レビュアーが 6 ファイル書いた）ので deny にし、例外は作らない。
# エージェントへの指示文に `/tmp` を書くことも禁じる（サブエージェント自身の Bash/Write は
# PreToolUse がそのまま発火するので、同じ deny が当たる）。
#
# Write / Edit の書き込み先は、パスそのものなので `/tmp` で始まるかだけを見る。
TMP_PATH = re.compile(r"^/tmp(?:/|$)")

# 🔴 指示文は「**書き込み先として指している形**」だけを見る（2026-10-20 ユーザー承認）。
# 2026-10-16 の正規表現は `/tmp` の出現だけで止めていたため、
# **「`/tmp` は使わない」と書いてある禁止の文言そのもの**を誤検知し、
# design-review-v2 のレビュアー起動を止めていた（`skills/design-review-v2/SKILL.md` の
# 「作業ディレクトリを作る（`/tmp` は使わない）」が指示文に入る）。
# 言及だけの文は通し、**保存先・出力先として書いている形**で止める。
TMP_IN_PROMPT = re.compile(
    r">>?\s*/tmp/"                                      # > /tmp/out.log
    r"|(?<![\w./-])(?:tee|mkdir|touch|cp|mv|install|cd)\s[^|;&\n]*\s/tmp/"
    r"|(?<![\w.-])/tmp/[\w.-]"                          # /tmp/report.md のようにパスが続く
    r"|[A-Za-z_][A-Za-z0-9_]*=/tmp(?:/|\b)"             # WORKDIR=/tmp/...
    # 「出力先は /tmp」のように、保存を指す語が**先に**来る形
    r"|(?:保存|出力|書き出|置[いくき])[^\n]{0,8}(?<![\w.-])/tmp(?:/|\b)"
    # 「/tmp に保存して」のように、保存を指す語が**後に**来る形
    r"|(?<![\w.-])/tmp\b[^\n]{0,8}(?:保存|出力|書き出|置[いくき]|作業)"
)


def check_tmp_write(text: str, what: str) -> None:
    if not text:
        return
    if what == "コマンド":
        pattern = TMP_WRITE
    elif what == "エージェントへの指示文":
        pattern = TMP_IN_PROMPT
    else:
        pattern = TMP_PATH
    if pattern.search(text):
        deny(
            "META-01",
            f"{what}が `/tmp` 配下を指している。一時ファイルは `.claude/tmp/<タスク>/` に置くこと"
            "（エージェントへの指示文も同じ。例外は無い）",
        )


def warn(findings: list) -> None:
    """実行は止めず、Claude にだけ警告を届ける。

    このルール群は本文に例外が書かれているので、フックには例外に当たるか判定できない。
    判定は Claude が行う。気づかせるところまでがフックの仕事。
    """
    lines = ["⚠️ ルールに触れている可能性があります（実行は止めていません。自分で判定すること）"]
    for rule_id, detail in findings:
        name, summary = locate(rule_id)
        lines.append(
            f"\n[{rule_id}] {summary or '(要約を取得できませんでした)'}\n"
            f"  検出: {detail}\n"
            f"  このルールには**ユーザーの判断が要る例外**が書かれているため、フックは止めていない。"
            f"例外に当たるかを自分で判定し、当たらないなら投げ直すこと。\n"
            f"  定義: ~/.claude/memory/{name or '(ファイル不明)'} の `## {rule_id}`"
        )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": "\n".join(lines),
                }
            },
            ensure_ascii=False,
        )
    )
    sys.exit(0)


def check_warnings(cmd: str) -> None:
    findings = []
    for rule_id, pattern, detail in WARN_RULES:
        for segment in re.split(r"&&|\|\||;|\n", cmd):
            if pattern.search(segment):
                findings.append((rule_id, detail))
                break
    if findings:
        warn(findings)


HEREDOC_START = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_heredocs(cmd: str) -> str:
    """ヒアドキュメント本文はシェルが解釈しないデータなので判定から外す。

    heavy-command-guard.local.py と同じ理由。ドキュメントに `sed -i` と書いただけで
    拒否されるのを防ぐ。
    """
    out, lines, i = [], cmd.split("\n"), 0
    while i < len(lines):
        out.append(lines[i])
        match = HEREDOC_START.search(lines[i])
        i += 1
        if not match:
            continue
        terminator = match.group(2)
        while i < len(lines) and lines[i].strip() != terminator:
            i += 1
        if i < len(lines):
            i += 1
    return "\n".join(out)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or {}
    # 相対パスはこの cwd で解決する。フックプロセスの cwd とは別物（_abs のコメント参照）。
    cwd = data.get("cwd") or ""

    # 🔴 タスク定義書を開いたら、そのセッションの対象として記録する（FLOW-23 の判定に使う）。
    # サブエージェントは親と同じ session_id を持つので、ワーカーが開いた定義書も対象になる。
    if tool in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit") and not data.get("agent_id"):
        helper = _taskdef_helper()
        if helper is not None:
            helper.record_session_taskdef(
                data.get("session_id") or "", _abs(tool_input.get("file_path") or "", cwd)
            )

    if tool == "Bash":
        cmd = strip_heredocs(tool_input.get("command") or "")
        if not cmd:
            sys.exit(0)
        # deny 系を先に通す。止めるべきものは警告より優先する。
        check_git(cmd)
        check_script_edit(cmd)
        check_codegen(cmd)
        check_rm(cmd, data)
        check_tmp_write(cmd, "コマンド")
        check_delegate_prompt(cmd, "コマンド")
        check_output_trunc(cmd)
        check_v1_paths(cmd, is_command=True)
        check_tmp_housekeeping(cmd, cwd)
        # ここまで来たら実行は許す。触れているルールがあれば警告だけ出す。
        check_done_leftover_tmp(cmd, cwd)
        check_warnings(cmd)
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = tool_input.get("file_path") or ""
        check_v1_paths(path, is_command=False)
        check_tmp_write(path, "書き込み先")
        check_delegate_prompt(path, "書き込み先")
        check_tmp_housekeeping(path, cwd)
        check_taskdef_phase(data, tool, tool_input)
    elif tool in ("Agent", "Task"):
        # ツール名はビルドによって違う（このビルドは `Agent`、従来は `Task`）。両方見る。
        check_delegation(tool_input)
        check_tmp_write(tool_input.get("prompt") or "", "エージェントへの指示文")
        check_taskdef_phase(data, tool, tool_input)

    sys.exit(0)


if __name__ == "__main__":
    main()
