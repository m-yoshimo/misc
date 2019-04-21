let g:indentLine_color_term = 242
augroup JsonIndent
  autocmd!
  autocmd Filetype json :IndentLinesDisable
  autocmd Filetype json set list listchars=tab:\¦_,space:.
augroup END
