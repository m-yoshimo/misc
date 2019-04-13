"--- 保存時の自動フォーマットなどの設定をまとめる

let g:go_fmt_autosave = 0  " vim-go
augroup GoSaveHook
  autocmd!
  autocmd BufWritePre *.go GoImports
augroup END
