#!/usr/bin/env python3
"""
Claude-Minecraft Bridge — Python/Quartz edition

A local macOS companion that gives Claude eyes and hands for Minecraft.
Lower latency than the bash controller because it uses Quartz CGEvent
injection directly instead of spawning osascript subprocesses.

Architecture:
    Vision:  screencapture via CGWindowID (Minecraft window only)
    Input:   Quartz CGEvent injection (keyboard + mouse)
    Comms:   Shared folder with JSON command files + screenshot PNGs

Usage:
    python3 bridge.py

Requirements:
    - macOS Screen Recording permission for Terminal
    - macOS Accessibility permission for Terminal
    - Minecraft Java Edition running and in a world

Command format (JSON array of command objects):
    [
        {"action": "chat", "text": "/gamemode creative"},
        {"action": "walk", "duration": 2.0},
        {"action": "look", "dx": 100, "dy": 0},
        {"action": "left_click"},
        {"action": "hotbar", "slot": 1},
        {"action": "key_tap", "key": "e"},
        {"action": "slash", "text": "time set day"},
        {"action": "hold_click", "duration": 3.0},
        {"action": "sleep", "duration": 0.5}
    ]

Author: Claude Opus 4.6
"""

import os
import sys
import time
import json
import subprocess

try:
    import Quartz

    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False
    print("WARNING: Quartz not available. Install pyobjc-framework-Quartz.")
    print("  pip3 install pyobjc-framework-Quartz")

# --- Config ---
SHARED_DIR = os.path.expanduser("~/Desktop/claude-minecraft")
SCREENSHOT_PATH = os.path.join(SHARED_DIR, "screen.png")
COMMANDS_PATH = os.path.join(SHARED_DIR, "commands.json")
READY_PATH = os.path.join(SHARED_DIR, "ready.flag")
DONE_PATH = os.path.join(SHARED_DIR, "done.flag")
STATE_PATH = os.path.join(SHARED_DIR, "state.json")

# macOS virtual key codes
KEY_CODES = {
    "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3, "g": 5, "h": 4,
    "i": 34, "j": 38, "k": 40, "l": 37, "m": 46, "n": 45, "o": 31, "p": 35,
    "q": 12, "r": 15, "s": 1, "t": 17, "u": 32, "v": 9, "w": 13, "x": 7,
    "y": 16, "z": 6,
    "0": 29, "1": 18, "2": 19, "3": 20, "4": 21, "5": 23, "6": 22, "7": 26,
    "8": 28, "9": 25,
    "space": 49, "return": 36, "enter": 36, "escape": 53, "esc": 53,
    "tab": 48, "delete": 51, "backspace": 51,
    "shift": 56, "control": 59, "option": 58, "command": 55,
    "up": 126, "down": 125, "left": 123, "right": 124,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96,
    "f11": 103, "f12": 111,
    "/": 44, ".": 47, ",": 43, "-": 27, "=": 24, "[": 33, "]": 30,
    "`": 50, "'": 39, ";": 41, "\\": 42,
}

# Characters that need shift held
SHIFT_CHARS = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7",
    "*": "8", "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]",
    "|": "\\", ":": ";", '"': "'", "<": ",", ">": ".", "?": "/", "~": "`",
}


def find_minecraft_window():
    """Find the Minecraft Java window CGWindowID."""
    if not HAS_QUARTZ:
        return None, None

    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    for w in windows:
        name = w.get("kCGWindowName", "") or ""
        owner = w.get("kCGWindowOwnerName", "") or ""
        if "Minecraft" in name and owner in ("java", "MinecraftGame"):
            wid = w.get("kCGWindowNumber")
            print(f"  Found: '{name}' (owner: {owner}, CGWindowID: {wid})")
            return wid, name
    return None, None


def take_screenshot(window_id=None):
    """Capture screenshot of Minecraft window (or full screen)."""
    try:
        if window_id:
            cmd = ["screencapture", "-x", "-l", str(window_id), SCREENSHOT_PATH]
        else:
            cmd = ["screencapture", "-x", SCREENSHOT_PATH]
        subprocess.run(cmd, check=True, timeout=5)
        return os.path.exists(SCREENSHOT_PATH)
    except Exception as e:
        print(f"  Screenshot error: {e}")
        return False


def focus_minecraft():
    """Bring Minecraft window to front."""
    try:
        subprocess.run(
            [
                "osascript", "-e",
                """
            tell application "System Events"
                set javaProcesses to every process whose name is "java" or name is "MinecraftGame"
                if (count of javaProcesses) > 0 then
                    set frontmost of item 1 of javaProcesses to true
                end if
            end tell
        """,
            ],
            check=False,
            timeout=3,
        )
    except Exception:
        pass


