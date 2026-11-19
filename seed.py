"""Initialise the database and load data.

python seed.py            load demo users and the UNILAG records
python seed.py --demo N   also add N synthetic records (origin='demo') for load testing only
python seed.py --reset    delete the database first
"""
import argparse
import json
import os
import random

from app import db, quality
from app.main import hash_password

HERE = os.path.dirname(os.path.abspath(__file__))

USERS = [
    ("depositor@demo.edu.ng", "Demo Depositor (Postgraduate Student)", "depositor"),
    ("librarian@demo.edu.ng", "Demo Librarian (Repository Manager)", "librarian"),
    ("admin@demo.edu.ng", "Demo Administrator", "admin"),
]
PASSWORD = "Demo@2026"


UNILAG_FILES = ["unilag_records.json", "unilag_records_extension.json"]


def load_unilag(c):
    records = []
    for fn in UNILAG_FILES:
        records += json.load(open(os.path.join(HERE, "data", fn), encoding="utf-8"))["records"]
    n = 0
    for r in records:
        if c.execute("SELECT 1 FROM items WHERE source_url=?", (r["url"],)).fetchone():
            continue
        item = {
            "title": r["title"], "creators": r["creators"], "advisor": r["contributor_advisor"],
            "date_issued": r["date"], "item_type": r["type"], "subjects": r["subjects"],
            "abstract": r["abstract"], "publisher": r["publisher"], "language": r["language"],
            "faculty": r["faculty"], "rights": "open",
        }
        q = quality.check(item)
        cur = c.execute(
            "INSERT INTO items(handle,title,creators,advisor,date_issued,item_type,subjects,abstract,publisher,"
            "language,faculty,rights,source_url,origin,batch,status,quality_score) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'unilag',?,'published',?)",
            (r["handle"] or None, r["title"], json.dumps(r["creators"]), r["contributor_advisor"], r["date"],
             r["type"], json.dumps(r["subjects"]), r["abstract"], r["publisher"], r["language"], r["faculty"],
             "open", r["url"], r["batch"], q["overall"]))
        for f in r.get("files", []):
            c.execute("INSERT INTO files(item_id,filename,stored_name,size_bytes) VALUES (?,?,?,?)",
                      (cur.lastrowid, f["name"], "", int(f["size_mb"] * 1048576)))
        n += 1
    return n


WORDS = ("library information repository digital preservation metadata access open scholarly "
         "communication research university nigeria lagos education health engineering policy "
         "management analysis assessment development evaluation impact students staff services "
         "technology adoption systems network energy water urban rural market finance law").split()


def load_demo(c, n):
    rnd = random.Random(42)
    for i in range(n):
        title = " ".join(rnd.choice(WORDS) for _ in range(rnd.randint(6, 12))).capitalize()
        creators = [f"{rnd.choice(['Adeyemi','Okafor','Bello','Eze','Ogunleye','Musa','Nwosu','Ibrahim'])}, "
                    f"{rnd.choice('ABCDEFGIKOS')}. {rnd.choice('ABCDEFGIKOS')}."]
        subjects = rnd.sample(WORDS, 4)
        abstract = " ".join(rnd.choice(WORDS) for _ in range(rnd.randint(120, 250)))
        item = {"title": title, "creators": creators, "advisor": "Supervisor, A. B.",
                "date_issued": str(rnd.randint(1985, 2026)), "item_type": rnd.choice(quality.ITEM_TYPES[:4]),
                "subjects": subjects, "abstract": abstract, "publisher": quality.CANONICAL_THESIS_PUBLISHER,
                "language": "en", "faculty": rnd.choice(quality.FACULTIES), "rights": "open"}
        c.execute("INSERT INTO items(title,creators,advisor,date_issued,item_type,subjects,abstract,publisher,"
                  "language,faculty,rights,origin,status,quality_score) VALUES (?,?,?,?,?,?,?,?,?,?,?,'demo','published',?)",
                  (item["title"], json.dumps(creators), item["advisor"], item["date_issued"], item["item_type"],
                   json.dumps(subjects), abstract, item["publisher"], "en", item["faculty"], "open",
                   quality.check(item)["overall"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", type=int, default=0)
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.reset and os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
    db.init_db()
    with db.get_conn() as c:
        for email, name, role in USERS:
            if not c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                c.execute("INSERT INTO users(email,full_name,role,password_hash) VALUES (?,?,?,?)",
                          (email, name, role, hash_password(PASSWORD)))
        n = load_unilag(c)
        if a.demo:
            load_demo(c, a.demo)
        total = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    print(f"Loaded {n} UNILAG records; {a.demo} demo records; {total} items in database")


if __name__ == "__main__":
    main()
