import time
import uuid
from pathlib import Path
from datetime import datetime, timezone

import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


DATA_DIR = Path(__file__).parent / "data"

ADK_EVENTARC_URL = (
    "http://127.0.0.1:8000/apps/my_agent/trigger/eventarc"
)

COOLDOWN_SECONDS = 10


class FinancialDataHandler(FileSystemEventHandler):

    def __init__(self):
        super().__init__()
        self.last_trigger_time = 0

    def on_modified(self, event):
        if event.is_directory:
            return

        changed_file = Path(event.src_path)

        if changed_file.parent != DATA_DIR:
            return

        if changed_file.name not in {
            "transactions.json",
            "emails.json",
        }:
            return

        now = time.monotonic()

        # Ignore repeated filesystem events for the same
        # financial data change.
        if now - self.last_trigger_time < COOLDOWN_SECONDS:
            print(
                f"↪ Ignoring duplicate filesystem event: "
                f"{changed_file.name}"
            )
            return

        self.last_trigger_time = now

        print(f"\n⚡ Financial data changed: {changed_file.name}")
        print("→ Waking Safe Signal...")

        payload = {
            "data": {
                "event": "financial_data_changed",
                "file": changed_file.name,
                "path": str(changed_file),
            },
            "source": "agent-sentinel--local",
            "type": "financial.data.changed",
            "id": str(uuid.uuid4()),
            "time": datetime.now(timezone.utc).isoformat(),
            "specversion": "1.0",
        }

        try:
            response = requests.post(
                ADK_EVENTARC_URL,
                json=payload,
                timeout=120,
            )

            response.raise_for_status()

            print("✓ Agent processed event")

        except requests.RequestException as e:
            print(f"✗ Failed to trigger Safe Signal: {e}")


def main():
    observer = Observer()

    handler = FinancialDataHandler()

    observer.schedule(
        handler,
        str(DATA_DIR),
        recursive=False,
    )

    observer.start()

    print("🟢 Safe Signal event listener started")
    print(f"👀 Watching: {DATA_DIR}")
    print("Waiting for financial data changes...")

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Stopping event listener...")
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()