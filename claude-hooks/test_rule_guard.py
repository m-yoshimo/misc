#!/usr/bin/env python3
"""rule_guard.py の検証。

テストケースをフック本体に食わせ、期待どおり PASS / WARN / DENY になるかを確認する。
シェル経由だとテストスクリプト自体がフックに引っかかるので、Python から直接叩く。

## 置き場所について（2026-09-14）

以前は `idpf-api/.claude/tmp/feedback-inventory/` に置いていたが、**そこは一時ファイルの場所**で
META-01 の掃除対象。実際に 2026-09-14 の掃除で消えた。**フックと同じ寿命のものはフックの隣に置く。**
消えた版はセッションのトランスクリプトから復元した（101 ケース）。

## 相対パスのケースについて

`.claude/tmp/...` を含むケースがあるので、**フックは必ず「空の作業ディレクトリ」で実行する**。
実プロジェクトの `.claude/tmp` の中身によって結果が変わると、テストが日によって落ちるため。
"""

import json
import os
import shutil
import subprocess
import sys
import time

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rule_guard.py")

# テスト用の足場。終了時に必ず消す。
SANDBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmptest")
NEUTRAL = os.path.join(SANDBOX, "neutral")          # 相対パス判定用の空ディレクトリ
TMP_ROOT = os.path.join(SANDBOX, "proj", ".claude", "tmp")

SANDBOX_HOME = os.path.join(SANDBOX, "home")        # build_global_owner_cases() だけ HOME をここに向ける

# delegate の発行記録はテスト用の場所に向ける（フックの子プロセスにも環境変数で渡る）
os.environ["DELEGATE_ISSUED_LOG"] = os.path.join(SANDBOX, "state", "issued.jsonl")
WORKER_TEMPLATE = os.path.join(os.path.expanduser("~"), ".claude", "skills", "delegate", "templates", "worker.md")