def inject_key(key_code, down=True):
    """Inject a keyboard event via Quartz."""
    evt = Quartz.CGEventCreateKeyboardEvent(None, key_code, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)


def inject_key_tap(key_code, shift=False):
    """Press and release a key."""
    if shift:
        inject_key(KEY_CODES["shift"], True)
        time.sleep(0.02)
    inject_key(key_code, True)
    time.sleep(0.02)
    inject_key(key_code, False)
    if shift:
        time.sleep(0.02)
        inject_key(KEY_CODES["shift"], False)


def type_string(text):
    """Type a string character by character using Quartz key injection."""
    for ch in text:
        if ch == " ":
            inject_key_tap(KEY_CODES["space"])
        elif ch in SHIFT_CHARS:
            base = SHIFT_CHARS[ch]
            if base in KEY_CODES:
                inject_key_tap(KEY_CODES[base], shift=True)
        elif ch.isupper():
            if ch.lower() in KEY_CODES:
                inject_key_tap(KEY_CODES[ch.lower()], shift=True)
        elif ch.lower() in KEY_CODES:
            inject_key_tap(KEY_CODES[ch.lower()])
        else:
            subprocess.run(
                ["osascript", "-e",
                 f'tell application "System Events" to keystroke "{ch}"'],
                check=False, timeout=2,
            )
        time.sleep(0.03)


def inject_mouse_move(dx, dy):
    """Move mouse by delta (for camera look)."""
    cur = Quartz.CGEventCreate(None)
    pos = Quartz.CGEventGetLocation(cur)
    new_x = pos.x + dx
    new_y = pos.y + dy
    evt = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventMouseMoved, Quartz.CGPointMake(new_x, new_y), 0
    )
    Quartz.CGEventSetIntegerValueField(evt, 87, int(dx))  # deltaX
    Quartz.CGEventSetIntegerValueField(evt, 88, int(dy))  # deltaY
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)


def inject_mouse_click(x=None, y=None, button="left", down=True):
    """Click or press/release mouse button."""
    if x is not None and y is not None:
        point = Quartz.CGPointMake(x, y)
    else:
        cur = Quartz.CGEventCreate(None)
        point = Quartz.CGEventGetLocation(cur)

    if button == "left":
        evt_type = Quartz.kCGEventLeftMouseDown if down else Quartz.kCGEventLeftMouseUp
        btn = Quartz.kCGMouseButtonLeft
    else:
        evt_type = Quartz.kCGEventRightMouseDown if down else Quartz.kCGEventRightMouseUp
        btn = Quartz.kCGMouseButtonRight

    evt = Quartz.CGEventCreateMouseEvent(None, evt_type, point, btn)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)


