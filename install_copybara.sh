#!/usr/bin/env bash
set -euo pipefail

# Directory setup
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$SCRIPT_DIR/bin"
JAR_PATH="$BIN_DIR/copybara_deploy.jar"
WRAPPER_PATH="$BIN_DIR/copybara"

DOWNLOAD_URL="https://github.com/miv403/copybara-http/releases/download/v20260727-patch/copybara_deploy-PATCHED.jar"

mkdir -p "$BIN_DIR"

echo "Downloading patched Copybara JAR..."
if command -v curl >/dev/null 2>&1; then
    curl -fL --progress-bar -o "$JAR_PATH" "$DOWNLOAD_URL"
elif command -v wget >/dev/null 2>&1; then
    wget -O "$JAR_PATH" "$DOWNLOAD_URL"
else
    echo "Error: Neither curl nor wget found on system." >&2
    exit 1
fi

echo "Creating executable copybara wrapper at $WRAPPER_PATH..."
cat << 'EOF' > "$WRAPPER_PATH"
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec java -jar "$SCRIPT_DIR/copybara_deploy.jar" "$@"
EOF

chmod +x "$WRAPPER_PATH"

echo "Copybara successfully installed to $BIN_DIR"
echo "  - Wrapper script: $WRAPPER_PATH"
echo "  - Executable JAR: $JAR_PATH"
