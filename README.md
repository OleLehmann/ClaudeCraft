# Claude Plays Minecraft

**Claude (Opus 4.6) playing Minecraft Java Edition using computer-use tools on macOS.**

This repo contains the tools and techniques we developed to give Claude full visual and interactive control of Minecraft Java Edition through Anthropic's computer-use API. The entire project — code, problem-solving, and this documentation — was authored by Claude Opus 4.6.

## The Problem

Anthropic's computer-use tools use **macOS compositor-level screenshot filtering**: only apps on a session allowlist are visible. You grant access by calling `request_access("app name")`, which looks up apps by their **macOS bundle ID** (`CFBundleIdentifier` in `Info.plist`).

Minecraft Java Edition has a split architecture:

| Process | Bundle ID | Recognized by computer-use? |
|---|---|---|
| **Launcher** (`/Applications/Minecraft.app`) | `com.mojang.minecraftlauncher` | Yes |
| **Game** (bare `java` binary) | *none* | **No** |

The launcher is a proper `.app` bundle. But the actual game is a raw Java process spawned by the launcher and reparented to `launchd` (PID 1). It has no `.app` bundle, no `Info.plist`, no `CFBundleIdentifier`. To macOS, it's just an anonymous `/path/to/bin/java` process.

**Result:** The game window is invisible to screenshots and untouchable by click/key tools. Requesting access to `"java"`, `"net.java.openjdk.jdk"` (the JRE bundle ID), or `"Minecraft"` (which only matches the launcher) all fail.

## The Solution: `.app` Wrapper with Symlinked Java Binary

We create a minimal macOS `.app` bundle where `CFBundleExecutable` is a **symlink to the actual Java binary**. When launched via `open -a`, macOS Launch Services registers the process under our custom bundle ID (`com.claude.minecraftgame`). Since Java runs directly as the app's process (no intermediate shell, no `exec`), all windows it creates are associated with our bundle.

```
/Applications/MinecraftGame.app/
  Contents/
    Info.plist              ← bundle ID: com.claude.minecraftgame
    MacOS/
      MinecraftGame → symlink → ~/.../jre.bundle/.../bin/java
```

### How it works step by step

1. **Capture the launch command** — The Minecraft Launcher handles Microsoft/Xbox authentication and constructs a complex Java command line with ~42 arguments including a session access token. We let the launcher start the game normally, then use `sysctl KERN_PROCARGS2` to extract the full `argv` array from the running process (preserving arguments with spaces in paths like `~/Library/Application Support/minecraft/...`).

2. **Kill the original process** — The Java game started by the launcher has no bundle association.

3. **Build the `.app` bundle** — Create a minimal `.app` in `/Applications` with a symlink from `Contents/MacOS/MinecraftGame` to the Java binary, and an `Info.plist` with our custom bundle ID.

4. **Relaunch through the `.app`** — Run `open -a MinecraftGame --args <captured arguments>`. Launch Services registers the PID under `com.claude.minecraftgame`. Java creates its LWJGL/OpenGL window, which WindowServer associates with that PID.

5. **Grant access** — `request_access("MinecraftGame")` now works. Claude can see and interact with the Minecraft window.

### Why `exec` doesn't work

Our first attempt used a bash script as `CFBundleExecutable` that called `exec java ...`. While `exec` preserves the PID, Launch Services appears to deregister the bundle association when the process image changes. The symlink approach avoids this entirely — Java **is** the executable from the start.

### Why location matters

The `.app` must be in `/Applications` (or another standard app directory). Computer-use tools don't recognize apps in arbitrary locations like `~/Desktop`.

## Quick Start

```bash
# Run the all-in-one build script
bash app-wrapper/build.sh
```

This will:
1. Open the Minecraft Launcher (click Play when it appears)
2. Capture the Java command line with auth token
3. Build `MinecraftGame.app` in `/Applications`
4. Relaunch Minecraft under the new bundle

Then in your computer-use session:
```
request_access("MinecraftGame")  # or "com.claude.minecraftgame"
```

Claude can now see and play Minecraft.

## Alternative: Terminal-Based Controller

If you don't need computer-use tools specifically, the `controller/` directory has standalone bridges that use `screencapture` + `osascript`/`Quartz` for vision and input:

- **`controller.sh`** — Bash-based. Uses `screencapture` for screenshots and `osascript` for keyboard/mouse input. Simple command protocol via text files.
- **`bridge.py`** — Python-based. Uses Quartz `CGEvent` injection for lower-latency input. JSON command protocol.

Both use a shared-folder architecture: take screenshot → wait for Claude to write commands → execute commands → repeat.

## Repository Structure

```
claude-plays-minecraft/
├── README.md                    # This file
├── app-wrapper/
│   ├── build.sh                 # All-in-one: capture, build .app, launch
│   ├── Info.plist               # Template Info.plist for the .app bundle
│   └── capture-argv.py          # Standalone argv capture via sysctl
├── controller/
│   ├── controller.sh            # Bash-based screen+input bridge
│   └── bridge.py                # Python/Quartz-based bridge (lower latency)
└── docs/
    └── how-it-works.md          # Deep technical explanation
```

## Requirements

- **macOS** (tested on macOS 15 / Apple Silicon)
- **Minecraft Java Edition** (tested with 26.1.1)
- **Python 3** (ships with macOS)
- **Accessibility permission** for Terminal (System Settings → Privacy & Security → Accessibility)
- **Screen Recording permission** for Terminal (for the controller/bridge approach)
- **Anthropic computer-use API access** (for the `.app` wrapper approach)

## How Claude Plays

With the `.app` wrapper granting visual access, Claude uses the computer-use tools' native screenshot and click/key capabilities to:

1. **See** — Take screenshots of the Minecraft window
2. **Decide** — Analyze the game state (health, inventory, surroundings, objectives)
3. **Act** — Send keyboard and mouse inputs (movement, commands, inventory management)
4. **Repeat** — Screenshot → think → act loop

For game commands (which tolerate latency), Claude opens chat with `T` and types commands like `/gamemode creative`, `/give`, `/tp`, `/fill`, etc.

For real-time actions (which need lower latency), Claude uses the controller bridge to batch inputs.

## Auth Token Notes

The Minecraft access token is obtained by the launcher via Microsoft/Xbox Live authentication. It's session-specific and typically valid for ~24 hours. The `build.sh` script captures it from the running process's arguments. If the token expires, just run `build.sh` again (delete `/tmp/mc_java_argv.txt` first to force re-capture).

## Credits

This entire project — the problem diagnosis, the solution engineering, the code, and this documentation — was authored by **Claude Opus 4.6** (Anthropic's Claude, `claude-opus-4-6` model). The human provided the Minecraft installation, macOS environment, enthusiasm, and the critical nudge to "not give up" when the first approaches failed.

## License

MIT
