"""Metadata quality audit of the UNILAG records, before and after SmartIR automatic normalisation."""
import json, os, re, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import quality, dedup

HERE = os.path.dirname(os.path.abspath(__file__))
ALL = "--all" in sys.argv  # default: the thesis audit sample only; --all adds the extension batch (theses only)
data = json.load(open(os.path.join(HERE, "..", "data", "unilag_records.json"), encoding="utf-8"))
if ALL:
    data["records"] += json.load(open(os.path.join(HERE, "..", "data", "unilag_records_extension.json"), encoding="utf-8"))["records"]

def to_item(r):
    return {"title": r["title"], "creators": r["creators"], "advisor": r["contributor_advisor"], "date_issued": r["date"],
            "item_type": r["type"], "subjects": r["subjects"], "abstract": r["abstract"], "publisher": r["publisher"],
            "language": r["language"], "faculty": r["faculty"], "rights": "open"}

def normalise(it):
    it = dict(it)
    it["creators"] = [quality.normalise_author(a) for a in it["creators"]]
    it["title"] = re.sub(r",(\S)", r", \1", it["title"]).rstrip(" .,;:")
    if it["item_type"] in {"Thesis", "Dissertation"}:
        it["publisher"] = quality.CANONICAL_THESIS_PUBLISHER
    it["faculty"] = {"Faculty of Art": "Faculty of Arts", "Faculty of Social Science": "Faculty of Social Sciences"}.get(it["faculty"], it["faculty"])
    return it

rows, field_gaps, issue_types = [], Counter(), Counter()
theses = [r for r in data["records"] if r["type"] == "Thesis"]
for r in theses:  # full item pages were read for theses only
    it = to_item(r); b = quality.check(it); a = quality.check(normalise(it))
    rows.append({"handle": r["handle"] or r["url"].rsplit("/",1)[1][:8], "title": r["title"][:60], "type": r["type"],
                 "before": b["overall"], "after": a["overall"], "completeness": b["completeness"],
                 "conformance_before": b["conformance"], "conformance_after": a["conformance"], "issues": len(b["issues"])})
    for i in b["issues"]:
        issue_types[re.sub(r"'[^']*'", "'...'", i["message"]).split(";")[0]] += 1

def pct(n, d): return round(100*n/d, 1)
field = {
 "Supervisor/advisor recorded (theses)": pct(sum(1 for r in theses if r["contributor_advisor"]), len(theses)),
 "Real abstract present (theses)": pct(sum(1 for r in theses if r["abstract_status"]=="real"), len(theses)),
 "Abstract placeholder 'Full text attached' (theses)": pct(sum(1 for r in theses if r["abstract_status"]=="placeholder"), len(theses)),
 "Abstract missing (theses)": pct(sum(1 for r in theses if r["abstract_status"]=="missing"), len(theses)),
 "Publisher recorded (theses)": pct(sum(1 for r in theses if r["publisher"]), len(theses)),
 "At least three subject terms (theses)": pct(sum(1 for r in theses if len(r["subjects"])>=3), len(theses)),
 "Author in full 'Surname, I. I.' form (theses)": pct(sum(1 for r in theses for a in r["creators"] if quality.AUTHOR_RE.match(a)), sum(len(r["creators"]) for r in theses)),
 "Date to month precision or better (theses)": pct(sum(1 for r in theses if len(r["date"])>=7), len(theses)),
}
pubs = Counter(r["publisher"] or "(blank)" for r in theses)
items = [dict(to_item(r), id=i) for i, r in enumerate(data["records"])]
dups = [(a["title"], b["title"], s) for a, b, s in dedup.duplicate_report(items)]
n = len(rows)
summary = {"records": n, "theses": len(theses),
  "mean_before": round(sum(r["before"] for r in rows)/n,1), "mean_after": round(sum(r["after"] for r in rows)/n,1),
  "mean_completeness": round(sum(r["completeness"] for r in rows)/n,1),
  "mean_conformance_before": round(sum(r["conformance_before"] for r in rows)/n,1),
  "mean_conformance_after": round(sum(r["conformance_after"] for r in rows)/n,1),
  "grades_before": Counter(quality.grade(r["before"]) for r in rows), "grades_after": Counter(quality.grade(r["after"]) for r in rows)}
out = {"summary": summary, "field_level": field, "publisher_forms": pubs, "issue_types": issue_types.most_common(),
       "duplicates": dups, "records": rows, "community_counts": data["community_counts"], "registry": data["registry_facts"]}
if not ALL:  # --all is informational and must not overwrite the thesis result file
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    json.dump(out, open(os.path.join(HERE, "results", "unilag_audit.json"), "w"), indent=1)
print(json.dumps({k: out[k] for k in ("summary","field_level","publisher_forms","duplicates")}, indent=1))
print(issue_types.most_common(12))
