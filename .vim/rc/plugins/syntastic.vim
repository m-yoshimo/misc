"--- syntastic
"ファイルを開いたときはチェックしない
let g:syntastic_check_on_open=0
"保存時にはチェック
let g:syntastic_check_on_save=1
" wqではチェックしない
let g:syntastic_check_on_wq = 0
" エラーがあったら自動でロケーションリストを開く
let g:syntastic_auto_loc_list=1
" エラー表示ウィンドウの高さ
let g:syntastic_loc_list_height=6
" エラーメッセージの書式
set statusline+=%#warningmsg#
set statusline+=%{SyntasticStatuslineFlag()}
set statusline+=%*

" golang 向け設定
let g:syntastic_mode_map = {
 \ "mode" : "active",
 \ "active_filetypes" : ["go"],
 \}
let g:syntastic_go_checkers = ['golint', 'govet']
let g:syntastic_aggregate_errors = 1
