"--- lightline --------------------
" カラースキーマ
let g:lightline = {
  \ 'colorscheme': 'wombat',
  \ 'active': {
    \ 'left' : [
      \ [ 'mode', 'paste' ],
      \ [ 'fugitive', 'filename' ]
      \ ],
    \ 'right': [
      \ [ 'lineinfo' ],
      \ [ 'fileformat', 'fileencoding', 'filetype' ],
      \ [ 'linter_checking', 'linter_warnings', 'linter_errors', 'linter_ok' ],
      \ ],
    \ },
  \ 'component_expand': {
      \ 'linter_checking': 'lightline#ale#checking',
      \ 'linter_warnings': 'lightline#ale#warnings',
      \ 'linter_errors': 'lightline#ale#errors',
      \ 'linter_ok': 'lightline#ale#ok',
    \ },
  \ 'component_type': {
      \ 'linter_checking': 'left',
      \ 'linter_warnings': 'warning',
      \ 'linter_errors': 'error',
      \ 'linter_ok': 'left',
    \ },
  \ 'component_function': {
    \ },
  \ }
" ステータスラインを常に表示
set laststatus=2
" 現在のモードを表示
set showmode
" 打ったコマンドをステータスラインの下に表示
set showcmd
" ステータスラインの右側にカーソルの現在位置を表示する
set ruler