# (期待, ツール, 入力)  期待: PASS / WARN / DENY
CASES = [
    # ---- 通す: git の read-only と要許可 ----
    ("PASS", "Bash", "git status --short"),
    ("PASS", "Bash", "git diff origin/main"),
    ("PASS", "Bash", "git log --oneline -5"),
    ("PASS", "Bash", "git show HEAD"),
    ("PASS", "Bash", "git blame foo.go"),
    ("PASS", "Bash", "git ls-files"),
    ("PASS", "Bash", "git rev-parse --abbrev-ref HEAD"),
    ("PASS", "Bash", "git stash list"),
    ("PASS", "Bash", "git branch --list"),
    ("PASS", "Bash", "git remote -v"),
    # `git config` は 2026-10-05 に読み取りだけ許可へ（書き込み形は deny）
    ("PASS", "Bash", "git config user.name"),
    ("PASS", "Bash", "git config --get user.email"),
    ("PASS", "Bash", "git config --get-regexp '^remote\\.'"),
    ("PASS", "Bash", "git config --list"),
    ("PASS", "Bash", "git config -l"),
    ("DENY", "Bash", "git config user.name 'Someone Else'"),
    ("DENY", "Bash", "git config --global user.email x@example.com"),
    ("DENY", "Bash", "git config --add safe.directory /tmp/foo"),
    ("DENY", "Bash", "git config --unset user.name"),
    ("DENY", "Bash", "git config --edit"),
    ("PASS", "Bash", "git checkout feature/foo"),
    ("PASS", "Bash", "git switch main"),
    # `git fetch` は 2026-10-02 にユーザー承認で許可側へ。`--prune` 系だけ除外する
    ("PASS", "Bash", "git fetch"),
    ("PASS", "Bash", "git fetch --all"),
    ("PASS", "Bash", "git fetch origin main"),
    ("DENY", "Bash", "git fetch --prune"),
    ("DENY", "Bash", "git fetch -p"),
    ("DENY", "Bash", "git fetch --all --prune-tags"),
    ("PASS", "Bash", "cd apps/api && git diff origin/main"),
    # ---- 通す: git が「文字列」として現れるだけ ----
    ("PASS", "Bash", "echo 'git add . は禁止'"),
    ("PASS", "Bash", 'grep -n "git restore" ~/.claude/memory/feedback_03_commands.md'),
    ("PASS", "Bash", "printf '%s\\n' 'git commit -m x'"),
    # ---- 通す: その他 ----
    ("PASS", "Bash", "grep -rn 'foo' apps/api/"),
    ("PASS", "Bash", "grep -n foo internal/env/config.go"),
    ("PASS", "Bash", "go test ./internal/..."),
    # 2026-10-05: META-01 に「一時ディレクトリは未完了のタスク定義書が宣言していること」が入ったので、
    # 宣言の無い名前（`t`）は止まる。SAFE-12 の保存先を作るときも宣言が先に要る。
    # 宣言済みの名前が通ることは build_owner_cases() で確かめている。
    ("DENY", "Bash", "make lint > .claude/tmp/t/lint.log 2>&1"),
    ("PASS", "Bash", 'sed -n "1,20p" foo.md'),
    ("PASS", "Bash", 'awk -F"\\t" "{print $1}" a.tsv'),
    ("PASS", "Bash", 'python3 -c "print(open(\'a.txt\').read())"'),
    ("PASS", "Bash", 'python3 -c "import json; json.load(open(\'a.json\'))"'),
    ("PASS", "Bash", "cat ~/.claude/notes/design_philosophy.md"),
    ("PASS", "Bash", "grep -n foo ~/.claude/notes/design_review_rubric.md"),
    ("PASS", "Bash", 'echo "sed -i is forbidden"'),
    ("PASS", "Bash", "ls -1 /tmp/claude-1000"),
    ("PASS", "Bash", "head -20 foo.md"),
    ("PASS", "Write", "/home/m-yoshimo/work/foo.go"),
    ("PASS", "Write", "/home/m-yoshimo/.claude/memory/feedback_03_commands.md"),
    # ---- 警告のみ（実行は止めない）----
    ("WARN", "Bash", "grep -rn 'VITE_FEATURE' ."),
    # ---- 止める: META-01 の `/tmp`（2026-10-16 ユーザー指示で警告から deny へ。例外なし）----
    ("DENY", "Bash", "echo x > /tmp/out.log"),
    ("DENY", "Bash", "cp foo.txt /tmp/"),
    ("DENY", "Bash", "mkdir -p /tmp/claude-1000/work"),
    ("DENY", "Write", "/tmp/claude-1000/work/out.md"),
    ("DENY", "Agent", "結果は /tmp/report.md に書いて"),
    ("PASS", "Bash", "cat /tmp/existing.log"),
    # ---- 指示文は「書き込み先として指している形」だけ止める（2026-10-20 ユーザー承認）----
    # 言及だけの文で止めていたため、design-review-v2 の起動が止まっていた
    # （SKILL.md の「作業ディレクトリを作る（`/tmp` は使わない）」が指示文に入る）
    ("PASS", "Agent", "作業ディレクトリを作る（`/tmp` は使わない）: .claude/tmp/design-review/20261020"),
    ("PASS", "Agent", "/tmp は使用禁止です。出力は .claude/tmp/GID-1474/ に置いてください"),
    ("PASS", "Agent", "ハーネスが案内する /tmp 系のスクラッチパッドは使わないこと"),
    ("PASS", "Agent", "レビュー対象は .claude/tmp/design-review/x/target.diff です"),
    ("DENY", "Agent", "ログを /tmp に保存してください"),
    ("DENY", "Agent", "WORKDIR=/tmp/review-1 を作って作業して"),
    ("DENY", "Agent", "mkdir -p /tmp/work && cd /tmp/work"),
    ("DENY", "Agent", "出力先は /tmp"),
    ("DENY", "Agent", "/tmp を作業ディレクトリにして"),
    # ---- 委任の指示文のファイルは build_prompt.py 以外が触らない（2026-10-22 ユーザー決定）----
    ("DENY", "Write", "/home/m-yoshimo/.claude/state/delegate/prompts/8ba2c76ab8ae.md"),
    ("DENY", "Edit", "/home/m-yoshimo/work/x/.claude/tmp/GID-1/delegate/20261022-1-review/prompts/a1b2c3d4e5f6.md"),
    ("DENY", "Bash", "echo x > /home/m-yoshimo/.claude/state/delegate/prompts/8ba2c76ab8ae.md"),
    ("DENY", "Bash", "sed -i 's/a/b/' /home/m-yoshimo/.claude/state/delegate/prompts/8ba2c76ab8ae.md"),
    ("DENY", "Bash", "chmod 644 /home/m-yoshimo/.claude/state/delegate/prompts/8ba2c76ab8ae.md"),
    ("DENY", "Bash", "cp a.md /home/m-yoshimo/.claude/state/delegate/prompts/8ba2c76ab8ae.md"),
    ("DENY", "Bash", "mv /home/m-yoshimo/.claude/state/delegate/prompts/8ba2c76ab8ae.md /home/m-yoshimo/x.md"),
    ("PASS", "Bash", "cat /home/m-yoshimo/.claude/state/delegate/prompts/8ba2c76ab8ae.md"),
    ("PASS", "Read", "/home/m-yoshimo/.claude/state/delegate/prompts/8ba2c76ab8ae.md"),
    # ---- 止める: SAFE-12（2026-09-11 に警告から deny へ移した）----
    # パイプラインの**先頭**が許可列挙に無いものを止める
    ("DENY", "Bash", "make lint 2>&1 | tail -30"),
    ("DENY", "Bash", "go build ./... | head -20"),
    ("DENY", "Bash", "make test | grep FAIL | head -5"),  # 途中に grep を挟んでも先頭は make
    ("DENY", "Bash", "pnpm run lint | head -40"),
    ("DENY", "Bash", "docker compose logs | tail -50"),
    ("DENY", "Bash", "make test | head -20 > out.log"),  # 保存の前に切っている
    # 許可列挙にある先頭は通す（既存ファイル・状態を読むだけ／やり直しが安い）
    ("PASS", "Bash", "cat out.log | head -20"),
    ("PASS", "Bash", "grep FAIL out.log | head -5"),
    ("PASS", "Bash", "git status --short | head -10"),
    ("PASS", "Bash", "git log --oneline -20 | head -5"),
    ("PASS", "Bash", "ls -1 apps/api | head -20"),
    ("PASS", "Bash", "sort out.log | uniq -c | tail -10"),
    ("PASS", "Bash", 'echo "make test | head -5 はダメ"'),  # 先頭 echo＝文字列を出すだけ
    # ---- 2026-10-16 ユーザー承認で拡大した列挙（通るべきもの）----
    ("PASS", "Bash", "timeout 60 grep -rn foo apps/api | head -20"),
    ("PASS", "Bash", "timeout 5m git log --oneline | head -5"),
    ("PASS", "Bash", "L=$(grep -n foo bar.go | head -1)"),
    ("PASS", "Bash", "D=`ls -t logs | head -1`"),
    ("PASS", "Bash", "gh pr list --limit 100 | head -60"),
    ("PASS", "Bash", "gh pr view 2424 --json files | jq -r '.files[].path' | head"),
    ("PASS", "Bash", "gh run list --workflow ci.yml | head -10"),
    ("PASS", "Bash", "gh auth status | tail -3"),
    ("PASS", "Bash", "gh api repos/genda-tech/idpf-api/pulls | head -5"),
    ("PASS", "Bash", "git ls-files apps/api | head -30"),
    ("PASS", "Bash", "git merge-base origin/main HEAD | head -1"),  # 2026-10-16 ユーザー承認
    ("PASS", "Bash", "git merge-base --is-ancestor HEAD origin/main"),
    ("PASS", "Bash", "git blame -L 1,20 apps/api/main.go | head"),
    ("PASS", "Bash", "git stash list | head -5"),
    ("PASS", "Bash", "git fetch origin 2>&1 | tail -3"),
    ("PASS", "Bash", "git remote -v | head -2"),
    ("PASS", "Bash", "docker ps | head -5"),
    ("PASS", "Bash", "docker compose ps | head"),
    ("PASS", "Bash", "go version | head -2"),
    ("PASS", "Bash", "go env GOPATH | head -1"),
    ("PASS", "Bash", "node --version | tail -1"),
    ("PASS", "Bash", "python3 --version | head -1"),
    ("PASS", "Bash", "df -h . | tail -2"),
    ("PASS", "Bash", "du -sh .claude | tail -1"),
    ("PASS", "Bash", "ps aux | grep mysqld | head -3"),
    ("PASS", "Bash", "nl -ba apps/api/main.go | head -40"),
    ("PASS", "Bash", "stat -c %s out.log | head -1"),
    ("PASS", "Bash", "diff a.txt b.txt | head -20"),
    ("PASS", "Bash", "find . -name '*.go' -newer go.mod | head -20"),
    # ---- 拡大しても止まり続けるべきもの（やり直しのコストがユーザーに出る）----
    ("DENY", "Bash", "timeout 60 go test ./... | tail -5"),  # 接頭辞を剥がすと go test
    ("DENY", "Bash", "timeout 120 make lint | head -30"),
    ("DENY", "Bash", "nohup make build | tail -5"),
    ("DENY", "Bash", "sudo docker compose up -d | tail -20"),
    ("DENY", "Bash", "docker compose exec api go test ./... | head"),
    ("DENY", "Bash", "docker build -t x . | tail -10"),
    ("DENY", "Bash", "gh pr create --title x --body y | head -3"),
    ("DENY", "Bash", "gh pr merge 2424 --squash | head"),
    ("DENY", "Bash", "gh api -X POST repos/genda-tech/idpf-api/issues | head -5"),
    ("DENY", "Bash", "gh api --method DELETE repos/x/y/git/refs/heads/z | head"),
    ("DENY", "Bash", "git stash pop | head -5"),  # SAFE-01 側でも止まる
    ("DENY", "Bash", "go build ./internal/... 2>&1 | head -20"),
    ("DENY", "Bash", "npm ci | tail -5"),
    ("DENY", "Bash", "pnpm build | head -20"),
    ("DENY", "Bash", "terraform plan | tail -30"),
    ("DENY", "Bash", "curl -s https://example.com/big.json | head -40"),
    ("DENY", "Bash", "aws s3 ls s3://bucket | head -20"),
    ("DENY", "Bash", "python3 scripts/gen.py | head -20"),  # --version ではない
    ("DENY", "Bash", "node -e 'console.log(1)' | head -2"),
    ("DENY", "Bash", "X=$(make test | head -1)"),  # コマンド置換の中も判定する
    ("DENY", "Bash", "V=`pnpm run build | tail -1`"),
    # ---- 長い連結コマンド（1 文でも、止めるべき段が 1 つあれば止める）----
    ("PASS", "Bash", "git fetch origin && git log --oneline origin/main --not HEAD | head -20"),
    ("PASS", "Bash", "git status --short | head -5; git diff --stat | tail -3"),
    ("DENY", "Bash", "git status --short | head -5 && make build 2>&1 | tail -3"),
    ("DENY", "Bash", "git fetch origin && go test ./internal/handler/... | tail -20"),
    ("DENY", "Bash",
     "git ls-files apps/api | head -5; grep -rn foo apps/api | head -3; "
     "make test 2>&1 | tail -10; echo done"),
    ("DENY", "Bash",
     "N=$(git ls-files | wc -l) && echo $N | head -1 && pnpm run lint 2>&1 | head -40"),
    ("PASS", "Bash",
     "F=$(git ls-files 'apps/api/**/*.go' | head -1) && nl -ba \"$F\" | head -20 "
     "&& git log --oneline -3 -- \"$F\" | tail -2"),
    # ---- 止める: SAFE-01 ----
    ("DENY", "Bash", "git restore apps/api/foo.go"),
    ("DENY", "Bash", "git reset --hard HEAD"),
    ("DENY", "Bash", "git clean -fd"),
    ("DENY", "Bash", "git stash"),
    ("DENY", "Bash", "git stash pop"),
    ("DENY", "Bash", "git add ."),
    ("DENY", "Bash", 'git commit -m "x"'),
    ("DENY", "Bash", "git push origin main"),
    ("DENY", "Bash", "git rm foo.go"),
    ("DENY", "Bash", "git cherry-pick abc123"),
    ("DENY", "Bash", "git rebase main"),
    ("DENY", "Bash", "git worktree remove foo"),
    ("DENY", "Bash", "git branch -D foo"),
    ("DENY", "Bash", "git merge main"),
    ("DENY", "Bash", "git revert HEAD"),
    ("DENY", "Bash", "git mv a b"),
    ("DENY", "Bash", "cd apps/api && git add ."),
    ("DENY", "Bash", "echo start; git commit -m x"),
    # ---- `git branch`: 表示は通し、変更系と作成は止める（2026-10-16 ユーザー承認）----
    ("PASS", "Bash", "git branch"),
    ("PASS", "Bash", "git branch -a"),
    ("PASS", "Bash", "git branch -r"),
    ("PASS", "Bash", "git branch -vv"),
    ("PASS", "Bash", "git branch --all"),
    ("PASS", "Bash", "git branch --show-current"),
    ("PASS", "Bash", "git branch --list 'feat/*'"),
    ("PASS", "Bash", "git branch --contains HEAD"),
    ("PASS", "Bash", "git branch --merged origin/main"),
    ("PASS", "Bash", "git branch --sort=-committerdate --format='%(refname:short)'"),
    ("DENY", "Bash", "git branch -d foo"),
    ("DENY", "Bash", "git branch --delete foo"),
    ("DENY", "Bash", "git branch -m old new"),
    ("DENY", "Bash", "git branch -M old new"),
    ("DENY", "Bash", "git branch -c a b"),
    ("DENY", "Bash", "git branch -u origin/main"),
    ("DENY", "Bash", "git branch --set-upstream-to=origin/main"),
    ("DENY", "Bash", "git branch feature/x"),  # 引数を渡す形は作成
    ("DENY", "Bash", "git branch -f main HEAD"),
    # ---- `git remote`: 表示は通し、設定を書き換える形は止める（2026-10-16 ユーザー承認）----
    ("PASS", "Bash", "git remote"),
    ("PASS", "Bash", "git remote -v"),
    ("PASS", "Bash", "git remote show origin"),
    ("PASS", "Bash", "git remote get-url origin"),
    ("DENY", "Bash", "git remote add up git@github.com:x/y.git"),
    ("DENY", "Bash", "git remote remove up"),
    ("DENY", "Bash", "git remote rename a b"),
    ("DENY", "Bash", "git remote set-url origin x"),
    ("DENY", "Bash", "git remote prune origin"),
    # ---- 止める: SAFE-05 ----
    ("DENY", "Bash", 'sed -i "s/a/b/" foo.go'),
    ("DENY", "Bash", 'perl -pi -e "s/a/b/" foo.go'),
    ("DENY", "Bash", "python3 -c \"open('a.txt', 'w').write('x')\""),
    # ---- 止める: TECH-02 ----
    ("DENY", "Bash", "make -C apps/api openapi_generate_api"),
    ("DENY", "Bash", "gomockhandler -config=x mockgen"),
    ("DENY", "Bash", "go run cmd/migration_apply/main.go"),
    ("DENY", "Bash", "go run cmd/generate_models/main.go"),
    # ---- 止める: META-08 ----
    ("DENY", "Bash", "echo x >> ~/.claude/notes/design_philosophy.md"),
    ("DENY", "Bash", "rm ~/.claude/notes/design_review_rubric.md"),
    ("DENY", "Bash", "mv ~/.claude/notes/design_philosophy.md /tmp/"),
    ("DENY", "Write", "/home/m-yoshimo/.claude/notes/design_philosophy.md"),
    ("DENY", "Write", "/home/m-yoshimo/.claude/notes/design_review_rubric.md"),
    # ---- deny は warn より優先 ----
    ("DENY", "Bash", "git add . | tail -5"),
    # ---- 2026-09-11 追加: ヒアドキュメントでの上書き（auto mode の案内経路）----
    ("DENY", "Bash", "cat > foo.go <<'EOF'\npackage main\nEOF"),
    ("DENY", "Bash", "cat >> ~/.claude/memory/feedback_03_commands.md <<EOF\nx\nEOF"),
    ("DENY", "Bash", "tee apps/api/main.go <<'EOF'\npackage main\nEOF"),
    # 解析結果をファイルに保存するのは書き換えではない（SAFE-12 が求める形）
    ("PASS", "Bash", "python3 - > out.txt 2>&1 <<'PY'\nprint(1)\nPY"),
    ("PASS", "Bash", "cat foo.go"),
    ("PASS", "Bash", "cat foo.go > bar.txt"),
    # ---- 2026-09-11 追加: SAFE-10 の誤検知（`.` がパターンであってディレクトリではない）----
    ("PASS", "Bash", "grep -c . README.md"),
    ("PASS", "Bash", "grep -n . apps/api/main.go"),
    ("WARN", "Bash", "grep -rn foo ."),
    ("WARN", "Bash", "grep --recursive foo ."),
    ("WARN", "Bash", "rg foo ."),
    # ---- 止める: FLOW-22（実装の委任なのに無断改変の宣言が無い）----
    ("DENY", "Agent", ".claude/tasks/GID-1856.md のとおり実装して。"),
    ("DENY", "Agent", "~/.claude/memory/feedback_*.md を全文読む。.claude/tasks/GID-1856.md のとおり実装して。"),
    # 宣言があれば通す
    ("PASS", "Agent", ".claude/tasks/GID-1856.md のとおり実装して。"
                      "報告の②に書かれていない差異が後から見つかったら無断改変として扱う。"),
    # ---- 止める: FLOW-22（design-review の判定者にルールを渡していない）----
    ("DENY", "Agent", "あなたは設計レビューの判定者です。\n"
                      "## 前提として必ず読むもの\n1. ~/.claude/notes/design-review-v2/00-principles.md\n"
                      "## レビュー対象\ntarget.md"),
    ("PASS", "Agent", "あなたは設計レビューの判定者です。\n"
                      "## 前提として必ず読むもの\n1. ~/.claude/memory/MEMORY.md\n"
                      "2. ~/.claude/notes/design-review-v2/00-principles.md\n"
                      "## レビュー対象\ntarget.md"),
    # ---- 2026-09-14 変更: ルール本文を読ませる条件は deny から外した ----
    # 軽い委任（実行・調査）を deny していたため。deny 段はサブエージェントでもフックが止める
    ("PASS", "Agent", "apps/api でテストを実行して、失敗した一覧を報告してください。"),
    ("PASS", "Agent", "このリポジトリの Go のバージョンを調べて教えて。"),
    ("PASS", "Task", "この PR の差分をレビューして、問題があれば指摘してください。"),
    ("PASS", "Agent", "まず ~/.claude/memory/MEMORY.md を読んでから、foo.go を直してください。"),
    ("PASS", "Agent", "~/.claude/memory/feedback_*.md を全文読んでから、この差分をレビューして。"),
    ("PASS", "Agent", ""),  # 空プロンプトは対象外（他ツールの入力形と衝突させない）
    # ---- META-01 の掃除（2026-09-14 追加）は build_tmp_cases() で動的に作る ----
]


