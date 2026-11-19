# SmartIR in Plain Language

This guide explains what SmartIR is, what it does and how to use it. You do not need a technical background to follow it.

---

## 1. The big picture

### What is SmartIR?

Think of a university library that keeps a digital shelf of everything its students and staff have written: theses, dissertations and research papers. That shelf is called an **institutional repository**.

**SmartIR is a working example of such a shelf, with a built-in "checker" that keeps the records tidy.** This project uses the University of Lagos as its example.

### What problem does it solve?

In many repositories, whoever uploads a paper types the details by hand. People make small mistakes:

- One person writes the author as `adebayo, k.o` and another as `K.O. Adebayo`.
- Dates are written in different styles, such as `12/05/2025` and `2025-05-12`.
- The same paper is uploaded twice.
- Fields are left empty, such as the abstract or the keywords.

Messy records are hard to search, hard to cite and hard for other systems to read. SmartIR catches these problems **while the person is typing**, and gives librarians tools to tidy up what is already stored.

### Who uses it?

| Person | In everyday words | What they can do |
|---|---|---|
| **Visitor** | Anyone on the internet, no login needed | Search, read records, download open files, copy a citation |
| **Depositor** | A student or staff member who wants to upload their work | Submit work, see a quality score as they type, track their submissions |
| **Librarian** | The person who looks after the repository | Check and approve submissions, fix messy records, view reports |
| **Administrator** | The person who manages the whole system | Everything a librarian can do |

### What it is made of (the simple version)

- **A website** that people open in their browser.
- **A database** (a very organised filing system) that stores all the records.
- **A set of rules** that check the quality of each record.
- **A "sharing door"** that lets other library systems collect the records automatically.

You do not need to understand these parts to use SmartIR.

---

## 2. The features, explained simply

### 1. Submitting work
A student or staff member fills in an online form (title, authors, summary, keywords and so on) and attaches a PDF. The work does **not** appear publicly straight away. It goes into a waiting list for a librarian to check first.

### 2. The live quality check
While the person types, a panel on the right shows a **score out of 100** and a list of problems to fix, such as "Author name should look like Adebayo, K. O." It works like a spell-checker, but for library records.

How the score is worked out:
- **60% is completeness.** Have the important boxes been filled in? Title, authors and summary are worth the most.
- **40% is correctness.** Are the details written in the proper style? For example, authors written as `Surname, Initials` and dates written as `2025` or `2025-06`.

This is why typing `adebayo, k.o` with the date `12/05/2025` gives a low score of about 52 ("Poor"). The checker is doing its job.

### 3. Spotting duplicates
Before submitting, the person is warned if the same work seems to be in the repository already. SmartIR flags a record when **both** of these are true:
1. The title is at least **90% similar** to an existing title.
2. It was published in the **same year**, or it shares an **author's surname**.

It is simple text comparison, so a librarian can easily understand why something was flagged. Because both conditions are needed, typing only a title will not trigger the warning.

### 4. Keyword suggestions
When choosing keywords, the form suggests words already used in the repository. This keeps the keywords consistent, so related works are easier to find together.

### 5. Librarian review
For each submission, the librarian can:
- **Approve and publish** it, so everyone can see it.
- **Return it with a note** asking for corrections.
- **Withdraw** it, so it is hidden.

There is also an **automatic tidy-up** button that fixes author names and publisher names in one click. Every action is recorded in a history log, so it is always clear who did what.

### 6. Searching
Visitors can type words and get ranked results. The search looks in the title, authors, keywords, summary and even the text inside the PDF. Results can be narrowed by faculty, type of work, access level and year.

### 7. Who can open which files
Each work has an access level:
- **Open:** anyone can download the file.
- **Embargoed:** the details are visible, but the file is locked until a set date.
- **Restricted:** the file is not available to the public.

Work that is still waiting for approval can be seen only by its owner and the librarians.

### 8. Copy-ready citations
Every record page shows how to cite the work in **APA 7** style, and offers a **BibTeX** file for people who use reference-management software.

### 9. Repository health report ("Metadata quality")
This page gives a score to **every record in the repository** and lists the most common problems and any duplicates. It shows a librarian where the clean-up effort is needed.

### 10. Usage reports ("Analytics")
It shows how the repository is being used: how many times records were viewed and downloaded, what people searched for, which searches found nothing, and how the records are spread across faculties, types of work and decades.

### 11. Sharing records with other systems
Library systems around the world collect records from repositories using a shared standard called **OAI-PMH**. SmartIR follows this standard, so its records can be collected automatically. Two example addresses (add them to the end of the website address):
- `/oai?verb=Identify` shows who the repository is.
- `/oai?verb=ListRecords&metadataPrefix=oai_dc` lists the records in a standard format.

The output was checked against the official standard in the project's tests.

---

## 3. How to use it: a step-by-step walkthrough

**Demonstration logins** (the password for all of them is `Demo@2026`):

| Role | Email |
|---|---|
| Depositor | depositor@demo.edu.ng |
| Librarian | librarian@demo.edu.ng |
| Administrator | admin@demo.edu.ng |

### A. As a visitor (no login)
1. Open the home page.
2. Search for `lagos`. You should see 6 results.
3. Choose a faculty on the left to narrow the list.
4. Click a result to read the full record.
5. Click **BibTeX** to download the citation.

### B. As a depositor
1. Log in as the depositor and click **Submit work**.
2. **See the quality check:** type the author `adebayo, k.o` and the date `12/05/2025`. A low score and a list of problems appear on the right.
3. **See the duplicate warning:** on a fresh form, enter this title:
   *Market Structure Paradigm and Institutional Settings in the Nigerian Electricity Industry*
   with author `Isola, W. A.` and date `2007`. A "Possible duplicates" box appears.
4. **Submit a proper record:** fill in all the boxes, attach a PDF and click **Submit for review**.
5. Open **My submissions** to follow its progress.

### C. As a librarian
1. Log in as the librarian and open the **Review queue**.
2. Open the new submission and read through it.
3. Click **Approve and publish** (or **Return for correction** with a note).
4. Open **Metadata quality** and choose "UNILAG records only" to see the health report.
5. Open **Analytics** to see usage.

### D. Checking the sharing feature
Add `/oai?verb=Identify` and then `/oai?verb=ListRecords&metadataPrefix=oai_dc` to the website address. You should see structured text (XML), which is what other systems read.

---

## 4. Good to know

- **The demo resets.** On the free hosting plan, the system starts fresh whenever it restarts. Anything submitted during a demo may disappear. That is fine for a demonstration but not for real storage.
- **The site can be slow to wake up.** After about 15 minutes without visitors it goes to sleep. The first visit can take 30 to 60 seconds. Open it a few minutes before presenting.
- **The records are real, the accounts are not.** The 15 records come from the real University of Lagos repository. The login accounts are for demonstration only, and their passwords are public. Change them before sharing the link widely.
- **The checker is rule-based.** SmartIR follows clear, fixed rules. It does not use artificial intelligence, so every score and warning can be explained.

---

## 5. Quick glossary

| Term | Meaning |
|---|---|
| **Repository** | A digital shelf that stores and shares a university's research |
| **Metadata** | The details about a work (title, author, date, keywords), as opposed to the work itself |
| **Dublin Core** | A widely used standard list of metadata fields |
| **Deposit / submit** | Uploading a work to the repository |
| **Embargo** | A period during which a file is locked from public download |
| **Duplicate** | The same work stored twice |
| **OAI-PMH** | The standard that lets other library systems collect a repository's records automatically |
| **Citation (APA, BibTeX)** | A ready-made reference to the work in a standard format |
