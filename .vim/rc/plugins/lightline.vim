"--- lightline --------------------
" カラースキーマ
let g:lightline = {
  \ 'colorscheme': 'wombat',
  \ 'component_function': {
    \   'syntastic': 'SyntasticStatuslineFlag'
    \ },
  \ 'active': {
    \   'right': [ [ 'syntastic', 'lineinfo' ],
    \              [ 'percent' ],
    \              [ 'fileformat', 'fileencoding', 'filetype' ] ]
    \ },
  \ 'component_type': {
    \   'syntastic': 'error'
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
