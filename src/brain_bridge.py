#!/usr/bin/env python3
# brain_bridge.py — Fast JSON CLI Bridge between the Native macOS SwiftUI Liquid Glass App and Python Backend
import os
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))

import database
import brain_ai as ai
from brain_core import (
    handle_focus_command, ingest_drop, ask_brain_agent, VAULT_PATH
)
import mac_integration as mac


def get_full_state() -> dict:
    return {
        "focus": database.get_focus() or "",
        "tasks": database.get_pending_tasks(limit=25),
        "ideas": database.get_recent_drops(limit=25),
        "vault_path": os.path.abspath(VAULT_PATH),
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "Missing command"}))
        return

    cmd = sys.argv[1]
    try:
        if cmd == "state":
            print(json.dumps({"status": "success", "state": get_full_state()}))

        elif cmd == "submit":
            text = sys.argv[2].strip() if len(sys.argv) > 2 else ""
            if not text:
                print(json.dumps({"status": "error", "message": "Empty input"}))
                return

            if text.lower().startswith("/focus"):
                args = text[6:].strip()
                msg = handle_focus_command(args)
                print(json.dumps({
                    "status": "success",
                    "mode": "command",
                    "status_text": msg,
                    "state": get_full_state()
                }))
                return

            if text.lower().startswith("/remind "):
                args = text[8:].strip()
                ok = mac.create_reminder(args)
                print(json.dumps({
                    "status": "success",
                    "mode": "command",
                    "status_text": "Reminder created" if ok else "Reminder failed",
                    "state": get_full_state()
                }))
                return

            if ai.is_question_text(text):
                res = ask_brain_agent(text.lstrip("?").strip())
                print(json.dumps({
                    "status": "success",
                    "mode": "question",
                    "reply": res.get("reply", ""),
                    "citations": res.get("citations", []),
                    "status_text": "Answered",
                    "state": get_full_state()
                }))
            else:
                res = ingest_drop(text, source_hint="HUD Input")
                kind = res.get("item_kind", "idea")
                title = res.get("title", "Saved")
                print(json.dumps({
                    "status": "success",
                    "mode": kind,
                    "title": title,
                    "item_id": res.get("item_id"),
                    "status_text": f"{'Task added' if kind == 'task' else 'Idea saved'}: {title[:28]}",
                    "state": get_full_state()
                }))

        elif cmd == "toggle_task":
            task_id = int(sys.argv[2])
            new_st = database.toggle_task_status(task_id)
            print(json.dumps({
                "status": "success",
                "new_status": new_st,
                "task_detail": database.get_task_by_id(task_id),
                "state": get_full_state()
            }))

        elif cmd == "delete_task":
            task_id = int(sys.argv[2])
            database.delete_task(task_id)
            print(json.dumps({"status": "success", "state": get_full_state()}))

        elif cmd == "delete_idea":
            drop_id = int(sys.argv[2])
            database.delete_drop(drop_id)
            print(json.dumps({"status": "success", "state": get_full_state()}))

        elif cmd == "clear_done":
            database.clear_completed_tasks()
            print(json.dumps({"status": "success", "state": get_full_state()}))

        elif cmd == "clear_focus":
            database.set_focus(None)
            print(json.dumps({"status": "success", "state": get_full_state()}))

        elif cmd == "add_link":
            kind = sys.argv[2]
            item_id = int(sys.argv[3])
            url = sys.argv[4]
            if kind == "task":
                links = database.add_link_to_task(item_id, url)
                detail = database.get_task_by_id(item_id)
            else:
                links = database.add_link_to_drop(item_id, url)
                detail = database.get_drop_by_id(item_id)
            print(json.dumps({
                "status": "success",
                "links": links,
                "detail": detail,
                "state": get_full_state()
            }))

        elif cmd == "remove_link":
            kind = sys.argv[2]
            item_id = int(sys.argv[3])
            url = sys.argv[4]
            if kind == "task":
                links = database.remove_link_from_task(item_id, url)
                detail = database.get_task_by_id(item_id)
            else:
                links = database.remove_link_from_drop(item_id, url)
                detail = database.get_drop_by_id(item_id)
            print(json.dumps({
                "status": "success",
                "links": links,
                "detail": detail,
                "state": get_full_state()
            }))

        elif cmd == "set_due":
            kind = sys.argv[2]
            item_id = int(sys.argv[3])
            due = sys.argv[4].strip() or None
            if kind == "task":
                database.update_task_due_date(item_id, due)
                detail = database.get_task_by_id(item_id)
            else:
                database.update_drop_due_date(item_id, due)
                detail = database.get_drop_by_id(item_id)
            print(json.dumps({
                "status": "success",
                "detail": detail,
                "state": get_full_state()
            }))

        elif cmd == "detail":
            kind = sys.argv[2]
            item_id = int(sys.argv[3])
            detail = database.get_task_by_id(item_id) if kind == "task" else database.get_drop_by_id(item_id)
            print(json.dumps({"status": "success", "detail": detail}))

        else:
            print(json.dumps({"status": "error", "message": f"Unknown command: {cmd}"}))

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))


if __name__ == "__main__":
    main()
