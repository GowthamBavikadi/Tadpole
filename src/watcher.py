# watcher.py — Optional background inbox folder watcher
# Automatically ingests any file dropped into ~/Desktop/Brain_Drop and archives it.

import os
import sys
import time
import shutil
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

from brain_core import ingest_drop

DROP_DIR = os.path.expanduser("~/Desktop/Brain_Drop")
ARCHIVE_DIR = os.path.join(DROP_DIR, "Processed")


def ensure_dirs():
    os.makedirs(DROP_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)


def watch_inbox(poll_interval: float = 2.0):
    ensure_dirs()
    print(f"[Watcher] Monitoring inbox folder: {DROP_DIR}")
    print(f"[Watcher] Processed files will be moved to: {ARCHIVE_DIR}")

    seen = set()

    while True:
        try:
            for item in os.listdir(DROP_DIR):
                if item == "Processed" or item.startswith("."):
                    continue

                item_path = os.path.join(DROP_DIR, item)
                if not os.path.isfile(item_path):
                    continue

                # Wait 1s to ensure file write is finished (e.g. large PDF/video)
                time.sleep(1.0)

                print(f"[Watcher] Detected drop: {item}")
                try:
                    res = ingest_drop(item_path, source_hint=f"Folder Drop: {item}")
                    print(f"[Watcher] Successfully ingested: {res.get('title')}")

                    # Archive file
                    timestamp = time.strftime("%Y%m%d_%H%M%S_")
                    dest_path = os.path.join(ARCHIVE_DIR, timestamp + item)
                    shutil.move(item_path, dest_path)
                    print(f"[Watcher] Archived to: {dest_path}")
                except Exception as e:
                    print(f"[Watcher] Ingestion error on {item}: {e}")

            time.sleep(poll_interval)
        except KeyboardInterrupt:
            print("\n[Watcher] Stopped monitoring.")
            break
        except Exception as e:
            print(f"[Watcher] Error: {e}")
            time.sleep(poll_interval)


if __name__ == "__main__":
    watch_inbox()
