syntax on
filetype plugin on

" filetype
let pascal_delphi=1
let pascal_symbol_operator=1
let pascal_no_tabs=1
au BufNewFile,BufRead *.pp,*.rops setf pascal
au BufNewFile,BufRead *.htn setf hatena
au BufNewFile,BufRead *.rml setf xml

" tab
set tabstop=2
set shiftwidth=2
set softtabstop=2
set expandtab
" set smarttab

" indent
set ai

set noeol
set nobackup
set noundofile
set fileencoding=utf-8
set fileencodings=utf-8,euc-jp,cp932
set fileformats=unix,dos,mac
map <C-I> :tabnext<cr>
map <S-TAB> :tabprev<cr>
set bs=2

" Exec
map mm :!make<cr>
map mt :!make test<cr>
map mh :!make html<cr>
map md :!dcc32 %<cr>
map me :!%:r.exe<cr>
map mp :!pep8 %<cr>
map mf :!pyflakes %<cr>

" Server only
"set mouse=a
"set ttymouse=xterm2

" color scheme
colorscheme delek

" yankling
let g:yankring_history_file='.yankling_history'

" qbuf
let g:qb_hotkey=';;'

" cursorline
set cursorline

" special char width
if exists('&ambiwidth')
  set ambiwidth=double
endif

" dropbox swap exclude
set directory=~/.swap

" jedi-vim
"autocmd FileType python setlocal omnifunc=jedi#completions
"let g:jedi#auto_initialization = 1
"let g:jedi#completions_enabled = 1
"let g:jedi#auto_vim_configuration = 1
"let g:jedi#force_py_version = 2
