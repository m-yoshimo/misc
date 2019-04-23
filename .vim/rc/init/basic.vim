" setting
set fenc=utf-8
set encoding=utf-8
set showcmd

" display
set number
set cursorline
set laststatus=2
set noautoindent
set nocindent
set nosmartindent
set virtualedit=onemore
set showmatch
set wildmode=list:longest
set list listchars=tab:\¦_
syntax enable

" tab/space
set list
set tabstop=2
set expandtab
set shiftwidth=2

" find
set ignorecase
set smartcase
set incsearch
set wrapscan
set hlsearch

function! ProfileCursorMove() abort
  let profile_file = expand('~/log/vim-profile.log')
  if filereadable(profile_file)
    call delete(profile_file)
  endif

  normal! gg
  normal! zR

  execute 'profile start ' . profile_file
  profile func *
  profile file *

  augroup ProfileCursorMove
    autocmd!
    autocmd CursorHold <buffer> profile pause | q
  augroup END

  for i in range(100)
    call feedkeys('j')
  endfor
endfunction
