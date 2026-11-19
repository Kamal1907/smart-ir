"""Functional test cases. Each test docstring holds: line 1 the test case, line 2 the expected result.
The `req` attribute maps each case to a functional requirement in Chapter Four."""
import io
import os
import re

import pytest
import xmlschema
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app.main import app
from app import quality, dedup

HERE = os.path.dirname(__file__)
OAI_XSD = xmlschema.XMLSchema(os.path.join(HERE, "schemas", "OAI-PMH.xsd"))
DC_XSD = xmlschema.XMLSchema(os.path.join(HERE, "schemas", "oai_dc.xsd"))
PW = "Demo@2026"


def req(code):
    def deco(f):
        f.req = code
        return f
    return deco


def client(role=None):
    c = TestClient(app)
    if role:
        r = c.post("/login", data={"email": f"{role}@demo.edu.ng", "password": PW, "next": "/"},
                   follow_redirects=False)
        assert r.status_code == 303
    return c


def good_item(**over):
    d = dict(title="Adoption of Open Access Repositories by Academic Librarians in Lagos State",
             creators="Adewale, T. O.", advisor="Okoro, C. N.", date_issued="2025-06",
             item_type="Thesis", subjects="Institutional repositories; Open access; Academic libraries",
             abstract=("This study examined the adoption of open access institutional repositories by academic "
                       "librarians in universities in Lagos State and identified factors that affect deposit."),
             publisher=quality.CANONICAL_THESIS_PUBLISHER, language="en", faculty="Faculty of Education",
             department="Library and Information Science", rights="open", embargo_until="")
    d.update(over)
    return d


def make_pdf(text):
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.drawString(72, 720, text)
    pdf.save()
    return buf.getvalue()


def submit(c, **over):
    return c.post("/submit", data=good_item(**over), follow_redirects=False)


def last_id():
    from app import db
    with db.get_conn() as c:
        return c.execute("SELECT MAX(id) FROM items").fetchone()[0]


# ---------------------------------------------------------------- FR1 search and discovery
@req("FR1")
def test_tc01_keyword_search():
    """Keyword search for 'lungfish' returns the matching UNILAG thesis.
    The lungfish thesis is listed in the results."""
    r = client().get("/search", params={"q": "lungfish"})
    assert r.status_code == 200 and "African Lungfish" in r.text


@req("FR1")
def test_tc02_author_search():
    """Search by author surname 'Kemjika'.
    The 1989 Faculty of Education thesis by Kemjika is returned."""
    r = client().get("/search", params={"q": "Kemjika"})
    assert "Creativity Intelligence" in r.text


@req("FR1")
def test_tc03_faculty_facet():
    """Filter results by the faculty facet 'Faculty of Pharmacy'.
    Only the Faculty of Pharmacy item is shown (1 result)."""
    r = client().get("/search", params={"faculty": "Faculty of Pharmacy"})
    assert "1 result" in r.text and "Pharmacoeconomic" in r.text


@req("FR1")
def test_tc04_year_range():
    """Filter by year range 2014 to 2014.
    Only items issued in 2014 are returned (3 in the audit sample plus 1 in the extension batch = 4 results)."""
    r = client().get("/search", params={"year_from": "2014", "year_to": "2014"})
    assert "4 results" in r.text


@req("FR1")
def test_tc05_stemming():
    """Search for 'model' where the title only contains the word 'Modelling'.
    Porter stemming returns the traffic congestion thesis."""
    r = client().get("/search", params={"q": "model"})
    assert "Traffic Congestion" in r.text


@req("FR1")
def test_tc06_no_results():
    """Search for a nonsense term.
    The system reports no results without an error."""
    r = client().get("/search", params={"q": "zzqxwv"})
    assert r.status_code == 200 and "No items match" in r.text


@req("FR1")
def test_tc07_injection_safe():
    """Search with SQL and FTS control characters.
    The query is handled safely and the page loads (HTTP 200)."""
    r = client().get("/search", params={"q": '"); DROP TABLE items;-- NEAR( * AND OR'})
    assert r.status_code == 200
    assert client().get("/health").json()["items"] >= 15


