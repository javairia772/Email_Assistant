import os
import json
import time
from dotenv import load_dotenv
import sys
import io
from datetime import datetime
try:
    from groq import Groq
except ImportError:
    Groq = None

import requests 



load_dotenv()
if not sys.stdout.encoding or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="ignore")



class GroqSummarizer:
    def __init__(self, cache_path=None, ttl_hours=24):
        """
        Set PROVIDER in .env: groq
        """
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        summaries_dir = os.path.join(project_root, "Summaries")
        os.makedirs(summaries_dir, exist_ok=True)
        self.provider = os.getenv("PROVIDER", "groq").lower()
        self.cache_path = cache_path or os.path.join(summaries_dir, "summaries_cache.json")
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
        Also automatically classifies role and importance and caches them.
        """
        from classifier.email_classifier import classify_email

        # Force clear cache for this contact if needed
        if force and source and contact_email:
            self._clear_contact_cache(source, contact_email)

        # 1. Check cache first
        if thread_id and source and contact_email:
            cached = self.cache.get(self._get_cache_key(source, contact_email, thread_id))
            if cached:
                print(f"⚡ Using cached summary for thread {thread_id}")
                return cached.get("summary", "")

        # 2. Combine thread messages
        combined = "\n\n---\n\n".join(
            f"From: {m.get('sender', 'Unknown Sender')}\n"
            f"Subject: {m.get('subject', 'No Subject')}\n\n"
            f"{m.get('body', '')}"
            for m in thread_emails
        )

        # 3. Summarize text using Groq
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

        summary = self._run_groq_model(prompt)

        # 4. Classify role & importance for the thread
        try:
            sender = thread_emails[0].get("sender", contact_email)
            subject = thread_emails[0].get("subject", "")
            body = thread_emails[0].get("body", "")
            classification = classify_email(sender, subject, body)
            role = classification.get("role", "Unknown")
            importance = classification.get("importance", "Unknown")
            role_conf = classification.get("role_confidence", 0)
            importance_conf = classification.get("importance_confidence", 0)
        except Exception as e:
            print(f"[Classifier ERROR] {e}")
            role = "Unknown"
            importance = "Unknown"
            role_conf = 0
            importance_conf = 0

        # 5. Save summary + classification in cache
        if thread_id and source and contact_email:
            cache_key = self._get_cache_key(source, contact_email, thread_id)
            self.cache[cache_key] = {
                "summary": summary,
                "subject": thread_emails[0].get("subject", ""),
                "preview": thread_emails[0].get("body", "")[:100],  # optional preview
                "role": role,
                "importance": importance,
                "role_confidence": role_conf,
                "importance_confidence": importance_conf,
                "timestamp": time.time()
            }
            self._save_cache()

        return summary


    # ------------------------------------------------------
    # CONTACT-WIDE SUMMARY
    # ------------------------------------------------------

    def summarize_contact_threads(self, all_threads, source=None, contact_email=None, thread_ids=None, force=False):
        """
        Summarize multiple threads for a contact into a contact-level summary.
        Also fetches per-thread summaries with role/importance from cache.
        Returns a JSON object in the unified format.
        
        IMPORTANT: 
        - Role is determined ONCE at the contact level (same for all threads from this email)
        - Importance is determined PER THREAD (can vary between threads)
        """
        from classifier.email_classifier import classify_email, classify_role
        from datetime import datetime
        from collections import Counter

        # Force clear cache if requested
        if force and source and contact_email:
            self._clear_contact_cache(source, contact_email)

        # Join threads for the contact summary
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

        Write the summary as if you're briefing your manager in plain English.
        """

        contact_summary_text = self._run_groq_model(prompt)

        # ✅ Determine CONTACT-LEVEL ROLE (consistent across all threads)
        # Use the most common role from all threads, or classify once
        contact_role = "Unknown"
        contact_role_conf = 0
        
        if thread_ids:
            # Collect all roles from cached threads
            roles = []
            role_confs = []
            
            for tid in thread_ids:
                cache_key = self._get_cache_key(source, contact_email, tid)
                entry = self.cache.get(cache_key, {})
                if entry.get("role") and entry.get("role") != "Unknown":
                    roles.append(entry["role"])
                    role_confs.append(entry.get("role_confidence", 0))
            
            # If we have roles, use the most common one
            if roles:
                role_counter = Counter(roles)
                contact_role = role_counter.most_common(1)[0][0]
                # Average confidence for this role
                contact_role_conf = sum(role_confs) / len(role_confs) if role_confs else 0
            else:
                # Classify role once for the contact
                try:
                    first_thread = thread_ids[0] if thread_ids else None
                    if first_thread:
                        cache_key = self._get_cache_key(source, contact_email, first_thread)
                        entry = self.cache.get(cache_key, {})
                        subject = entry.get("subject", "")
                        preview = entry.get("preview", "")
                        email_text = f"From: {contact_email}\nSubject: {subject}\nBody: {preview}"
                        contact_role, contact_role_conf = classify_role(email_text)
                except Exception as e:
                    print(f"[Classifier ERROR] Failed to classify contact role: {e}")
                    contact_role = "Unknown"
                    contact_role_conf = 0

        # Build contact entry
        contact_entry = {
            "id": f"{source}:{contact_email}",
            "email": contact_email,
            "source": source,
            "role": contact_role,  # ✅ Contact-level role
            "role_confidence": round(contact_role_conf, 3),
            "threads": [],
            "summary": contact_summary_text,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        # Add per-thread summaries with THREAD-LEVEL importance
        if thread_ids:
            for tid in thread_ids:
                cache_key = self._get_cache_key(source, contact_email, tid)
                entry = self.cache.get(cache_key, {})
                subject = entry.get("subject", "")
                preview = entry.get("preview", "")
                body = preview or subject

                # ✅ Each thread gets its own importance classification
                importance = entry.get("importance", "Unknown")
                importance_conf = entry.get("importance_confidence", 0)

                if importance == "Unknown":
                    try:
                        from classifier.email_classifier import classify_importance
                        email_text = f"From: {contact_email}\nSubject: {subject}\nBody: {body}"
                        importance, importance_conf = classify_importance(email_text)

                        # Update cache with thread importance
                        entry["importance"] = importance
                        entry["importance_confidence"] = importance_conf
                        self.cache[cache_key] = entry
                    except Exception as e:
                        print(f"[Classifier ERROR] Failed to classify importance: {e}")
                        importance = "Unknown"
                        importance_conf = 0

                # ✅ Store contact-level role in each thread cache entry for consistency
                entry["role"] = contact_role
                entry["role_confidence"] = contact_role_conf
                self.cache[cache_key] = entry

                contact_entry["threads"].append({
                    "id": tid,
                    "subject": subject,
                    "preview": preview,
                    "summary": entry.get("summary", ""),
                    "role": contact_role,  # ✅ Same role for all threads from this contact
                    "importance": importance,  # ✅ Thread-specific importance
                    "importance_confidence": round(importance_conf, 3)
                })

            # Save cache after updating roles/importance
            self._save_cache()

        return contact_entry

