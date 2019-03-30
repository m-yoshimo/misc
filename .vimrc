" setting
set fenc=utf-8
set encoding=utf-8
set showcmd

" display
set number
set cursorline
"set cursorcolumn
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
set listchars=tab:^t,trail:%
"eol:↲
set tabstop=2
set expandtab
set shiftwidth=2

" find
set ignorecase
set smartcase
set incsearch
set wrapscan
set hlsearch
nmap <Esc><Esc> :nohlsearch<CR><Esc>

" color
"hi Function ctermfg=darkgreen
"hi Repeat ctermfg=darkgreen
hi String ctermfg=203
hi Number ctermfg=196
hi Boolean ctermfg=196
"hi Normal ctermfg=gray ctermbg=black
"hi Cursor ctermfg=gray
hi Comment ctermfg=darkgreen
hi Constant term=underline ctermfg=blue
"hi Special ctermfg=blue
hi Identifier term=underline ctermfg=130
hi Statement ctermfg=75
hi Keyword ctermfg=33
hi PreProc ctermfg=183
"hi Type term=underline ctermfg=darkgreen
"hi Underlined term=underline cterm=underline ctermfg=darkcyan
"hi Ignore ctermfg=blue
"hi Error term=bold ctermbg=darkmagenta ctermfg=black
"hi Todo term=bold ctermfg=black ctermbg=darkcyan
"hi Pmenu ctermbg=black ctermfg=gray
"hi PmenuSel ctermbg=darkcyan ctermfg=black
"hi PmenuSbar ctermbg=darkred
"hi PmenuThumb cterm=reverse ctermfg=gray
"hi TabLine term=underline cterm=underline ctermfg=gray ctermbg=darkred
"hi TabLineSel term=bold
"hi TabLineFill term=reverse cterm=reverse
"hi MatchParen term=reverse ctermfg=brown ctermbg=darkcyan
hi SpecialKey term=reverse ctermfg=240 ctermbg=NONE
hi NonText term=bold ctermfg=240 ctermbg=NONE
hi LineNr ctermfg=130
hi CursorLine term=none ctermfg=NONE ctermbg=NONE
hi CursorLineNr term=underline cterm=NONE ctermfg=white ctermbg=130
"hi Directory term=bold ctermfg=brown
"hi ErrorMsg ctermbg=darkmagenta ctermfg=black
"hi IncSearch term=reverse cterm=reverse ctermfg=brown ctermbg=black
"hi Search term=reverse ctermfg=black ctermbg=brown
"hi MoreMsg term=bold ctermfg=darkgreen
"hi ModeMsg term=bold ctermfg=darkmagenta
"hi LineNr term=underline cterm=underline ctermfg=blue ctermbg=black
"hi Question term=bold ctermfg=blue
"hi StatusLine term=bold,reverse cterm=reverse ctermfg=blue ctermbg=black
"hi StatusLineNC term=bold,reverse cterm=reverse ctermfg=blue ctermbg=black
"hi VertSplit ctermfg=black ctermbg=darkred term=reverse cterm=reverse
"hi Title ctermfg=gray
"hi Visual term=reverse cterm=reverse ctermfg=darkcyan ctermbg=black
"hi VisualNOS term=bold,underline ctermfg=darkcyan ctermbg=black
"hi WarningMsg term=bold ctermfg=darkmagenta
"hi WildMenu term=bold ctermfg=black ctermbg=darkcyan
"hi Folded ctermbg=darkcyan ctermfg=black
"hi FoldColumn ctermbg=darkcyan ctermfg=black
"hi DiffAdd term=bold ctermbg=brown ctermfg=black
"hi DiffChange term=bold ctermbg=darkred
"hi DiffDelete term=bold ctermfg=black ctermbg=brown
"hi DiffText term=reverse ctermbg=darkmagenta ctermfg=black
"hi SignColumn term=bold ctermfg=black ctermbg=darkcyan
