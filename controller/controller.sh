#!/bin/bash
# controller.sh — Bash-based Minecraft controller for Claude
#
# A shared-folder bridge that gives Claude eyes and hands for Minecraft
# without requiring computer-use tools. Uses screencapture for vision
# and osascript for keyboard/mouse input.
#
# Architecture:
#   1. Take screenshot → save to screen.png
#   2. Signal ready (touch ready.flag)
#   3. Wait for Claude to write commands.txt
#   4. Execute each command via osascript
#   5. Signal done (touch done.flag)
#   6. Repeat
#
# Claude's side:
#   1. Wait for ready.flag
#   2. Read screen.png (Claude can read images)
#   3. Decide what to do
#   4. Write commands.txt
#   5. Wait for done.flag
#   6. Repeat
#
# Requirements:
#   - Accessibility permission for Terminal
#   - Screen Recording permission for Terminal
#   - Minecraft Java Edition running and in a world
#
# Command format (one per line, pipe-separated):
#   chat|/gamemode creative     — Open chat, type, press enter
#   slash|gamemode creative     — Open with /, type command, press enter
#   key|<keycode>               — Press a key by macOS virtual key code
#   type|hello world            — Type text
#   enter                       — Press Enter
#   escape                      — Press Escape
#   walk|2                      — Hold W for 2 seconds
#   jump                        — Press Space
#   sneak|1                     — Hold Shift for 1 second
#   look|100|0                  — Mouse delta move (dx|dy)
#   keydown|w                   — Hold a key down
#   keyup|w                     — Release a key
#   sleep|0.5                   — Wait 0.5 seconds
#   noop                        — Do nothing (just cycle)
#
# Author: Claude Opus 4.6

DIR="$HOME/Desktop/claude-minecraft"
SCREENSHOT="$DIR/screen.png"
COMMANDS="$DIR/commands.txt"
DONE_FLAG="$DIR/done.flag"
READY_FLAG="$DIR/ready.flag"

echo "=== Claude Minecraft Controller ==="
echo "Shared folder: $DIR"
echo "Press Ctrl+C to stop."
echo ""

# Clean up old state
rm -f "$COMMANDS" "$DONE_FLAG" "$READY_FLAG" "$SCREENSHOT"

# Find the Minecraft window CGWindowID for targeted capture
echo "Looking for Minecraft window..."
WINDOW_ID=$(python3 -c "
import Quartz
windows = Quartz.CGWindowListCopyWindowInfo(
    Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
    Quartz.kCGNullWindowID
)
for w in windows:
    name = w.get('kCGWindowName', '') or ''
    owner = w.get('kCGWindowOwnerName', '') or ''
    if 'Minecraft' in name and owner in ('java', 'MinecraftGame'):
        print(w['kCGWindowNumber'])
        break
" 2>/dev/null)

if [ -z "$WINDOW_ID" ]; then
    echo "Minecraft window not found — using full screen capture."
    CAPTURE_CMD="screencapture -x"
else
    echo "Found Minecraft window! (CGWindowID: $WINDOW_ID)"
    CAPTURE_CMD="screencapture -x -l $WINDOW_ID"
fi

# Bring Minecraft to front
osascript -e '
tell application "System Events"
    set javaProcesses to every process whose name is "java" or name is "MinecraftGame"
    if (count of javaProcesses) > 0 then
        set frontmost of item 1 of javaProcesses to true
    end if
end tell
'

echo "Starting control loop..."
echo ""

CYCLE=0
while true; do
    CYCLE=$((CYCLE + 1))

    # Take screenshot
    $CAPTURE_CMD "$SCREENSHOT" 2>/dev/null

    if [ ! -f "$SCREENSHOT" ]; then
        echo "[$(date +%H:%M:%S)] WARNING: Screenshot failed!"
        sleep 1
        continue
    fi

    FILESIZE=$(stat -f%z "$SCREENSHOT" 2>/dev/null || stat --format=%s "$SCREENSHOT" 2>/dev/null)
    echo "[$(date +%H:%M:%S)] Cycle $CYCLE - Screenshot (${FILESIZE} bytes). Waiting for commands..."

    # Signal ready
    rm -f "$READY_FLAG"
    touch "$READY_FLAG"

    # Wait for Claude to write commands
    while [ ! -f "$COMMANDS" ]; do
        sleep 0.3
    done

    echo "[$(date +%H:%M:%S)] Executing commands..."

    # Focus Minecraft before sending input
    osascript -e '
    tell application "System Events"
        set javaProcesses to every process whose name is "java" or name is "MinecraftGame"
        if (count of javaProcesses) > 0 then
            set frontmost of item 1 of javaProcesses to true
        end if
    end tell
    '
    sleep 0.2

    # Execute each command
    while IFS='|' read -r action arg1 arg2; do
        [[ -z "$action" || "$action" == \#* ]] && continue

        case "$action" in
            key)
                osascript -e "tell application \"System Events\" to key code $arg1" 2>/dev/null || \
                osascript -e "tell application \"System Events\" to keystroke \"$arg1\""
                ;;
            type)
                osascript -e "tell application \"System Events\" to keystroke \"$arg1\""
                ;;
            enter)
                osascript -e 'tell application "System Events" to key code 36'
                ;;
            escape)
                osascript -e 'tell application "System Events" to key code 53'
                ;;
            chat)
                osascript -e 'tell application "System Events" to keystroke "t"'
                sleep 0.4
                osascript -e "tell application \"System Events\" to keystroke \"$arg1\""
                sleep 0.15
                osascript -e 'tell application "System Events" to key code 36'
                ;;
            slash)
                osascript -e 'tell application "System Events" to keystroke "/"'
                sleep 0.4
                osascript -e "tell application \"System Events\" to keystroke \"$arg1\""
                sleep 0.15
                osascript -e 'tell application "System Events" to key code 36'
                ;;
            keydown)
                osascript -e "tell application \"System Events\" to key down \"$arg1\""
                ;;
            keyup)
                osascript -e "tell application \"System Events\" to key up \"$arg1\""
                ;;
            walk)
                osascript -e 'tell application "System Events" to key down "w"'
                sleep "${arg1:-1}"
                osascript -e 'tell application "System Events" to key up "w"'
                ;;
            jump)
                osascript -e 'tell application "System Events" to keystroke " "'
                ;;
            sneak)
                osascript -e 'tell application "System Events" to key down shift'
                sleep "${arg1:-1}"
                osascript -e 'tell application "System Events" to key up shift'
                ;;
            look)
                python3 -c "
import Quartz
cur = Quartz.CGEventCreate(None)
pos = Quartz.CGEventGetLocation(cur)
dx, dy = $arg1, $arg2
evt = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved,
    Quartz.CGPointMake(pos.x + dx, pos.y + dy), 0)
Quartz.CGEventSetIntegerValueField(evt, 87, int(dx))
Quartz.CGEventSetIntegerValueField(evt, 88, int(dy))
Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
" 2>/dev/null
                ;;
            sleep)
                sleep "$arg1"
                ;;
            noop)
                ;;
            *)
                echo "  Unknown command: $action"
                ;;
        esac
        sleep 0.05
    done < "$COMMANDS"

    # Clean up and signal done
    rm -f "$COMMANDS"
    rm -f "$DONE_FLAG"
    touch "$DONE_FLAG"

    sleep 0.2
done
