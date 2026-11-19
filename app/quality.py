"""Metadata quality engine.

Implements rule-based checks drawn from the Dublin Core Metadata Initiative
(DCMI) element set and the Bruce and Hillmann (2004) metadata quality
framework. Two sub-scores are produced:

* completeness: weighted presence of required and recommended elements
* conformance: share of format and consistency rules passed

overall = 0.6 * completeness + 0.4 * conformance (both on a 0 to 100 scale)
"""
import re

ITEM_TYPES = [
    "Thesis", "Dissertation", "Article", "Conference Paper", "Book",
    "Book Chapter", "Technical Report", "Inaugural Lecture", "Dataset",
]
LANGUAGES = {"en": "English", "yo": "Yoruba", "ig": "Igbo", "ha": "Hausa", "fr": "French"}
FACULTIES = [
    "Distance Learning Institute", "Faculty of Architecture", "Faculty of Arts",
    "Faculty of Basic Medical Sciences", "Faculty of Clinical Sciences",
    "Faculty of Communication and Media Studies", "Faculty of Computing and Informatics",
    "Faculty of Dental Sciences", "Faculty of Education", "Faculty of Engineering",
    "Faculty of Environmental Sciences", "Faculty of Law", "Faculty of Life Sciences",
    "Faculty of Management Sciences", "Faculty of Pharmacy",
    "Faculty of Physical and Earth Sciences", "Faculty of Science",
    "Faculty of Social Sciences", "Staff Publications",
]
CANONICAL_THESIS_PUBLISHER = "University of Lagos School of Postgraduate Studies"
PLACEHOLDER_ABSTRACTS = {"full text attached", "full text attached.", "abstract", "n/a", "na", "none", "-"}

# (field, weight, applies_to) ; applies_to None means all types
COMPLETENESS_RULES = [
    ("title", 15, None),
    ("creators", 15, None),
    ("date_issued", 10, None),
    ("item_type", 10, None),
    ("abstract", 15, None),
    ("subjects", 10, None),
    ("advisor", 5, {"Thesis", "Dissertation"}),
    ("publisher", 5, None),
    ("language", 5, None),
    ("faculty", 5, None),
    ("rights", 5, None),
]

AUTHOR_RE = re.compile(r"^[A-Z][A-Za-z'\-]+(?: [A-Z][A-Za-z'\-]+)*, (?:[A-Z]\. ?)+$")
DATE_RE = re.compile(r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$")


def _present(item, field):
    v = item.get(field)
    if isinstance(v, list):
        return len([x for x in v if str(x).strip()]) > 0
    if field == "abstract":
        return bool(v and v.strip() and v.strip().lower() not in PLACEHOLDER_ABSTRACTS)
    return bool(v and str(v).strip())


def normalise_author(name):
    """'Okafor, A.I' -> 'Okafor, A. I.' ; leaves well-formed names unchanged."""
    name = re.sub(r"\s+", " ", (name or "").strip())
    if "," not in name:
        return name
    surname, given = [p.strip() for p in name.split(",", 1)]
    if re.fullmatch(r"(?:[A-Za-z]\.? ?)+", given):
        initials = re.findall(r"[A-Za-z]", given)
        given = " ".join(i.upper() + "." for i in initials)
    surname = surname[:1].upper() + surname[1:]
    return f"{surname}, {given}"


def check(item):
    """Return dict with completeness, conformance, overall and a list of issues."""
    issues = []
    item_type = item.get("item_type") or ""

    # ---- completeness
    possible, earned = 0, 0
    for field, weight, applies in COMPLETENESS_RULES:
        if applies and item_type not in applies:
            continue
        possible += weight
        if _present(item, field):
            earned += weight
        else:
            level = "error" if weight >= 10 else "warning"
            msg = f"Missing {field.replace('_', ' ')}"
            if field == "abstract" and (item.get("abstract") or "").strip():
                msg = "Abstract is a placeholder (for example 'Full text attached'), not a real abstract"
            issues.append({"field": field, "level": level, "message": msg})
    completeness = round(100 * earned / possible, 1) if possible else 0

    # ---- conformance and consistency
    rules_run, rules_passed = 0, 0

    def rule(ok, field, message, level="warning"):
        nonlocal rules_run, rules_passed
        rules_run += 1
        if ok:
            rules_passed += 1
        else:
            issues.append({"field": field, "level": level, "message": message})

    title = (item.get("title") or "").strip()
    if title:
        rule(not re.search(r"[.,;:]$", title), "title", "Title ends with stray punctuation")
        rule(not re.search(r",\S", title), "title", "Missing space after comma in title")
        rule(title != title.upper(), "title", "Title is in all capitals")

    for a in item.get("creators") or []:
        rule(bool(AUTHOR_RE.match(a.strip())), "creators",
             f"Author '{a}' is not in 'Surname, I. I.' form; suggested: '{normalise_author(a)}'")

    d = (item.get("date_issued") or "").strip()
    if d:
        rule(bool(DATE_RE.match(d)), "date_issued", "Date is not ISO 8601 (YYYY, YYYY-MM or YYYY-MM-DD)", "error")

    if item_type:
        rule(item_type in ITEM_TYPES, "item_type", f"Type '{item_type}' is not in the controlled list")

    lang = (item.get("language") or "").strip()
    if lang:
        rule(lang in LANGUAGES, "language", f"Language '{lang}' is not an ISO 639-1 code in the list")

    fac = (item.get("faculty") or "").strip()
    if fac:
        rule(fac in FACULTIES, "faculty", f"Faculty '{fac}' is not in the controlled list")

    pub = (item.get("publisher") or "").strip()
    if pub and item_type in {"Thesis", "Dissertation"}:
        rule(pub == CANONICAL_THESIS_PUBLISHER, "publisher",
             f"Publisher form varies; use '{CANONICAL_THESIS_PUBLISHER}'")

    subj = item.get("subjects") or []
    if subj:
        rule(len(subj) >= 3, "subjects", "Fewer than three subject terms")

    abstract = (item.get("abstract") or "").strip()
    if _present(item, "abstract"):
        rule(len(abstract.split()) >= 10, "abstract", "Abstract is very short (under 10 words)")

    if item.get("rights") == "embargo":
        rule(bool(DATE_RE.match(item.get("embargo_until") or "")), "embargo_until",
             "Embargo selected but no valid embargo end date", "error")

    conformance = round(100 * rules_passed / rules_run, 1) if rules_run else 100.0
    overall = round(0.6 * completeness + 0.4 * conformance, 1)
    return {
        "completeness": completeness,
        "conformance": conformance,
        "overall": overall,
        "grade": grade(overall),
        "issues": issues,
        "errors": sum(1 for i in issues if i["level"] == "error"),
    }


def grade(score):
    if score >= 85:
        return "Good"
    if score >= 70:
        return "Fair"
    return "Poor"


def suggest_subjects(title, abstract, vocabulary, limit=6):
    """Suggest existing subject terms whose words appear in the title or abstract.
    Simple controlled-vocabulary matching; no machine learning involved."""
    text = f" {title} {abstract} ".lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    scored = []
    for term in vocabulary:
        words = [w for w in re.sub(r"[^a-z0-9 ]", " ", term.lower()).split() if len(w) > 3]
        if not words:
            continue
        hits = sum(1 for w in words if f" {w} " in text)
        if hits == len(words):
            scored.append((hits, term))
    scored.sort(key=lambda x: (-x[0], x[1]))
    seen, out = set(), []
    for _, t in scored:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:limit]
