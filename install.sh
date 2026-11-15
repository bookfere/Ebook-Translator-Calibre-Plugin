#!/usr/bin/env bash
# Install the Ebook Translator plugin into the local Calibre plugins directory.
# Usage: ./install.sh
#
# This creates a zip of the plugin source and copies it to Calibre's plugins
# folder, replacing the existing installation. Calibre must be restarted for
# changes to take effect.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_NAME="Ebook Translator"

# Detect Calibre plugins directory (macOS and Linux)
if [[ -d "$HOME/Library/Preferences/calibre/plugins" ]]; then
    CALIBRE_PLUGINS="$HOME/Library/Preferences/calibre/plugins"
elif [[ -d "$HOME/.config/calibre/plugins" ]]; then
    CALIBRE_PLUGINS="$HOME/.config/calibre/plugins"
else
    echo "Error: Could not find Calibre plugins directory." >&2
    echo "Looked in:" >&2
    echo "  $HOME/Library/Preferences/calibre/plugins (macOS)" >&2
    echo "  $HOME/.config/calibre/plugins (Linux)" >&2
    exit 1
fi

DEST="$CALIBRE_PLUGINS/$PLUGIN_NAME.zip"

echo "Building plugin zip..."
cd "$SCRIPT_DIR"

# Create zip excluding dev/build artifacts
TMP_ZIP="/tmp/ebook-translator-$$.zip"
rm -f "$TMP_ZIP"
zip -r "$TMP_ZIP" . \
    -x ".git/*" \
    -x ".github/*" \
    -x ".claude/*" \
    -x ".idea/*" \
    -x "__pycache__/*" \
    -x "*/__pycache__/*" \
    -x "*/*/__pycache__/*" \
    -x "__MACOSX/*" \
    -x "*.pyc" \
    -x ".gitignore" \
    -x ".gitattributes" \
    -x "install.sh" \
    -x ".DS_Store" \
    -x "*/.DS_Store" \
    > /dev/null

# Replace existing plugin
mv -f "$TMP_ZIP" "$DEST"

echo "Installed to: $DEST"
echo "Restart Calibre to load the updated plugin."
