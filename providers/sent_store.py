import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


class SentStore:
    """
    Lightweight persistence for emails sent via the Compose flow.
    Only stores metadata for display in the UI; it does not affect delivery.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = path or Path("Summaries") / "sent_emails.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict:
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data.setdefault("sent", [])
                        return data
            except Exception:
                pass
        return {"sent": []}

    def _save(self, data: Dict):
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def record(self, to_email: str, subject: str, body: str, source: str = "gmail"):
        """Persist a sent email originating from the Compose feature."""
        payload = {
            "to": to_email,
            "subject": subject or "(No subject)",
            "body": body or "",
            "source": source or "gmail",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        data = self._load()
        sent_list = data.setdefault("sent", [])
        sent_list.insert(0, payload)  # newest first
        # Keep storage bounded to avoid unbounded growth
        if len(sent_list) > 200:
            sent_list = sent_list[:200]
            data["sent"] = sent_list
        self._save(data)
        return payload

    def list_sent(self, limit: int = 200) -> List[Dict]:
        data = self._load()
        sent_list = data.get("sent", [])
        return sent_list[:limit]