def build_delegate_cases() -> list:
    """delegate skill の指示文と FLOW-22 の検査がずれていないことを確かめる（2026-10-07）。

    テンプレートの宣言の文は、実物の worker.md から読む。テンプレートとフックが再びずれたら、ここで落ちる。
    """
    sys.path.insert(0, os.path.dirname(HOOK))
    import delegate_guard

    with open(WORKER_TEMPLATE, encoding="utf-8") as fh:
        decl = [line for line in fh.read().splitlines() if "無断改変" in line]
    os.makedirs(os.path.dirname(os.environ["DELEGATE_ISSUED_LOG"]), exist_ok=True)

    def stamped(body: str, kind: str) -> str:
        stamp = delegate_guard.fingerprint(body)
        delegate_guard.append_jsonl(os.environ["DELEGATE_ISSUED_LOG"], {"id": stamp, "kind": kind, "label": kind})
        return f"{body}\n[delegate:{stamp}]\n"

    task = "/home/x/repo/.claude/tasks/GID-1/t.md"
    return [
        # 宣言の文が worker.md から消えていたら、ここで落ちる
        ("PASS" if decl else "DENY", "Agent", f"{task} のとおり実装して。\n" + "\n".join(decl)),
        # worker の指示文（発行印つき）: 宣言があれば通し、無ければ止める
        ("PASS", "Agent", stamped(f"{task} のとおり実装して。\n" + "\n".join(decl), "worker")),
        ("DENY", "Agent", stamped(f"{task} のとおり実装して。", "worker")),
        # 実装ではない種類は、定義書のパスを含んでいても宣言の検査を掛けない
        ("PASS", "Agent", stamped(f"補助資料:\n- {task}（元: overview.md）\n"
                                  "1. ~/.claude/memory/MEMORY.md\n2. ~/.claude/notes/design-review-v2/00-principles.md",
                                  "review-design-v2")),
        ("PASS", "Agent", stamped(f"{task} の前提を調べて、結果を書き出して。", "research")),
        # 発行記録に無い発行印は文字列で判定する（宣言が無ければ止める）
        ("DENY", "Agent", f"{task} のとおり実装して。\n[delegate:0123456789ab]\n"),
    ]


