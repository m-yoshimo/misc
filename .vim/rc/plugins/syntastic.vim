"--- syntastic
let g:syntastic_check_on_open=0 "ファイルを開いたときはチェックしない
let g:syntastic_check_on_save=1 "保存時にはチェック
let g:syntastic_check_on_wq = 0 " wqではチェックしない
let g:syntastic_auto_loc_list=1 "エラーがあったら自動でロケーションリストを開く
let g:syntastic_loc_list_height=6 "エラー表示ウィンドウの高さ
set statusline+=%#warningmsg# "エラーメッセージの書式
set statusline+=%{SyntasticStatuslineFlag()}
set statusline+=%*

""---- golang
let g:syntastic_mode_map = {
 \ "mode" : "active",
 \ "active_filetypes" : ["go"],
 \}
let g:syntastic_go_checkers = ['go', 'golint', 'govet']
let g:go_fmt_autosave = 1
let g:syntastic_aggregate_errors = 1
augroup GoSaveHook
  autocmd!
  autocmd BufWritePre *.go GoImports
augroup END
