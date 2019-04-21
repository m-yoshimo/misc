"--- 保存時の自動フォーマットなどの設定をまとめる

let g:go_fmt_autosave = 0  " vim-go
augroup GoSaveHook
  autocmd!
  autocmd BufWritePre *.go GoImports
augroup END
let g:ale_fixers = {'javascript': ['prettier']}
let g:ale_fix_on_save = 1