def build_owner_cases() -> list:
    """「未完了のタスク定義書が宣言した一時ディレクトリだけ作れる」ことを確かめる。

    2026-10-05 に META-01 へ入った仕組み。**宣言されていない名前は作れず、
    宣言されていないディレクトリが残っていると新しいものも作れない。**
    持ち主のいないディレクトリが混ざっていない別のプロジェクトを作って検証する
    （`build_tmp_cases()` の足場は、わざと残骸がある状態にしてあるため）。
    """
    proj = os.path.join(SANDBOX, "proj2")
    tmp_root = os.path.join(proj, ".claude", "tmp")
    tasks = os.path.join(proj, ".claude", "tasks")
    done = os.path.join(tasks, "done")
    os.makedirs(tmp_root, exist_ok=True)
    os.makedirs(done, exist_ok=True)
    with open(os.path.join(tasks, "GID-6666-active.md"), "w", encoding="utf-8") as fh:
        fh.write(
            "# 進行中\n\n## ステータス\n\n- [ ] 実装中\n"
            "- 一時ディレクトリ: `.claude/tmp/GID-6666-work/`\n"
        )
    # done/ 配下の宣言は無効（完了済みタスクの作業ディレクトリは作らせない）
    with open(os.path.join(done, "GID-5555-finished.md"), "w", encoding="utf-8") as fh:
        fh.write(
            "# 済み\n\n## ステータス\n\n- [x] 完了（2026-10-01）\n"
            "- 一時ディレクトリ: `.claude/tmp/GID-5555-work/`\n"
        )
    return [
        # 共用の delegate/ は作らせない（委任のファイルは宣言済みの一時ディレクトリの中に置く。2026-10-06）
        ("DENY", "Write", f"{tmp_root}/delegate/20261005-120000-review-abcdef/target.diff"),
        ("PASS", "Write", f"{tmp_root}/GID-6666-work/delegate/20261005-120000-review-abcdef/target.diff"),
        ("PASS", "Write", f"{tmp_root}/GID-6666-work/probe.log"),
        ("PASS", "Bash", f"make lint > {tmp_root}/GID-6666-work/lint.log 2>&1"),
        ("DENY", "Write", f"{tmp_root}/GID-6666-undeclared/probe.log"),
        ("DENY", "Write", f"{tmp_root}/GID-5555-work/probe.log"),
    ]


