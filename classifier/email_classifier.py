import re



def _count_keywords(text, keywords):
    return sum(
        1 for kw in keywords
        if re.search(rf"\b{re.escape(kw)}\b", text)
    )

# -----------------------------------------------------
# 🔹 ROLE CLASSIFICATION ENHANCED DICTIONARY (EXPANDED)
# -----------------------------------------------------
ROLE_KEYWORDS = {
    "Student": [
        "student", "undergraduate", "undergrad", "grad", "graduate", "bachelor", "masters", "msc",
        "phd", "doctoral", "thesis", "dissertation", "coursework", "class assignment", "homework",
        "project submission", "semester", "enrolled", "transcript", "exam", "midterm", "final exam",
        "lecture note", "canvas", "moodle", "blackboard", "gpa", "credit hours", "enroll", "advisor",
        "supervisor", "professor", "teacher", "study", "group study", "academic advisor", "student id",
        "attendance", "plagiarism", "assignment due", "extension request", "course registration",
        "lab report", "capstone", "project milestone", "internship report", "research proposal", "thesis defense",
        "academic program", "semester plan", "study schedule", "student council", "student union",
        "exam schedule", "course syllabus", "practicum", "peer review assignment", "quiz", "online class",
        "virtual lab", "grading feedback", "student project", "faculty recommendation"
    ],
    "Faculty": [
        "professor", "lecturer", "faculty", "instructor", "supervisor", "advisor", "department chair",
        "dean", "academic staff", "postdoc", "research fellow", "publication", "conference paper",
        "research grant", "peer review", "call for papers", "academic journal", "editor", "faculty meeting",
        "reviewer", "university", "lab", "department", "academic conference", "presentation", "syllabus",
        "mentorship", "exam committee", "grading", "evaluation", "tenure", "faculty development",
        "curriculum design", "teaching assistant", "course coordination", "lecture schedule",
        "research supervision", "academic project", "student evaluation", "seminar organization",
        "committee member", "journal submission", "peer evaluation", "faculty workshop", "academic advisor"
    ],
    "Admin": [
        "admin", "administration", "registrar", "record office", "billing", "tuition", "enrollment",
        "admission", "finance", "accounting", "human resources", "hr", "office", "clearance", "fee",
        "department of finance", "office of registrar", "scholarship", "support office", "it support",
        "policy", "deadline", "payroll", "official notice", "document verification", "university office",
        "forms", "certificates", "official transcript", "student record", "financial aid", "admission form",
        "fee invoice", "clearance certificate", "office memo", "office announcement", "admin request",
        "staff meeting", "enrollment form", "document processing", "course registration form", "university notification"
    ],
    "Industry": [
        "company", "corporate", "recruiter", "recruitment", "hiring", "headhunter", "career",
        "internship", "job", "vacancy", "opening", "business", "partner", "collaboration",
        "industry", "enterprise", "sponsor", "startup", "ceo", "cto", "hr manager", "engineering team",
        "offer letter", "job description", "role requirement", "portfolio", "application process",
        "meeting request", "networking", "linkedin", "job application", "employment contract",
        "project proposal", "client meeting", "business development", "partnership request", "corporate training",
        "recruitment drive", "talent acquisition", "career fair", "internship offer", "job interview"
    ],
    "External Academic": [
        "research collaboration", "university", "college", "institute", "external examiner",
        "academic partner", "joint research", "visiting scholar", "academic conference",
        "research paper", "workshop", "seminar", "symposium", "faculty exchange", "guest lecture",
        "academic invitation", "collaborative research", "journal editor", "scientific committee",
        "call for participation", "research grant", "academic publication", "conference invitation",
        "research seminar", "publication submission", "external reviewer", "academic workshop"
    ],
    "Government / Organization": [
        "government", "ministry", "department", "ngo", "non-profit", "foundation", "agency", "council",
        "authority", "public sector", "federal", "provincial", "municipal", "secretariat", "official",
        "policy", "program", "initiative", "grant", "funding", "tender", "procurement", "compliance",
        "legal", "report", "regulation", "gov.pk", "gov.in", "gov.uk", "gov.us", "gov",
        "public notice", "government office", "official communication", "administrative order",
        "policy update", "legal notice", "project proposal", "committee", "government initiative",
        "funding request"
    ],
    "General External": [
        "dear sir", "dear madam", "to whom it may concern", "greetings", "hello", "hi", "thank you",
        "regards", "appreciate", "best wishes", "inquiry", "feedback", "suggestion", "information request",
        "website", "newsletter", "general", "customer support", "info@", "contact@", "help@", "support@",
        "service request", "general inquiry", "external communication", "client email", "partner email",
        "user feedback", "external notice"
    ],
}

