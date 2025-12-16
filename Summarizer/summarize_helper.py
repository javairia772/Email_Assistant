from Summarizer.groq_summarizer import GroqSummarizer
import traceback

summarizer = GroqSummarizer()


def summarize_thread_logic(source: str, contact_email: str, thread_id: str, text=None, thread_obj=None, force=False):
    """
    Summarize a single thread.
    If `text` is provided, it takes priority over thread_obj for summarization.
    """
    try:
        if force:
            summarizer._clear_contact_cache(source, contact_email)

        cached_summary = summarizer._get_from_cache(source, contact_email, thread_id)
        if cached_summary:
            print(f"⚡ Using cached summary for {contact_email}:{thread_id}")
            return {"thread_id": thread_id, "summary": cached_summary, "used_cache": True}

        # ✅ Prefer direct text if given
        if text and len(text.strip()) > 20:
            combined = text.strip()
        else:
            # fallback: reconstruct text from thread_obj
            if isinstance(thread_obj, str):
                thread_obj = [{"sender": "Unknown", "subject": "No Subject", "body": thread_obj}]
            elif not isinstance(thread_obj, list):
                thread_obj = [thread_obj]

            combined = "\n\n---\n\n".join(
                f"From: {m.get('sender','Unknown')}\nSubject: {m.get('subject','No Subject')}\n\n{m.get('body','')}"
                for m in thread_obj
            )

        # ✅ Only summarize meaningful text
        if not combined or len(combined.strip()) < 20:
            return {"thread_id": thread_id, "summary": "No meaningful content to summarize."}

        summary = summarizer.summarize_text(combined)
        summarizer._set_cache(source, contact_email, thread_id, summary)

        return {"thread_id": thread_id, "summary": summary, "used_cache": False}

    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def summarize_contact_logic(source: str, contact_email: str, fetch_fn, top: int = 50, force_refresh: bool = False):
    """
    fetch_fn = function to fetch threads (e.g., gmail.fetch_threads or outlook.fetch_threads)
    """
    try:
        fetch_res = fetch_fn(contact_email, top)
        if isinstance(fetch_res, dict) and fetch_res.get("error"):
            return {"error": fetch_res}

        threads = fetch_res or []
        thread_summaries = []

        for i, thread in enumerate(threads, start=1):
            thread_id = None
            if isinstance(thread, list) and len(thread) > 0 and isinstance(thread[0], dict):
                thread_id = thread[0].get("conversationId") or thread[0].get("threadId")
            elif isinstance(thread, dict):
                thread_id = thread.get("id") or thread.get("threadId") or thread.get("conversationId")
            if not thread_id:
                thread_id = f"{source}_thread_{i}"
            s = summarize_thread_logic(source, contact_email, thread_id, thread_obj=thread, force=force_refresh)

        summaries_texts = [t["summary"] for t in thread_summaries if "summary" in t]
        contact_summary = summarizer.summarize_contact_threads(
            summaries_texts, source=source, contact_email=contact_email, force=force_refresh
        ) if summaries_texts else ""

        return {
            "contact_email": contact_email,
            "source": source,
            "thread_count": len(threads),
            "thread_summaries": thread_summaries,
            "contact_summary": contact_summary,
            "display_summary": contact_summary
        }

    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def get_thread_text_for_debug(thread_obj):
    """Extracts raw text from thread_obj for debugging summarization input."""
    text_parts = []
    for msg in thread_obj.get("messages", []):
        payload = msg.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
        subject = headers.get("Subject", "")
        sender = headers.get("From", "")
        body = ""
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    import base64
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                    break
        text_parts.append(f"From: {sender}\nSubject: {subject}\n\n{body}")
    return "\n---\n".join(text_parts)
