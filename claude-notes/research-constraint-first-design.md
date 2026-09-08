# 調査レポート: 「制約を優先する設計思想」の理論的裏付けと適用基準

- 作成日: 2026-07-08
- 調査手法: deep-research ハーネス（5検索角度に fan-out → 22ソース取得 → 95主張抽出 → 上位25主張を3票の敵対的検証、2/3で棄却）
- 検証統計: 25主張を検証 → **25 confirmed / 0 refuted / 0 unverified**、統合後5ファインディング
- 中心命題（＝検証対象の直観）:
  - 「実装とは、動く範囲を広げることではなく、動いてはいけない範囲を型やインターフェースで塞ぐ（＝制約を付ける）ことである」
  - 「汎用性・再利用性を上げるほど、可読性は落ち、誤用の余地が増え、変更の影響範囲が広がる」

---

## エグゼクティブサマリ

**「制約 > 汎用性」という直観は、確立した設計理論によって広く・強く裏付けられる**（言語非依存の一般原則として）。一方、**「いつ共通化（抽象化）に踏み切るか」の境界は、理論では割り切れず経験則が残る**。

- **裏付けが強い側（問1）**: 型で不正を表現不能にする（Parse, don't validate / Make illegal states unrepresentable）、最小表現力の原則（Least Power）、情報隠蔽（Parnas）、誤用不能なインターフェース（Meyers）——いずれも一次資料で確認。
- **対立軸がある側（問2）**: 「制約・重複許容」派（Metz「間違った抽象は重複よりはるかに高い」／ Dodds AHA）と「DRY・共通化」派の対立。理論的には**早計な抽象を戒める側の主張が強い**が、閾値（何箇所で共通化するか）は Rule of Three 的な経験則。
- **手薄だった側（問3）**: 「制約の付けすぎ／過剰抽象」の境界は、独立した一次資料での裏付けが今回は弱く、主に AHA/Wrong Abstraction 経由でのみ支持された（正直に区別する）。

---

## 第1部: 「制約 > 汎用性」を裏付ける原則（問1）

### 1-1. Parse, don't validate / Make illegal states unrepresentable（型で不正を表現不能にする）

- **主張**: 実行時に検証して弾く（validate＝`()` を返し、得た知識を捨てる）のではなく、境界で入力を**一度だけ最も精密な型へパース**する（parse＝`NonEmpty a` のような精緻型を返し、得た保証を型に保持する）。引数の型を強めることで、不変条件の証明責任を呼び出し側に移し、違反を**実行時の暗黙のバグからコンパイルエラーへ**変える。Minsky は状態を discriminated union（各 variant が自身に関係するフィールドだけを持つ）で表し、optional フィールドの組合せが生む「不可能な状態」を排除する。
- **この直観をどこまで裏付けるか**: **中心命題を直接裏付ける**。「動いてはいけない範囲を型で塞ぐ」の最も具体的な方法論。
- **一次出典**:
  - Alexis King, "Parse, don't validate" (2019) — 『Use a data structure that makes illegal states unrepresentable』『Get your data into the most precise representation ... at the boundary of your system』『main will fail to typecheck, alerting us to the problem before we even run the program』
  - Yaron Minsky, "Effective ML Revisited" (Jane Street) — 『Make illegal states unrepresentable』を節見出しとして使用。optional フィールドの record を per-state variant（connecting/connected/disconnected）へリファクタする例。
  - ※留意: マキシムの初出は Minsky の2010年講演 "Effective ML"。上記記事はその follow-up（一次だが最初の発話ではない）。

### 1-2. Rule / Principle of Least Power（最小表現力の原則）

