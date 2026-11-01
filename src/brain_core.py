# brain_core.py — Shared Second-Brain Engine for Tasks, Idea Boxes & Direct Q&A
import os
import re
import json
import subprocess
import tempfile
from datetime import datetime
from database import (
    get_db, get_focus, set_focus, add_drop, add_link_to_drop,
    remove_link_from_drop, delete_drop, add_task,
    get_pending_tasks, get_recent_drops, update_task, search_knowledge_chunks
)
import brain_ai as ai
import mac_integration as mac

VAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "vault")


def save_to_obsidian(title: str, content: str, source: str = "",
                     tags: list[str] = None, folder: str = "Ideas") -> str:
    """Write a structured .md note to the Obsidian vault. Returns the file path."""
    folder_path = os.path.join(VAULT_PATH, folder)
    os.makedirs(folder_path, exist_ok=True)

    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:60].strip() or "Note"
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_str} {safe_title}.md"
    filepath = os.path.join(folder_path, filename)

    tags_str = ", ".join(tags) if tags else ""
    frontmatter = f"""---
title: "{safe_title}"
source: "{source}"
created: {date_str}
tags: [{tags_str}]
---

"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter + content)

    with get_db() as conn:
        conn.execute(
            "INSERT INTO notes (title, filename, source) VALUES (?, ?, ?)",
            (safe_title, filename, source)
        )

    return filepath


def append_link_to_obsidian_note(filepath: str, url: str):
    if not filepath or not os.path.exists(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            txt = f.read()
        if url in txt:
            return
        if "## Associated Links" in txt:
            txt = txt.rstrip() + f"\n- {url}\n"
        else:
            txt = txt.rstrip() + f"\n\n## Associated Links\n\n- {url}\n"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(txt)
    except Exception:
        pass


def parse_pdf(path: str) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(pages).strip()
        return text if text else "[No extractable text found in this PDF]"
    except Exception as e:
        return f"[PDF parse error: {e}]"


def handle_pdf(path: str, ai_mod) -> str:
    text = parse_pdf(path)
    if text.startswith("["):
        return text
    summary = ai_mod.summarise(
        text,
        context="Summarise this document. Extract key points and important dates/numbers."
    )
    basename = os.path.basename(path)
    note_content = f"## Summary\n\n{summary}\n\n## Full Text\n\n```\n{text[:10000]}\n```\n"
    filepath = save_to_obsidian(
        title=f"PDF — {os.path.splitext(basename)[0]}",
        content=note_content,
        source=path,
        tags=["pdf", "document"],
        folder="Documents"
    )
    return f"PDF parsed and saved to Obsidian\n\n{summary}\n\nNote: {os.path.basename(filepath)}"


def handle_image(path: str, ai_mod, user_prompt: str = "") -> str:
    prompt = user_prompt if user_prompt else "Describe this image in detail. Extract any visible text, data, or key information."
    return ai_mod.describe_image(path, prompt)


def is_instagram_url(text: str) -> bool:
    return bool(re.search(r'instagram\.com/(reel|p|tv)/', text))


def handle_reel(url: str, ai_mod, use_audio: bool = True) -> str:
    url = url.strip()
    with tempfile.TemporaryDirectory() as tmpdir:
        transcript = ""
        if use_audio:
            audio_path = os.path.join(tmpdir, "reel.mp4")
            try:
                subprocess.run(
                    ["yt-dlp", "-x", "--audio-format", "mp4", "--no-playlist", "-o", audio_path, url],
                    check=True, capture_output=True, timeout=60
                )
                if os.path.exists(audio_path):
                    transcript = ai_mod.transcribe_audio(audio_path)
            except Exception:
                use_audio = False

        if not use_audio or not transcript:
            sub_path = os.path.join(tmpdir, "subs")
            try:
                subprocess.run(
                    ["yt-dlp", "--write-auto-sub", "--sub-format", "vtt", "--skip-download", "--no-playlist", "-o", sub_path, url],
                    check=True, capture_output=True, text=True, timeout=60
                )
                vtt_files = [f for f in os.listdir(tmpdir) if f.endswith(".vtt")]
                if vtt_files:
                    with open(os.path.join(tmpdir, vtt_files[0]), encoding="utf-8") as f:
                        raw = f.read()
                    lines = []
                    for line in raw.splitlines():
                        line = line.strip()
                        if line and not line.startswith("WEBVTT") and "-->" not in line and not re.match(r'^\d+$', line):
                            clean = re.sub(r'<[^>]+>', '', line)
                            if clean and clean not in lines[-1:]:
                                lines.append(clean)
                    transcript = " ".join(lines)
                else:
                    transcript = "[No subtitles found for this reel]"
            except Exception as e:
                transcript = f"[Could not extract subtitles: {e}]"

    summary = ai_mod.summarise(
        transcript,
        context="This is a transcript from an Instagram reel. Write a concise summary and key takeaways."
    )
    title_line = summary.split("\n")[0].strip().lstrip("#").strip()
    note_title = title_line if len(title_line) < 80 else "Instagram Reel Idea"
    note_content = f"## Summary\n\n{summary}\n\n## Full Transcript\n\n{transcript[:5000]}\n\n## Source\n\n{url}\n"
    filepath = save_to_obsidian(
        title=note_title,
        content=note_content,
        source=url,
        tags=["reel", "instagram"],
        folder="Clippings"
    )
    return f"Reel processed and saved to Obsidian\n\n{summary}\n\nNote: {os.path.basename(filepath)}"


def handle_focus_command(args: str) -> str:
    args = args.strip()
    if not args or args.lower() == "off":
        set_focus(None)
        return "Focus mode disabled."
    set_focus(args)
    return f"Focus set: {args}"


def check_and_warn_drift(user_message: str, ai_mod) -> str | None:
    topic = get_focus()
    if not topic:
        return None
    if any(word.lower() in user_message.lower() for word in topic.split()[:3]):
        return None
    try:
        if ai_mod.check_focus_drift(user_message, topic):
            return f"[Focus drift warning] Focus: {topic}"
    except Exception:
        pass
    return None


def handle_quick_note(text: str) -> str:
    res = ingest_drop(text, source_hint="Quick Note")
    return f"Saved: {res.get('title', 'Note')}"


def ingest_drop(raw_input: str, source_hint: str = "", force_type: str | None = None) -> dict:
    """
    Unified ingestion pipeline for both Tasks and Idea Boxes:
      1. Rewrites raw conversational input into a polished Title and polished Description/Summary.
      2. Preserves the verbatim `raw_input` for the bottom of the Detail Page.
      3. Routes Tasks to `tasks` (with due_date, links, description, raw_text) regardless of active tab,
         and routes Ideas to `drops` (with summary, links, due_date, raw_content).
    """
    raw_input = raw_input.strip()
    source = source_hint or "Input"
    raw_content = ""
    file_path = None
    initial_links = []

    if raw_input.startswith("file://"):
        import urllib.parse
        cleaned = urllib.parse.unquote(raw_input[7:])
        if os.path.exists(cleaned):
            file_path = cleaned
    elif os.path.exists(raw_input.strip("'\"")):
        file_path = raw_input.strip("'\"")

    if file_path:
        source = file_path
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            raw_content = parse_pdf(file_path)
            source_hint = "PDF Document"
        elif ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
            raw_content = ai.describe_image(file_path)
            source_hint = "Visual Image / Screenshot"
        elif ext in [".txt", ".md", ".json", ".csv", ".py", ".sh"]:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    raw_content = f.read()
                source_hint = f"Text File ({ext})"
            except Exception as e:
                raw_content = f"[Could not read file: {e}]"
        else:
            raw_content = f"Dropped file: {os.path.basename(file_path)}"
    elif is_instagram_url(raw_input):
        source = raw_input
        initial_links.append(raw_input)
        source_hint = "Instagram Reel"
        raw_content = handle_reel(raw_input, ai, use_audio=True)
    elif re.match(r"^https?://\S+$", raw_input):
        source = raw_input
        initial_links.append(raw_input)
        source_hint = "Web Link"
        try:
            import requests
            from urllib.parse import urlparse
            res = requests.get(raw_input, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
            title_match = re.search(r"<title>(.*?)</title>", res.text, re.IGNORECASE)
            page_title = title_match.group(1).strip() if title_match else urlparse(raw_input).netloc
            clean_text = re.sub(r"<[^>]+>", " ", res.text[:25000])
            clean_text = " ".join(clean_text.split())[:6000]
            raw_content = f"Title: {page_title}\nURL: {raw_input}\n\nContent:\n{clean_text}"
        except Exception:
            raw_content = f"Link: {raw_input}"
    else:
        raw_content = raw_input

    data = ai.triage_drop(raw_content, source=source, drop_hint=source_hint)

    item_type = (force_type or data.get("type", "idea")).lower()
    polished_title = data.get("title", "Untitled")
    polished_summary = data.get("summary", "")
    due_date = data.get("due_date")
    all_links = list(dict.fromkeys(initial_links + (data.get("links") or [])))

    tags_list = data.get("tags", ["#task"] if item_type == "task" else ["#idea"])
    if isinstance(tags_list, str):
        tags_list = [tags_list]

    folder_map = {
        "task": "Tasks",
        "idea": "Ideas",
        "project": "Projects",
        "document": "Documents",
        "link": "Clippings",
    }
    folder = folder_map.get(item_type, "Ideas")

    note_lines = [f"## Overview\n\n{polished_summary}\n"]
    if due_date:
        note_lines.append(f"\n- **To Be Completed By**: {due_date}\n")
    if all_links:
        note_lines.append("\n## Associated Links\n\n")
        for u in all_links:
            note_lines.append(f"- {u}\n")
    note_lines.append(f"\n## Original Raw Text\n\n{raw_content[:8000]}\n")

    note_path = save_to_obsidian(
        title=polished_title,
        content="".join(note_lines),
        source=source,
        tags=tags_list,
        folder=folder,
    )

    if item_type == "task":
        # Store in tasks table with full detail fields (polished title, polished description, links, due_date, raw_text)
        task_id = add_task(
            title=polished_title,
            description=polished_summary,
            raw_text=raw_input,
            links=all_links,
            due_date=due_date,
            tags=", ".join(tags_list),
            drop_id=None,
        )
        if due_date:
            try:
                mac.create_reminder(title=polished_title, due_date=due_date)
            except Exception:
                pass
        return {
            "item_kind": "task",
            "item_id": task_id,
            "title": polished_title,
            "summary": polished_summary,
            "type": "task",
            "due_date": due_date,
            "links": all_links,
            "raw_text": raw_input,
            "note_path": note_path,
            "status": "success",
        }
    else:
        drop_id = add_drop(
            title=polished_title,
            summary=polished_summary,
            drop_type="idea",
            tags=", ".join(tags_list),
            source=note_path if not file_path else file_path,
            raw_content=raw_input if not file_path else raw_content[:12000],
            links=all_links,
            due_date=due_date,
        )
        return {
            "item_kind": "idea",
            "item_id": drop_id,
            "drop_id": drop_id,
            "title": polished_title,
            "summary": polished_summary,
            "type": "idea",
            "due_date": due_date,
            "links": all_links,
            "raw_text": raw_input,
            "note_path": note_path,
            "status": "success",
        }


def ask_brain_agent(user_query: str) -> dict:
    focus = get_focus() or "None"
    tasks = get_pending_tasks(limit=12)
    chunks = search_knowledge_chunks(user_query, limit=6)

    res = ai.query_notebook_brain(user_query, chunks, tasks, focus)
    return {
        "status": res.get("status", "success"),
        "reply": res.get("reply", ""),
        "citations": res.get("citations", []),
        "added_tasks": 0,
        "provider": ai.get_active_provider_label(),
    }
