" 表示系プラグインの起動回り
""---- NERDTree と TlistToggle がバッティングするので纏める

" 起動処理
""---- 先に NERDTree を起動して左側に表示
""---- 次に taglist をウインドウ分割で右側に表示
""---- 最後にフォーカスを開いたファイルに移す
let Tlist_Use_Horiz_Window = 0
let Tlist_Use_Right_Window = 1
autocmd StdinReadPre * let s:std_in=1
autocmd VimEnter * if argc() == 1 && isdirectory(argv()[0]) && !exists("s:std_in") | exe 'NERDTree' argv()[0] | wincmd p | ene | exe 'cd '.argv()[0] | endif
autocmd VimEnter * execute 'NERDTree' | normal ss
autocmd VimEnter *.{py,js,rb,go,php} execute 'TlistToggle'

" 終了処理
autocmd bufenter * if (winnr("$") == 1 && exists("b:NERDTree") && b:NERDTree.isTabTree()) | q | endif
autocmd bufenter * if (winnr("$") == 2 && (bufname(winbufnr(1)) == "NERD_tree_1" || bufname(winbufnr(1)) == "__TAG_LIST__") && (bufname(winbufnr(2)) == "NERD_tree_1" || bufname(winbufnr(2)) == "__TAG_LIST__")) | q | endif
