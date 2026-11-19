# SmartIR demo checklist

Before you start: run `python seed.py --reset`, start the server, and open `/health` (expect `{"status":"ok","items":15}`).
On Render, open the site 5 minutes early so the free instance is awake.
All demo accounts use the password `Demo@2026`.

| # | Click path | Expected result |
|---|---|---|
| 1 | Home, then search `lagos` | 6 results |
| 2 | Tick the faculty filter "Faculty of Education" | The list narrows (2 results) |
| 3 | Open any item (for example `/items/5`) | Dublin Core record, "Cite this item" box with APA text, related items |
| 4 | Click **BibTeX** | A `.bib` entry is returned |
| 5 | Log in as `depositor@demo.edu.ng`, open **Submit work** | Empty form with the "Live metadata check" panel |
| 6 | Type author `adebayo, k.o` and date `12/05/2025` | Panel updates within about 1 second to a low score (about 52/100, "Poor") with issues listed |
| 7 | On a fresh form enter title `Market Structure Paradigm and Institutional Settings in the Nigerian Electricity Industry`, author `Isola, W. A.`, date `2007` | "Possible duplicates" card appears, similarity about 99% |
| 8 | Fill a good record (title, author, advisor, date `2025-06`, type, faculty, department, abstract, 3+ subjects, publisher, PDF) and click **Submit for review** | "Submission received" page with a reference number |
| 9 | Log in as `librarian@demo.edu.ng`, open **Review queue**, open the item, click **Approve and publish** | Item leaves the queue and is publicly visible at `/items/<id>` |
| 10 | **Metadata quality**, choose "UNILAG records only" | Repository-wide scores, most frequent problems, duplicate report |
| 11 | **Analytics** | Views, downloads, searches, zero-result searches, items by faculty/type/decade |
| 12 | Open `/oai?verb=Identify` | OAI-PMH XML with repository details |
| 13 | Open `/oai?verb=ListRecords&metadataPrefix=oai_dc` | XML list of `oai_dc` records |

## The 3 things most likely to go wrong live

1. **Duplicate warning does not appear (step 7).** The rule needs a similar title *and* either the same year or a shared author surname. Typing only the title will not trigger it. Recovery: enter author `Isola, W. A.` and date `2007`, wait one second.
2. **Render site is slow or blank at the start.** The free instance sleeps after about 15 minutes and takes 30 to 60 seconds to wake. A restart also re-seeds the database, so earlier submissions vanish. Recovery: open the site 5 minutes before, and keep the laptop copy (`uvicorn app.main:app`) running as a fallback.
3. **Analytics or Quality pages look empty or logins fail after a reset.** `seed.py --reset` wipes usage data, and a reset while the server is running can leave a stale connection. Recovery: stop the server, run `python seed.py --reset`, start the server, and do a few searches and item views before opening Analytics.

Cosmetic: the browser console shows one 404 for `/favicon.ico`. It does not affect anything.
