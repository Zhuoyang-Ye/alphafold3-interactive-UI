# AlphaFold 3 Explorer for macOS

Native macOS desktop application for **AlphaFold 3 · Interaction Studio**.

---

## ⚡ Quick Start

1. Download **[AlphaFold3-Explorer-macOS.zip](AlphaFold3-Explorer-macOS.zip)**.
2. Unzip and drag **AlphaFold 3 Explorer.app** to your `Applications` folder.
3. Double-click to launch!

---

## 🌟 Features

- **Native macOS Window & Menu Bar**: Seamless integration with macOS appearance, window management, and keyboard shortcuts.
- **Dark / Light Theme Switch**: Switch appearance with `⌘T` or the in-app toggle.
- **Beginner-Friendly Explorer Mode**: Explore molecular architectures with plain-English guides, smooth 3D auto-spin, and pocket focus.
- **Local Data Portal**: Built-in automated database download and environment assistant (`⌘D`).
- **Hardware Acceleration**: Optimized for Apple Silicon (M1/M2/M3/M4) GPU with Metal / MPS.

---

## 🛠️ Building from Source

To compile the native app bundle from Swift source:

```bash
swiftc -parse-as-library -framework Cocoa -framework WebKit apps/macos/AppDelegate.swift -o "apps/macos/AlphaFold3 Explorer.app/Contents/MacOS/AlphaFold3 Explorer"
```