@req("FR1")
def test_tc08_snippet_highlight():
    """Matched terms are highlighted in result snippets.
    The result contains a <mark> element around the search term."""
    r = client().get("/search", params={"q": "corruption"})
    assert "<mark>" in r.text


# ---------------------------------------------------------------- FR2 item display and citation
@req("FR2")
def test_tc09_item_dublin_core():
    """Open an item page.
    Dublin Core fields (dc.title, dc.creator, dc.date.issued, dc.subject) are displayed."""
    r = client().get("/items/1")
    for f in ("dc.title", "dc.creator", "dc.date.issued", "dc.subject"):
        assert f in r.text


@req("FR2")
def test_tc10_unpublished_hidden():
    """An anonymous user requests an item still under review.
    The system returns 404 so unreviewed work is not exposed."""
    c = client("depositor")
    submit(c, title="Hidden Work Awaiting Review on Repository Metadata Practice")
    r = client().get(f"/items/{last_id()}")
    assert r.status_code == 404


@req("FR2")
def test_tc11_citation_export():
    """Export a citation in APA and BibTeX.
    APA text appears on the item page and a valid @phdthesis BibTeX entry is downloaded."""
    c = client()
    assert "(2010)" in c.get("/items/1").text
    b = c.get("/items/1/cite.bib").text
    assert b.startswith("@phdthesis{") and "school = {University of Lagos}" in b


@req("FR2")
def test_tc12_related_items():
    """The item page lists related items using shared subjects and faculty.
    At least one related item is shown for a Faculty of Arts thesis."""
    r = client().get("/items/1")
    assert "Related items" in r.text and "Kierkegaard" in r.text


# ---------------------------------------------------------------- FR3 authentication and roles
@req("FR3")
def test_tc13_login_valid():
    """Log in with valid librarian credentials.
    The user is redirected and the review queue is accessible."""
    assert client("librarian").get("/review").status_code == 200


@req("FR3")
def test_tc14_login_invalid():
    """Log in with a wrong password.
    Access is refused with an error message."""
    r = client().post("/login", data={"email": "librarian@demo.edu.ng", "password": "wrong"})
    assert "Incorrect email or password" in r.text


@req("FR3")
def test_tc15_role_enforcement():
    """A depositor tries to open the librarian review queue.
    Access is denied (HTTP 403)."""
    assert client("depositor").get("/review").status_code == 403


