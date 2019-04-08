"--- taglist ----------------

"タグに色をつけるか
"0(付けない) または 1(付ける)
let Tlist_Auto_Highlight_Tag = 1

"TagListをVim起動時に開くか
"0(開かない) または 1(開く)
"この設定で開くとフォーカスがtaglistに奪われるので別で設定する
let Tlist_Auto_Open = 0

"新規ファイルを開いた時に自動的にタグリストに追加するか
"0(追加しない) または 1(追加する)
let Tlist_Auto_Update = 1

"タグを選択時に、画面遷移後にタグリストを閉じるか
"0(閉じない) または 1(閉じる)
let Tlist_Close_On_Select = 0

"デフォルト表示かコンパクト表示か
"0(デフォルト) または 1(コンパクト)
let Tlist_Compact_Format = 1

"ctagsコマンドの場所
let Tlist_Ctags_Cmd = "/usr/bin/ctags"

"タグのプロトタイプを表示するかどうか
"0(表示しない) または 1(表示する)
let Tlist_Display_Prototype = 1

"C++のようにスコープを持つタグで、スコープを表示するか
"0(表示しない) または 1(表示する)
let Tlist_Display_Tag_Scope = 1

"Foldカラムを表示するか表示しないか。狭い場所に表示させたい時は非表示に
"0(表示しない) または 1(表示する)
let Tlist_Enable_Fold_Column = 1

"タグリストだけが表示されているときに自動的にVimを終了するか
"0(終了しない) または 1(終了する)
let Tlist_Exit_OnlyWindow = 1

"ファイルが非アクティブのとき自動的にタグリストを閉じるか
"0(閉じない) または 1(閉じる)
let Tlist_File_Fold_Auto_Close = 1

"TlistToggleコマンド入力時、フォーカスをタグリストに移動するか
"0(移動しない) または 1(移動する)
let Tlist_GainFocus_On_ToggleOpen = 1

"自動ハイライト表示
"0(表示しない) または 1(表示する)
let Tlist_Highlight_Tag_On_BufEnter = 1

"ウィンドウ幅を変更出来ない場合や幅を固定したい場合
let Tlist_Inc_Winwidth = 1

"function variable classなど区分けがこの値より多い場合、分割して表示する
let Tlist_Max_Submenu_Items = 25

"タグ名の最大幅
let Tlist_Max_Tag_Length = 10

"TagListが自動的に動作し、新たな関数や変数が追加した時に対応するか
"0(自動的に動作しない) または 1(自動的に動作する)
let Tlist_Process_File_Always = 1

"Vimのバッファにある全てのファイルのタグを表示するか、カレントバッファのタグだけを表示するか
"1(カレントバッファのみ)
let Tlist_Show_One_File = 1

"どの順番でソートを行うか
"設定しない(定義順) または name(アルファベット順)
"let Tlist_Sort_Type = "name"

"画面を上下に分割してタグを表示するか
"設定しない(左右に分割) または 1(上下に分割)
"let Tlist_Use_Horiz_Window = 1

"タグ画面を右に表示するか
"設定しない(左に表示) または 1(右に表示)
"let Tlist_Use_Right_Window = 1

"マウスでタグをシングルクリックして、対象場所へ遷移するか
"0(遷移しない) または 1(遷移する)
let Tlist_Use_SingleClick = 0

"画面を上下に分割した場合の、タグ画面の初期高さ
let Tlist_WinHeight = 10

"画面を左右に分割した場合の、タグ画面の初期幅
let Tlist_WinWidth = 30

"---------------------------------------
"-- CustomSettings ---------------------
"---------------------------------------

" javascript/go だと taglist に何も出ないので設定変更する
let g:tlist_javascript_settings = 'javascript;C:class;M:method;F:function;P:property'
let g:tlist_go_settings = 'go;g:enum;s:struct;u:union;t:type;v:variable;f:function'
