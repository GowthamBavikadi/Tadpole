# Lily Pad

<div align="center">

![Platform](https://img.shields.io/badge/platform-macOS%2014%2B-black?style=flat-square&logo=apple&logoColor=white)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-6.6%2B-41CD52?style=flat-square&logo=qt&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)

**A desktop frog that catches your ideas before your mind hops to the next one.**

</div>

---

## The Problem

My mind jumps between topics all day. Good ideas disappear the moment I switch context. Most "second brain" tools are built around organization — folders, tags, workflows. That's not the problem I needed to solve. The problem is *capture*. Catching the idea in the first second before it's gone.

So I built a small desktop companion that catches them for me.

---

## What It Does

Lily Pad runs as a floating Ash-Greninja sprite that lives on your macOS screen. You drag a file, URL, screenshot, or half-formed thought onto it — an AI triage engine sorts it into an idea, a task, or a reference in the background, writes a clean summary, and stores it locally. Click the pet to open a native Apple Liquid Glass HUD and see everything you were thinking about, what's pending, and what's worth picking up.

Capture is instant. Nothing needs organizing. Nothing gets lost.

```
Drop anything onto the pet  →  AI triage (background thread)  →  SQLite + Obsidian vault  →  0 ms HUD
```

Your notes and vault stay on your Mac.

---

## Features

| Feature | Detail |
|---|---|
| **Floating Desktop Pet** | Ash-Greninja sprite with 60 FPS ballistic throw physics and elastic wall bouncing |
| **Apple Liquid Glass HUD** | Native macOS frosted-glass popover with hardware blur, task tabs, ideas tab, and a slash-command input |
| **AI Triage Pipeline** | Multi-provider LLM cascade (Groq → Gemini → Pollinations → NVIDIA NIM) — runs on drop, never on display |
| **Zero-Latency Surface** | HUD reads static SQLite rows at open time — renders in under 5 ms regardless of vault size |
| **Drag-and-Drop Capture** | Drop PDFs, images, URLs, text snippets, or video links directly onto the pet |
| **Obsidian Vault Sync** | Every captured item auto-generates a structured Markdown note with YAML frontmatter |
| **macOS Automation** | Native Apple Reminders and Calendar creation via AppleScript (`/remind`, `/calendar`) |
| **Focus Guard** | `/focus [topic]` sets an active focus context broadcast to the AI system prompt |
| **Inbox Watcher** | Background daemon monitors `~/Desktop/Brain_Drop` and auto-ingests any file dropped there |
| **Terminal CLI** | Full REPL with streaming AI responses and all slash commands |

---

## Architecture

```
+----------------------------------------------------------+
|                      CAPTURE LAYER                       |
|   Drag & Drop onto pet  *  Terminal /drop  *  Inbox Watch|
+---------------------------+------------------------------+
                            |  QThread (non-blocking)
                            v
+----------------------------------------------------------+
|               ASYNC TRIAGE ENGINE (brain_ai.py)          |
|   Groq -> Gemini -> Pollinations -> NVIDIA NIM cascade   |
|   Single-pass JSON: title, summary, type, tags, due_date |
+------------------+---------------------------------------+
                   |
        +----------+-----------+
        v                      v
+---------------+    +----------------------+
|   SQLite DB   |    |    Obsidian Vault    |
|   brain.db    |    |    vault/Ideas/      |
|   drops tasks |    |    vault/Tasks/      |
|   focus notes |    |    vault/Documents/  |
+-------+-------+    +----------------------+
        |
        v
+----------------------------------------------------------+
|                     SURFACE LAYER                        |
|   Liquid Glass HUD  *  Task toggles  *  Focus badge     |
|   0 ms render latency (reads static cache only)         |
+----------------------------------------------------------+
```

**Core principle:** Compute on drop. Never on display.

---

## Project Structure

```
lily-pad/
├── src/
│   ├── pet_main.py          # Entry point — compiles & launches native binary
│   ├── pet_window.py        # Transparent overlay, Cocoa flags, physics, drag-drop
│   ├── pet_hud.py           # Apple Liquid Glass HUD — tasks, ideas, slash commands
│   ├── brain_core.py        # Unified ingest_drop() pipeline, Obsidian sync
│   ├── brain_ai.py          # Multi-provider LLM cascade, triage_drop(), local refiner
│   ├── database.py          # SQLite schema, WAL mode, FTS5 full-text search
│   ├── mac_integration.py   # AppleScript: Reminders + Calendar
│   ├── brain.py             # Terminal CLI REPL
│   ├── watcher.py           # ~/Desktop/Brain_Drop folder daemon
│   └── BrainPet.swift       # Native SwiftUI Liquid Glass binary (compiled on first run)
├── assets/
│   ├── greninja/            # Sprite sheets (frame_ROW_COL.png, 4 rows x 8 frames)
│   ├── greninja_crouch/     # Crouch variant sprite sheets
│   ├── greninja_shiny/      # Shiny variant sprite sheets
│   └── pet_manifest.json    # Model registry — hot-swap characters without touching Python
├── vault/                   # Obsidian vault (auto-created on first run, git-ignored)
├── data/
│   └── brain.db             # SQLite database (auto-created, WAL mode)
├── logs/                    # stdout/stderr from LaunchAgent (auto-created)
├── com.gowtham.brainpet.plist  # macOS LaunchAgent — auto-start at login
├── run.sh                   # Unified launcher (pet / cli / watcher)
├── requirements.txt         # Python dependencies
└── .env                     # API keys (never committed)
```

---

## Setup

### Prerequisites

- macOS 14 Sonoma or later
- Python 3.11+
- Xcode Command Line Tools (`xcode-select --install`) — required to compile the Swift binary on first run

### Install

```bash
git clone https://github.com/YOUR_USERNAME/lily-pad.git
cd lily-pad

# Copy and fill in your API keys
cp .env.example .env
```

```
# .env
GEMINI_API_KEY=...       # Free at aistudio.google.com
GROQ_API_KEY=...         # Free at console.groq.com  (optional, fastest)
NVIDIA_API_KEY=...       # Free at build.nvidia.com  (optional, fallback)
```

```bash
# Run (creates venv + installs deps on first launch)
./run.sh
```

The first run compiles `src/BrainPet.swift` into `bin/BrainPet` and starts the pet. Subsequent runs are instant.

### Other Modes

```bash
./run.sh --cli       # Terminal REPL with streaming AI
./run.sh --watcher   # Background inbox folder daemon
```

---

## Usage

### Desktop Pet

| Action | Result |
|---|---|
| **Left-click** | Toggle the Liquid Glass HUD open/close |
| **Drag & drop file** | Ingest PDF, image, or any file into the AI pipeline |
| **Drag & drop URL / text** | Triage and save as idea or task |
| **Click-drag to move** | Reposition the pet anywhere on screen |
| **Flick/throw** | Release with velocity to launch with bounce physics |
| **Right-click** | Context menu: Open HUD, Rest in Place, Open Vault, Quit |

### HUD Slash Commands

Type directly in the input pill at the bottom of the HUD:

```
/focus Ship v2             Set active focus context
/focus off                 Clear focus
/remind Call dentist tomorrow 09:00
/calendar Team sync 2026-11-05 14:00
/note Quick thought to capture
/clear reminders           Delete all app-created Apple Reminders
```

### Terminal CLI

```bash
./run.sh --cli

> /drop https://arxiv.org/abs/2310.01234    # Triage a paper
> /drop assets/research.pdf                 # Summarise a PDF
> /tasks                                    # List pending tasks
> /focus Write thesis chapter 3
> What did I save about transformers?       # Semantic vault search
```

### Inbox Watcher

```bash
./run.sh --watcher
# Drop any file into ~/Desktop/Brain_Drop
# Auto-ingested and archived to ~/Desktop/Brain_Drop/Processed/
```

---

## Auto-Start at Login

> **Note:** Update the absolute paths in `com.gowtham.brainpet.plist` to match your local clone location before loading.

```bash
mkdir -p ~/Library/LaunchAgents
cp com.gowtham.brainpet.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.gowtham.brainpet.plist
```

Logs go to `logs/pet_stdout.log` and `logs/pet_stderr.log`.

To stop auto-start:

```bash
launchctl unload ~/Library/LaunchAgents/com.gowtham.brainpet.plist
```

---

## AI Provider Cascade

The triage engine tries providers in order, falling back automatically:

1. **Groq** (`llama-3.3-70b-versatile`) — fastest, free tier, requires `GROQ_API_KEY`
2. **Google Gemini** (`gemini-2.5-flash`) — free tier, requires `GEMINI_API_KEY`
3. **Pollinations AI** — zero-key free public endpoint, always available
4. **NVIDIA NIM** (`llama-3.3-70b-instruct`, `mistral-large-2-instruct`) — requires `NVIDIA_API_KEY`

All providers produce the same structured JSON output. The active provider is shown in the HUD status badge.

---

## Sprite Sheet Format

The pet renderer expects sprites in `assets/<skin_name>/frame_ROW_COL.png`:

```
Row 0  IDLE animation   (8 frames)
Row 1  WANDER / THROWN  (8 frames)
Row 2  EATING           (8 frames)
Row 3  THINKING         (8 frames)
```

To add a new skin, drop a folder matching this layout into `assets/` and add an entry to `assets/pet_manifest.json`.

---

## Requirements

```
google-genai>=0.3.0
python-dotenv>=1.0.0
requests>=2.31.0
pypdf>=4.0.0
yt-dlp>=2024.1.0
pillow>=10.0.0,<12.0.0
PySide6>=6.6.0
pyobjc-framework-Cocoa>=10.0
pyobjc-framework-Quartz>=10.0
```

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">
Built on a MacBook Air. Powered by Gemini, Groq, and the need to not lose another idea.
</div>