def build_global_owner_cases() -> list:
    """`~/.claude/tasks/` の定義書が宣言したディレクトリも、持ち主ありとして扱うことを確かめる。

    2026-10-05 に、ここを見ていなかったため別セッションの作業データを残骸と判定した。
    実際の `~/.claude/tasks/` に左右されないよう、これらのケースは HOME を足場の中に向けて実行する。
    """
    global_tasks = os.path.join(SANDBOX_HOME, ".claude", "tasks")
    os.makedirs(os.path.join(global_tasks, "done"), exist_ok=True)
    declarations = {
        "no-ticket-a.md": "`~/work/proj3/.claude/tmp/GID-4444-global/`",
        "no-ticket-b.md": "`.claude/tmp/no-path-global/`",
        "no-ticket-c.md": "`~/work/other/.claude/tmp/GID-3333-other-proj/`",
        os.path.join("done", "no-ticket-d.md"): "`~/work/proj5/.claude/tmp/GID-2222-done/`",
    }
    for rel, decl in declarations.items():
        with open(os.path.join(global_tasks, rel), "w", encoding="utf-8") as fh:
            fh.write(f"## ステータス\n\n- [ ] 実装中\n- 一時ディレクトリ: {decl}\n")

    def project(name: str, existing: tuple) -> str:
        proj = os.path.join(SANDBOX_HOME, "work", name)
        tmp_root = os.path.join(proj, ".claude", "tmp")
        tasks = os.path.join(proj, ".claude", "tasks")
        os.makedirs(tasks, exist_ok=True)
        for d in existing:
            os.makedirs(os.path.join(tmp_root, d), exist_ok=True)
        with open(os.path.join(tasks, "GID-6666-active.md"), "w", encoding="utf-8") as fh:
            fh.write("## ステータス\n\n- [ ] 実装中\n- 一時ディレクトリ: `.claude/tmp/GID-6666-work/`\n")
        return tmp_root

    proj3 = project("proj3", ("GID-4444-global", "no-path-global"))
    proj4 = project("proj4", ("GID-3333-other-proj",))
    proj5 = project("proj5", ("GID-2222-done",))
    return [
        # パス付き（このプロジェクト）とパス無しの宣言は持ち主になる → 残骸なしで通る
        ("PASS", "Write", f"{proj3}/GID-6666-work/probe.log"),
        # 別プロジェクトのパスを付けた宣言は持ち主にならない → 残骸ありで止まる
        ("DENY", "Write", f"{proj4}/GID-6666-work/probe.log"),
        # done/ の宣言は持ち主にならない
        ("DENY", "Write", f"{proj5}/GID-6666-work/probe.log"),
    ]


