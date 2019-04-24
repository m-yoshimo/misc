"------- vim-lsp ---------
let g:lsp_diagnostics_enabled = 0
let g:lsp_highlight_references_enabled = 0
set completeopt=menuone
autocmd! CompleteDone * if pumvisible() == 0 | pclose | endif

"" ruby
if executable('solargraph')
  au User lsp_setup call lsp#register_server({
    \ 'name': 'solargraph',
    \ 'cmd': {server_info->['solargraph', 'stdio']},
    \ 'initialization_options': {"diagnostics": "false"},
    \ 'root_uri': { server_info->lsp#utils#path_to_uri(lsp#utils#find_nearest_parent_directory(lsp#utils#get_buffer_path(), '.git/..'))},
    \ 'whitelist': ['ruby'],
    \ })
endif

"" javascript/typescript
if executable('typescript-language-server')
  au User lsp_setup call lsp#register_server({
    \ 'name': 'typescript-language-server',
    \ 'cmd': {server_info->[&shell, &shellcmdflag, 'typescript-language-server --stdio']},
    \ 'initialization_options': {"diagnostics": "false"},
    \ 'root_uri': { server_info->lsp#utils#path_to_uri(lsp#utils#find_nearest_parent_directory(lsp#utils#get_buffer_path(), '.git/..'))},
    \ 'whitelist': ['javascript'],
    \ })
endif

"" go
if executable('go-langserver')
  au User lsp_setup call lsp#register_server({
    \ 'name': 'go-langserver',
    \ 'cmd': {server_info->['go-langserver', '-gocodecompletion']},
    \ 'initialization_options': {"diagnostics": "false"},
    \ 'root_uri': { server_info->lsp#utils#path_to_uri(lsp#utils#find_nearest_parent_directory(lsp#utils#get_buffer_path(), '.git/..'))},
    \ 'whitelist': ['go'],
    \ })
endif

"" python
if executable('pyls')
  au User lsp_setup call lsp#register_server({
    \ 'name': 'pyls',
    \ 'cmd': {server_info->['pyls']},
    \ 'initialization_options': {"diagnostics": "false"},
    \ 'root_uri': { server_info->lsp#utils#path_to_uri(lsp#utils#find_nearest_parent_directory(lsp#utils#get_buffer_path(), '.git/..'))},
    \ 'whitelist': ['python'],
    \ })
endif
