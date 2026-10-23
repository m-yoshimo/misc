#!/usr/bin/env python3
"""ユーザーが削除に触れたターンだけ、`rm` の実行を通すための許可を記録する。

`UserPromptSubmit` フックとして動く（配線は `~/.claude/settings.json`）。
判定するのは `PreToolUse`（`rule_guard.py` の `check_rm`）で、ここは**記録だけ**。

## なぜこの形か（2026-09-17 ユーザー指示）

- **`rm` はどのフックでも止まっていなかった。** SAFE-09 が「取り返しがつかないものは実行しない」と
  定めているだけで、機械的な歯止めが無かった。サブエージェントにはルール本文が届かない（FLOW-22）ので、
  **ワーカーにとって `rm` を止めるものが何も無い**状態だった。
- **ただしユーザーが事前に許可したときは止めない**、というのが要件。
- 🔴 **許可の記録を Claude に書かせない。** Claude が「許可された」と書けば通る仕組みでは、
  SAFE-07 が禁じている自己例外化そのものになる。**書けるのはユーザーの発言だけ**にする。
- **合図の文言を決めてユーザーに覚えさせる案は取り下げた**（2026-09-17「面倒くさ」）。
  **ふだん使う言葉（消して／削除／rm）がそのまま許可になる。**

## 有効範囲

- **そのターンだけ。** 次のユーザー発言に削除の意図が無ければ、許可は消える
- **サブエージェントにも効く。** 許可は `session_id` で記録し、ワーカーの `PreToolUse` も
  同じ `session_id` を持つ（2026-09-17 に `cli.js` 2.1.81 の `Fw()` で確認）
"""

import json
import os
import re
import sys
import time

STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", "rm_grant")
STATE_TTL_DAYS = 7

# ふだんの言い方をそのまま拾う。**ここに無い言い方だと `rm` は止まる**が、
# そのときは「フックに止められた」と報告して確認すればよい（deny の理由文にそう書いてある）。
DELETE_INTENT = re.compile(
    r"削除|消[しすせさ]|捨て|クリーンアップ|片づけ|片付け"
    r"|(?<![\w./-])rm\b|(?<![\w./-])rmdir\b|(?<![\w./-])unlink\b"
)

# 🔴 2026-10-22 ユーザー指示「research に（ルール読み込みを）省くオプションを付けろ、
# ただしこのオプションが僕が明示的にルール不要といった時だけ使えるようにしろ」。
# 調査役にルール本文（実測 274,261 バイト）を読ませない許可。**ここに記録できるのはユーザーの発言だけ**で、
# Claude 側から書く経路は無い（自己例外化の禁止・SAFE-07）。`build_prompt.py --no-rules` がこの記録を見る。
NO_RULES_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", "no_rules_grant")
NO_RULES_INTENT = re.compile(
    r"ルール(?:は|を|の)?(?:読み込み|読込|読み|読ま)?(?:は)?(?:不要|いらな|要らな|なしで|無しで|抜きで)"
    r"|ルール(?:は|を)?(?:読ま|読み込ま)(?:なくて|無くて)(?:いい|良い|よい|ok|OK)"
    r"|(?:ルール|memory|メモリ)(?:の)?(?:読み込み|読込)(?:は)?(?:スキップ|省略|不要)"
)


def state_path(session_id: str, state_dir: str = None) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")
    return os.path.join(state_dir or STATE_DIR, f"{safe}.json")


def sweep() -> None:
    """自分が作った記録だけを掃除する（META-01 と同じ考え方）。"""
    limit = time.time() - STATE_TTL_DAYS * 86400
    try:
        names = os.listdir(STATE_DIR)
    except OSError:
        return
    for name in names:
        path = os.path.join(STATE_DIR, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < limit:
                os.remove(path)
        except OSError:
            continue


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    prompt = data.get("prompt") or ""
    path = state_path(data.get("session_id") or "")

    if DELETE_INTENT.search(prompt):
        sweep()
        os.makedirs(STATE_DIR, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(
                    {"granted_at": time.time(), "prompt": prompt[:200]},
                    fh,
                    ensure_ascii=False,
                )
        except OSError:
            pass
    else:
        # 削除に触れていないターンに入った時点で失効させる
        try:
            os.remove(path)
        except OSError:
            pass

    # ルール読み込みを省く許可（`build_prompt.py research --no-rules`）。有効範囲は `rm` と同じ「そのターンだけ」
    no_rules = state_path(data.get("session_id") or "", NO_RULES_DIR)
    if NO_RULES_INTENT.search(prompt):
        os.makedirs(NO_RULES_DIR, exist_ok=True)
        try:
            with open(no_rules, "w", encoding="utf-8") as fh:
                json.dump({"granted_at": time.time(), "prompt": prompt[:200]}, fh, ensure_ascii=False)
        except OSError:
            pass
    else:
        try:
            os.remove(no_rules)
        except OSError:
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()
