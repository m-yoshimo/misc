let g:deoplete#enable_at_startup = 1
let g:deoplete#auto_complete_delay = 0
let g:deoplete#auto_complete_start_length = 1
let g:deoplete#enable_camel_case = 0
let g:deoplete#enable_ignore_case = 0
let g:deoplete#enable_refresh_always = 0
let g:deoplete#enable_smart_case = 1
let g:deoplete#file#enable_buffer_path = 1
let g:deoplete#max_list = 10000
"set completeopt+=noinsert

" keymap
inoremap <expr><tab> pumvisible() ? "\<C-n>" :
  \ neosnippet#expandable_or_jumpable() ?
  \    "\<Plug>(neosnippet_expand_or_jump)" : "\<tab>"

" LSP settings here
let g:LanguageClient_serverCommands = {
  \ 'ruby': ['solargraph', 'stdio'],
  \ 'javascript': ['typescript-language-server', '--stdio'],
  \ 'go': ['go-langserver', '-format-tool','gofmt','-lint-tool','golint'],
  \}
call deoplete#custom#var('omni', 'input_patterns', {
  \ 'ruby': ['[^. *\t]\.\w*', '[a-zA-Z_]\w*::'],
  \})
