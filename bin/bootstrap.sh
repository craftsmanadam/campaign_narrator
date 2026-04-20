#!/usr/bin/env bash

# bin/bootstrap.sh: Resolve all dependencies that the project requires to run.

set -e

# Set the working directory to be the project's base directory; all
# subsequent paths are relative to that base directory.
cd "$(dirname "$0")/.."

source bin/build_variables.sh

quiet_apt_get()
{
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -qq "$@"
}

is_wsl()
{
	case "$(uname -r)" in
	*microsoft* ) true ;; # WSL 2
	*Microsoft* ) true ;; # WSL 1
	* ) false;;
	esac
}

installed()
{
  return "$(dpkg-query -W -f '${Status}\n' "${1}" 2>&1|awk '/ok installed/{print 0;exit}{print 1}')"
}

puts "${BLUE}───────────────────────────────────────────────────────────────────────${RESET}"
if [ -z "${CI}" ]; then
    puts " RUNNING LOCALLY…"
else
    puts " RUNNING IN CI…"
    if [ "${CIRCLE_BRANCH}" != "main" ]; then
        puts " NOT ON MAIN BRANCH…"
    fi
fi
puts " VERSION: $VERSION"
puts "${BLUE}───────────────────────────────────────────────────────────────────────${RESET}"

# Install system dependencies
# macOS
if command -v brew >/dev/null 2>&1 && [ -f "Brewfile" ]; then
  brew bundle check >/dev/null 2>&1 || {
    puts "🤖 ⟶  Installing system prerequisites…"
    brew bundle --quiet
  }
fi
# Ubuntu/Debian/Mint
if command -v apt-get >/dev/null 2>&1; then
  puts "🤖 ⟶  Installing system prerequisites…"
  # pyenv dependencies, see:
  # https://github.com/pyenv/pyenv/wiki#suggested-build-environment
  pkgs=(make build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev)
  missing_pkgs=()

  for pkg in "${pkgs[@]}"; do
    if ! eval installed "$pkg"; then
      missing_pkgs+=("$pkg")
    fi
  done

  if [ -n "${missing_pkgs[*]}" ]; then
    sudo apt-get update -qq
    quiet_apt_get "${missing_pkgs[@]}" < /dev/null > /dev/null
  fi

  if ! command -v docker >/dev/null 2>&1; then
    if is_wsl; then
      puts "${RED}🤖 ⟶  Unable to install Docker in WSL.${RESET}"
      puts ""
      puts "You'll need to install Docker Desktop for Windows manually:"
      puts ""
      puts "https://docs.docker.com/desktop/windows/install/"
      puts ""
      puts "When installing, make sure WSL 2 is selected as the backend."
      puts "After installing, enable WSL integration:"
      puts ""
      puts "https://docs.docker.com/desktop/windows/wsl/#enabling-docker-support-in-wsl-2-distros"
      puts ""
      exit 1
    else
      puts "🤖 ⟶  Installing Docker…"
      curl -fsSL https://get.docker.com | sudo sh
      getent group docker >/dev/null 2>&1 \
        || sudo groupadd docker \
        && sudo usermod -aG docker "$USER" \
        && newgrp docker
    fi
  fi
fi

grep 'host.docker.internal' /etc/hosts >/dev/null 2>&1 || {
  if [ -z "${CI}" ]; then
    puts "${RED}🤖 ⟶  Add '127.0.0.1 host.docker.internal' to your /etc/hosts file.${RESET}"
    exit 1
  else
    echo 127.0.0.1 host.docker.internal | sudo tee -a /etc/hosts
  fi
}
if ! command -v pyenv >/dev/null 2>&1; then
  puts "🤖 ⟶  Installing pyenv…"
  curl https://pyenv.run | bash
  # This will setup pyenv for the duration of the script, but the user still
  # needs to make the setup permanent in their shell configuration file.
  export PYENV_ROOT="$HOME/.pyenv"
  export PATH="$PYENV_ROOT/bin:$PATH"
  eval "$(pyenv init -)"
  pyenv_installed=true
fi

# If Poetry adds support for reading versions from pyproject.toml, we can
# talk about removing the .python-version file. See this issue for more
# details: https://github.com/pyenv/pyenv/issues/1233.
if [ -f ".python-version" ] && [ -z "$(pyenv version-name 2>/dev/null)" ]; then
  puts "🤖 ⟶  Installing Python…"
  pyenv install --skip-existing
fi

if ! command -v poetry >/dev/null 2>&1; then
  puts "🤖 ⟶  Installing Poetry…"
  curl -sSL https://install.python-poetry.org | python3 -
  # This will setup Poetry for the duration of the script, but the user still
  # needs to make the setup permanent in their shell configuration file.
  export PATH="$HOME/.local/bin:$PATH"
  poetry_installed=true
fi

if [ -f "pyproject.toml" ]; then
  puts "🤖 ⟶  Installing Python dependencies…"
  if [ "$(uname -m)" == 'arm64' ]; then
    export CRYPTOGRAPHY_DONT_BUILD_RUST=1
  fi
  poetry install
fi

if [ -n "$pyenv_installed" ]; then
  puts "${BLUE}🤖 ⟶  Don't forget to finish setting up pyenv.${RESET}"
  puts ""
  puts "Add to (and re-source) your shell configuration file (~/.bashrc):"
  puts ""
  puts "${PURPLE}export PYENV_ROOT=\"\$HOME/.pyenv\"${RESET}"
  puts "${PURPLE}command -v pyenv >/dev/null || export PATH=\"\$PYENV_ROOT/bin:\$PATH\"${RESET}"
  puts "${PURPLE}eval \"\$(pyenv init -)\"${RESET}"
  puts ""
fi

if [ -n "$poetry_installed" ]; then
  puts "${BLUE}🤖 ⟶  Don't forget to finish setting up Poetry.${RESET}"
  puts ""
  puts "Add to (and re-source) your shell configuration file (~/.bashrc):"
  puts ""
  puts "${PURPLE}command -v poetry >/dev/null || export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}"
  puts ""
fi
