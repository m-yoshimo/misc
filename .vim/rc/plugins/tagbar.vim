"--- tagbar ----
let g:tagbar_width = 30
let g:tagbar_autoshowtag = 1
let g:tagbar_autofocus = 0
let g:tagbar_autoclose = 0
let g:tagbar_compact = 1
let g:tagbar_indent = 1
let g:tagbar_left = 0
let g:tagbar_map_togglesort = "r"
let g:tagbar_map_togglefold = "l"
let g:tagbar_iconchars = ['▸', '▾']
let g:tagbar_sort=0
let g:tagbar_type_ruby = {
  \ 'ctagstype': 'ruby',
  \ 'deffile': '/home/m-yoshimo/.ctags.d/rails.ctags',
  \ 'kinds': [
    \ 'm:modules',
    \ 'c:classes',
    \ 'C:constants:1',
    \ 'V:varidates:1',
    \ 'A:associations:1',
    \ 'B:callbacks:1',
    \ 'd:describes',
    \ 'f:methods',
    \ 'S:singleton methods'
  \],
  \ 'kind2scope' : {
    \ 'f': 'methods'
  \},
\}
let g:tagbar_type_go = {
  \ 'ctagstype': 'go',
  \ 'kinds' : [
    \' p:package',
    \' f:function',
    \' v:variables',
    \' t:type',
    \' c:const'
  \]
\}
let js_ctags_exuberant = {
  \ 'ctagstype': 'javascript',
  \ 'ctagsbin' : 'ctags-exuberant',
  \ 'kinds': [
    \ 'E:exports',
    \ 'I:imports',
    \ 'C:constructors/classes',
    \ 'V:variables',
    \ 'M:methods',
    \ 'G:generator functions',
    \ 'F:functions',
    \ 'P:properties',
    \ 'A:arrays',
    \ 'O:objects',
    \ 'S:styled components',
    \ 'T:tags',
  \]
\}
let js_ctags_universal = {
  \ 'ctagstype': 'javascript',
  \ 'ctagsbin': 'ctags',
  \ 'kinds': [
    \ 'e:exports',
    \ 'i:imports',
    \ 'c:constructors/classes',
    \ 'v:variables',
    \ 'm:methods',
    \ 'g:generator functions',
    \ 'f:functions',
    \ 'p:properties',
    \ 'a:arrays',
    \ 'o:objects',
    \ 's:styled components',
    \ 't:tags',
  \]
\}
let g:tagbar_type_javascript = js_ctags_exuberant
