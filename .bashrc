# ~/.bashrc: executed by bash(1) for non-login shells.
# see /usr/share/doc/bash/examples/startup-files (in the package bash-doc)
# for examples

# If not running interactively, don't do anything
[ -z "$PS1" ] && return

# don't put duplicate lines in the history. See bash(1) for more options
# ... or force ignoredups and ignorespace
HISTCONTROL=ignoredups:ignorespace

# append to the history file, don't overwrite it
shopt -s histappend

# for setting history length see HISTSIZE and HISTFILESIZE in bash(1)
HISTSIZE=1000
HISTFILESIZE=2000

# check the window size after each command and, if necessary,
# update the values of LINES and COLUMNS.
shopt -s checkwinsize

# make less more friendly for non-text input files, see lesspipe(1)
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

# set variable identifying the chroot you work in (used in the prompt below)
if [ -z "$debian_chroot" ] && [ -r /etc/debian_chroot ]; then
    debian_chroot=$(cat /etc/debian_chroot)
fi

# set a fancy prompt (non-color, unless we know we "want" color)
case "$TERM" in
    xterm-color) color_prompt=yes;;
esac

# uncomment for a colored prompt, if the terminal has the capability; turned
# off by default to not distract the user: the focus in a terminal window
# should be on the output of commands, not on the prompt
#force_color_prompt=yes

if [ -n "$force_color_prompt" ]; then
    if [ -x /usr/bin/tput ] && tput setaf 1 >&/dev/null; then
        # We have color support; assume it's compliant with Ecma-48
        # (ISO/IEC-6429). (Lack of such support is extremely rare, and such
        # a case would tend to support setf rather than setaf.)
        color_prompt=yes
    else
        color_prompt=
    fi
fi

if [ "$color_prompt" = yes ]; then
    PS1='${debian_chroot:+($debian_chroot)}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
else
    PS1='${debian_chroot:+($debian_chroot)}\u@\h:\w\$ '
fi
unset color_prompt force_color_prompt

# If this is an xterm set the title to user@host:dir
case "$TERM" in
xterm*|rxvt*)
    PS1="\[\e]0;${debian_chroot:+($debian_chroot)}\u@\h: \w\a\]$PS1"
    ;;
*)
    ;;
esac

# enable color support of ls and also add handy aliases
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    #alias dir='dir --color=auto'
    #alias vdir='vdir --color=auto'

    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
fi

# some more ls aliases
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'

# Alias definitions.
# You may want to put all your additions into a separate file like
# ~/.bash_aliases, instead of adding them here directly.
# See /usr/share/doc/bash-doc/examples in the bash-doc package.

if [ -f ~/.bash_aliases ]; then
    . ~/.bash_aliases
fi

# enable programmable completion features (you don't need to enable
# this, if it's already enabled in /etc/bash.bashrc and /etc/profile
# sources /etc/bash.bashrc).
if ! shopt -oq posix; then
  if [ -f /usr/share/bash-completion/bash_completion ]; then
    . /usr/share/bash-completion/bash_completion
  elif [ -f /etc/bash_completion ]; then
    . /etc/bash_completion
  fi
fi

#####################################################
# Local settings ####################################
#####################################################
# alias
alias scrr='screen -t'

# git
source ~/.git-prompt.sh

# locale
export LC_MESSAGES=ja_JP.UTF-8
export LC_IDENTIFICATION=ja_JP.UTF-8
export LC_COLLATE=ja_JP.UTF-8
export LANG=ja_JP.UTF-8
export LC_MEASUREMENT=ja_JP.UTF-8
export LC_CTYPE=ja_JP.UTF-8
export LC_TIME=ja_JP.UTF-8
export LC_NAME=ja_JP.UTF-8

# prompt color
#export PS1="[\[\e[38;05;45m\\]\u\[\e[0m\]@\[\e[38;05;9m\]\h\[\e[0m\]:\[\e[38;05;46m\]\w\[\e[0m\]]\n\\$ "
export PS1='[\[\e[38;05;12m\]\u\[\e[0m\]@\[\e[38;05;41m\]\w\[\e[0m\]] \[\e[38;05;203m\]$(__git_ps1 "(%s)")\[\e[0m\]\n\\$ '

# dircolor edit
if [ -f "${HOME}/.dircolors" ] ; then
    eval $(dircolors -b ${HOME}/.dircolors)
fi

# disable C-s
stty stop undef

# git
export GIT_EDITOR=vim

# screen for WSL
if [ ! -f /var/run/utmp ] ; then
  sudo touch /var/run/utmp
fi
export SCREENDIR=${HOME}/.screen

# path for lib on bionic
export PATH=/usr/lib/x86_64-linux-gnu:${PATH}

# anyenv
export PATH=${HOME}/.anyenv/bin:${PATH}

# ruby
#export PATH=${HOME}/.rbenv/bin:${PATH}
#eval "$(rbenv init -)"

# go
export GOPATH=${HOME}/go
export PATH=${GOPATH}/bin:${PATH}
eval "$(goenv init -)"

# python
#export PYENV_ROOT=${HOME}/.pyenv
#export PATH=${PYENV_ROOT}/bin:${PATH}
#eval "$(pyenv init -)"

# fzf
[ -f ~/.fzf.bash ] && source ~/.fzf.bash

# gcloud
export CLOUD_SDK_REPO="cloud-sdk-$(lsb_release -c -s)"
#export GOOGLE_PROJECT_ID="$(gcloud config get-value project -q)"  # 読み込み長いのでコメントアウト

source ${HOME}/.bashrc_genda
