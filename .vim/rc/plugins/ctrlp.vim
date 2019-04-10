"---- CtrlP --------------
let g:ctrlp_map = '<c-p>'
let g:ctrlp_cmd = 'CtrlP'
let g:ctrlp_cache_dir = $HOME . '/.cache/ctrlp'
set wildignore+=*/tmp/*,*.so,*.swp,*.zip,*/vendor/*,*/\.git/*
let g:ctrlp_custom_ignore = 'tmp$\|\.git$\|\.hg$\|\.svn$\|.rvm$|.bundle$\|vendor'
let g:ctrlp_working_path_mode = 0
let g:ctrlp_match_window='bottom'
let g:ctrlp_max_height=10
let g:ctrlp_match_window_reversed=0
let g:ctrlp_mruf_max=500
let g:ctrlp_follow_symlinks=1
let g:ctrlp_clear_cache_on_exit=0
