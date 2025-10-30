from typing import List, Dict, Protocol


class SummariesProvider(Protocol):
    def get_summaries(self, limit: int = 20) -> List[Dict]:
        """
        Return a list of summary dicts with the shape:
        {
          "email": str,
          "role": str,            # e.g., "Student", "Faculty", "Vendor"
          "summary": str,
          "date": str             # ISO-8601 or human-readable date
        }
        """
        ...


