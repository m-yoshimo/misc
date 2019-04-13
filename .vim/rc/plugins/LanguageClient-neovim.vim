"--- LanguageClient-neovim --------
let g:LanguageClient_diagnosticsDisplay = {
  \ 1: {
    \ "name": "Error",
    \ "signText": '▸',
    \ },
  \ 2: {
    \ "name": "Warning",
    \ "signText": '▸',
    \ },
  \ 3: {
    \ "name": "Information",
    \ "signText": '▸',
    \ },
  \ 4: {
    \ "name": "Hint",
    \ "signText": '▸',
    \},
  \}
let g:LanguageClient_diagnosticsList = "Location"
let g:LanguageClient_hoverPreview = "Never"
let g:LanguageClient_diagnosticsEnable = 0
