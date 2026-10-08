#!/usr/bin/env bash
# build_plugin.sh — Crea lo zip installabile del plugin Ebook Translator.
#
# Uso:
#   ./build_plugin.sh              # produce ebook-translator-calibre-plugin.zip
#   ./build_plugin.sh mio-file.zip # produce mio-file.zip
#
# Lo script deve essere eseguito dall'interno della directory del plugin
# (quella che contiene __init__.py).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_OUTPUT="../ebook-translator-calibre-plugin.zip"
OUTPUT="${1:-$DEFAULT_OUTPUT}"

# Converti in percorso assoluto se relativo.
if [[ "$OUTPUT" != /* ]]; then
    OUTPUT="$SCRIPT_DIR/$OUTPUT"
fi

echo "Building plugin zip..."
echo "  Source : $SCRIPT_DIR"
echo "  Output : $OUTPUT"

# Rimuovi eventuale zip precedente.
rm -f "$OUTPUT"

cd "$SCRIPT_DIR"

zip -r "$OUTPUT" . \
    -x "*.pyc" \
    -x "./__pycache__" \
    -x "./__pycache__/*" \
    -x "*/__pycache__" \
    -x "*/__pycache__/*" \
    -x "./.git" \
    -x "./.git/*" \
    -x "./.github" \
    -x "./.github/*" \
    -x "./tests" \
    -x "./tests/*" \
    -x "./page" \
    -x "./page/*" \
    -x "./build_plugin.sh" \
    > /dev/null

SIZE=$(du -h "$OUTPUT" | cut -f1)
echo "Done: $OUTPUT ($SIZE)"
echo ""
echo "Per installare in Calibre:"
echo "  Preferenze → Plugin → Carica plugin da file → $OUTPUT"
echo "  oppure: calibre-customize -a \"$OUTPUT\""
