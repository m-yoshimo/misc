"---- CtrlP --------------
let g:ctrlp_cache_dir = $HOME . '/.cache/ctrlp'
let g:ctrlp_clear_cache_on_exit = 0
let g:ctrlp_lazy_update = 1
set wildignore+=*/tmp/*,*.so,*.swp,*.zip,*.jpg,*.png,*/node_modules/*
let g:ctrlp_custom_ignore = {
  \ 'dir'  : '\.git$\|\.hg$\|\.svn$\|\.rvm$\|\.bundle$\|\.circleci$\|\..*-ci-reports$\|\.vscode$\|vendor$\|node_modules$\|companies$\|files$\|tmp$\|spec$\|test$',
  \ 'file' : '\.so$\|\.swp$\|\.zip$\|\.jpg$\|\.png$'
  \}
let g:ctrlp_working_path_mode = 'ra'
let g:ctrlp_root_markers = ['Gemfile', 'package.json', 'LICENSE']
let g:ctrlp_match_window='bottom'
let g:ctrlp_max_height=10
let g:ctrlp_match_window_reversed=0
let g:ctrlp_mruf_max=500
let g:ctrlp_follow_symlinks=1
