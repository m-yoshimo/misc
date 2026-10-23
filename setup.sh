#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXTENSIONS_FILE="$SCRIPT_DIR/vscode-extensions.txt"

# =============================================================================
# 移行対象の定義
# =============================================================================
# ここが唯一の定義で、--dump（この PC → repo）と配布（repo → 新しい PC）の両方が
# これを読む。片方にしか書かないと必ず片側が漏れ、移行先の環境が一致しなくなる。
# 実際に 2026-10-23 時点で、repo 側の claude-hooks にはフックが 1 本しか無く、
# claude-memory は 9/11 に再編成する前の旧 14 ファイルのままだった。

# ~/.claude 配下のディレクトリ。repo では claude-<名前>/ に入る。
CLAUDE_DIRS=(memory hooks skills notes tasks)

# ~/.claude 直下のファイル。repo では claude-<名前> に入る。
CLAUDE_FILES=(settings.json keybindings.json)

# シェル・エディタの設定は、repo の実体へのシンボリックリンクで運用している
# （このマシンの現状がそうなっている）。コピーにすると repo を直してもホーム側が
# 古いまま残るため、リンクを維持する。書式は "ホーム側のパス:repo 内のパス"。
# `.vim` 自体はリンクにしない — ~/.vim には dein のプラグイン（118MB）や colors/ が
# あり、これはマシンごとのものなので、リンクするのは rc/ だけ。
HOME_SYMLINKS=(
  ".bashrc:.bashrc"
  ".vimrc:.vimrc"
  ".ctags:.ctags"
  ".ctags.d:.ctags.d"
  ".screenrc:.screenrc"
  ".vim/rc:.vim/rc"
)

# ディレクトリごとの rsync フィルタ。移さないものとその理由:
#   hooks/__pycache__/ … python が自動生成する。運ぶと別環境の .pyc が残る
#   skills/synced/     … アカウント側から自動同期される（4.6MB）。手で運ぶものではない
#   tasks/             … テンプレートだけ運ぶ。残りはそのマシンの作業内容
# なお rsync は --delete でも「除外したもの」は消さないので、移行先にあるその
# マシン固有のファイル（作業中のタスク定義書など）は残る。
set_filters() {
  FILTERS=()
  case "$1" in
    hooks)  FILTERS=(--exclude='__pycache__/') ;;
    skills) FILTERS=(--exclude='synced/') ;;
    tasks)  FILTERS=(--include='_TEMPLATE*.md' --exclude='*') ;;
  esac
}

if ! command -v rsync &>/dev/null; then
  echo "ERROR: rsync が必要です（sudo apt install rsync）" >&2
  exit 1
fi