def execute_command(cmd):
    """Execute a single command dict."""
    action = cmd.get("action", "")

    if action == "chat":
        inject_key_tap(KEY_CODES["t"])
        time.sleep(0.4)
        type_string(cmd.get("text", ""))
        time.sleep(0.15)
        inject_key_tap(KEY_CODES["return"])

    elif action == "slash":
        inject_key_tap(KEY_CODES["/"])
        time.sleep(0.4)
        type_string(cmd.get("text", ""))
        time.sleep(0.15)
        inject_key_tap(KEY_CODES["return"])

    elif action == "key_tap":
        key = cmd.get("key", "")
        shift = cmd.get("shift", False)
        if key.lower() in KEY_CODES:
            inject_key_tap(KEY_CODES[key.lower()], shift=shift)

    elif action == "key_down":
        key = cmd.get("key", "")
        if key.lower() in KEY_CODES:
            inject_key(KEY_CODES[key.lower()], True)

    elif action == "key_up":
        key = cmd.get("key", "")
        if key.lower() in KEY_CODES:
            inject_key(KEY_CODES[key.lower()], False)

    elif action == "walk":
        duration = cmd.get("duration", 1.0)
        inject_key(KEY_CODES["w"], True)
        time.sleep(duration)
        inject_key(KEY_CODES["w"], False)

    elif action == "walk_back":
        duration = cmd.get("duration", 1.0)
        inject_key(KEY_CODES["s"], True)
        time.sleep(duration)
        inject_key(KEY_CODES["s"], False)

    elif action == "strafe_left":
        duration = cmd.get("duration", 1.0)
        inject_key(KEY_CODES["a"], True)
        time.sleep(duration)
        inject_key(KEY_CODES["a"], False)

    elif action == "strafe_right":
        duration = cmd.get("duration", 1.0)
        inject_key(KEY_CODES["d"], True)
        time.sleep(duration)
        inject_key(KEY_CODES["d"], False)

    elif action == "jump":
        inject_key_tap(KEY_CODES["space"])

    elif action == "sprint_jump":
        inject_key(KEY_CODES["w"], True)
        time.sleep(0.05)
        inject_key(KEY_CODES["w"], False)
        time.sleep(0.05)
        inject_key(KEY_CODES["w"], True)
        time.sleep(0.1)
        inject_key_tap(KEY_CODES["space"])
        time.sleep(cmd.get("duration", 1.0))
        inject_key(KEY_CODES["w"], False)

    elif action == "look":
        inject_mouse_move(cmd.get("dx", 0), cmd.get("dy", 0))

    elif action == "left_click":
        inject_mouse_click(button="left", down=True)
        time.sleep(0.05)
        inject_mouse_click(button="left", down=False)

    elif action == "right_click":
        inject_mouse_click(button="right", down=True)
        time.sleep(0.05)
        inject_mouse_click(button="right", down=False)

    elif action == "hold_click":
        duration = cmd.get("duration", 1.0)
        inject_mouse_click(button="left", down=True)
        time.sleep(duration)
        inject_mouse_click(button="left", down=False)

    elif action == "escape":
        inject_key_tap(KEY_CODES["escape"])

    elif action == "inventory":
        inject_key_tap(KEY_CODES["e"])

    elif action == "drop":
        inject_key_tap(KEY_CODES["q"])

    elif action == "hotbar":
        slot = str(cmd.get("slot", 1))
        if slot in KEY_CODES:
            inject_key_tap(KEY_CODES[slot])

    elif action == "sneak":
        duration = cmd.get("duration", 1.0)
        inject_key(KEY_CODES["shift"], True)
        time.sleep(duration)
        inject_key(KEY_CODES["shift"], False)

    elif action == "scroll":
        amount = cmd.get("amount", 1)
        direction = cmd.get("direction", "up")
        scroll_val = amount if direction == "up" else -amount
        evt = Quartz.CGEventCreateScrollWheelEvent(None, 0, 1, scroll_val)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)

    elif action == "sleep":
        time.sleep(cmd.get("duration", 0.5))

    elif action == "noop":
        pass

    else:
        print(f"  Unknown action: {action}")


def main():
    print("=" * 50)
    print("  Claude-Minecraft Bridge (Python/Quartz)")
    print("=" * 50)
    print(f"Shared folder: {SHARED_DIR}")
    print()

    os.makedirs(SHARED_DIR, exist_ok=True)

    # Clean up
    for f in [COMMANDS_PATH, READY_PATH, DONE_PATH, SCREENSHOT_PATH, STATE_PATH]:
        if os.path.exists(f):
            os.remove(f)

    # Find Minecraft window
    print("Looking for Minecraft window...")
    window_id, window_name = find_minecraft_window()
    if window_id:
        print(f"  Will capture window: {window_name}")
    else:
        print("  Minecraft window not found — using full screen capture")

    # Focus Minecraft
    print("Bringing Minecraft to front...")
    focus_minecraft()
    time.sleep(0.5)

    print()
    print("Bridge running! Claude can now see and control Minecraft.")
    print("Press Ctrl+C to stop.")
    print()

    cycle = 0
    while True:
        try:
            cycle += 1

            success = take_screenshot(window_id)
            if not success:
                print(f"  [Cycle {cycle}] Screenshot failed, retrying...")
                time.sleep(1)
                window_id, window_name = find_minecraft_window()
                continue

            fsize = os.path.getsize(SCREENSHOT_PATH)
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] Cycle {cycle} — Screenshot ({fsize:,} bytes). Waiting...")

            state = {
                "cycle": cycle,
                "timestamp": time.time(),
                "window_id": window_id,
                "window_name": window_name,
                "screenshot_size": fsize,
            }
            with open(STATE_PATH, "w") as f:
                json.dump(state, f)

            with open(READY_PATH, "w") as f:
                f.write(str(cycle))

            while not os.path.exists(COMMANDS_PATH):
                time.sleep(0.2)

            time.sleep(0.1)

            try:
                with open(COMMANDS_PATH, "r") as f:
                    commands = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"  Error reading commands: {e}")
                os.remove(COMMANDS_PATH)
                continue

            print(f"[{time.strftime('%H:%M:%S')}] Executing {len(commands)} command(s)...")

            focus_minecraft()
            time.sleep(0.15)

            for i, cmd in enumerate(commands):
                try:
                    execute_command(cmd)
                    time.sleep(0.03)
                except Exception as e:
                    print(f"  Error in command {i}: {e}")

            os.remove(COMMANDS_PATH)
            with open(DONE_PATH, "w") as f:
                f.write(str(cycle))

            time.sleep(0.15)

        except KeyboardInterrupt:
            print("\nBridge stopped.")
            break
        except Exception as e:
            print(f"  Error in main loop: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
