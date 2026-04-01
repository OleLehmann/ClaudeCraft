#!/usr/bin/env python3
"""
Capture the full argv of a running process on macOS using sysctl KERN_PROCARGS2.

Unlike `ps -o args=` which truncates long command lines and joins arguments
with spaces (breaking paths that contain spaces), this reads the raw
null-terminated argument array from the kernel.

This is essential for Minecraft Java Edition, whose classpath contains paths
like "~/Library/Application Support/minecraft/..." — the space in
"Application Support" would cause naive ps-based parsing to split it into
two arguments.

Usage:
    python3 capture-argv.py <pid> [output_file]

If output_file is omitted, prints one argument per line to stdout.

Author: Claude Opus 4.6
"""

import sys
import struct
import ctypes
import ctypes.util


def get_process_argv(pid: int) -> list[str]:
    """
    Read the full argument vector of a process using sysctl KERN_PROCARGS2.

    On macOS, the kernel stores process arguments in a structure accessible
    via sysctl with CTL_KERN + KERN_PROCARGS2. The layout is:

        [argc: int32]
        [exec_path: null-terminated string]
        [padding: zero or more null bytes]
        [argv[0]: null-terminated string]
        [argv[1]: null-terminated string]
        ...
        [argv[argc-1]: null-terminated string]
        [environment variables follow, but we stop at argc]

    Returns a list of strings: [argv[0], argv[1], ..., argv[argc-1]]
    where argv[0] is typically the executable path.
    """
    libc = ctypes.CDLL(ctypes.util.find_library("c"))

    CTL_KERN = 1
    KERN_PROCARGS2 = 49

    mib = (ctypes.c_int * 3)(CTL_KERN, KERN_PROCARGS2, pid)

    # First call: get required buffer size
    size = ctypes.c_size_t(0)
    ret = libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0)
    if ret != 0:
        raise OSError(f"sysctl size query failed for PID {pid} (process may not exist or permission denied)")

    # Second call: read the data
    buf = ctypes.create_string_buffer(size.value)
    ret = libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0)
    if ret != 0:
        raise OSError(f"sysctl read failed for PID {pid}")

    raw = buf.raw[: size.value]

    # Parse argc (first 4 bytes, little-endian int32)
    argc = struct.unpack("i", raw[:4])[0]

    # Skip past the exec_path (null-terminated string after argc)
    idx = 4
    while idx < len(raw) and raw[idx] != 0:
        idx += 1

    # Skip past null padding between exec_path and argv
    while idx < len(raw) and raw[idx] == 0:
        idx += 1

    # Read argc null-terminated argument strings
    args = []
    for _ in range(argc):
        end = raw.index(b"\x00", idx)
        args.append(raw[idx:end].decode("utf-8", errors="replace"))
        idx = end + 1

    return args


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <pid> [output_file]", file=sys.stderr)
        sys.exit(1)

    pid = int(sys.argv[1])
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        args = get_process_argv(pid)
    except OSError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if output_file:
        with open(output_file, "w") as f:
            for arg in args:
                f.write(arg + "\n")
        print(f"Captured {len(args)} arguments → {output_file}")
    else:
        for i, arg in enumerate(args):
            print(f"argv[{i}]: {arg}")


if __name__ == "__main__":
    main()
