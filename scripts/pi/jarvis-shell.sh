# Bash on the Pi, like the devcontainer (#214): the same prompt (user, a red arrow after a
# failed command, the folder, and the git branch with a ✗ when the tree is dirty), `ll`,
# and vim as the editor. setup.sh installs it as /etc/profile.d/jarvis-shell.sh and sources
# it at the end of ~/.bashrc, so it wins over Debian's prompt.
# shellcheck shell=bash
[ -n "${BASH_VERSION:-}" ] || return 0
case $- in *i*) ;; *) return 0 ;; esac

# The branch part of the prompt. \001 and \002 mark colour codes as zero-width: \[ \] only
# work in PS1 itself, not in what a command substitution prints.
__jarvis_git_prompt() {
  local branch
  branch="$(git --no-optional-locks symbolic-ref --short HEAD 2>/dev/null ||
    git --no-optional-locks rev-parse --short HEAD 2>/dev/null)" || return 0
  [ -n "$branch" ] || return 0
  printf '\001\033[0;36m\002(\001\033[1;31m\002%s' "$branch"
  if git --no-optional-locks ls-files --error-unmatch -m --directory --no-empty-directory \
    -o --exclude-standard ":/*" >/dev/null 2>&1; then
    printf ' \001\033[1;33m\002✗'
  fi
  printf '\001\033[0;36m\002) '
}
# shellcheck disable=SC2016 # expanded at each prompt, not now
PS1='\[\033[0;32m\]\u $([ $? = 0 ] && printf "\001\033[0m\002➜" || printf "\001\033[1;31m\002➜") \[\033[1;34m\]\w $(__jarvis_git_prompt)\[\033[0m\]\$ '
PROMPT_DIRTRIM=4

alias ll='ls -la'

# Full vim (setup installs it); without a ~/.vimrc it loads Debian's defaults.vim.
export EDITOR=vim VISUAL=vim
