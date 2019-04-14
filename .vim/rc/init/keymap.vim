"--- Key Mapping Description ----------------
" Window 操作
"   sm : 水平分割
"   sv : 垂直分割
"   ss : 次に移動
"   si : 上に移動
"   sn : 下に移動
"   sl : 右に移動
"   sh : 左に移動
"   s0 : ウインドウサイズ初期化
"   s; : 高さ +1
"   s- : 高さ -1
"   s, : 横幅 +1
"   s. : 横幅 -1
"
" 設定・表示切り替え
"   <C-e> : タブ入力時の space/tab 切替 (デフォルト space)
"   <C-p> : ペーストモード切替
"   <Esc><Esc> : ハイライトのキャンセル
"   <C-n> : フォルダツリー表示・非表示切替
"   <C-m> : 関数一覧表示・非表示切替
"
" 検索
"   <C-s> : ファイル検索
"
" ジャンプ
"   <C-Up>   : 前の Lint Error/Warning
"   <C-Down> : 次の Lint Error/Warning
"
" 関数一覧
"   ;       : 関数 fold を開閉
"   <Enter> : 関数ジャンプ
"
" オートコンプリート
"   <C-k>   : スニペットの展開


"- 検索 -----------------
"" highlight のキャンセル
nnoremap <Esc><Esc> :nohlsearch<CR><Esc>

"- window 操作 ----------
nnoremap s <Nop>
""-- 水平分割
nnoremap sm :<C-u>sp<CR>
""-- 垂直分割
nnoremap sv :<C-u>vs<CR>
""-- ウインドウ移動
"""--- 下に移動
nnoremap sn <C-w>j
"""--- 上に移動
nnoremap si <C-w>k
"""--- 右に移動
nnoremap sl <C-w>l
"""--- 左に移動
nnoremap sh <C-w>h
"""--- 次に移動
nnoremap ss <C-w>w
""---- ウインドウサイズ初期化
nnoremap s0 <C-w>=
""---- ウインドウサイズ変更 (vim-submode 使ってみたい)
nnoremap s, <C-w>>
nnoremap s. <C-w><
nnoremap s; <C-w>+
nnoremap s- <C-w>-

"--- オートコンプリート ---

"--- その他 ---------------
""---- expandtab 設定の on/off (default on)
nnoremap <C-e> :set expandtab!<CR>
""---- ペーストモード切替
nnoremap <C-p> :set paste!<CR>

"--- プラグインの keymapping
nnoremap <silent><C-n> :NERDTreeToggle<CR>
nnoremap <silent><C-m> :TagbarToggle<CR>
" Tagbar 非表示時に Enter 押すと Tagbar 表示に hook されるので無効にする
nnoremap <ENTER> j

""---- deoplete/neosnippet
imap <expr><Down>
  \ pumvisible() ? "\<C-n>" :
  \ neosnippet#expandable_or_jumpable() ?
  \    "\<Plug>(neosnippet_expand_or_jump)" : "\<Down>"

imap <expr><Up>
  \ pumvisible() ? "\<C-p>" :
  \ neosnippet#expandable_or_jumpable() ?
  \    "\<Plug>(neosnippet_expand_or_jump)" : "\<Up>"

imap <C-k>     <Plug>(neosnippet_expand_or_jump)
smap <C-k>     <Plug>(neosnippet_expand_or_jump)
xmap <C-k>     <Plug>(neosnippet_expand_target)

""---- CtrlP
let g:ctrlp_map = '<C-s>'  "<C-p> は paste モード切替で頻繁に使うので <C-s> をアサイン
let g:ctrlp_cmd = 'CtrlP'

""---- Tagbar
let g:tagbar_map_togglesort = "r"
let g:tagbar_map_togglefold = ";"

""---- ALE
nnoremap <silent> <C-Up> <Plug>(ale_previous_wrap)
nnoremap <silent> <C-Down> <Plug>(ale_next_wrap)
