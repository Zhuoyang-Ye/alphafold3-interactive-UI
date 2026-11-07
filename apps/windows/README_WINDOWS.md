# Getting Started on Windows (No Python Experience Needed)

This guide walks you through running the **AlphaFold 3 Explorer Desktop App** on Windows 10 or 11.

---

## ⚡ Quick Start (One-Click)

1. Double-click **`AlphaFold3_Explorer.bat`**.
2. If this is your first time, it will automatically download `uv` and configure Python.
3. The app opens in its own window (powered by Microsoft Edge / Chrome in app mode).
4. You are ready to explore and run predictions!

---

## 🛠️ Automated Setup

If you prefer to run setup from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
```

This creates a convenient **"AlphaFold 3 Explorer"** shortcut directly on your Windows Desktop.

---

## 💾 Downloading Local Databases

AlphaFold 3 offers two execution modes:

### 1. Instant Sequence-Only Mode (0 GB download)
In the app, choose **New experiment → Run mode: Sequence-only prediction**.
No large databases are needed! Perfect for fast initial checks and learning.

### 2. Full Database Mode (~250 GB download / ~630 GB disk space)
To download the complete databases for maximum accuracy:

```powershell
# Default: downloads to %USERPROFILE%\public_databases
powershell -ExecutionPolicy Bypass -File .\fetch_databases_windows.ps1

# Or put them on an external SSD (e.g. Drive D:)
powershell -ExecutionPolicy Bypass -File .\fetch_databases_windows.ps1 -TargetDir "D:\AlphaFold3_Databases"
```

---

## 🔑 Model Weights

Obtain the model parameters (`af3.bin.zst`, ~1 GB) from Google DeepMind as described in the repository's [docs/installation.md](../../docs/installation.md#obtaining-model-parameters). Place the file in `%USERPROFILE%\models\af3.bin.zst`.
