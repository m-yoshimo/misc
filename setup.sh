#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== 1. Claude memory ==="
mkdir -p "$HOME/.claude/memory"
cp -r "$SCRIPT_DIR/claude-memory/"* "$HOME/.claude/memory/"
echo "  Done"

echo "=== 2. Claude settings ==="
mkdir -p "$HOME/.claude"
cp "$SCRIPT_DIR/claude-settings.json" "$HOME/.claude/settings.json"
echo "  Done"

echo "=== 3. VSCode user settings ==="
WIN_USER=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n')
VSCODE_SETTINGS_DIR="/mnt/c/Users/$WIN_USER/AppData/Roaming/Code/User"
if [ -d "$VSCODE_SETTINGS_DIR" ]; then
  cp "$SCRIPT_DIR/vscode.setting.json" "$VSCODE_SETTINGS_DIR/settings.json"
  echo "  Copied to $VSCODE_SETTINGS_DIR/settings.json"
else
  echo "  WARNING: $VSCODE_SETTINGS_DIR が見つかりません"
  echo "  手動でコピー: cp $SCRIPT_DIR/vscode.setting.json /mnt/c/Users/<username>/AppData/Roaming/Code/User/settings.json"
fi

echo "=== 4. VSCode extensions ==="
EXTENSIONS=(
  anthropic.claude-code
  arjun.swagger-viewer
  darkriszty.markdown-table-prettify
  dbaeumer.vscode-eslint
  editorconfig.editorconfig
  esbenp.prettier-vscode
  formulahendry.vscode-mysql
  github.vscode-pull-request-github
  golang.go
  hashicorp.terraform
  humao.rest-client
  mermade.openapi-lint
  ms-ceintl.vscode-language-pack-ja
  ms-python.debugpy
  ms-python.isort
  ms-python.python
  ms-python.vscode-pylance
  ms-python.vscode-python-envs
  redhat.vscode-yaml
  shardulm94.trailing-spaces
  shd101wyy.markdown-preview-enhanced
  streetsidesoftware.code-spell-checker
  uctakeoff.vscode-counter
  vitest.explorer
  yzhang.markdown-all-in-one
)
for ext in "${EXTENSIONS[@]}"; do
  code --install-extension "$ext" --force 2>/dev/null && echo "  $ext" || echo "  WARN: $ext のインストール失敗（後で手動で）"
done

echo "=== 5. anyenv ==="
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
