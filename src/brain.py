# brain.py — Cloud-powered terminal agent (Gemini)
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from database import get_db, get_focus, get_pending_tasks
from brain_ai import chat, stream_chat, NVIDIA_MODEL
import brain_ai as ai
from brain_core import (
    is_instagram_url, handle_reel, handle_pdf, handle_image,
    handle_focus_command, check_and_warn_drift, handle_quick_note, ingest_drop
)
from mac_integration import create_reminder, create_calendar_event, delete_all_created_reminders

# ─── DARK MONOCHROME PALETTE ─────────────────────────────────────────────────
W  = "\033[97m"   # bright white — primary text
G  = "\033[37m"   # light grey   — secondary
D  = "\033[90m"   # dark grey    — dim/muted
B  = "\033[1m"    # bold
R  = "\033[0m"    # reset

LOGO = r"""
  ██████╗ ██████╗  █████╗ ██╗███╗   ██╗
  ██╔══██╗██╔══██╗██╔══██╗██║████╗  ██║
  ██████╔╝██████╔╝███████║██║██╔██╗ ██║
  ██╔══██╗██╔══██╗██╔══██║██║██║╚██╗██║
  ██████╔╝██║  ██║██║  ██║██║██║ ╚████║
  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝
"""

BANNER = (
    f"{W}{B}{LOGO}{R}\n"
    f"{D}  --------------------------------------------------------{R}\n"
    f"  {W}[NVIDIA ENGINE]{R}   {G}[OBSIDIAN SYNC]{R}   {G}[FOCUS MODE]{R}\n"
    f"  {D}Model: {NVIDIA_MODEL} | Cloud-powered | Vault: ./vault{R}\n"
    f"{D}  --------------------------------------------------------{R}\n"
    f"  {D}Commands: /help  /focus  /remind  /calendar  /note  exit{R}\n"
)

history = []


def _save(role: str, content: str):
    with get_db() as conn:
        conn.execute("INSERT INTO conversations (role, content) VALUES (?, ?)", (role, content))


def _load_history(limit: int = 10):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM conversations ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def print_help():
    print(f"""
{B}  COMMANDS{R}
{D}  ──────────────────────────────────────────────────────{R}
  {W}/focus [topic]{R}      {D}Set focus topic (e.g. /focus Build gym app){R}
  {W}/focus off{R}          {D}Disable focus mode{R}
  {W}/drop [text/URL/file]{R}{D}Single-pass cloud AI triage → tasks & vault{R}
  {W}/tasks{R}              {D}List pending action items{R}
  {W}/remind [text]{R}      {D}Add Apple Reminder (e.g. /remind Call doctor 2026-10-01){R}
  {W}/calendar [text]{R}    {D}Add Calendar event (e.g. /calendar Team sync 2026-10-01 14:00){R}
  {W}/note [text]{R}        {D}Quick note → Obsidian{R}
  {W}/clear reminders{R}    {D}Delete all reminders created by Brain{R}
  {W}Drag & drop image{R}   {D}Analyse image with Gemini vision{R}
  {W}Drag & drop PDF{R}     {D}Parse and summarise PDF → Obsidian{R}
  {W}Instagram URL{R}       {D}Transcribe reel → summarise → Obsidian note{R}
  {W}exit / quit{R}         {D}Exit{R}
{D}  ──────────────────────────────────────────────────────{R}
""")


