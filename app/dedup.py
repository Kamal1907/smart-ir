"""Duplicate detection.

A candidate pair is flagged when the normalised titles are highly similar
(difflib ratio >= 0.90) and either the publication year matches or at least
one author surname is shared. This is deterministic string matching and can
be explained to library staff without any machine learning.
"""
import re
from difflib import SequenceMatcher

TITLE_THRESHOLD = 0.90
STOP = {"a", "an", "the", "of", "in", "on", "and", "for", "to", "among", "some", "selected"}


def norm_title(t):
    t = re.sub(r"[^a-z0-9 ]", " ", (t or "").lower())
    return " ".join(w for w in t.split() if w not in STOP)


def surnames(creators):
    return {c.split(",")[0].strip().lower() for c in creators or [] if c.strip()}


def year(d):
    m = re.match(r"(\d{4})", d or "")
    return m.group(1) if m else ""


def similarity(a, b):
    return SequenceMatcher(None, norm_title(a), norm_title(b)).ratio()


def is_duplicate(a, b):
    s = similarity(a["title"], b["title"])
    if s < TITLE_THRESHOLD:
        return False, s
    same_year = year(a.get("date_issued")) and year(a.get("date_issued")) == year(b.get("date_issued"))
    shared_author = bool(surnames(a.get("creators")) & surnames(b.get("creators")))
    return bool(same_year or shared_author), s


def find_duplicates(candidate, items, exclude_id=None):
    out = []
    for it in items:
        if exclude_id is not None and it["id"] == exclude_id:
            continue
        dup, s = is_duplicate(candidate, it)
        if dup:
            out.append({"id": it["id"], "title": it["title"], "similarity": round(s, 3),
                        "date_issued": it.get("date_issued", ""), "status": it.get("status", "")})
    return sorted(out, key=lambda x: -x["similarity"])


def block_key(title):
    """Blocking key: the three longest significant title words, sorted.
    Near-identical titles share this key, so only items in the same block are compared."""
    words = sorted(set(norm_title(title).split()), key=lambda w: (-len(w), w))[:3]
    return " ".join(sorted(words))


def duplicate_report(items):
    blocks = {}
    for it in items:
        blocks.setdefault(block_key(it["title"]), []).append(it)
    pairs = []
    for group in blocks.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                dup, s = is_duplicate(group[i], group[j])
                if dup:
                    pairs.append((group[i], group[j], round(s, 3)))
    return pairs
