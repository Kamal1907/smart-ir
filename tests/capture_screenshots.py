"""Drive the running prototype through a realistic session and capture screenshots for the report.
Requires the server on http://127.0.0.1:8000 with a freshly seeded database."""
import os
import re

from playwright.sync_api import sync_playwright

B = "http://127.0.0.1:8000"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "screenshots")
os.makedirs(OUT, exist_ok=True)
PW = "Demo@2026"
PDF = os.path.join(OUT, "..", "sample_thesis.pdf")
from reportlab.pdfgen import canvas as _c
_p = _c.Canvas(PDF); _p.drawString(72, 720, "Use of Electronic Information Resources by Postgraduate Students (sample full text)"); _p.save()


def shot(page, name, full=False):
    page.evaluate("window.scrollTo(0,0)")
    page.screenshot(path=os.path.join(OUT, name + ".png"), full_page=full)
    print("saved", name)


def login(page, who):
    page.goto(B + "/logout")
    page.goto(B + "/login")
    page.fill("#email", f"{who}@demo.edu.ng")
    page.fill("#pw", PW)
    page.click("button:has-text('Log in')")


def fill_form(page, d):
    page.fill("input[name=title]", d["title"])
    page.fill("textarea[name=creators]", d["creators"])
    page.fill("input[name=advisor]", d.get("advisor", ""))
    page.fill("input[name=date_issued]", d.get("date", ""))
    if d.get("type"):
        page.select_option("select[name=item_type]", d["type"])
    if d.get("faculty"):
        page.select_option("select[name=faculty]", d["faculty"])
    page.fill("input[name=department]", d.get("dept", ""))
    page.fill("textarea[name=abstract]", d.get("abstract", ""))
    page.fill("#subjects", d.get("subjects", ""))
    page.fill("input[name=publisher]", d.get("publisher", ""))
    page.wait_for_timeout(1200)


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 1366, "height": 860}, device_scale_factor=2)
    page = ctx.new_page()

    # realistic anonymous usage to populate analytics
    for q in ["lagos", "thesis education", "corruption", "lungfish", "electricity market", "traffic congestion",
              "philosophy leadership", "pharmacy", "creativity", "institutional repository", "lagos", "novels",
              "blockchain", "lagos state"]:
        page.goto(f"{B}/search?q={q}")
    for i in [1, 1, 2, 4, 5, 5, 5, 7, 8, 10, 10, 3]:
        page.goto(f"{B}/items/{i}")

    for v in ["Identify", "ListRecords&metadataPrefix=oai_dc", "ListRecords&metadataPrefix=oai_dc&set=fac_faculty_of_education"]:
        page.goto(f"{B}/oai?verb={v}")
    page.goto(B + "/")
    shot(page, "01_home")
    page.goto(B + "/search?q=lagos")
    shot(page, "02_search_results")
    page.goto(B + "/search?q=lagos&faculty=Faculty%20of%20Education")
    shot(page, "03_search_faceted")
    page.goto(B + "/items/5")
    shot(page, "04_item_page", full=True)
    page.goto(B + "/login")
    shot(page, "05_login")

    # depositor: poor draft to show live checks
    login(page, "depositor")
    page.goto(B + "/submit")
    fill_form(page, {"title": "Information Needs of Postgraduate Students in University of Lagos Library.",
                     "creators": "adebayo, k.o", "date": "12/05/2025", "type": "Thesis",
                     "faculty": "Faculty of Education", "subjects": "Library"})
    page.wait_for_timeout(1500)
    shot(page, "06_submit_live_check")

    # duplicate warning
    page.goto(B + "/submit")
    fill_form(page, {"title": "Market Structure Paradigm and Institutional Settings in the Nigerian Electricity Industry",
                     "creators": "Isola, W. A.", "date": "2007", "type": "Thesis", "faculty": "Faculty of Social Sciences",
                     "subjects": "Electricity Industry; Market Structure Paradigms; Nigeria",
                     "abstract": "This study examined the structure of the electricity market and the institutions that govern it in Nigeria."})
    page.wait_for_timeout(1500)
    shot(page, "07_submit_duplicate_warning")

    # good submission
    page.goto(B + "/submit")
    fill_form(page, {"title": "Use of Electronic Information Resources by Postgraduate Students at the University of Lagos",
                     "creators": "Adebayo, K. O.", "advisor": "Okoro, C. N.", "date": "2025-06", "type": "Thesis",
                     "faculty": "Faculty of Education", "dept": "Library and Information Science",
                     "abstract": ("This study examined how postgraduate students at the University of Lagos use electronic "
                                  "information resources, the problems they face and the support they need from the library."),
                     "subjects": "Electronic information resources; Postgraduate students; Academic libraries",
                     "publisher": "University of Lagos School of Postgraduate Studies"})
    page.set_input_files("input[name=file]", PDF)
    page.wait_for_timeout(1500)
    shot(page, "08_submit_good_record")
    page.click("button:has-text('Submit for review')")
    page.wait_for_load_state()
    shot(page, "09_submission_received")
    good_id = int(re.search(r"smartir/(\d+)", page.content()).group(1))

    # second submission that will be returned
    page.goto(B + "/submit")
    fill_form(page, {"title": "Records Management Practices in Selected Federal Universities in South West Nigeria",
                     "creators": "Bello, F. A.", "date": "2024", "type": "Dissertation", "faculty": "Faculty of Education",
                     "abstract": "The dissertation assessed records management practices, staff skills and the use of digital records systems in selected federal universities.",
                     "subjects": "Records management; Federal universities; Digital records"})
    page.click("button:has-text('Submit for review')")
    page.wait_for_load_state()
    ret_id = int(re.search(r"smartir/(\d+)", page.content()).group(1))

    # librarian
    login(page, "librarian")
    page.goto(B + "/review")
    shot(page, "10_review_queue")
    page.goto(f"{B}/review/{good_id}")
    shot(page, "11_review_item", full=True)
    page.click("button:has-text('Approve and publish')")
    page.wait_for_load_state()
    page.goto(f"{B}/items/{good_id}")
    with page.expect_download():
        page.click("text=Download")
    page.goto(f"{B}/review/{ret_id}")
    page.fill("textarea[name=note]", "Please add the name of your supervisor and upload the full-text PDF.")
    page.click("button:has-text('Return for correction')")

    page.goto(B + "/review/2")
    shot(page, "12_review_unilag_record", full=True)
    page.goto(B + "/quality?origin=unilag")
    shot(page, "13_quality_audit", full=True)

    page.goto(B + "/items/5")
    page.goto(B + "/review/5")
    page.click("button:has-text('Apply automatic normalisation')")
    page.wait_for_load_state()
    shot(page, "14_after_normalisation", full=True)

    page.goto(B + "/analytics")
    shot(page, "15_analytics", full=True)

    login(page, "depositor")
    page.goto(B + "/my")
    shot(page, "16_my_submissions")

    page.goto(B + "/oai?verb=Identify")
    shot(page, "17_oai_identify")
    page.goto(B + "/oai?verb=ListRecords&metadataPrefix=oai_dc&set=fac_faculty_of_education")
    shot(page, "18_oai_listrecords")

    mob = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2).new_page()
    mob.goto(B + "/search?q=lagos")
    shot(mob, "19_mobile_search")
    br.close()
