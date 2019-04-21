let g:ale_linters = {
  \ 'javascript': ['jshint'],
  \ 'go': ['gometalinter'],
  \ 'ruby': ['ruby'],
  \ }
let g:ale_sign_warning = '>>'
let g:ale_sign_column_always = 0
let g:ale_lint_on_save = 1
let g:ale_lint_on_text_changed = 0
let g:ale_lint_on_enter = 0
let g:ale_open_list = 1
let g:ale_keep_list_window_open = 0
let g:ale_list_window_size = 6
let g:ale_echo_msg_error_str = 'E'
let g:ale_echo_msg_warning_str = 'W'
let g:ale_echo_msg_format = '[%linter%] %s [%severity%]'
augroup CloseLoclistWindowGroup
  autocmd!
  autocmd QuitPre * if empty(&buftype) | lclose | endif
augroup END
let g:ale_go_gometalinter_options = '--fast --enable=staticcheck --enable=gosimple --enable=unused'