- **主張**: 目的に足る**最も表現力の低い（最も制約された）言語を選べ**。制約を「限界」ではなく「可能性を広げる有効化装置」と位置づける。表現力／計算能力が上がるほど解析可能性は下がり（Turing 完全な言語は一般に実行しないと挙動が分からない）、逆に制約された宣言的言語は静的解析・情報の再利用・安全性を高める。『言語の力が弱いほど、そのデータで出来ることは増える』。
- **この直観をどこまで裏付けるか**: 「汎用性↑ → 解析可能性・安全性↓」を**理論的に説明**（停止性問題・Rice の定理が背景）。
- **限定・留意**: ここでの "power" は主に**計算能力／Turing 完全性**を指す。研究課題が言う「汎用性・再利用性（＝コード再利用）」とは概念がずれる。W3C 文書の "reuse" は Web 情報の機械可読な再利用であり、DRY 文脈のコード共通化とは厳密には別物。この対応付けは**合理的だが解釈上の拡張**。また「Turing 完全＝解析不能」という表現は絶対的すぎる（Rice の定理が禁じるのは普遍的決定手続きであり、個々のプログラムの解析は可能）。
- **一次出典**: W3C TAG, "The Rule of Least Power" (Berners-Lee & Mendelsohn) — 『Use the least powerful language suitable for expressing information, constraints or programs on the World Wide Web』『the less powerful the language, the more you can do with the data』

### 1-3. 情報隠蔽（Parnas, 1972）

- **主張**: モジュール分割は処理手順のフローチャートからではなく、『**難しい／変わりやすい設計判断のリスト**』から始め、各モジュールが1つの判断を他から隠すよう設計する（ゆえにモジュールは処理ステップに対応しない）。隠した判断（例: 行の格納方法）の変更は**単一モジュールに封じ込められる**のに対し、フローチャート分割では同じ変更が全モジュールに波及する。インターフェースは内部を極力見せないよう選び、**必要以上の仕様公開（例: 不要なシフト順序の規定）は「作れるシステムの範囲を不必要に制限する」ため明確に『設計上の誤り(design error)』**。
- **この直観をどこまで裏付けるか**: 「制約（隠蔽）は変更の影響範囲を閉じ込める」「過剰な公開は誤り」を**古典論文が正面から支持**。中心命題の「変更の影響範囲が広がる」に直結。
- **一次出典**: David L. Parnas, "On the Criteria To Be Used in Decomposing Systems into Modules", CACM 15(12), 1972 — 『We propose instead that one begins with a list of difficult design decisions or design decisions which are likely to change』『Any change in the manner of storage can be confined to that module!』『its interface ... was chosen to reveal as little as possible about its inner workings』『unnecessarily restricted the class of systems ... must clearly be classified as a design error』

### 1-4. 誤用不能なインターフェース設計（Meyers, 2004）

- **主張**: 最も重要な一般的インターフェース設計指針は『**Make interfaces easy to use correctly and hard to use incorrectly**』。**誤用の責任は利用者ではなく設計者にある**（利用者が誤用できたなら、それは簡単に誤れる設計だったから）。制約は**新しい型を定義して誤用を不能化**することで実現する（例: Day/Month/Year を別型にして引数順序の取り違えを防ぐ／Month を12個の不変定数だけに限定して不正な月を表現不能にする）。
- **この直観をどこまで裏付けるか**: 「制約された設計は誤用を不能にする」を**直接支持**。今回の GN-5832 で「`Scope<Plan>` を meter 点に適用したらコンパイルエラー」にしたのと同じ発想。
- **一次出典**: Scott Meyers, "The Most Important Design Guideline?", IEEE Software, Jul/Aug 2004 — 『responsibility for interface usage errors belongs to the interface designer, not the interface user』『Creating separate types for days, months, and years can eliminate the ordering errors』
- **留意**: 単一の一次資料（著者本人の原典）に依拠。ただし広く引用され対立情報なし。

---

## 第2部: 「制約 vs DRY／共通化」の対立軸（問2）

**確認された対立軸**: 「重複を許容し早計な抽象を避ける」派 vs 「DRY で共通化する」派。今回の検証では**前者（重複許容）側の主張が一次資料で強く支持された**。

