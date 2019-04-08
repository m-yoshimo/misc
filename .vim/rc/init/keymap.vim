"--- 検索 -----------------
"" highlight のキャンセル
nnoremap <Esc><Esc> :nohlsearch<CR><Esc>

"--- window 操作 ----------
nnoremap s <Nop>
""---- 水平分割
nnoremap sn :<C-u>sp<CR>
""---- 垂直分割
nnoremap sv :<C-u>vs<CR>
""---- ウインドウ移動
nnoremap sj <C-w>j
nnoremap sk <C-w>k
nnoremap sl <C-w>l
nnoremap sh <C-w>h
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

"--- プラグインの keymapping
nnoremap <silent><C-l> :NERDTreeToggle<CR>
nnoremap <silent><C-m> :TlistToggle<CR>
