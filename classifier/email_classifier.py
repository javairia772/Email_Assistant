import re

# -----------------------------------------------------
# 🔹 ROLE CLASSIFICATION ENHANCED DICTIONARY
# -----------------------------------------------------
ROLE_KEYWORDS = {
    "Student": [
        "student", "undergraduate", "undergrad", "grad", "graduate", "bachelor", "masters", "msc",
        "phd", "thesis", "dissertation", "coursework", "class assignment", "homework", "project submission",
        "semester", "enrolled", "transcript", "exam", "midterm", "final exam", "lecture note", "canvas",
        "moodle", "blackboard", "gpa", "credit hours", "enroll", "advisor", "supervisor", "professor", 
        "teacher", "study", "group study", "academic advisor", "student id", "attendance", "plagiarism",
        "assignment due", "extension request", "course registration"
    ],
    "Faculty": [
        "professor", "lecturer", "faculty", "instructor", "supervisor", "advisor", "department chair",
        "dean", "academic staff", "postdoc", "research fellow", "publication", "conference paper",
        "research grant", "peer review", "call for papers", "academic journal", "editor", "faculty meeting",
        "reviewer", "university", "lab", "department", "academic conference", "presentation", "syllabus",
        "mentorship", "exam committee", "grading", "evaluation", "tenure", "faculty development"
    ],
    "Admin": [
        "admin", "administration", "registrar", "record office", "billing", "tuition", "enrollment",
        "admission", "finance", "accounting", "human resources", "hr", "office", "clearance", "fee",
        "department of finance", "office of registrar", "scholarship", "support office", "it support",
        "policy", "deadline", "payroll", "official notice", "document verification", "university office",
        "forms", "certificates", "official transcript"
    ],
    "Industry": [
        "company", "corporate", "recruiter", "recruitment", "hiring", "headhunter", "career",
        "internship", "job", "vacancy", "opening", "business", "partner", "collaboration",
        "industry", "enterprise", "sponsor", "startup", "ceo", "cto", "hr manager", "engineering team",
        "offer letter", "job description", "role requirement", "portfolio", "application process",
        "meeting request", "networking", "linkedin"
    ],
    "External Academic": [
        "research collaboration", "university", "college", "institute", "external examiner",
        "academic partner", "joint research", "visiting scholar", "academic conference",
        "research paper", "workshop", "seminar", "symposium", "faculty exchange", "guest lecture",
        "academic invitation", "collaborative research", "journal editor", "scientific committee",
        "call for participation"
    ],
    "Government / Organization": [
        "government", "ministry", "department", "ngo", "non-profit", "foundation", "agency", "council",
        "authority", "public sector", "federal", "provincial", "municipal", "secretariat", "official",
        "policy", "program", "initiative", "grant", "funding", "tender", "procurement", "compliance",
        "legal", "report", "regulation", "gov.pk", "gov.in", "gov.uk", "gov.us", "gov"
    ],
    "General External": [
        "dear sir", "dear madam", "to whom it may concern", "greetings", "hello", "hi", "thank you",
        "regards", "appreciate", "best wishes", "inquiry", "feedback", "suggestion", "information request",
        "website", "newsletter", "general", "customer support", "info@", "contact@", "help@", "support@"
    ],
}

# -----------------------------------------------------
# 🔹 IMPORTANCE CLASSIFICATION ENHANCED DICTIONARY
# -----------------------------------------------------
IMPORTANCE_KEYWORDS = {
    "High": [
        "urgent", "asap", "immediate", "important", "critical", "emergency", "deadline", 
        "time sensitive", "respond soon", "action required", "response needed", "final reminder",
        "today", "within 24 hours", "by end of day", "meeting request", "schedule confirmation",
        "project update", "interview", "offer", "contract", "payment due", "approval needed",
        "review required", "final notice", "requires your attention", "submission deadline"
    ],
    "Medium": [
        "follow up", "reminder", "update", "notification", "information", "proposal", 
        "request", "invitation", "appointment", "discussion", "reschedule", "progress report",
        "clarification", "question", "status update", "coordination", "internal communication",
        "weekly report", "monthly report", "planning", "documentation", "meeting minutes"
    ],
    "Low": [
        "newsletter", "announcement", "promotion", "advertisement", "marketing", "survey",
        "thank you", "automated message", "no reply", "auto response", "digest", "news",
        "summary", "blog post", "weekly update", "event invite", "holiday greetings", "offer",
        "subscription", "reminder: optional", "course announcement", "workshop notice"
    ]
}

# -----------------------------------------------------
# 🔹 DOMAIN HINTS (ADDITIONAL WEIGHT)
# -----------------------------------------------------
DOMAIN_HINTS = {
    "Student": ["@student.", ".edu", ".edu.pk", ".uni", ".campus"],
    "Faculty": ["@faculty.", "@university.", ".edu", ".ac."],
    "Admin": ["@admin.", "@registrar.", "@office.", "@hr.", "@finance.", "@admissions."],
    "Industry": [".com", "@company.", "@recruit", "@business.", "@enterprise.", "@startup."],
    "External Academic": [".edu", ".ac.", ".research", "@journal."],
    "Government / Organization": [".gov", ".org", ".ngo", ".foundation"],
    "General External": ["@gmail.", "@yahoo.", "@outlook.", "@hotmail."]
}

# -----------------------------------------------------
# 🔹 CLASSIFICATION LOGIC
# -----------------------------------------------------
def classify_role(email_text, sender_email):
    email_lower = email_text.lower()
    role_scores = {role: 0 for role in ROLE_KEYWORDS}

    # Keyword-based scoring
    for role, keywords in ROLE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in email_lower:
                role_scores[role] += 1

    # Domain-based scoring
    sender_lower = sender_email.lower()
    for role, domains in DOMAIN_HINTS.items():
        for domain in domains:
            if domain in sender_lower:
                role_scores[role] += 2  # domain matches weigh more

    if not any(role_scores.values()):
        return "General External", 0.0

    best_role = max(role_scores, key=role_scores.get)
    confidence = min(role_scores[best_role] / 5, 1.0)
    return best_role, confidence


def classify_importance(email_text):
    email_lower = email_text.lower()
    imp_scores = {lvl: 0 for lvl in IMPORTANCE_KEYWORDS}

    for level, keywords in IMPORTANCE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in email_lower:
                imp_scores[level] += 1

    if not any(imp_scores.values()):
        return "Medium", 0.5

    best = max(imp_scores, key=imp_scores.get)
    confidence = min(imp_scores[best] / 5, 1.0)
    return best, confidence


def classify_email(sender, subject, body):
    email_text = f"From: {sender}\nSubject: {subject}\nBody: {body}"
    role, role_conf = classify_role(email_text, sender)
    imp, imp_conf = classify_importance(email_text)
    return {
        "role": role,
        "role_confidence": round(role_conf, 3),
        "importance": imp,
        "importance_confidence": round(imp_conf, 3),
    }
