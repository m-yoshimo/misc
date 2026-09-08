#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXTENSIONS_FILE="$SCRIPT_DIR/vscode-extensions.txt"

# 現在の環境を EXTENSIONS_FILE に書き出す。手で一覧を保守すると必ず陳腐化するため。
# grep で publisher.name 形式だけ拾うのは、リモート接続時のみ先頭に
# 「WSL: xxx にインストールされている拡張機能:」というヘッダー行が混じるため
# （tail -n +2 だとローカル実行時に拡張機能を1個取りこぼす）。
if [ "$1" = "--dump" ]; then
  # 一時ファイル経由にするのは、code が失敗したときに復旧の起点である
  # EXTENSIONS_FILE を空で上書きしてしまうのを防ぐため。
  tmp=$(mktemp)
  if ! code --list-extensions | grep -E '^[A-Za-z0-9][A-Za-z0-9-]*\.[A-Za-z0-9]' | sort > "$tmp" || [ ! -s "$tmp" ]; then
    rm -f "$tmp"
    echo "ERROR: 拡張機能一覧を取得できませんでした（$EXTENSIONS_FILE は変更していません）" >&2
    exit 1
  fi
  mv "$tmp" "$EXTENSIONS_FILE"
  echo "書き出し完了: $EXTENSIONS_FILE ($(wc -l < "$EXTENSIONS_FILE") 個)"
  exit 0
fi

echo "=== 1. Claude memory ==="
mkdir -p "$HOME/.claude/memory"
cp -r "$SCRIPT_DIR/claude-memory/"* "$HOME/.claude/memory/"
echo "  Done"

echo "=== 2. Claude settings ==="
mkdir -p "$HOME/.claude"
cp "$SCRIPT_DIR/claude-settings.json" "$HOME/.claude/settings.json"
echo "  Done"

echo "=== 3. Claude skills ==="
mkdir -p "$HOME/.claude/skills"
cp -r "$SCRIPT_DIR/claude-skills/"* "$HOME/.claude/skills/"
echo "  Done"

# notes は design-review 系スキルが参照するレビュー基準の実体
# （design_review_rubric.md / design_philosophy.md / design-review-v2/）。
# スキルだけ入れても notes が無いとレビューが基準なしで走る。
echo "=== 4. Claude notes ==="
mkdir -p "$HOME/.claude/notes"
cp -r "$SCRIPT_DIR/claude-notes/"* "$HOME/.claude/notes/"
echo "  Done"

# hooks と tasks/_TEMPLATE.md は claude-settings.json の PostToolUse から
# 呼ばれる taskdef_review_prompt.py とその参照先。3点セットで揃わないと機能しない。
echo "=== 5. Claude hooks ==="
mkdir -p "$HOME/.claude/hooks"
cp -r "$SCRIPT_DIR/claude-hooks/"* "$HOME/.claude/hooks/"
echo "  Done"

echo "=== 6. Claude task template ==="
mkdir -p "$HOME/.claude/tasks"
cp -r "$SCRIPT_DIR/claude-tasks/"* "$HOME/.claude/tasks/"
echo "  Done"

echo "=== 7. VSCode user settings ==="
WIN_USER=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n')
VSCODE_SETTINGS_DIR="/mnt/c/Users/$WIN_USER/AppData/Roaming/Code/User"
if [ -d "$VSCODE_SETTINGS_DIR" ]; then
  cp "$SCRIPT_DIR/vscode.setting.json" "$VSCODE_SETTINGS_DIR/settings.json"
  echo "  Copied to $VSCODE_SETTINGS_DIR/settings.json"
else
  echo "  WARNING: $VSCODE_SETTINGS_DIR が見つかりません"
  echo "  手動でコピー: cp $SCRIPT_DIR/vscode.setting.json /mnt/c/Users/<username>/AppData/Roaming/Code/User/settings.json"
fi

echo "=== 8. VSCode extensions ==="
if [ ! -f "$EXTENSIONS_FILE" ]; then
  echo "  WARNING: $EXTENSIONS_FILE が無いためスキップ（./setup.sh --dump で作成できます）"
  EXTENSIONS=()
else
  mapfile -t EXTENSIONS < "$EXTENSIONS_FILE"
fi
for ext in "${EXTENSIONS[@]}"; do
  code --install-extension "$ext" --force 2>/dev/null && echo "  $ext" || echo "  WARN: $ext のインストール失敗（後で手動で）"
done

echo "=== 9. anyenv ==="
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
