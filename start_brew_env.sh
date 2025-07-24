#!/bin/zsh

# This script modifies your CURRENT shell to prioritize Homebrew.
# It should be run with 'source activate_brew_env.sh'.

echo "Activating Homebrew-priority environment..."

# Prepend Homebrew's bin directory to the current shell's PATH
export PATH="/home/linuxbrew/.linuxbrew/bin:$PATH"

echo "✅ Homebrew is now first in PATH."
echo "   To return to your default Nix environment, open a new terminal."