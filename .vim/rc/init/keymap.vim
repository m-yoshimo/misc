"- 検索 -----------------
"" highlight のキャンセル
nnoremap <Esc><Esc> :nohlsearch<CR><Esc>

"- window 操作 ----------
nnoremap s <Nop>
""-- 水平分割
nnoremap sn :<C-u>sp<CR>
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
nnoremap s. <C-w>>
nnoremap s, <C-w><
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
inoremap <expr><tab> pumvisible() ? "\<C-n>" :
  \ neosnippet#expandable_or_jumpable() ?
  \    "\<Plug>(neosnippet_expand_or_jump)" : "\<tab>"

imap <C-k>     <Plug>(neosnippet_expand_or_jump)
smap <C-k>     <Plug>(neosnippet_expand_or_jump)
xmap <C-k>     <Plug>(neosnippet_expand_target)

smap <expr><TAB> neosnippet#expandable_or_jumpable() ?
  \ "\<Plug>(neosnippet_expand_or_jump)" : "\<TAB>"

""---- CtrlP
let g:ctrlp_map = '<C-s>'  "<C-p> は paste モード切替で頻繁に使うので <C-s> をアサイン
let g:ctrlp_cmd = 'CtrlP'

""---- tagbar keymapping
let g:tagbar_map_togglesort = "r"
let g:tagbar_map_togglefold = ";"

