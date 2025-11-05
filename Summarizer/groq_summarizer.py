import os
from pathlib import Path
import json
from dotenv import load_dotenv
import sys
import io
import time  # for TTL handling
from datetime import datetime, timezone
# Conditional imports for supported providers
try:
    from groq import Groq
except ImportError:
    Groq = None

import requests  # for Ollama



load_dotenv()
if not sys.stdout.encoding or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="ignore")



class GroqSummarizer:
    def __init__(self, cache_path=None, ttl_hours=24):
        """
        Universal Summarizer supporting Groq, OpenAI, or Ollama.
        Set PROVIDER in .env: groq / openai / ollama
        """
        BASE_DIR = Path(__file__).resolve().parent.parent
        cache_path = cache_path or os.path.join(BASE_DIR, "Summaries", "summaries_cache.json")
        self.provider = os.getenv("PROVIDER", "groq").lower().strip()
        self.cache_path = cache_path
        self.ttl_seconds = ttl_hours * 3600  # Convert hours to seconds

        # ✅ Load cache safely and ensure it's a dict
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                if not isinstance(self.cache, dict):
                    print("[WARN] summaries_cache.json was not a dict, resetting...")
                    self.cache = {}
            except Exception as e:
                print("[WARN] Failed to load cache:", e)
                self.cache = {}
        else:
            self.cache = {}

        # ✅ Clean up expired cache entries
        self._cleanup_expired_cache()

        # ---- Initialize provider client ----
        if self.provider == "groq":
            if not Groq:
                raise ImportError("groq package not installed. Run: pip install groq")
            self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

        else:
            raise ValueError(f"Unsupported PROVIDER: {self.provider}")

        print(f"[INFO] Summarizer initialized with provider='{self.provider}' and model='{self.model}'")


    # --------------------
    # Cache helpers with TTL
    # --------------------
    def _load_cache(self):
        try:
            if os.path.exists(self.cache_path):
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[WARN] Cache load failed: {e}. Resetting.")
            return {}
        return {}


    def _save_cache(self):
        with open(self.cache_path, "w", encoding="utf-8", errors="ignore") as f:
            json.dump(self.cache, f, indent=2, ensure_ascii=False)

    def _cleanup_expired_cache(self):
        """Remove entries that exceeded TTL."""
        now = time.time()
        keys_to_delete = [
            k for k, v in self.cache.items()
            if "timestamp" in v and now - v["timestamp"] > self.ttl_seconds
        ]
        for k in keys_to_delete:
            self.cache.pop(k, None)
        if keys_to_delete:
            self._save_cache()

    # --------------------
    # Per-contact cache management
    # --------------------
    def _get_cache_key(self, source, contact_email, thread_id):
        return f"{source}:{contact_email}:{thread_id}"

    def _get_from_cache(self, source, contact_email, thread_id):
        key = self._get_cache_key(source, contact_email, thread_id)
        entry = self.cache.get(key)
        if not entry:
            return None
        if time.time() - entry.get("timestamp", 0) > self.ttl_seconds:
            self.cache.pop(key, None)
            self._save_cache()
            return None
        return entry.get("summary")

    def _set_cache(self, source, contact_email, thread_id, summary):
        key = self._get_cache_key(source, contact_email, thread_id)
        self.cache[key] = {
            "summary": summary,
            "timestamp": time.time()
        }
        self._save_cache()

    def _clear_contact_cache(self, source, contact_email):
        """
        Clear all cached summaries related to a contact (thread-level and contact-wide).
        """
        prefix = f"{source}:{contact_email}"
        keys_to_remove = [k for k in self.cache if k == prefix or k.startswith(prefix + ":")]
        for k in keys_to_remove:
            self.cache.pop(k, None)
        if keys_to_remove:
            self._save_cache()


    # --------------------------------------------------------------------
    # 🧩 Universal Model Runner
    # --------------------------------------------------------------------
    def _run_groq_model(self, prompt):
        """
        Unified model handler — works with Groq, OpenAI.
        """
        try:
            if self.provider == "groq":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"❌ Summarization failed ({self.provider}): {e}")
            return "Summary unavailable due to model error."


    # ------------------------------------------------------
    # CORE: Universal summarizer
    # ------------------------------------------------------
    def summarize_text(self, text, purpose="general summary"):
        """
        Generate a concise, human-like summary for busy users.
        Keeps essential context but avoids unnecessary length.
        """

        prompt = f"""
        You are an AI assistant summarizing emails for a busy professional.

        Summarize the following text into 3–5 lines maximum.
        Focus on:
        - The main purpose or topic
        - Key people, organizations, or events
        - Any next steps, meeting times, or deadlines
        - Keep it natural, human, and easy to read
        - Avoid repetitive or robotic phrasing

        Text:
        {text}

        Write the summary directly. No greetings, headings, or bullet points.
        """

        # Run through Groq model
        return self._run_groq_model(prompt)


    # ------------------------------------------------------
    # PER THREAD SUMMARY (with caching)
    # ------------------------------------------------------
    def summarize_thread(self, thread_emails, source=None, contact_email=None, thread_id=None, force=False):
        """
        Summarize a single email thread into a concise, natural, and context-rich paragraph.

        Args:
            thread_emails (list[dict]): Each email should include 'sender', 'subject', and 'body'.
            thread_id (str, optional): Used for caching thread summaries.

        Returns:
            str: Human-friendly summary for the thread.
        """
        # Force clear
        if force and source and contact_email:
            self._clear_contact_cache(source, contact_email)


        # ✅ 1. Check cache first
        if thread_id and source and contact_email and (cached := self._get_from_cache(source, contact_email, thread_id)):
            print(f"⚡ Using cached summary for thread {thread_id}")
            return cached

        # ✅ 2. Combine thread messages cleanly
        combined = "\n\n---\n\n".join(
            f"From: {m.get('sender', 'Unknown Sender')}\n"
            f"Subject: {m.get('subject', 'No Subject')}\n\n"
            f"{m.get('body', '')}"
            for m in thread_emails
        )

        # ✅ 3. Natural, executive-style summarization prompt
        prompt = f"""
        You are an AI email summarization assistant for a busy professional.

        Summarize the following thread into one natural, human-like paragraph that:
        - Captures the main topic and purpose of the conversation
        - Includes who is involved and any meeting times, decisions, or next steps
        - Keeps the tone professional but easy to read
        - Avoids unnecessary greetings, repetition, or formal sign-offs
        - Should be no longer than 5–6 lines

        Email Thread:
        {combined}

        Write the summary as if you're briefing a colleague who didn’t read the thread.
        """

        # ✅ 4. Use summarize_text for consistent tone & caching behavior
        summary = self._run_groq_model(prompt)

        # ✅ 5. Save summary in cache
        if thread_id and source and contact_email:
            self._set_cache(source, contact_email, thread_id, summary)


        return summary


    # ------------------------------------------------------
    # CONTACT-WIDE SUMMARY
    # ------------------------------------------------------

    def summarize_contact(self, contact_obj, source=None, force=False):
        """
        Summarize all thread summaries for a given contact into a single compact summary.

        Args:
            contact_obj (dict): Contact record containing 'email' and 'threads'
            source (str): Source label (e.g., gmail/outlook)
            force (bool): If True, clears cache and regenerates

        Returns:
            str: Compact, human-readable summary for the entire contact.
        """
        contact_email = contact_obj.get("email", "unknown")
        threads = contact_obj.get("threads", [])
        if not threads:
            return "No threads found for this contact."

        # ✅ Collect thread summaries
        thread_summaries = []
        for t in threads:
            if "summary" in t:
                thread_summaries.append(t["summary"])
            else:
                # if thread summary not generated yet
                summary = self.summarize_thread(
                    t.get("messages", []),
                    source=source,
                    contact_email=contact_email,
                    thread_id=t.get("id")
                )
                t["summary"] = summary
                thread_summaries.append(summary)

        # ✅ Create one compact summary from all threads
        compact_summary = self.summarize_contact_threads(
            all_threads=thread_summaries,
            source=source,
            contact_email=contact_email,
            force=force
        )

        # (Optional) Save in cache as “contact-level” summary
        if source and contact_email:
            contact_key = f"{source}:{contact_email}"
            self.cache[contact_key] = {"summary": compact_summary, "timestamp": time.time()}
            self._save_cache()
        # ✅ Update JSON with full contact + threads
        contact_obj["contact summary"] = compact_summary
        self._update_contact_json(contact_obj, source)

        return compact_summary


    def summarize_contact_threads(self, all_threads, source=None, contact_email=None, force=False):
        """
        Create a natural, concise summary from multiple email threads.
        Designed for busy users who need clarity fast.
        """
        if force and source and contact_email:
            self._clear_contact_cache(source, contact_email)

        joined_threads = "\n\n---\n\n".join(all_threads)

        prompt = f"""
        You are an AI assistant that creates email briefings for a busy professional.

        Below are multiple email threads between contacts.

        Summarize them into one cohesive, human-like summary that:
        - Captures the overall context and purpose of communication
        - Mentions key decisions, updates, people, and dates
        - Includes next steps, meetings, or follow-ups if mentioned
        - Keeps it natural and conversational (avoid bullet points)
        - Is no longer than 6 lines
        - Feels like an executive recap, not a formal email

        Threads:
        {joined_threads}

        Write the summary as if you’re briefing your manager in plain English.
        """

        return self._run_groq_model(prompt)


    # ------------------------------------------------------
    # INTERNAL: Update contact summaries JSON
    # ------------------------------------------------------
    def _update_contact_json(self, contact_obj, source):
        """
        Update the main summaries_ID.json file with the latest contact record.
        If the contact already exists, replace it; otherwise append a new record.
        """
        json_path = os.path.join(Path(__file__).resolve().parent.parent, "Summaries", "summaries_ID.json")
        os.makedirs(os.path.dirname(json_path), exist_ok=True)

        try:
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = []
        except Exception as e:
            print(f"[WARN] Failed to load summaries_ID.json: {e}. Starting new.")
            data = []

        # remove any old record for this contact
        email = contact_obj.get("email")
        data = [d for d in data if d.get("email") != email]

        # add the updated record
        contact_obj["source"] = source
        contact_obj["id"] = f"{source}:{email}"
        contact_obj["timestamp"] = datetime.now(timezone.utc).isoformat()

        data.append(contact_obj)

        # save back
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"✅ Updated JSON for contact: {email}")