- **Sandi Metz, "The Wrong Abstraction" (2016)**: 『**duplication is far cheaper than the wrong abstraction**』『**prefer duplication over the wrong abstraction**』。間違った抽象は、後続の開発者が要件差異をパラメータと条件分岐で押し込むことで腐敗が累積する。処方箋は『前に進む最速の道は後退する』＝**抽象をインライン展開して重複に戻す**こと。
- **Kent C. Dodds, "AHA Programming" (2019)**: AHA = Avoid Hasty Abstractions。『**Optimize for change first**』『write the abstraction when it feels right and don't be afraid to duplicate code until you get there』『After you've got a few places where that code is running, the commonalities will scream at you for abstraction』。Metz を明示的に引用し中核に据える。
- **境界は経験則**: 「いつ抽象化するか」の閾値は、Dodds は数値でなく『a few places』『feels right』と述べる。数値化（2〜3箇所）は **Fowler の Rule of Three 由来**であり、**理論というより経験則**。

> このセッションへの含意: `matchesMeterReadPoint` と `matchesPlanPoint` で boothName 判定を重複させたまま残した判断は、Metz/Dodds の立場から**理論的に正当**（早計な共通化＝間違った抽象を避けた）。

### 未確認（今回の生存クレームに含まれず、要追加調査）
- **DRY の原義**: Hunt & Thomas "The Pragmatic Programmer" における DRY は「コードの重複」ではなく「**知識(knowledge)の重複**」の排除である、という原点の正確な定義。→ 書籍該当箇所での一次確認が未達。

---

## 第3部: 「制約の付けすぎ／過剰抽象」の境界（問3）

**正直な状態**: この軸は、独立した一次資料での裏付けが今回は手薄。主に AHA/Wrong Abstraction 経由でのみ支持された。以下は検索では出典が挙がったが、生存クレームとしては十分に検証しきれていない（＝**経験則寄り**として扱う）:

- **YAGNI (Fowler)**: 憶測（speculative）機能は4つのコストを負う — cost of build / cost of delay / cost of carry / cost of repair。「今必要か、将来の憶測か」を問う枠組み。
- **Speculative Generality (Fowler の code smell)**: 「いつか使うかも」で導入した汎用性・間接参照は負債。
- **認知負荷（cognitive load）**: 抽象・間接参照は読み手の追跡コストを増やす。可読性とのトレードオフ。
- **A Philosophy of Software Design (Ousterhout)**: 複雑性・深いモジュール等の観点（今回未検証）。

> このセッションへの含意: scopes 方式を「制約は強いがレンダリング（安定参照責任の分散）で保守性を損なう」として退けた判断は、まさにこの「別の軸を損なう過剰制約」の回避に当たる。ただしこの線引きの**一般的指針を述べた一次資料は今回特定できていない**（下記 openQuestion）。

---

## 実務チェックリスト（理論から導けた範囲。★＝一次資料の裏付けあり／☆＝経験則）

### A. 制約を付けるべきか（型・インターフェースを絞るか）
1. ★ この不変条件を破る呼び出しを、**コンパイル時に不能**にできるか？（Meyers: hard to use incorrectly ／ Minsky: illegal states unrepresentable）
2. ★ 境界（入力・API）で**最精密型に一度パース**しているか、各所で検証を繰り返していないか？（King: parse, don't validate）
3. ★ インターフェースは内部判断を**隠して**いるか、必要以上に公開して将来の実装自由度を狭めていないか？（Parnas: over-specify は design error）
4. ★ 目的に対して**過剰な表現力**を与えていないか？（Least Power ※計算能力の文脈からの拡張解釈）

### B. 共通化すべきか／重複を許すか
5. ☆ その重複は「**同じ知識**」か「たまたま同じ形」か？ 知識の重複だけが DRY の対象（※原義は要一次確認）
6. ★ 抽象は「今 **feels right**」か、それとも将来予測で先回りしているか？（Dodds: optimize for change first）
7. ☆ 出現は**3箇所以上**か？（Rule of Three ＝経験則）
8. ★ 後から要件差異が来たとき、この抽象はパラメータ・条件分岐で**腐敗**しないか？ **迷うなら重複を選ぶ**（Metz）

### C. 過剰制約・過剰抽象になっていないか
9. ☆ その制約・抽象は、**別の軸**（拡張の柔軟性・パフォーマンス・レンダリング・認知負荷）を損なっていないか？（← scopes 却下の判断軸。一般指針の一次資料は未特定）
10. ☆ その汎用性は**今必要**か、将来の憶測か？（YAGNI: build/delay/carry/repair の4コスト）