@req("FR3")
def test_tc16_login_required():
    """An anonymous user opens the submission form.
    The user is redirected to the login page."""
    r = client().get("/submit", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


@req("FR3")
def test_tc17_open_redirect_blocked():
    """Log in with an external 'next' address.
    The user is sent to the home page, not the external site."""
    r = TestClient(app).post("/login", data={"email": "depositor@demo.edu.ng", "password": PW,
                                             "next": "//evil.example.com"}, follow_redirects=False)
    assert r.headers["location"] == "/"


# ---------------------------------------------------------------- FR4 submission
@req("FR4")
def test_tc18_valid_submission():
    """A depositor submits a complete thesis record.
    The item is saved with status 'submitted' and a quality score."""
    c = client("depositor")
    r = submit(c)
    assert "Submission received" in r.text
    assert "submitted" in c.get("/my").text


@req("FR4")
def test_tc19_invalid_date_blocked():
    """Submit a record with the date '16/11/2026'.
    Submission is blocked and the ISO 8601 error is shown."""
    r = submit(client("depositor"), date_issued="16/11/2026")
    assert "ISO 8601" in r.text and "Submission received" not in r.text


@req("FR4")
def test_tc20_non_pdf_rejected():
    """Upload a .docx file as the full text.
    The file is rejected with the message 'Only PDF files are accepted'."""
    c = client("depositor")
    r = c.post("/submit", data=good_item(title="File Type Test Record for Upload Validation"),
               files={"file": ("thesis.docx", b"PK\x03\x04fake", "application/octet-stream")})
    assert "Only PDF files are accepted" in r.text


@req("FR4")
def test_tc21_pdf_fulltext_indexed():
    """Upload a PDF containing the word 'mangroveflux' and publish it.
    The item is found by full-text search for a word that appears only inside the PDF."""
    c = client("depositor")
    c.post("/submit", data=good_item(title="Full Text Indexing Test of Coastal Wetland Records"),
           files={"file": ("test.pdf", make_pdf("Field notes on mangroveflux in Lagos lagoon"), "application/pdf")})
    lib = client("librarian")
    lib.post(f"/review/{last_id()}", data={"action": "approve", "note": ""})
    assert "Coastal Wetland" in client().get("/search", params={"q": "mangroveflux"}).text


# ---------------------------------------------------------------- FR5 metadata quality
@req("FR5")
def test_tc22_placeholder_abstract():
    """Check a UNILAG record whose abstract reads 'Full text attached'.
    The engine flags the abstract as a placeholder."""
    it = {"title": "X", "creators": ["Isola, W. A."], "abstract": "Full text attached.", "item_type": "Thesis"}
    msgs = [i["message"] for i in quality.check(it)["issues"]]
    assert any("placeholder" in m for m in msgs)


@req("FR5")
def test_tc23_author_normalisation():
    """Normalise the author form 'Okafor, A.I' found in UNILAG records.
    The suggested form is 'Okafor, A. I.'."""
    assert quality.normalise_author("Okafor, A.I") == "Okafor, A. I."


@req("FR5")
def test_tc24_live_check_api():
    """Send draft metadata to the live check service.
    A score, a grade and a list of issues are returned."""
    r = client("depositor").post("/api/check", json=good_item(abstract="", subjects="One"))
    j = r.json()
    assert r.status_code == 200 and "overall" in j["quality"] and len(j["quality"]["issues"]) >= 2


@req("FR5")
def test_tc25_subject_suggestion():
    """Draft a record about 'Judicial Corruption' without subjects.
    The existing vocabulary term 'Judicial Corruption' is suggested."""
    r = client("depositor").post("/api/check", json=good_item(
        title="Judicial Corruption and Public Trust in Lagos Courts", subjects=""))
    assert "Judicial Corruption" in r.json()["suggested_subjects"]


# ---------------------------------------------------------------- FR6 duplicate detection
@req("FR6")
def test_tc26_real_duplicate_detected():
    """Run the duplicate report over the loaded UNILAG records.
    The two 'Cement Dust' records deposited separately in the live repository are flagged."""
    r = client("librarian").get("/quality")
    assert "Cement Dust" in r.text.split("Possible duplicates")[1].split("Records by score")[0]


@req("FR6")
def test_tc27_distinct_not_flagged():
    """Compare two different theses from the same faculty.
    They are not flagged as duplicates."""
    a = {"title": "Social Protest and Literary Imagination in Selected Nigerian Novels",
         "creators": ["Oniyide, A.K"], "date_issued": "2010"}
    b = {"title": "Commitment in Soren Aabye Kierkegaard's Philosophy: Implication for Leadership",
         "creators": ["Obaweki, J.O"], "date_issued": "2012"}
    assert dedup.is_duplicate(a, b)[0] is False


@req("FR6")
def test_tc28_duplicate_warning_on_submit():
    """A depositor drafts a record with a near-identical title to an existing thesis.
    The live check returns the existing item as a possible duplicate."""
    r = client("depositor").post("/api/check", json=good_item(
        title="Market Structure Paradigm and Institutional Settings in the Nigerian Electricity Industry",
        creators="Isola, W. A.", date_issued="2007"))
    assert any("Electricity Industry" in d["title"] for d in r.json()["duplicates"])


# ---------------------------------------------------------------- FR7 review workflow
@req("FR7")
def test_tc29_approve_publishes():
    """A librarian approves a submitted item.
    The item becomes publicly visible and searchable."""
    submit(client("depositor"), title="Digital Preservation Readiness of Nigerian University Libraries")
    iid = last_id()
    client("librarian").post(f"/review/{iid}", data={"action": "approve", "note": "Good record"})
    assert client().get(f"/items/{iid}").status_code == 200
    assert "Preservation Readiness" in client().get("/search", params={"q": "preservation readiness"}).text


@req("FR7")
def test_tc30_return_needs_note():
    """A librarian returns an item without a note.
    The action is refused because a note to the depositor is required."""
    submit(client("depositor"), title="Return Note Test on Repository Workflow Design")
    r = client("librarian").post(f"/review/{last_id()}", data={"action": "return", "note": ""})
    assert r.status_code == 400 or "note to the depositor is required" in r.text


@req("FR7")
def test_tc31_return_and_resubmit():
    """A returned item is corrected by the depositor and resubmitted.
    The status changes from 'returned' back to 'submitted'."""
    dep = client("depositor")
    submit(dep, title="Resubmission Test on Metadata Correction Cycles")
    iid = last_id()
    client("librarian").post(f"/review/{iid}", data={"action": "return", "note": "Add supervisor name"})
    assert "Add supervisor name" in dep.get("/my").text
    d = good_item(title="Resubmission Test on Metadata Correction Cycles", advisor="Bello, M. A.")
    dep.post(f"/items/{iid}/edit", data=d)
    from app import db
    with db.get_conn() as c:
        assert c.execute("SELECT status FROM items WHERE id=?", (iid,)).fetchone()[0] == "submitted"


@req("FR7")
def test_tc32_depositor_cannot_edit_published():
    """A depositor tries to edit an item that is already published.
    The edit is refused (HTTP 403)."""
    assert client("depositor").get("/items/1/edit").status_code == 403


@req("FR7")
def test_tc33_audit_log():
    """Every workflow action is written to the audit log.
    The review page history lists 'submitted' and 'approve' actions."""
    submit(client("depositor"), title="Audit Trail Test for Repository Accountability")
    iid = last_id()
    lib = client("librarian")
    lib.post(f"/review/{iid}", data={"action": "approve", "note": ""})
    h = lib.get(f"/review/{iid}").text.split("History")[1]
    assert "submitted" in h and "approve" in h


@req("FR7")
def test_tc34_normalisation_improves_score():
    """A librarian applies automatic normalisation to a UNILAG record.
    Author forms are corrected and the quality score increases."""
    from app import db
    with db.get_conn() as c:
        before = c.execute("SELECT quality_score FROM items WHERE id=5").fetchone()[0]
    client("librarian").post("/review/5", data={"action": "normalise"})
    with db.get_conn() as c:
        row = c.execute("SELECT quality_score, creators FROM items WHERE id=5").fetchone()
    assert row[0] > before and "Okafor, A. I." in row[1]


# ---------------------------------------------------------------- FR8 access rights
@req("FR8")
def test_tc35_embargo_enforced():
    """Download the file of an embargoed item.
    The download is refused (HTTP 403) while metadata stays visible."""
    dep = client("depositor")
    dep.post("/submit", data=good_item(title="Embargoed Thesis on Industrial Patents", rights="embargo",
                                       embargo_until="2028-12-31"),
             files={"file": ("e.pdf", make_pdf("embargoed content"), "application/pdf")})
    iid = last_id()
    client("librarian").post(f"/review/{iid}", data={"action": "approve", "note": ""})
    from app import db
    with db.get_conn() as c:
        fid = c.execute("SELECT id FROM files WHERE item_id=?", (iid,)).fetchone()[0]
    anon = client()
    assert anon.get(f"/items/{iid}").status_code == 200
    assert anon.get(f"/items/{iid}/files/{fid}").status_code == 403


# ---------------------------------------------------------------- FR9 OAI-PMH
def oai(**params):
    return client().get("/oai", params=params).content


@req("FR9")
def test_tc36_identify_valid():
    """Send the OAI-PMH Identify request.
    The response validates against the official OAI-PMH 2.0 XML schema."""
    x = oai(verb="Identify")
    assert OAI_XSD.is_valid(x) and b"<protocolVersion>2.0</protocolVersion>" in x


@req("FR9")
def test_tc37_listrecords_valid():
    """Send ListRecords with metadataPrefix oai_dc.
    The response is schema-valid and contains only published records."""
    x = oai(verb="ListRecords", metadataPrefix="oai_dc")
    assert OAI_XSD.is_valid(x) and b"Hidden Work Awaiting Review" not in x


@req("FR9")
def test_tc38_oai_dc_valid():
    """Validate the Dublin Core block of a GetRecord response.
    The oai_dc element validates against the oai_dc schema."""
    from lxml import etree
    x = oai(verb="GetRecord", identifier="oai:smartir.unilag.prototype:1", metadataPrefix="oai_dc")
    t = etree.fromstring(x)
    dc = t.find(".//{http://www.openarchives.org/OAI/2.0/oai_dc/}dc")
    assert dc is not None and DC_XSD.is_valid(etree.tostring(dc))


@req("FR9")
def test_tc39_bad_verb():
    """Send an illegal verb.
    The badVerb error code is returned in a schema-valid response."""
    x = oai(verb="Harvest")
    assert b'code="badVerb"' in x and OAI_XSD.is_valid(x)


@req("FR9")
def test_tc40_bad_argument():
    """Send GetRecord without the identifier argument.
    The badArgument error code is returned."""
    assert b'code="badArgument"' in oai(verb="GetRecord", metadataPrefix="oai_dc")


@req("FR9")
def test_tc41_id_does_not_exist():
    """Request a record identifier that does not exist.
    The idDoesNotExist error code is returned."""
    assert b'code="idDoesNotExist"' in oai(verb="GetRecord", identifier="oai:smartir.unilag.prototype:99999",
                                           metadataPrefix="oai_dc")


@req("FR9")
def test_tc42_cannot_disseminate():
    """Request an unsupported metadata format (marc21).
    The cannotDisseminateFormat error code is returned."""
    assert b'code="cannotDisseminateFormat"' in oai(verb="ListRecords", metadataPrefix="marc21")


@req("FR9")
def test_tc43_set_harvesting():
    """Harvest only the set fac_faculty_of_education.
    Every returned header carries that setSpec."""
    x = oai(verb="ListIdentifiers", metadataPrefix="oai_dc", set="fac_faculty_of_education").decode()
    headers = re.findall(r"<header>.*?</header>", x)
    assert headers and all("fac_faculty_of_education" in h for h in headers)


@req("FR9")
def test_tc44_resumption_token():
    """Harvest a list larger than one page (more than 50 records) using resumption tokens.
    Every record is retrieved once across pages and each page is schema-valid."""
    from app import db
    import json as _json
    with db.get_conn() as c:
        for i in range(60):
            c.execute("INSERT INTO items(title,creators,status,item_type,faculty,origin) "
                      "VALUES (?,?, 'published','Article','Faculty of Law','demo')",
                      (f"Paging test record {i}", _json.dumps(["Test, A. B."])))
        expected = c.execute("SELECT COUNT(*) FROM items WHERE status='published'").fetchone()[0]
    seen, x = set(), oai(verb="ListIdentifiers", metadataPrefix="oai_dc").decode()
    pages = 0
    while True:
        pages += 1
        assert OAI_XSD.is_valid(x.encode())
        seen.update(re.findall(r"<identifier>(.*?)</identifier>", x))
        m = re.search(r"<resumptionToken[^>]*>([^<]+)</resumptionToken>", x)
        if not m:
            break
        x = oai(verb="ListIdentifiers", resumptionToken=m.group(1)).decode()
    assert pages >= 2 and len(seen) == expected


@req("FR9")
def test_tc45_date_filter():
    """Harvest with from=2999-01-01 (a future date).
    The noRecordsMatch error code is returned."""
    assert b'code="noRecordsMatch"' in oai(verb="ListRecords", metadataPrefix="oai_dc", **{"from": "2999-01-01"})


# ---------------------------------------------------------------- FR10 analytics
@req("FR10")
def test_tc46_usage_counted():
    """View an item three times.
    The item view counter increases by three."""
    c = client()
    def views():
        return int(re.search(r'<div class="stat">(\d+)<small>Views', c.get("/items/2").text).group(1))
    v0 = views()
    c.get("/items/2"); c.get("/items/2")
    assert views() == v0 + 3


@req("FR10")
def test_tc47_search_logging():
    """Run a search that has no matching items.
    The term appears under 'Searches with no results' on the analytics page."""
    client().get("/search", params={"q": "cryptocurrency"})
    r = client("librarian").get("/analytics")
    assert "cryptocurrency" in r.text.split("Searches with no results")[1]


@req("FR10")
def test_tc48_analytics_restricted():
    """A depositor opens the analytics dashboard.
    Access is denied (HTTP 403)."""
    assert client("depositor").get("/analytics").status_code == 403