def run():
    global history
    print(BANNER)

    recent = _load_history()
    if recent:
        history = recent
        print(f"  {D}Resumed {len(recent)} messages from last session.{R}\n")

    while True:
        focus = get_focus()
        focus_tag = f" [focus: {focus[:20]}]" if focus else ""

        try:
            user_input = input(f"{G}You{focus_tag}>{R} ").strip()
        except KeyboardInterrupt:
            print(f"\n\n{D}Goodbye. Context preserved.{R}\n")
            break
        except EOFError:
            break

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit", "bye"]:
            print(f"\n{D}Later. All context saved.{R}\n")
            break

        # -- HELP --
        if user_input.lower() in ["/help", "help"]:
            print_help()
            continue

        # -- FOCUS MODE --
        if user_input.lower().startswith("/focus"):
            args = user_input[6:].strip()
            print(f"\n  {W}{handle_focus_command(args)}{R}\n")
            continue

        # -- DROP / TRIAGE --
        if user_input.lower().startswith("/drop "):
            drop_text = user_input[6:].strip()
            print(f"\n  {D}Ingesting drop via cloud AI...{R}")
            res = ingest_drop(drop_text, source_hint="CLI /drop")
            print(f"\n  {W}Drop Ingested:{R} {res.get('title')}")
            print(f"  {D}Summary:{R} {res.get('summary')}")
            if res.get("tasks"):
                print(f"  {G}Action Items:{R}")
                for t in res["tasks"]:
                    print(f"    - {t['title']}")
            print(f"  {D}Vault note: {os.path.basename(res.get('note_path', ''))}{R}\n")
            continue

        # -- TASKS --
        if user_input.lower() in ["/tasks", "tasks"]:
            pending = get_pending_tasks(limit=10)
            if not pending:
                print(f"\n  {W}No pending tasks! All caught up.{R}\n")
            else:
                print(f"\n{B}  PENDING ACTION ITEMS ({len(pending)}){R}")
                print(f"{D}  ------------------------------------------------------{R}")
                for t in pending:
                    due = f" {D}[Due: {t['due_date']}]{R}" if t.get("due_date") else ""
                    print(f"  {W}[ ] #{t['id']}{R} {t['title']}{due}")
                print(f"{D}  ──────────────────────────────────────────────────────{R}\n")
            continue

        # ── QUICK NOTE ──
        if user_input.lower().startswith("/note "):
            text = user_input[6:].strip()
            print(f"\n  {W}{handle_quick_note(text)}{R}\n")
            continue

        # ── REMINDERS ──
        if user_input.lower().startswith("/remind "):
            args = user_input[8:].strip()
            # Try to parse optional date at end (YYYY-MM-DD)
            parts = args.split()
            date = None
            if parts and re.match(r'\d{4}-\d{2}-\d{2}', parts[-1]):
                date = parts[-1]
                title = " ".join(parts[:-1])
            else:
                title = args
            import re as _re
            ok = create_reminder(title, due_date=date)
            status = "Reminder added to Apple Reminders" if ok else "Failed to add reminder"
            print(f"\n  {W}{status}{R}\n")
            continue

        # -- CALENDAR --
        if user_input.lower().startswith("/calendar "):
            import re as _re
            args = user_input[10:].strip()
            parts = args.split()
            date_match = None
            time_match = None
            for i, p in enumerate(parts):
                if _re.match(r'\d{4}-\d{2}-\d{2}', p):
                    date_match = (i, p)
                elif _re.match(r'\d{1,2}:\d{2}', p) and date_match:
                    time_match = (i, p)
            if date_match:
                idx = date_match[0]
                title = " ".join(parts[:idx])
                date = date_match[1]
                time = time_match[1] if time_match else "09:00"
            else:
                title = args
                date = None
                time = "09:00"
            if date:
                ok = create_calendar_event(title, date, time)
                status = f"Event '{title}' added to Calendar on {date} at {time}" if ok else "Failed to add event"
            else:
                status = "Please include a date: /calendar [title] [YYYY-MM-DD] [HH:MM]"
            print(f"\n  {W}{status}{R}\n")
            continue

        # -- CLEAR REMINDERS --
        if user_input.lower() == "/clear reminders":
            count = delete_all_created_reminders()
            print(f"\n  {W}Deleted {count} reminder(s).{R}\n")
            continue

        # -- FILE / IMAGE / PDF --
        cleaned = user_input.strip("'\" ")
        if os.path.isfile(cleaned):
            ext = os.path.splitext(cleaned)[1].lower()
            if ext == ".pdf":
                print()
                result = handle_pdf(cleaned, ai)
                print(f"\n{G}[Brain]{R}\n{result}\n")
            elif ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                print()
                result = handle_image(cleaned, ai)
                print(f"\n{G}[Brain vision]{R}\n{result}\n")
            else:
                print(f"\n  {D}Unsupported file type: {ext}{R}\n")
            continue

        # -- INSTAGRAM REEL --
        if is_instagram_url(user_input):
            print()
            result = handle_reel(user_input, ai, use_audio=True)
            print(f"\n{G}[Brain reel]{R}\n{result}\n")
            continue

        # -- FOCUS DRIFT CHECK --
        drift_warning = check_and_warn_drift(user_input, ai)
        if drift_warning:
            print(f"  {D}{drift_warning}{R}")

        # -- NORMAL CHAT --
        _save("user", user_input)
        history.append({"role": "user", "content": user_input})
        trimmed = history[-12:]

        print(f"\n{G}[Brain {NVIDIA_MODEL}]{R}")
        sys.stdout.write("  ")
        sys.stdout.flush()

        chunks = []
        try:
            for chunk in stream_chat(trimmed):
                sys.stdout.write(chunk)
                sys.stdout.flush()
                chunks.append(chunk)
        except Exception as e:
            print(f"\n  {D}Error: {e}{R}")
            print(f"  {D}Check your NVIDIA_API_KEY and internet connection.{R}")
            continue

        reply = "".join(chunks)
        print("\n")
        _save("assistant", reply)
        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    import re
    run()