---

## 留意点（caveats）
1. 時間非依存性は高い（対象は設計哲学・古典論文: Parnas 1972 / W3C 2006 / Meyers 2004 / Minsky 2011 / King 2019 / Metz 2016 / Dodds 2019）。陳腐化の懸念はほぼない。
2. Meyers の項は単一の一次資料（著者本人の原典）に依拠。
3. Least Power の "power" は主に計算能力を指し、「コード汎用性・再利用」への一般化は**解釈上の拡張**。
4. 「Turing 完全＝解析不能」の表現は絶対化しすぎ（禁じられるのは普遍的決定手続き）。substance（表現力↑→解析可能性↓）は正しい。
5. **中心命題「制約>汎用性」を反証する一次資料は見つからなかった**が、これは「反証の不在」であって網羅的探索の結果ではない。問3（付けすぎ側の境界）は裏付けが手薄。

## 未解決の問い（追加調査候補）
1. 「過剰抽象の境界」を、YAGNI・認知負荷・speculative generality の**独立した一次資料**で直接裏付けられるか。
2. **DRY の原義**（知識の重複 vs コードの重複）を書籍該当箇所で一次確認。
3. Rule of Three の原典（Fowler, Refactoring）での正確な定式化と、AHA の『feels right』との差異（数値で切るか感覚で切るか）。
4. Least Power の「power=計算能力」を、型の表現力・API の汎用性へ橋渡しする学術資料の有無。
5. 「制約が強い設計が別の軸を損なう場合の優先順位」を述べた一次資料の特定（問3後半・チェックリスト9番の裏付け）。

---

## 参考文献（一次資料を優先）

**問1（制約 > 汎用性）**
- Alexis King, "Parse, don't validate" (2019) — https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/ 〔primary〕
- Yaron Minsky, "Effective ML Revisited" (Jane Street) — https://blog.janestreet.com/effective-ml-revisited/ 〔primary〕
- W3C TAG, "The Rule of Least Power" — https://www.w3.org/2001/tag/doc/leastPower.html 〔primary〕
- D. L. Parnas, "On the Criteria To Be Used in Decomposing Systems into Modules", CACM 1972 — https://dl.acm.org/doi/10.1145/361598.361623 〔primary〕（PDF: https://www.win.tue.nl/~wstomv/edu/2ip30/references/criteria_for_modularization.pdf ）
- Scott Meyers, "The Most Important Design Guideline?", IEEE Software 2004 — https://www.aristeia.com/Papers/IEEE_Software_JulAug_2004_revised.htm 〔primary〕

**問2（制約 vs DRY）**
- Sandi Metz, "The Wrong Abstraction" (2016) — https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction 〔primary〕
- Kent C. Dodds, "AHA Programming" (2019) — https://kentcdodds.com/blog/aha-programming 〔primary〕
- Rule of Three (参考) — https://en.wikipedia.org/wiki/Rule_of_three_(computer_programming) 〔secondary〕
- DRY (参考) — https://en.wikipedia.org/wiki/Don't_repeat_yourself 〔secondary〕

**問3（過剰制約・過剰抽象の境界）**
- Martin Fowler, "Yagni" — https://martinfowler.com/bliki/Yagni.html 〔primary〕
- Martin Fowler, Refactoring catalog（Speculative Generality 等）— https://refactoring.com/catalog/ 〔primary〕
- John Ousterhout, "A Philosophy of Software Design"（参考）— https://web.stanford.edu/~ouster/cgi-bin/aphilosophyofsoftwaredesign.php 〔primary〕
- "Cognitive Load"（参考）— https://github.com/zakirullin/cognitive-load 〔blog〕

**補助的に参照した二次・ブログ資料**
- Rusty Russell, "API Design Manifesto"（API design levels）— https://rusty.ozlabs.org/?p=140 〔blog〕
- The Morning Paper: Parnas 解説 — https://blog.acolyer.org/2016/09/05/on-the-criteria-to-be-used-in-decomposing-systems-into-modules/ 〔secondary〕