# Windows 側のプロファイルディレクトリ（VSCode のユーザー設定の置き場）を求める。
# 🔴 %USERNAME% から組み立てないこと。このマシンでは %USERNAME%=m-yoshimo だが
# プロファイルは C:\Users\laink で、名前とディレクトリが一致しない（アカウント名を
# 変えた名残）。そのため従来は VSCode の設定を配布・書き出しの両方で取りこぼしていた。
win_profile_dir() {
  local wp drive rest
  wp=$(cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r\n')
  [ -n "$wp" ] || return 1
  drive=$(printf '%s' "${wp%%:*}" | tr 'A-Z' 'a-z')   # "C:" → "c"
  rest=${wp#*:}
  printf '%s\n' "/mnt/$drive${rest//\\//}"
}

# =============================================================================
# --dump : この PC の環境を repo に書き出す
# =============================================================================
# 手で repo を保守すると必ず陳腐化する（実際に 7 週間ずれた）ので、常にこれで書き出す。
if [ "$1" = "--dump" ]; then
  echo "=== この PC の環境を repo に書き出します ==="

  for d in "${CLAUDE_DIRS[@]}"; do
    if [ ! -d "$HOME/.claude/$d" ]; then
      echo "  SKIP ~/.claude/$d（このマシンに無い）"
      continue
    fi
    set_filters "$d"
    mkdir -p "$SCRIPT_DIR/claude-$d"
    rsync -a --delete "${FILTERS[@]}" "$HOME/.claude/$d/" "$SCRIPT_DIR/claude-$d/"
    echo "  claude-$d/ ($(find "$SCRIPT_DIR/claude-$d" -type f | wc -l) ファイル)"
  done

  for f in "${CLAUDE_FILES[@]}"; do
    if [ -f "$HOME/.claude/$f" ]; then
      cp "$HOME/.claude/$f" "$SCRIPT_DIR/claude-$f"
      echo "  claude-$f"
    else
      echo "  SKIP ~/.claude/$f（このマシンに無い）"
    fi
  done

  # シェル・エディタの設定は repo 側が実体で、ホームはそこへのリンク。
  # 書き出すものは無いので、リンクが生きているかだけ確かめる。
  for entry in "${HOME_SYMLINKS[@]}"; do
    home_rel="${entry%%:*}"
    repo_rel="${entry##*:}"
    if [ ! -e "$SCRIPT_DIR/$repo_rel" ]; then
      echo "  WARNING: repo に $repo_rel が無い（~/$home_rel の実体が別の場所にある）"
    elif [ "$(readlink -f "$HOME/$home_rel" 2>/dev/null)" = "$(readlink -f "$SCRIPT_DIR/$repo_rel")" ]; then
      echo "  $repo_rel（repo が実体。~/$home_rel から参照済み）"
    else
      echo "  WARNING: ~/$home_rel が repo の $repo_rel を指していない。手で確認してください"
    fi
  done

  # VSCode のユーザー設定は WSL ではなく Windows 側に置かれている。
  VSCODE_SETTINGS="$(win_profile_dir || true)/AppData/Roaming/Code/User/settings.json"
  if [ -f "$VSCODE_SETTINGS" ]; then
    cp "$VSCODE_SETTINGS" "$SCRIPT_DIR/vscode.setting.json"
    echo "  vscode.setting.json"
  else
    echo "  SKIP $VSCODE_SETTINGS（見つからない）"
  fi

  # 拡張機能の一覧は最後に取る。code の失敗でここまでの書き出しを捨てないため。
  # grep で publisher.name 形式だけ拾うのは、リモート接続時のみ先頭に
  # 「WSL: xxx にインストールされている拡張機能:」というヘッダー行が混じるため
  # （tail -n +2 だとローカル実行時に拡張機能を1個取りこぼす）。
  # 一時ファイル経由にするのは、code が失敗したときに復旧の起点である
  # EXTENSIONS_FILE を空で上書きしてしまうのを防ぐため。
  tmp=$(mktemp)
  if ! code --list-extensions | grep -E '^[A-Za-z0-9][A-Za-z0-9-]*\.[A-Za-z0-9]' | sort > "$tmp" || [ ! -s "$tmp" ]; then
    rm -f "$tmp"
    echo "ERROR: 拡張機能一覧を取得できませんでした（$EXTENSIONS_FILE は変更していません）" >&2
    exit 1
  fi
  mv "$tmp" "$EXTENSIONS_FILE"
  echo "  vscode-extensions.txt ($(wc -l < "$EXTENSIONS_FILE") 個)"

  echo "=== 書き出し完了。git で差分を確認してコミットしてください ==="
  exit 0
fi

# =============================================================================
# 配布 : repo の内容をこのマシンへ入れる
# =============================================================================

echo "=== 1. Claude の設定・ルール（memory / hooks / skills / notes / tasks） ==="
for d in "${CLAUDE_DIRS[@]}"; do
  if [ ! -d "$SCRIPT_DIR/claude-$d" ]; then
    echo "  SKIP claude-$d（repo に無い。./setup.sh --dump で作られます）"
    continue
  fi
  set_filters "$d"
  mkdir -p "$HOME/.claude/$d"
  # --delete は、repo 側で消したファイルを移行先に残さないため。
  # 残すと新旧が混ざる。memory を 9/11 に再編成したとき、旧 14 ファイルが残ると
  # 矛盾した内容のルールが両方 SessionStart で注入される状態になる。
  rsync -a --delete "${FILTERS[@]}" "$SCRIPT_DIR/claude-$d/" "$HOME/.claude/$d/"
  echo "  ~/.claude/$d/ ($(find "$HOME/.claude/$d" -type f | wc -l) ファイル)"
done

# permissions.additionalDirectories だけはマシンごとに違う（取引先のリポジトリの絶対パス）。
# repo が持っている値は書き出した PC のものなので、配るときにこのマシンの値へ置き換える。
# `$HOME/.claude/memory` は $HOME から決まるので入力させない。
# hooks 側は全て `$HOME/...` で書かれているため、ユーザー名の置換は要らない。
echo "=== 2. Claude settings ==="
mkdir -p "$HOME/.claude"
if ! command -v jq &>/dev/null; then
  echo "ERROR: jq が必要です（additionalDirectories の書き換えに使います）" >&2
  echo "       sudo apt install jq などで入れてから再実行してください" >&2
  exit 1
fi
EXTRA_DIRS=${CLAUDE_EXTRA_DIRS:-}
# -t 0 は、パイプや CI から実行したときに read で止まらないようにするための判定。
if [ -z "$EXTRA_DIRS" ] && [ -t 0 ]; then
  echo "  Claude に触らせる追加ディレクトリを入力してください（スペース区切り／無ければ空 Enter）"
  echo "  例: \$HOME/work/<取引先>/<リポジトリ>/.claude/tasks"
  read -r -p "  > " EXTRA_DIRS || EXTRA_DIRS=""
fi
EXTRA_DIR_LIST=("$HOME/.claude/memory")
# クォートしないのは、スペース区切りの入力を 1 件ずつに割るため（意図的）。
for dir in $EXTRA_DIRS; do
  # 先頭の `~` だけ自分で展開する（eval は入力をそのまま実行してしまうので使わない）
  case "$dir" in "~"/*) dir="$HOME/${dir#\~/}" ;; esac
  [ -d "$dir" ] || echo "  WARNING: $dir は存在しません（設定はこのまま追加します）"
  EXTRA_DIR_LIST+=("$dir")
done
# 一時ファイル経由にするのは、jq が失敗したときに settings.json を壊さないため。
tmp=$(mktemp)
if ! jq --argjson dirs "$(printf '%s\n' "${EXTRA_DIR_LIST[@]}" | jq -Rs 'split("\n") | map(select(length > 0))')" \
     '.permissions.additionalDirectories = $dirs' \
     "$SCRIPT_DIR/claude-settings.json" > "$tmp" || [ ! -s "$tmp" ]; then
  rm -f "$tmp"
  echo "ERROR: settings.json を生成できませんでした（$HOME/.claude/settings.json は変更していません）" >&2
  exit 1
fi
mv "$tmp" "$HOME/.claude/settings.json"
echo "  additionalDirectories: ${EXTRA_DIR_LIST[*]}"
echo "  Done"

echo "=== 3. Claude keybindings ==="
if [ -f "$SCRIPT_DIR/claude-keybindings.json" ]; then
  cp "$SCRIPT_DIR/claude-keybindings.json" "$HOME/.claude/keybindings.json"
  echo "  Done"
else
  echo "  SKIP（repo に無い。./setup.sh --dump で作られます）"
fi

# anyenv の手順より前に置く。anyenv は .bashrc に追記するので、後から .bashrc を
# 上書きするとその追記が消える。
echo "=== 4. シェル・エディタの設定（repo へのリンクを張る） ==="
STAMP=$(date +%Y%m%d-%H%M%S)
for entry in "${HOME_SYMLINKS[@]}"; do
  home_rel="${entry%%:*}"
  repo_rel="${entry##*:}"
  src="$SCRIPT_DIR/$repo_rel"
  dst="$HOME/$home_rel"
  if [ ! -e "$src" ]; then
    echo "  SKIP $home_rel（repo に $repo_rel が無い）"
    continue
  fi
  mkdir -p "$(dirname "$dst")"
  if [ -L "$dst" ]; then
    ln -sfn "$src" "$dst"                 # 既存のリンクは張り替える
  elif [ -e "$dst" ]; then
    # 実体がある場合は消さずに退避してからリンクにする。
    # 移行先に元から入っていた設定を失わないため。
    mv "$dst" "$dst.bak-$STAMP"
    echo "  退避: ~/$home_rel.bak-$STAMP"
    ln -s "$src" "$dst"
  else
    ln -s "$src" "$dst"
  fi
  echo "  ~/$home_rel -> $src"
done

echo "=== 5. VSCode user settings ==="
VSCODE_SETTINGS_DIR="$(win_profile_dir || true)/AppData/Roaming/Code/User"
if [ -d "$VSCODE_SETTINGS_DIR" ]; then
  if [ -f "$VSCODE_SETTINGS_DIR/settings.json" ]; then
    cp "$VSCODE_SETTINGS_DIR/settings.json" "$VSCODE_SETTINGS_DIR/settings.json.bak-$(date +%Y%m%d-%H%M%S)"
  fi
  cp "$SCRIPT_DIR/vscode.setting.json" "$VSCODE_SETTINGS_DIR/settings.json"
  echo "  Copied to $VSCODE_SETTINGS_DIR/settings.json"
else
  echo "  WARNING: $VSCODE_SETTINGS_DIR が見つかりません"
  echo "  手動でコピー: cp $SCRIPT_DIR/vscode.setting.json '<Windows のプロファイル>/AppData/Roaming/Code/User/settings.json'"
fi

echo "=== 6. VSCode extensions ==="
if [ ! -f "$EXTENSIONS_FILE" ]; then
  echo "  WARNING: $EXTENSIONS_FILE が無いためスキップ（./setup.sh --dump で作成できます）"
  EXTENSIONS=()
else
  mapfile -t EXTENSIONS < "$EXTENSIONS_FILE"
fi
for ext in "${EXTENSIONS[@]}"; do
  code --install-extension "$ext" --force 2>/dev/null && echo "  $ext" || echo "  WARN: $ext のインストール失敗（後で手動で）"
done

echo "=== 7. anyenv ==="
if command -v anyenv &>/dev/null || [ -d "$HOME/.anyenv" ]; then
  echo "  すでにインストール済み、スキップ"
else
  git clone https://github.com/anyenv/anyenv "$HOME/.anyenv"
  echo 'export PATH="$HOME/.anyenv/bin:$PATH"' >> "$HOME/.bashrc"
  echo 'eval "$(anyenv init -)"' >> "$HOME/.bashrc"
  "$HOME/.anyenv/bin/anyenv" install --init -f
  echo "  anyenv インストール完了。シェルを再起動してから anyenv install <env> で各ランタイムを入れてください"
fi

echo ""
echo "=== 完了 ==="
echo "VSCode と shell を再起動してください"
echo ""
echo "Claude Code は別途ログインが必要です（認証情報は repo に入れていません）"
echo "プラグイン（gopls / vtsls の LSP）は初回起動時に marketplace から取得されます"
