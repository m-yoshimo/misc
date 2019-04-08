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

" paste
if &term =~ "xterm"
  let &t_SI .= "\e[?2004h"
  let &t_EI .= "\e[?2004l"
  let &pastetoggle = "\e[201~"

  function XTermPasteBegin(ret)
    set paste
    return a:ret
  endfunction

  inoremap <special> <expr> <Esc>[200~ XTermPasteBegin("")
endif