def build_tmp_cases() -> list:
    """`.claude/tmp/` に「前日以前の残骸」がある状態を作り、挙動を確かめる。"""
    os.makedirs(NEUTRAL, exist_ok=True)
    os.makedirs(os.path.join(TMP_ROOT, "GID-9999-old"), exist_ok=True)
    os.makedirs(os.path.join(TMP_ROOT, "GID-8888-today"), exist_ok=True)
    old_file = os.path.join(TMP_ROOT, "GID-9999-old", "note.txt")
    with open(old_file, "w", encoding="utf-8") as fh:
        fh.write("stale\n")
    stale = time.time() - 72 * 3600
    os.utime(old_file, (stale, stale))
    os.utime(os.path.join(TMP_ROOT, "GID-9999-old"), (stale, stale))

    new_dir = f"{TMP_ROOT}/GID-7777-new"
    today_dir = f"{TMP_ROOT}/GID-8888-today"
    old_dir = f"{TMP_ROOT}/GID-9999-old"
    return [
        # 前日以前の残骸があるので、新しい作業ディレクトリは作れない
        ("DENY", "Write", f"{new_dir}/probe.py"),
        ("DENY", "Bash", f"go build ./... > {new_dir}/build.log 2>&1"),
        # 既存ディレクトリへの追記は止めない（作業の途中で詰まらせない）
        ("PASS", "Write", f"{today_dir}/probe.py"),
        ("PASS", "Write", f"{old_dir}/note2.txt"),
        # `.claude/tmp` 以外は対象外
        ("PASS", "Write", os.path.join(SANDBOX, "proj", ".claude", "tasks", "GID-7777.md")),
    ]


