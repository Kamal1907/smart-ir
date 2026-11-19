"""Citation export in APA 7 and BibTeX."""
import re

from .quality import normalise_author


def _year(d):
    m = re.match(r"(\d{4})", d or "")
    return m.group(1) if m else "n.d."


def apa(item, base_url=""):
    authors = [normalise_author(a) for a in item["creators"]]
    if len(authors) == 1:
        a = authors[0]
    elif len(authors) == 2:
        a = f"{authors[0]}, & {authors[1]}"
    elif authors:
        a = ", ".join(authors[:-1]) + f", & {authors[-1]}"
    else:
        a = "Anonymous"
    title = item["title"].rstrip(". ")
    y = _year(item.get("date_issued"))
    url = f"{base_url}/items/{item['id']}" if base_url else ""
    if item.get("item_type") in {"Thesis", "Dissertation"}:
        kind = "Doctoral thesis" if item.get("item_type") == "Thesis" else "Dissertation"
        return f"{a} ({y}). {title} [{kind}, University of Lagos]. {url}".strip()
    pub = item.get("publisher") or ""
    return f"{a} ({y}). {title}. {pub + '. ' if pub else ''}{url}".strip()


def bibtex(item, base_url=""):
    first = (item["creators"][0].split(",")[0] if item["creators"] else "anon").lower()
    first = re.sub(r"[^a-z]", "", first)
    key = f"{first}{_year(item.get('date_issued'))}_{item['id']}"
    entry = "phdthesis" if item.get("item_type") in {"Thesis", "Dissertation"} else "article"
    authors = " and ".join(normalise_author(a) for a in item["creators"])
    fields = {
        "author": authors,
        "title": item["title"].rstrip(". "),
        "year": _year(item.get("date_issued")),
    }
    if entry == "phdthesis":
        fields["school"] = "University of Lagos"
    elif item.get("publisher"):
        fields["publisher"] = item["publisher"]
    if base_url:
        fields["url"] = f"{base_url}/items/{item['id']}"
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items())
    return f"@{entry}{{{key},\n{body}\n}}"
