# locale
export LC_MESSAGES=ja_JP.UTF-8
export LC_IDENTIFICATION=ja_JP.UTF-8
export LC_COLLATE=ja_JP.UTF-8
export LANG=ja_JP.UTF-8
export LC_MEASUREMENT=ja_JP.UTF-8
export LC_CTYPE=ja_JP.UTF-8
export LC_TIME=ja_JP.UTF-8
export LC_NAME=ja_JP.UTF-8

# wsl-terminal for WSL
export DISPLAY=localhost:0.0
export XIM=uim
export XMODIFIERS=@im=uim
export UIM_CANDWIN_PROG=uim-candwin-gtk
#export UIM_CANDWIN_PROG=uim-candwin-qt
export GTK_IM_MODULE=uim
export QT_IM_MODULE=uim
export NO_AT_BRIDGE=1
export XMODIFIRES=@im=uim

# prompt color
export PS1="[\[\e[38;05;45m\\]\u\[\e[0m\]@\[\e[38;05;9m\]\h\[\e[0m\]:\[\e[38;05;46m\]\w\[\e[0m\]]\n\\$ "

# dircolor edit
if [ -f "$HOME/.dircolors" ] ; then
    eval $(dircolors -b $HOME/.dircolors)
fi

# git
export GIT_EDITOR=vim

# screen for WSL
if [ ! -f /var/run/utmp ] ; then
  sudo touch /var/run/utmp
fi
export SCREENDIR=$HOME/.screen

# rbenv
export PATH=${HOME}/.rbenv/bin:${PATH}
eval "$(rbenv init -)"

# path for lib on bionic
export PATH=/usr/lib/x86_64-linux-gnu:${PATH}

# golang
export GOPATH=${HOME}/dev/go
export PATH=${GOPATH}/bin:${PATH}

# gcloud
export CLOUD_SDK_REPO="cloud-sdk-$(lsb_release -c -s)"
#export GOOGLE_PROJECT_ID="$(gcloud config get-value project -q)"  # 読み込み長いのでコメントアウト

# docker for windows
export DOCKER_HOST='tcp://0.0.0.0:2375'

source ~/.bashrc_private