def build_cwd_cases() -> list:
    """cwd がサブディレクトリに残っていても、プロジェクトの宣言を見つけられることを確かめる。

    2026-10-23 に判明した不具合。フックは `.claude/tmp/…` を cwd で解決していたため、
    `cd` でサブディレクトリへ移ったセッションでは `<サブディレクトリ>/.claude/tmp` を
    見てしまい、宣言済みの一時ディレクトリへの書き込みを
    「宣言している定義書が無い」と止めていた（原因と無関係なメッセージ）。

    返すのは **(期待, ツール, 入力, cwd)** の 4 要素。
    """
    proj = os.path.join(SANDBOX, "proj3")
    group = os.path.join(proj, ".claude", "tasks", "GID-8888-group")
    deep = os.path.join(proj, "apps", "api")
    os.makedirs(group, exist_ok=True)
    os.makedirs(deep, exist_ok=True)
    os.makedirs(os.path.join(proj, ".claude", "tmp"), exist_ok=True)
    # サブディレクトリの中の定義書（FLOW-05 のディレクトリ構成）
    with open(os.path.join(group, "overview.md"), "w", encoding="utf-8") as fh:
        fh.write("## ステータス\n\n- [ ] 設計中\n- 一時ディレクトリ: `.claude/tmp/GID-8888-work/`\n")
    # テンプレートのプレースホルダは持ち主として数えない
    with open(os.path.join(proj, ".claude", "tasks", "_TEMPLATE_X.md"), "w", encoding="utf-8") as fh:
        fh.write("## ステータス\n\n- [ ] 未着手\n- 一時ディレクトリ: `.claude/tmp/{チケット番号}-{内容}/`\n")
    return [
        # cwd がサブディレクトリでも、上位の .claude/tasks にある宣言を見つける
        ("PASS", "Bash", "make lint > .claude/tmp/GID-8888-work/lint.log 2>&1", deep),
        ("PASS", "Bash", "make lint > .claude/tmp/GID-8888-work/lint.log 2>&1", group),
        ("PASS", "Write", ".claude/tmp/GID-8888-work/probe.log", deep),
        # 宣言が無い名前は、cwd がどこであっても止める（ゆるめていない）
        ("DENY", "Bash", "make lint > .claude/tmp/GID-8888-undeclared/lint.log 2>&1", deep),
        ("DENY", "Write", ".claude/tmp/GID-8888-undeclared/probe.log", group),
        # ワイルドカードを含むパスは判定しない（一覧・検索を止めない）
        ("PASS", "Bash", f"ls -d {SANDBOX}/*/.claude/tmp/*/delegate", deep),
        ("PASS", "Bash", "find . -path './*/.claude/tmp/*/' -prune", deep),
        # テンプレートのプレースホルダは持ち主ではない
        ("DENY", "Bash", "echo x > .claude/tmp/{チケット番号}-{内容}/out.log", deep),
        # 上位に .claude/tasks が無ければ判定材料が無いので止めない（止めない側に倒す）
        ("PASS", "Bash", "echo x > .claude/tmp/whatever/out.log", "/"),
    ]


