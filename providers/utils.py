def extract_email(s: str) -> str:
    """Extract email from a string that might be an email or contact ID."""
    if not s:
        return ""
    # If it's already just an email
    if "@" in s and " " not in s and ":" not in s:
        return s.lower()
    # If it's in format "source:email"
    if ":" in s:
        return s.split(":", 1)[1].lower()
    return s.lower()

def normalize_contact_id(cid: str) -> str:
    """Convert anything into 'source:email'."""
    if not cid:
        return ""
    email = extract_email(cid)
    if cid.lower().startswith("outlook:"):
        source = "outlook"
    else:
        source = "gmail"
    return f"{source}:{email}"

def expand_possible_ids(cid: str):
    """Return all possible forms of the contact ID for backward matching."""
    if not cid:
        return []
    email = extract_email(cid)
    return list({
        cid,
        email,
        f"gmail:{email}",
        f"outlook:{email}",
    })
