if &compatible
  set nocompatible               " Be iMproved
endif

" Required:
set runtimepath+=/home/m-yoshimo/.vim/dein/repos/github.com/Shougo/dein.vim

" Required:
if dein#load_state('/home/m-yoshimo/.vim/dein')
  call dein#begin('/home/m-yoshimo/.vim/dein')

  " Let dein manage dein
  " Required:
  call dein#add('/home/m-yoshimo/.vim/dein/repos/github.com/Shougo/dein.vim')

  " Add or remove your plugins here like this:
  "--- オートコンプリート
  call dein#add('Shougo/deoplete.nvim')
  if !has('nvim')
    call dein#add('roxma/nvim-yarp')
    call dein#add('roxma/vim-hug-neovim-rpc')
  endif
  call dein#add('Shougo/neosnippet.vim')
  call dein#add('Shougo/neosnippet-snippets')
  "--- フォルダツリー
  call dein#add('scrooloose/nerdtree')
  "--- 関数一覧
  call dein#add('vim-scripts/taglist.vim')
  "--- 表示
  call dein#add('itchyny/lightline.vim')
  call dein#add('bronson/vim-trailing-whitespace')
  call dein#add('Yggdroot/indentLine')
  "--- Syntax / Lint
  call dein#add('scrooloose/syntastic')
  call dein#add('fatih/vim-go')
  "--- 自動挿入
  call dein#add('tpope/vim-endwise')
  call dein#add('tpope/vim-surround')
  "--- カラースキーマ
  call dein#add('jacoborus/tender.vim')

  " Required:
  call dein#end()
  call dein#save_state()
endif

" Required:
filetype plugin indent on
syntax enable

" If you want to install not installed plugins on startup.
if dein#check_install()
  call dein#install()
endif
