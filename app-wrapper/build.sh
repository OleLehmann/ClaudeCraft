#!/bin/bash
# build.sh — Build MinecraftGame.app and launch Minecraft under it
#
# Creates a minimal macOS .app bundle with the Java binary symlinked as
# CFBundleExecutable. This gives the Minecraft window a real bundle ID
# (com.claude.minecraftgame) so computer-use tools can see and interact with it.
#
# Usage:
#   bash build.sh           # Capture from launcher + build + launch
#   bash build.sh --clean   # Delete cached command and rebuild from scratch
#
# Author: Claude Opus 4.6

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="/Applications/MinecraftGame.app"
CMD_FILE="/tmp/mc_java_argv.txt"

log() { echo "[$(date +%H:%M:%S)] $*"; }

# Handle --clean flag
if [[ "${1:-}" == "--clean" ]]; then
    log "Cleaning cached command and app..."
    rm -f "$CMD_FILE"
    sudo rm -rf "$APP_DIR" 2>/dev/null || true
    log "Done. Run again without --clean to rebuild."
    exit 0
fi

# ===================================================================
# Step 1: Capture the Java launch command (if not already cached)
# ===================================================================
if [ ! -f "$CMD_FILE" ] || [ ! -s "$CMD_FILE" ]; then
    log "=== Step 1: Capture the Java launch command ==="
    log "Opening Minecraft Launcher — click PLAY when ready."

    open -a "Minecraft"

    log "Waiting for Minecraft Java process..."
    JAVA_PID=""
    for i in $(seq 1 120); do
        JAVA_PID=$(pgrep -f "net.minecraft.client.main.Main" 2>/dev/null || true)
        if [ -n "$JAVA_PID" ]; then
            break
        fi
        sleep 1
    done

    if [ -z "$JAVA_PID" ]; then
        log "ERROR: Timed out after 2 minutes. Did you click Play?"
        exit 1
    fi

    log "Found Minecraft Java process: PID $JAVA_PID"
    log "Waiting 3s for initialization..."
    sleep 3

    # Capture full argv using sysctl KERN_PROCARGS2
    log "Capturing command line (${SCRIPT_DIR}/capture-argv.py)..."
    python3 "$SCRIPT_DIR/capture-argv.py" "$JAVA_PID" "$CMD_FILE"

    if [ ! -s "$CMD_FILE" ]; then
        log "ERROR: Failed to capture Java command line."
        exit 1
    fi

    CAPTURED_ARGS=$(wc -l < "$CMD_FILE" | tr -d ' ')
    log "Captured $CAPTURED_ARGS arguments."

    # Kill the original Java process
    log "Killing original Java process (PID $JAVA_PID)..."
    kill "$JAVA_PID" 2>/dev/null || true
    sleep 2
    kill -0 "$JAVA_PID" 2>/dev/null && kill -9 "$JAVA_PID" 2>/dev/null || true
    sleep 1
else
    CACHED_ARGS=$(wc -l < "$CMD_FILE" | tr -d ' ')
    log "Using cached command ($CACHED_ARGS args from $CMD_FILE)"
fi

# ===================================================================
# Step 2: Build MinecraftGame.app
# ===================================================================
log "=== Step 2: Build MinecraftGame.app ==="

JAVA_BIN=$(head -1 "$CMD_FILE")
log "Java binary: $JAVA_BIN"

if [ ! -f "$JAVA_BIN" ]; then
    log "ERROR: Java binary not found at $JAVA_BIN"
    log "The Minecraft runtime may have been updated. Run with --clean and try again."
    exit 1
fi

# Create the .app bundle in /Applications (needs sudo)
sudo rm -rf "$APP_DIR"
sudo mkdir -p "$APP_DIR/Contents/MacOS"

# Symlink the Java binary as the app's direct executable
# This is the key trick: no exec, no shell wrapper — Java IS the app's process
sudo ln -sf "$JAVA_BIN" "$APP_DIR/Contents/MacOS/MinecraftGame"

# Copy Info.plist
sudo cp "$SCRIPT_DIR/Info.plist" "$APP_DIR/Contents/Info.plist"

# Register with Launch Services
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_DIR"

log "Built: $APP_DIR (bundle ID: com.claude.minecraftgame)"

# ===================================================================
# Step 3: Launch MinecraftGame.app
# ===================================================================
log "=== Step 3: Launch MinecraftGame.app ==="

# Read args (skip first line = java binary path, since it's now the app's executable)
ARGS=()
while IFS= read -r line; do
    ARGS+=("$line")
done < <(tail -n +2 "$CMD_FILE")

log "Launching with ${#ARGS[@]} arguments..."

# Launch via `open -a` — this properly registers the PID with Launch Services
open -a MinecraftGame --args "${ARGS[@]}"

log ""
log "=== SUCCESS ==="
log "Minecraft is now running as MinecraftGame.app"
log "Bundle ID: com.claude.minecraftgame"
log ""
log "In your computer-use session, run:"
log "  request_access('MinecraftGame')"
log "  request_access('com.claude.minecraftgame')"
log ""
log "To rebuild from scratch: bash build.sh --clean"
