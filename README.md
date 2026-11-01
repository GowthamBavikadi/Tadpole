# Brain — AI-Powered macOS Second Brain

<div align="center">

![Platform](https://img.shields.io/badge/platform-macOS%2014%2B-black?style=flat-square&logo=apple&logoColor=white)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-6.6%2B-41CD52?style=flat-square&logo=qt&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)

**A floating Ash-Greninja desktop pet that lives on your macOS screen, captures every idea and task you throw at it, and surfaces them through a zero-latency Apple Liquid Glass HUD.**

</div>

---

## What It Is

Brain is a personal AI second-brain built natively for macOS. It runs as a transparent, always-on-top Greninja sprite that roams your desktop. You drag files, URLs, screenshots, and raw thoughts onto it — it triages them with an LLM cascade in the background, persists everything to SQLite and an Obsidian vault, and makes it instantly accessible through a click-to-open HUD. No dock icon. No menu bar clutter. No latency.

```
Drag anything onto Greninja → AI triage (background thread) → SQLite + Obsidian → 0ms HUD
```

---

## Features

| Feature | Detail |
|---|---|
| **Floating Desktop Pet** | Ash-Greninja sprite with 60 FPS ballistic throw physics and elastic wall bouncing — roams your Terminal window region autonomously |
| **Apple Liquid Glass HUD** | Authentic macOS frosted-glass popover with hardware `CGSSetWindowBackgroundBlurRadius` blur, task tabs, ideas tab, and a slash-command input pill |
| **AI Triage Pipeline** | Multi-provider LLM cascade (Groq → Gemini → Pollinations → NVIDIA NIM) runs on drop in a `QThread` — never on display |
| **Zero-Latency Surface** | HUD reads static SQLite rows at open time — renders in `<5ms` regardless of vault size |
| **Drag-and-Drop Capture** | Drop PDFs, images, URLs, text snippets, or Instagram Reel links directly onto the pet |
| **Obsidian Vault Sync** | Every captured item auto-generates a structured Markdown note with YAML frontmatter into `vault/` |
| **macOS Automation** | Native Apple Reminders and Calendar creation via AppleScript (`/remind`, `/calendar`) |
| **Focus Guard** | `/focus [topic]` sets an active focus context broadcast to the AI system prompt |
| **Inbox Watcher** | Background daemon monitors `~/Desktop/Brain_Drop` and auto-ingests any file dropped there |
| **Terminal CLI** | Full `brain.py` REPL with streaming AI responses and all slash commands |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     CAPTURE LAYER                        │
│  Drag & Drop onto pet  •  Terminal /drop  •  Inbox Watch │
└──────────────────────────┬──────────────────────────────┘
                           │  QThread (non-blocking)
                           ▼
┌─────────────────────────────────────────────────────────┐
│               ASYNC TRIAGE ENGINE (brain_ai.py)          │
│  Groq → Gemini → Pollinations → NVIDIA NIM cascade       │
│  Single-pass JSON: title, summary, type, tags, due_date  │
└────────────────┬────────────────────────────────────────┘
                 │
      ┌──────────┴───────────┐
      ▼                      ▼
┌──────────────┐    ┌──────────────────────┐
│  SQLite DB   │    │   Obsidian Vault      │
│  brain.db    │    │   vault/Ideas/        │
│  drops tasks │    │   vault/Tasks/        │
│  focus notes │    │   vault/Documents/    │
└──────┬───────┘    └──────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│                    SURFACE LAYER                          │
│   Liquid Glass HUD  •  Task toggles  •  Focus badge      │
│   0ms render latency (reads cache only)                  │
└─────────────────────────────────────────────────────────┘
```

**Core principle:** Compute on drop. Never on display.

---

## Project Structure

```
brain/
├── src/
│   ├── pet_main.py          # Entry point — compiles & launches native BrainPet binary
│   ├── pet_window.py        # Transparent overlay, Cocoa flags, physics, drag-drop
│   ├── pet_hud.py           # Apple Liquid Glass HUD — tasks, ideas, slash commands
│   ├── brain_core.py        # Unified ingest_drop() pipeline, Obsidian sync
│   ├── brain_ai.py          # Multi-provider LLM cascade, triage_drop(), polish
│   ├── database.py          # SQLite schema, WAL mode, FTS5 full-text search
│   ├── mac_integration.py   # AppleScript: Reminders + Calendar
│   ├── brain.py             # Terminal CLI REPL
│   ├── watcher.py           # ~/Desktop/Brain_Drop folder daemon
│   └── BrainPet.swift       # Native SwiftUI Liquid Glass binary (compiled on first run)
├── assets/
│   ├── greninja_crouch/     # Sprite sheets (frame_ROW_COL.png, 4 rows × 8 frames)
│   ├── greninja_shiny/      # Shiny variant sprite sheets
│   ├── ash_greninja_3d/     # 3DS model textures (.fbx, .dae, .smd)
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
- Xcode Command Line Tools (`xcode-select --install`) — required to compile `BrainPet.swift`

### Install

```bash
git clone https://github.com/YOUR_USERNAME/brain.git
cd brain

# Copy and fill in your API keys
cp .env.example .env
```

```bash
# .env
GEMINI_API_KEY=AIza...          # Free at aistudio.google.com
GROQ_API_KEY=gsk_...            # Free at console.groq.com  (optional, fastest)
NVIDIA_API_KEY=nvapi-...        # Free at build.nvidia.com  (optional, fallback)
```

```bash
# Run the desktop pet (creates venv + installs deps on first launch)
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
| **Flick/throw** | Release with velocity to launch the pet with bounce physics |
| **Right-click** | Context menu: Open Brain, Rest in Place, Open Vault, Quit |

### HUD Slash Commands

Type directly in the input pill at the bottom of the HUD:

```
/focus Ship Brain v2       Set active focus context
/focus off                 Clear focus
/remind Buy groceries tomorrow 09:00
/calendar Team sync 2026-11-05 14:00
/note Quick thought to capture
/clear reminders           Delete all Brain-created Apple Reminders
```

### Terminal CLI

```bash
./run.sh --cli

# Then type naturally:
> /drop https://arxiv.org/abs/2310.01234    # Triage a paper
> /drop assets/research.pdf                 # Summarise a PDF
> /tasks                                    # List pending tasks
> /focus Write thesis chapter 3
> What did I save about transformers?       # Semantic vault search
```

### Inbox Watcher

```bash
./run.sh --watcher
# Drop any file into ~/Desktop/Brain_Drop — auto-ingested and archived to ~/Desktop/Brain_Drop/Processed/
```

---

## Auto-Start at Login

> **Note:** Update the working directory paths in `com.gowtham.brainpet.plist` to match your local clone location before loading the agent.

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

The provider that responds is shown in the HUD status badge. All providers produce the same structured JSON output.

---

## Sprite Sheet Format

The pet renderer expects sprites in `assets/<skin_name>/frame_ROW_COL.png`:

```
Row 0 → IDLE animation   (8 frames)
Row 1 → WANDER / THROWN  (8 frames)
Row 2 → EATING           (8 frames)
Row 3 → THINKING         (8 frames)
```

To add a new skin, drop a folder matching this layout into `assets/` and add an entry to `assets/pet_manifest.json`.

---

## Requirements

```
google-genai>=0.3.0
python-dotenv>=1.0.0
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
Built on a MacBook Air. Powered by Gemini, Groq, and an unhealthy amount of coffee.
</div>