def run_hook(tool: str, value: str, home: str = None, cwd: str = None) -> str:
    payload = {"tool_name": tool}
    if cwd:
        payload["cwd"] = cwd
    if tool == "Bash":
        payload["tool_input"] = {"command": value}
    elif tool in ("Agent", "Task"):
        payload["tool_input"] = {"prompt": value}
    else:
        payload["tool_input"] = {"file_path": value}
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=NEUTRAL,  # 相対パスのケースが実プロジェクトの状態に左右されないようにする
        env={**os.environ, "HOME": home} if home else None,
    )
    out = proc.stdout.strip()
    if not out:
        return "PASS"
    data = json.loads(out)["hookSpecificOutput"]
    if data.get("permissionDecision") == "deny":
        return "DENY"
    if data.get("additionalContext"):
        return "WARN"
    return "?"


def main() -> None:
    shutil.rmtree(SANDBOX, ignore_errors=True)
    cases = [(c, None) for c in CASES + build_tmp_cases() + build_owner_cases() + build_delegate_cases()]
    cases += [(c, SANDBOX_HOME) for c in build_global_owner_cases()]
    # cwd を指定するケースは 4 要素なので、cwd 無しの形に揃えてから回す
    cases += [((want, tool, value), None, cwd) for want, tool, value, cwd in build_cwd_cases()]
    failures = []
    try:
        for entry in cases:
            (want, tool, value), home = entry[0], entry[1]
            cwd = entry[2] if len(entry) > 2 else None
            got = run_hook(tool, value, home, cwd)
            if got != want:
                failures.append((want, got, tool, value))
    finally:
        shutil.rmtree(SANDBOX, ignore_errors=True)

    print(f"ケース数: {len(cases)}")
    for want, got, tool, value in failures:
        print(f"  NG 期待={want} 実際={got}  [{tool}] {value!r}")
    print(f"不一致: {len(failures)} 件")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
