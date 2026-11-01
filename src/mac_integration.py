from datetime import datetime, timedelta
import subprocess
from database import get_db


def _parse_date(date_str: str) -> tuple[int, int, int] | None:
    """Parse dates like YYYY-MM-DD, 'tomorrow', 'today', etc."""
    if not date_str:
        return None
    cleaned = str(date_str).strip().lower()
    now = datetime.now()
    if cleaned == "today":
        return now.year, now.month, now.day
    if cleaned == "tomorrow":
        tmr = now + timedelta(days=1)
        return tmr.year, tmr.month, tmr.day
    try:
        parts = cleaned.split("-")
        if len(parts) == 3:
            return int(parts[0]), int(parts[1]), int(parts[2])
    except Exception:
        pass
    return None


def create_reminder(title: str, notes: str = "", due_date: str = None,
                    due_time: str = None, list_name: str = "Reminders") -> bool:
    safe_title = title.replace('"', '\\"')
    safe_notes = notes.replace('"', '\\"')
    script = f'''
    tell application "Reminders"
        tell list "{list_name}"
            set r to make new reminder with properties {{name:"{safe_title}", body:"{safe_notes}"}}
    '''
    parsed_date = _parse_date(due_date) if due_date else None
    if parsed_date:
        year, month, day = parsed_date
        hour, minute = (9, 0)
        if due_time and ":" in due_time:
            try:
                hour, minute = [int(x) for x in due_time.split(":")]
            except Exception:
                pass
        script += f'''
            set d to current date
            set year of d to {year}
            set month of d to {int(month)}
            set day of d to {int(day)}
            set hours of d to {hour}
            set minutes of d to {minute}
            set seconds of d to 0
            set due date of r to d
        '''
    script += '\n        end tell\n    end tell'
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
        with get_db() as conn:
            conn.execute("INSERT INTO created_reminders (title) VALUES (?)", (title,))
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [reminder error: {e.stderr.strip()}]")
        return False


def create_calendar_event(title: str, date_str: str, time_str: str = "09:00",
                          notes: str = "", calendar_name: str = "Calendar") -> bool:
    safe_title = title.replace('"', '\\"')
    safe_notes = notes.replace('"', '\\"')
    parsed_date = _parse_date(date_str)
    if not parsed_date:
        return False
    year, month, day = parsed_date
    hour, minute = (9, 0)
    if time_str and ":" in time_str:
        try:
            hour, minute = [int(x) for x in time_str.split(":")]
        except Exception:
            pass
    script = f'''
    tell application "Calendar"
        tell calendar "{calendar_name}"
            set startDate to (current date)
            set year of startDate to {year}
            set month of startDate to {int(month)}
            set day of startDate to {int(day)}
            set hours of startDate to {hour}
            set minutes of startDate to {minute}
            set endDate to startDate + (1 * hours)
            make new event with properties {{summary:"{safe_title}", start date:startDate, end date:endDate, description:"{safe_notes}"}}
        end tell
    end tell
    '''
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [calendar error: {e.stderr.strip()}]")
        return False


def delete_all_created_reminders() -> int:
    with get_db() as conn:
        rows = conn.execute("SELECT title FROM created_reminders").fetchall()
        titles = [r["title"] for r in rows]
    count = 0
    for title in titles:
        safe = title.replace('"', '\\"')
        script = f'''
        tell application "Reminders"
            tell list "Reminders"
                delete (every reminder whose name is "{safe}")
            end tell
        end tell
        '''
        try:
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
            count += 1
        except Exception:
            pass
    with get_db() as conn:
        conn.execute("DELETE FROM created_reminders")
    return count
