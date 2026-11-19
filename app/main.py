"""SmartIR: Smart Institutional Repository prototype.

Run:  uvicorn app.main:app --reload
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from collections import Counter

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import citation, db, dedup, oai, quality

BASE = os.path.dirname(__file__)
UPLOAD_DIR = os.environ.get("SMARTIR_UPLOADS", os.path.join(BASE, "..", "data", "files"))
MAX_UPLOAD = 25 * 1024 * 1024
PAGE = 10

os.makedirs(UPLOAD_DIR, exist_ok=True)
db.init_db()

app = FastAPI(title="SmartIR", version="1.0")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SMARTIR_SECRET", secrets.token_hex(32)),
                   same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))


# ------------------------------------------------------------------ helpers
def hash_password(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${h}"


def verify_password(pw, stored):
    salt, h = stored.split("$", 1)
    return hmac.compare_digest(hash_password(pw, salt).split("$", 1)[1], h)


def current_user(request):
    uid = request.session.get("uid")
    if not uid:
        return None
    with db.get_conn() as c:
        r = c.execute("SELECT id,email,full_name,role FROM users WHERE id=?", (uid,)).fetchone()
    return dict(r) if r else None


def require(request, *roles):
    u = current_user(request)
    if not u:
        raise HTTPException(status_code=303, headers={"Location": f"/login?next={request.url.path}"})
    if roles and u["role"] not in roles and u["role"] != "admin":
        raise HTTPException(status_code=403, detail="You do not have permission for this page")
    return u


def render(request, name, status_code=200, **ctx):
    ctx.update(request=request, user=current_user(request))
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def log_event(c, item_id, kind, detail=""):
    c.execute("INSERT INTO events(item_id,kind,detail) VALUES (?,?,?)", (item_id, kind, detail))


def audit(c, item_id, user_id, action, note=""):
    c.execute("INSERT INTO audit_log(item_id,user_id,action,note) VALUES (?,?,?,?)",
              (item_id, user_id, action, note))


def get_item(c, item_id):
    return db.row_to_item(c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone())


def published(c):
    return [db.row_to_item(r) for r in c.execute("SELECT * FROM items WHERE status='published'")]


def vocabulary(c):
    terms = set()
    for r in c.execute("SELECT subjects FROM items WHERE status='published'"):
        terms.update(json.loads(r[0] or "[]"))
    return sorted(terms)


def fts_any(terms):
    words = []
    for t in terms:
        words += re.findall(r"[\w']{3,}", t or "")
    words = [w for w in dict.fromkeys(w.lower() for w in words) if w not in dedup.STOP][:20]
    return " OR ".join(f'"{w}"' for w in words)


def dup_candidates(c, item, exclude_id=None, limit=40):
    """Pre-select likely duplicates with the full-text index, then compare with difflib."""
    q = fts_any([item.get("title", "")])
    if not q:
        return []
    rows = c.execute("SELECT i.* FROM items_fts f JOIN items i ON i.id=f.rowid WHERE items_fts MATCH ? "
                     "AND i.status!='withdrawn' ORDER BY bm25(items_fts, 10.0, 1.0, 1.0, 0.1, 0.0, 0.0, 0.0) LIMIT ?",
                     ("title : (" + q + ")", limit)).fetchall()
    return dedup.find_duplicates(item, [db.row_to_item(r) for r in rows], exclude_id=exclude_id)


def related_items(c, it, limit=5):
    q = fts_any(it["subjects"])
    if not q:
        return []
    rows = c.execute("SELECT i.* FROM items_fts f JOIN items i ON i.id=f.rowid WHERE items_fts MATCH ? "
                     "AND i.status='published' AND i.id!=? ORDER BY bm25(items_fts) LIMIT 60",
                     ("subjects : (" + q + ")", it["id"])).fetchall()
    scored = []
    mine = {s.lower() for s in it["subjects"]}
    for r in rows:
        r = db.row_to_item(r)
        shared = {s.lower() for s in r["subjects"]} & mine
        score = 2 * len(shared) + (1 if r["faculty"] == it["faculty"] else 0)
        scored.append((score, r))
    return [r for _, r in sorted(scored, key=lambda x: -x[0])[:limit]]


def parse_list(text):
    return [x.strip() for x in re.split(r"[;\n]", text or "") if x.strip()]


def form_item(title, creators, advisor, date_issued, item_type, subjects, abstract,
              publisher, language, faculty, department, rights, embargo_until):
    return {
        "title": title.strip(), "creators": parse_list(creators), "advisor": advisor.strip(),
        "date_issued": date_issued.strip(), "item_type": item_type, "subjects": parse_list(subjects),
        "abstract": abstract.strip(), "publisher": publisher.strip(), "language": language,
        "faculty": faculty, "department": department.strip(), "rights": rights,
        "embargo_until": embargo_until.strip(),
    }


def fts_query(q):
    """Turn free text into a safe FTS5 query (prefix match on each term)."""
    terms = re.findall(r"[\w']+", q or "")
    return " ".join(f'"{t}"*' for t in terms[:12])


# ------------------------------------------------------------------ errors
@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if exc.status_code == 303:
        return RedirectResponse(exc.headers["Location"], status_code=303)
    return render(request, "error.html", status_code=exc.status_code, code=exc.status_code, message=exc.detail)


# ------------------------------------------------------------------ public pages
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with db.get_conn() as c:
        total = c.execute("SELECT COUNT(*) FROM items WHERE status='published'").fetchone()[0]
        by_type = c.execute("SELECT item_type,COUNT(*) n FROM items WHERE status='published' "
                            "GROUP BY item_type ORDER BY n DESC").fetchall()
        faculties = c.execute("SELECT faculty,COUNT(*) n FROM items WHERE status='published' "
                              "GROUP BY faculty ORDER BY faculty").fetchall()
        recent = [db.row_to_item(r) for r in c.execute(
            "SELECT * FROM items WHERE status='published' ORDER BY id DESC LIMIT 6")]
    return render(request, "home.html", total=total, by_type=by_type, faculties=faculties, recent=recent)


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", faculty: str = "", type: str = "", year_from: str = "",
           year_to: str = "", rights: str = "", sort: str = "relevance", page: int = 1):
    where, params = ["i.status='published'"], []
    if faculty:
        where.append("i.faculty=?"); params.append(faculty)
    if type:
        where.append("i.item_type=?"); params.append(type)
    if rights:
        where.append("i.rights=?"); params.append(rights)
    if year_from.isdigit():
        where.append("substr(i.date_issued,1,4)>=?"); params.append(year_from)
    if year_to.isdigit():
        where.append("substr(i.date_issued,1,4)<=?"); params.append(year_to)
    fq = fts_query(q)
    with db.get_conn() as c:
        if fq:
            base = ("FROM items_fts f JOIN items i ON i.id=f.rowid WHERE items_fts MATCH ? AND "
                    + " AND ".join(where))
            bparams = [fq] + params
            order = "bm25(items_fts, 10.0, 5.0, 4.0, 2.0, 1.0, 1.0, 1.0)" if sort == "relevance" else None
            sel = ("SELECT i.*, snippet(items_fts, -1, '<mark>', '</mark>', ' ... ', 18) AS snip ")
        else:
            base = "FROM items i WHERE " + " AND ".join(where)
            bparams = params
            order = None
            sel = "SELECT i.*, '' AS snip "
        if sort == "newest":
            order = "i.date_issued DESC"
        elif sort == "oldest":
            order = "i.date_issued ASC"
        elif sort == "title":
            order = "i.title COLLATE NOCASE ASC"
        order = order or "i.id DESC"
        total = c.execute("SELECT COUNT(*) " + base, bparams).fetchone()[0]
        rows = c.execute(f"{sel}{base} ORDER BY {order} LIMIT ? OFFSET ?",
                         bparams + [PAGE, (max(page, 1) - 1) * PAGE]).fetchall()
        results = []
        for r in rows:
            it = db.row_to_item(r)
            it["snip"] = r["snip"]
            results.append(it)
        facet_rows = c.execute("SELECT i.faculty, i.item_type, i.rights, substr(i.date_issued,1,4) y " + base,
                               bparams).fetchall()
        if q.strip():
            log_event(c, None, "search", q.strip()[:200])
    facets = {
        "faculty": Counter(r["faculty"] for r in facet_rows if r["faculty"]).most_common(),
        "type": Counter(r["item_type"] for r in facet_rows if r["item_type"]).most_common(),
        "rights": Counter(r["rights"] for r in facet_rows if r["rights"]).most_common(),
        "decade": sorted(Counter((r["y"][:3] + "0s") for r in facet_rows if r["y"]).items()),
    }
    pages = (total + PAGE - 1) // PAGE
    return render(request, "search.html", q=q, results=results, total=total, facets=facets,
                  f=dict(faculty=faculty, type=type, year_from=year_from, year_to=year_to,
                         rights=rights, sort=sort), page=page, pages=pages)


@app.get("/items/{item_id}", response_class=HTMLResponse)
def item_page(request: Request, item_id: int):
    u = current_user(request)
    with db.get_conn() as c:
        it = get_item(c, item_id)
        if not it:
            raise HTTPException(404, "Item not found")
        can_see = it["status"] == "published" or (u and (u["role"] in ("librarian", "admin")
                                                         or u["id"] == it["submitted_by"]))
        if not can_see:
            raise HTTPException(404, "Item not found")
        files = c.execute("SELECT * FROM files WHERE item_id=?", (item_id,)).fetchall()
        if it["status"] == "published":
            log_event(c, item_id, "view")
        views = c.execute("SELECT COUNT(*) FROM events WHERE item_id=? AND kind='view'", (item_id,)).fetchone()[0]
        downloads = c.execute("SELECT COUNT(*) FROM events WHERE item_id=? AND kind='download'",
                              (item_id,)).fetchone()[0]
        related = related_items(c, it)
    base = str(request.base_url).rstrip("/")
    q = quality.check(it)
    return render(request, "item.html", it=it, files=files, views=views, downloads=downloads,
                  related=related, apa=citation.apa(it, base), q=q)


@app.get("/items/{item_id}/files/{file_id}")
def download(item_id: int, file_id: int):
    with db.get_conn() as c:
        it = get_item(c, item_id)
        f = c.execute("SELECT * FROM files WHERE id=? AND item_id=?", (file_id, item_id)).fetchone()
        if not it or not f or it["status"] != "published":
            raise HTTPException(404, "File not found")
        if it["rights"] != "open":
            raise HTTPException(403, "This file is under embargo or restricted access")
        log_event(c, item_id, "download", f["filename"])
    path = os.path.join(UPLOAD_DIR, f["stored_name"] or "")
    if f["stored_name"] and os.path.exists(path):
        return FileResponse(path, filename=f["filename"], media_type=f["mime"])
    if it.get("source_url"):
        return RedirectResponse(it["source_url"], status_code=302)
    raise HTTPException(404, "File not stored in this prototype")


@app.get("/items/{item_id}/cite.bib")
def cite_bib(request: Request, item_id: int):
    with db.get_conn() as c:
        it = get_item(c, item_id)
    if not it or it["status"] != "published":
        raise HTTPException(404, "Item not found")
    return PlainTextResponse(citation.bibtex(it, str(request.base_url).rstrip("/")),
                             headers={"Content-Disposition": f"attachment; filename=item{item_id}.bib"})


@app.get("/api/items/{item_id}")
def api_item(item_id: int):
    with db.get_conn() as c:
        it = get_item(c, item_id)
    if not it or it["status"] != "published":
        return JSONResponse({"error": "not found"}, status_code=404)
    it.pop("fulltext", None)
    return it


# ------------------------------------------------------------------ auth
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = "/"):
    return render(request, "login.html", next=next, error="")


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("/")):
    with db.get_conn() as c:
        r = c.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    if not r or not verify_password(password, r["password_hash"]):
        return render(request, "login.html", next=next, error="Incorrect email or password")
    request.session["uid"] = r["id"]
    if not next.startswith("/") or next.startswith("//"):
        next = "/"
    return RedirectResponse(next, status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


# ------------------------------------------------------------------ submission
def submit_ctx(c):
    return dict(types=quality.ITEM_TYPES, faculties=quality.FACULTIES, languages=quality.LANGUAGES)


@app.get("/submit", response_class=HTMLResponse)
def submit_form(request: Request):
    require(request, "depositor", "librarian")
    with db.get_conn() as c:
        ctx = submit_ctx(c)
    return render(request, "submit.html", it=None, **ctx)


@app.post("/api/check")
async def api_check(request: Request):
    """Live metadata check used by the submission form."""
    require(request, "depositor", "librarian")
    data = await request.json()
    cand = form_item(**{k: str(data.get(k, "")) for k in (
        "title", "creators", "advisor", "date_issued", "item_type", "subjects", "abstract",
        "publisher", "language", "faculty", "department", "rights", "embargo_until")})
    exclude = int(data["item_id"]) if str(data.get("item_id", "")).isdigit() else None
    with db.get_conn() as c:
        dups = dup_candidates(c, cand, exclude_id=exclude)[:5] if cand["title"] else []
        vocab = vocabulary(c)
    return {
        "quality": quality.check(cand),
        "duplicates": dups,
        "suggested_subjects": [s for s in quality.suggest_subjects(cand["title"], cand["abstract"], vocab)
                               if s.lower() not in {x.lower() for x in cand["subjects"]}],
        "normalised_authors": [quality.normalise_author(a) for a in cand["creators"]],
    }


async def save_upload(c, item_id, upload):
    if not upload or not upload.filename:
        return None
    if not upload.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")
    data = await upload.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(400, "File is larger than 25 MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "The file is not a valid PDF")
    stored = f"{uuid.uuid4().hex}.pdf"
    with open(os.path.join(UPLOAD_DIR, stored), "wb") as fh:
        fh.write(data)
    c.execute("INSERT INTO files(item_id,filename,stored_name,size_bytes) VALUES (?,?,?,?)",
              (item_id, os.path.basename(upload.filename), stored, len(data)))
    text = ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(os.path.join(UPLOAD_DIR, stored))
        text = " ".join((p.extract_text() or "") for p in reader.pages[:60])
    except Exception:
        text = ""
    if text:
        c.execute("UPDATE items SET fulltext=? WHERE id=?", (text[:500_000], item_id))
    return stored


@app.post("/submit", response_class=HTMLResponse)
async def submit(request: Request, title: str = Form(...), creators: str = Form(...), advisor: str = Form(""),
                 date_issued: str = Form(""), item_type: str = Form(""), subjects: str = Form(""),
                 abstract: str = Form(""), publisher: str = Form(""), language: str = Form("en"),
                 faculty: str = Form(""), department: str = Form(""), rights: str = Form("open"),
                 embargo_until: str = Form(""), file: UploadFile = File(None)):
    u = require(request, "depositor", "librarian")
    it = form_item(title, creators, advisor, date_issued, item_type, subjects, abstract, publisher,
                   language, faculty, department, rights, embargo_until)
    q = quality.check(it)
    with db.get_conn() as c:
        if not it["title"] or not it["creators"]:
            return render(request, "submit.html", it=it, error="Title and at least one author are required",
                          **submit_ctx(c))
        if q["errors"]:
            return render(request, "submit.html", it=it, q=q,
                          error="Please correct the errors marked in red before submitting", **submit_ctx(c))
        cur = c.execute(
            "INSERT INTO items(title,creators,advisor,date_issued,item_type,subjects,abstract,publisher,"
            "language,faculty,department,rights,embargo_until,status,submitted_by,quality_score,origin) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'submitted',?,?,'local')",
            (it["title"], json.dumps(it["creators"]), it["advisor"], it["date_issued"], it["item_type"],
             json.dumps(it["subjects"]), it["abstract"], it["publisher"], it["language"], it["faculty"],
             it["department"], it["rights"], it["embargo_until"], u["id"], q["overall"]))
        item_id = cur.lastrowid
        c.execute("UPDATE items SET handle=? WHERE id=?", (f"smartir/{item_id}", item_id))
        await save_upload(c, item_id, file)
        audit(c, item_id, u["id"], "submitted", f"quality {q['overall']}")
        dups = dup_candidates(c, it, exclude_id=item_id)
    return render(request, "submit_done.html", item_id=item_id, q=q, dups=dups)


@app.get("/my", response_class=HTMLResponse)
def my_items(request: Request):
    u = require(request, "depositor", "librarian")
    with db.get_conn() as c:
        rows = [db.row_to_item(r) for r in c.execute(
            "SELECT * FROM items WHERE submitted_by=? ORDER BY id DESC", (u["id"],))]
    return render(request, "my.html", items=rows)


@app.get("/items/{item_id}/edit", response_class=HTMLResponse)
def edit_form(request: Request, item_id: int):
    u = require(request, "depositor", "librarian")
    with db.get_conn() as c:
        it = get_item(c, item_id)
        if not it:
            raise HTTPException(404, "Item not found")
        if u["role"] == "depositor" and (it["submitted_by"] != u["id"] or it["status"] != "returned"):
            raise HTTPException(403, "Only returned submissions can be edited by the depositor")
        return render(request, "submit.html", it=it, q=quality.check(it), edit=True, **submit_ctx(c))


@app.post("/items/{item_id}/edit", response_class=HTMLResponse)
async def edit(request: Request, item_id: int, title: str = Form(...), creators: str = Form(...),
               advisor: str = Form(""), date_issued: str = Form(""), item_type: str = Form(""),
               subjects: str = Form(""), abstract: str = Form(""), publisher: str = Form(""),
               language: str = Form("en"), faculty: str = Form(""), department: str = Form(""),
               rights: str = Form("open"), embargo_until: str = Form(""), file: UploadFile = File(None)):
    u = require(request, "depositor", "librarian")
    new = form_item(title, creators, advisor, date_issued, item_type, subjects, abstract, publisher,
                    language, faculty, department, rights, embargo_until)
    q = quality.check(new)
    with db.get_conn() as c:
        it = get_item(c, item_id)
        if not it:
            raise HTTPException(404, "Item not found")
        if u["role"] == "depositor" and (it["submitted_by"] != u["id"] or it["status"] != "returned"):
            raise HTTPException(403, "Only returned submissions can be edited by the depositor")
        if q["errors"]:
            return render(request, "submit.html", it={**new, "id": item_id}, q=q, edit=True,
                          error="Please correct the errors marked in red", **submit_ctx(c))
        status = "submitted" if u["role"] == "depositor" else it["status"]
        c.execute("UPDATE items SET title=?,creators=?,advisor=?,date_issued=?,item_type=?,subjects=?,"
                  "abstract=?,publisher=?,language=?,faculty=?,department=?,rights=?,embargo_until=?,"
                  "quality_score=?,status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                  (new["title"], json.dumps(new["creators"]), new["advisor"], new["date_issued"],
                   new["item_type"], json.dumps(new["subjects"]), new["abstract"], new["publisher"],
                   new["language"], new["faculty"], new["department"], new["rights"], new["embargo_until"],
                   q["overall"], status, item_id))
        await save_upload(c, item_id, file)
        audit(c, item_id, u["id"], "edited", f"quality {q['overall']}")
    return RedirectResponse(f"/review/{item_id}" if u["role"] != "depositor" else "/my", status_code=303)


# ------------------------------------------------------------------ librarian review
@app.get("/review", response_class=HTMLResponse)
def review_queue(request: Request):
    require(request, "librarian")
    with db.get_conn() as c:
        queue = [db.row_to_item(r) for r in c.execute(
            "SELECT * FROM items WHERE status='submitted' ORDER BY id")]
        for it in queue:
            it["q"] = quality.check(it)
            it["dups"] = dup_candidates(c, it, exclude_id=it["id"])
        returned = c.execute("SELECT COUNT(*) FROM items WHERE status='returned'").fetchone()[0]
    return render(request, "review_list.html", queue=queue, returned=returned)


@app.get("/review/{item_id}", response_class=HTMLResponse)
def review_item(request: Request, item_id: int):
    require(request, "librarian")
    with db.get_conn() as c:
        it = get_item(c, item_id)
        if not it:
            raise HTTPException(404, "Item not found")
        dups = dup_candidates(c, it, exclude_id=item_id)
        files = c.execute("SELECT * FROM files WHERE item_id=?", (item_id,)).fetchall()
        history = c.execute("SELECT a.*, u.full_name FROM audit_log a LEFT JOIN users u ON u.id=a.user_id "
                            "WHERE item_id=? ORDER BY a.id", (item_id,)).fetchall()
        vocab = vocabulary(c)
    sugg = [s for s in quality.suggest_subjects(it["title"], it["abstract"], vocab)
            if s.lower() not in {x.lower() for x in it["subjects"]}]
    return render(request, "review_item.html", it=it, q=quality.check(it), dups=dups, files=files,
                  history=history, suggested=sugg,
                  normalised=[quality.normalise_author(a) for a in it["creators"]])


@app.post("/review/{item_id}")
def review_action(request: Request, item_id: int, action: str = Form(...), note: str = Form("")):
    u = require(request, "librarian")
    with db.get_conn() as c:
        it = get_item(c, item_id)
        if not it:
            raise HTTPException(404, "Item not found")
        if action == "approve":
            q = quality.check(it)
            if q["errors"]:
                raise HTTPException(400, "Item still has metadata errors; edit it before approving")
            c.execute("UPDATE items SET status='published', reviewed_by=?, review_note=?, quality_score=?, "
                      "updated_at=CURRENT_TIMESTAMP WHERE id=?", (u["id"], note, q["overall"], item_id))
        elif action == "return":
            if not note.strip():
                raise HTTPException(400, "A note to the depositor is required when returning an item")
            c.execute("UPDATE items SET status='returned', reviewed_by=?, review_note=?, "
                      "updated_at=CURRENT_TIMESTAMP WHERE id=?", (u["id"], note, item_id))
        elif action == "withdraw":
            c.execute("UPDATE items SET status='withdrawn', reviewed_by=?, review_note=?, "
                      "updated_at=CURRENT_TIMESTAMP WHERE id=?", (u["id"], note, item_id))
        elif action == "normalise":
            creators = [quality.normalise_author(a) for a in it["creators"]]
            title = re.sub(r",(\S)", r", \1", it["title"]).rstrip(" .,;:")
            pub = it["publisher"]
            if it["item_type"] in {"Thesis", "Dissertation"}:
                pub = quality.CANONICAL_THESIS_PUBLISHER
            fac = {"Faculty of Art": "Faculty of Arts", "Faculty of Social Science": "Faculty of Social Sciences"}
            faculty = fac.get(it["faculty"], it["faculty"])
            new = {**it, "creators": creators, "title": title, "publisher": pub, "faculty": faculty}
            c.execute("UPDATE items SET creators=?, title=?, publisher=?, faculty=?, quality_score=?, "
                      "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                      (json.dumps(creators), title, pub, faculty, quality.check(new)["overall"], item_id))
        elif action == "add_subjects":
            vocab = vocabulary(c)
            add = quality.suggest_subjects(it["title"], it["abstract"], vocab)
            subjects = it["subjects"] + [s for s in add if s.lower() not in {x.lower() for x in it["subjects"]}]
            new = {**it, "subjects": subjects}
            c.execute("UPDATE items SET subjects=?, quality_score=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                      (json.dumps(subjects), quality.check(new)["overall"], item_id))
        else:
            raise HTTPException(400, "Unknown action")
        audit(c, item_id, u["id"], action, note)
    dest = "/review" if action in ("approve", "return", "withdraw") else f"/review/{item_id}"
    return RedirectResponse(dest, status_code=303)


# ------------------------------------------------------------------ quality audit
@app.get("/quality", response_class=HTMLResponse)
def quality_audit(request: Request, origin: str = ""):
    require(request, "librarian")
    with db.get_conn() as c:
        sql = "SELECT * FROM items WHERE status='published'"
        params = []
        if origin:
            sql += " AND origin=?"; params.append(origin)
        items = [db.row_to_item(r) for r in c.execute(sql, params)]
    rows, issue_counter, field_missing = [], Counter(), Counter()
    for it in items:
        q = quality.check(it)
        rows.append((it, q))
        for i in q["issues"]:
            key = re.sub(r"'[^']*'", "'...'", i["message"])
            issue_counter[(i["field"], key)] += 1
            if i["message"].startswith("Missing") or "placeholder" in i["message"]:
                field_missing[i["field"]] += 1
    n = len(rows) or 1
    summary = {
        "n": len(rows),
        "completeness": round(sum(q["completeness"] for _, q in rows) / n, 1),
        "conformance": round(sum(q["conformance"] for _, q in rows) / n, 1),
        "overall": round(sum(q["overall"] for _, q in rows) / n, 1),
        "grades": Counter(q["grade"] for _, q in rows),
    }
    pairs = dedup.duplicate_report(items)
    rows.sort(key=lambda x: x[1]["overall"])
    return render(request, "quality.html", rows=rows[:200], summary=summary,
                  issues=issue_counter.most_common(15), missing=field_missing.most_common(),
                  pairs=pairs, origin=origin)


# ------------------------------------------------------------------ analytics
@app.get("/analytics", response_class=HTMLResponse)
def analytics(request: Request):
    require(request, "librarian")
    with db.get_conn() as c:
        one = lambda sql, *p: c.execute(sql, p).fetchone()[0]
        stats = {
            "published": one("SELECT COUNT(*) FROM items WHERE status='published'"),
            "pending": one("SELECT COUNT(*) FROM items WHERE status='submitted'"),
            "returned": one("SELECT COUNT(*) FROM items WHERE status='returned'"),
            "views": one("SELECT COUNT(*) FROM events WHERE kind='view'"),
            "downloads": one("SELECT COUNT(*) FROM events WHERE kind='download'"),
            "searches": one("SELECT COUNT(*) FROM events WHERE kind='search'"),
            "harvests": one("SELECT COUNT(*) FROM events WHERE kind='harvest'"),
            "avg_quality": one("SELECT ROUND(AVG(quality_score),1) FROM items WHERE status='published'") or 0,
        }
        by_faculty = c.execute("SELECT faculty, COUNT(*) n FROM items WHERE status='published' "
                               "GROUP BY faculty ORDER BY n DESC").fetchall()
        by_type = c.execute("SELECT item_type, COUNT(*) n FROM items WHERE status='published' "
                            "GROUP BY item_type ORDER BY n DESC").fetchall()
        by_decade = c.execute("SELECT substr(date_issued,1,3)||'0s' d, COUNT(*) n FROM items "
                              "WHERE status='published' AND date_issued!='' GROUP BY d ORDER BY d").fetchall()
        top = c.execute("SELECT i.id, i.title, SUM(e.kind='view') v, SUM(e.kind='download') dl "
                        "FROM events e JOIN items i ON i.id=e.item_id GROUP BY i.id "
                        "ORDER BY v DESC, dl DESC LIMIT 10").fetchall()
        queries = c.execute("SELECT lower(detail) q, COUNT(*) n FROM events WHERE kind='search' "
                            "GROUP BY q ORDER BY n DESC LIMIT 10").fetchall()
        zero = []
        for r in queries:
            fq = fts_query(r["q"])
            if fq and c.execute("SELECT COUNT(*) FROM items_fts f JOIN items i ON i.id=f.rowid "
                                "WHERE items_fts MATCH ? AND i.status='published'", (fq,)).fetchone()[0] == 0:
                zero.append(r["q"])
    return render(request, "analytics.html", stats=stats, by_faculty=by_faculty, by_type=by_type,
                  by_decade=by_decade, top=top, queries=queries, zero=zero)


# ------------------------------------------------------------------ OAI-PMH
def _oai_items(params, offset=0, limit=50):
    sql, p = " FROM items WHERE status='published'", []
    if params.get("from"):
        sql += " AND replace(updated_at,' ','T')>=?"; p.append(params["from"].replace("Z", ""))
    if params.get("until"):
        u = params["until"].replace("Z", "")
        sql += " AND replace(updated_at,' ','T')<=?"; p.append(u if "T" in u else u + "T23:59:59")
    s = params.get("set", "")
    with db.get_conn() as c:
        if s.startswith(("fac_", "type_")):
            col = "faculty" if s.startswith("fac_") else "item_type"
            names = [n for (n,) in c.execute(f"SELECT DISTINCT {col}" + sql, p) if n and
                     ("fac_" if col == "faculty" else "type_") + oai.slug(n) == s]
            if not names:
                return [], 0
            sql += f" AND {col} IN ({','.join('?' * len(names))})"; p += names
        elif s:
            return [], 0
        total = c.execute("SELECT COUNT(*)" + sql, p).fetchone()[0]
        rows = c.execute("SELECT *" + sql + " ORDER BY id LIMIT ? OFFSET ?", p + [limit, offset]).fetchall()
    return [db.row_to_item(r) for r in rows], total


def _oai_item(item_id):
    with db.get_conn() as c:
        it = get_item(c, item_id)
    return it if it and it["status"] == "published" else None


def _oai_sets():
    with db.get_conn() as c:
        facs = [r[0] for r in c.execute("SELECT DISTINCT faculty FROM items WHERE status='published' AND faculty!=''")]
        types = [r[0] for r in c.execute("SELECT DISTINCT item_type FROM items WHERE status='published' AND item_type!=''")]
    return sorted([("fac_" + oai.slug(f), f) for f in facs]) + sorted([("type_" + oai.slug(t), t) for t in types])


@app.get("/oai")
def oai_endpoint(request: Request):
    args = dict(request.query_params)
    base = str(request.base_url).rstrip("/") + "/oai"
    xml = oai.handle(args, base, _oai_items, _oai_item, _oai_sets)
    if args.get("verb") in ("ListRecords", "GetRecord") and "<error" not in xml:
        with db.get_conn() as c:
            log_event(c, None, "harvest", args.get("verb"))
    return Response(xml, media_type="text/xml; charset=utf-8")


@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    return render(request, "about.html")


@app.get("/health")
def health():
    with db.get_conn() as c:
        n = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    return {"status": "ok", "items": n}