# -----------------------------------------------------
# 🔹 IMPORTANCE CLASSIFICATION ENHANCED DICTIONARY (EXPANDED)
# -----------------------------------------------------
IMPORTANCE_KEYWORDS = {
    "High": [
        "urgent", "asap", "immediate", "important", "critical", "emergency", "deadline", 
        "time sensitive", "respond soon", "action required", "response needed", "final reminder",
        "today", "within 24 hours", "by end of day", "meeting request", "schedule confirmation",
        "project update", "interview", "offer", "contract", "payment due", "approval needed",
        "review required", "final notice", "requires your attention", "submission deadline",
        "priority", "important update", "mandatory", "critical task", "high priority", "urgent action"
    ],
    "Medium": [
        "follow up", "reminder", "update", "notification", "information", "proposal", 
        "request", "invitation", "appointment", "discussion", "reschedule", "progress report",
        "clarification", "question", "status update", "coordination", "internal communication",
        "weekly report", "monthly report", "planning", "documentation", "meeting minutes",
        "review", "feedback requested", "action suggested", "update required"
    ],
    "Low": [
        "newsletter", "announcement", "promotion", "advertisement", "marketing", "survey",
        "thank you", "automated message", "no reply", "auto response", "digest", "news",
        "summary", "blog post", "weekly update", "event invite", "holiday greetings", "offer",
        "subscription", "reminder: optional", "informational", "general info", "FYI"
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
    text = email_text.lower()
    sender = sender_email.lower()

    scores = {role: 0 for role in ROLE_KEYWORDS}

    # 1️⃣ Keyword scoring (moderate weight)
    for role, keywords in ROLE_KEYWORDS.items():
        scores[role] += _count_keywords(text, keywords) * 2

    # 2️⃣ Sender-name overrides (VERY STRONG)
    sender_overrides = {
        "Admin": ["office", "registrar", "admissions", "admin", "hr", "finance"],
        "Faculty": ["prof", "dr.", "lecturer", "faculty"],
        "Student": ["student", "roll", "reg no"],
        "Industry": ["hr", "recruit", "talent", "company"],
        "Government / Organization": ["ministry", "department", "authority"],
    }

    for role, signals in sender_overrides.items():
        for s in signals:
            if s in sender:
                scores[role] += 6  # override-level weight

    # 3️⃣ Domain hints (light weight, conflict-safe)
    for role, domains in DOMAIN_HINTS.items():
        for d in domains:
            if d in sender:
                scores[role] += 1

    # 4️⃣ Priority resolution (important!)
    priority = [
        "Admin",
        "Faculty",
        "Student",
        "Industry",
        "External Academic",
        "Government / Organization",
        "General External",
    ]

    best_score = max(scores.values())
    if best_score == 0:
        return "General External", 0.4

    # Resolve ties by priority
    candidates = [r for r, s in scores.items() if s == best_score]
    for p in priority:
        if p in candidates:
            best_role = p
            break

    confidence = min(best_score / 8, 0.95)

    return best_role, round(confidence, 3)



def classify_importance(email_text):
    text = email_text.lower()
    scores = {lvl: 0 for lvl in IMPORTANCE_KEYWORDS}

    for level, keywords in IMPORTANCE_KEYWORDS.items():
        scores[level] += _count_keywords(text, keywords) * 2

    # Explicit urgency detection
    if re.search(r"\b(asap|urgent|deadline|today|immediately|within 24 hours)\b", text):
        scores["High"] += 4

    best_score = max(scores.values())
    if best_score == 0:
        return "Medium", 0.4

    best_level = max(scores, key=scores.get)
    confidence = min(best_score / 6, 0.95)

    return best_level, round(confidence, 3)



def classify_email(sender, subject, body):
    email_text = f"From: {sender}\nSubject: {subject}\nBody: {body}"

    role, role_conf = classify_role(email_text, sender)
    imp, imp_conf = classify_importance(email_text)

    return {
        "role": role,
        "role_confidence": role_conf,
        "importance": imp,
        "importance_confidence": imp_conf,
    }
