---
name: system-info
description: >
  Use when asked to report OS/hardware details, compile binaries, set up build
  environments, or diagnose architecture-specific issues. Triggers: 'system info',
  'what hardware', 'compile for this machine', 'build for arch', 'dettagli macchina',
  'hardware report', 'specifica sistema', 'check OS', 'uname'.
orchestrator:
  parallel: false
  type: kb
---

# System Info

Gather detailed machine information to make correct build decisions (architecture,
target triple, available toolchains, CPU features).

## Quick Report

Summarize at the start of any build task:

| Field | Command |
|-------|---------|
| OS | `uname -srmo` |
| Distro | `. /etc/os-release && echo "$ID $VERSION_ID"` |
| Kernel | `uname -r` |
| Arch | `uname -m` |
| CPU | `lscpu \| grep 'Model name' \| head -1 \| cut -d: -f2 \| xargs` |
| Cores | `nproc` |
| RAM | `free -h \| awk '/^Mem:/ {print $2}'` |
| GPU | `lspci \| grep -i 'vga\|3d\|display' \| head -1 \| cut -d: -f3- \| xargs` |
| GPU driver | `glxinfo -B 2>/dev/null \| grep 'Device:' \| head -1 \| xargs` |
| gcc/clang | `gcc --version 2>/dev/null \| head -1; clang --version 2>/dev/null \| head -1` |
| rustc | `rustc --version 2>/dev/null` |
| Target triple | `gcc -dumpmachine 2>/dev/null \|\| rustc -vV \| grep host \| cut -d' ' -f2` |
| Endianness | `lscpu \| grep 'Byte Order' \| cut -d: -f2 \| xargs` |

## Build Configuration

Set these variables based on system info:

- **ARCH** = `uname -m` (x86_64, aarch64, armv7l, riscv64, etc.)
- **OS** = distro ID from `/etc/os-release`
- **CPUS** = `nproc` (for `make -j$CPUS`)

### Cross-compilation hints

| Host arch | Common target | Notes |
|-----------|---------------|-------|
| x86_64 | aarch64-unknown-linux-gnu | Needs `gcc-aarch64-linux-gnu` |
| x86_64 | armv7-unknown-linux-gnueabihf | Needs `gcc-arm-linux-gnueabihf` |
| aarch64 | x86_64-unknown-linux-gnu | Needs `gcc-x86-64-linux-gnu` (slower) |
| any | wasm32-unknown-unknown | Needs `wasm-pack` or `rustup target add` |

## QEMU binfmt (container builds)

```bash
# Check binfmt support
ls /proc/sys/fs/binfmt_misc/ 2>/dev/null | grep -q qemu && echo "QEMU binfmt available"

# Register (if missing)
sudo docker run --privileged --rm tonistiigi/binfmt --install all
```

Full commands:

```bash
# Kernel + arch
uname -a

# Distro
cat /etc/os-release | head -10

# CPU features
lscpu | grep -E 'Model name|Architecture|CPU\(s\)|Thread|Core|Socket|Flag'

# Memory
free -h

# Disk
df -h / | tail -1 | awk '{print $2, $3, $4, $5}'

# GPU
lspci | grep -iE 'vga|3d|display'

# PCI devices
lspci | head -20

# USB devices
lsusb | head -10

# Installed dev tools
for tool in gcc g++ clang cmake make rustc cargo python3 node go java zig; do
  which "$tool" >/dev/null 2>&1 && echo "$tool: $($tool --version 2>&1 | head -1)"
done
```
