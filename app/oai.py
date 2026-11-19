"""OAI-PMH 2.0 data provider (oai_dc metadata format).

Supports the six protocol verbs, selective harvesting by set and date,
resumption tokens and the standard error codes.
"""
import base64
import json
import re
from datetime import datetime, timezone
from xml.sax.saxutils import escape

REPO_NAME = "SmartIR: Smart Institutional Repository Prototype (University of Lagos case study)"
ID_PREFIX = "oai:smartir.unilag.prototype:"
PAGE_SIZE = 50
EARLIEST = "2000-01-01T00:00:00Z"
ADMIN_EMAIL = "repository-admin@example.edu.ng"

ALLOWED_ARGS = {
    "Identify": (set(), set()),
    "ListMetadataFormats": (set(), {"identifier"}),
    "ListSets": (set(), {"resumptionToken"}),
    "GetRecord": ({"identifier", "metadataPrefix"}, set()),
    "ListIdentifiers": ({"metadataPrefix"}, {"from", "until", "set", "resumptionToken"}),
    "ListRecords": ({"metadataPrefix"}, {"from", "until", "set", "resumptionToken"}),
}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?$")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp(ts):
    ts = (ts or "").replace(" ", "T")
    return ts[:19] + "Z" if len(ts) >= 19 else EARLIEST


def envelope(base_url, args, body):
    attrs = "".join(f' {k}="{escape(v)}"' for k, v in args.items() if k in
                    {"verb", "identifier", "metadataPrefix", "from", "until", "set", "resumptionToken"})
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/ '
            'http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd">\n'
            f"<responseDate>{now()}</responseDate>\n"
            f"<request{attrs}>{escape(base_url)}</request>\n{body}\n</OAI-PMH>")


def error(code, msg):
    return f'<error code="{code}">{escape(msg)}</error>'


def header(item):
    sets = []
    if item.get("faculty"):
        sets.append("fac_" + slug(item["faculty"]))
    if item.get("item_type"):
        sets.append("type_" + slug(item["item_type"]))
    spec = "".join(f"<setSpec>{s}</setSpec>" for s in sets)
    return (f"<header><identifier>{ID_PREFIX}{item['id']}</identifier>"
            f"<datestamp>{stamp(item.get('updated_at'))}</datestamp>{spec}</header>")


def oai_dc(item, base_url):
    e = escape
    parts = [f"<dc:title>{e(item['title'])}</dc:title>"]
    parts += [f"<dc:creator>{e(c)}</dc:creator>" for c in item["creators"]]
    if item.get("advisor"):
        parts.append(f"<dc:contributor>{e(item['advisor'])}</dc:contributor>")
    parts += [f"<dc:subject>{e(s)}</dc:subject>" for s in item["subjects"]]
    if item.get("abstract"):
        parts.append(f"<dc:description>{e(item['abstract'])}</dc:description>")
    if item.get("publisher"):
        parts.append(f"<dc:publisher>{e(item['publisher'])}</dc:publisher>")
    if item.get("date_issued"):
        parts.append(f"<dc:date>{e(item['date_issued'])}</dc:date>")
    if item.get("item_type"):
        parts.append(f"<dc:type>{e(item['item_type'])}</dc:type>")
    parts.append("<dc:format>application/pdf</dc:format>")
    parts.append(f"<dc:identifier>{e(base_url.rsplit('/oai', 1)[0])}/items/{item['id']}</dc:identifier>")
    if item.get("source_url"):
        parts.append(f"<dc:source>{e(item['source_url'])}</dc:source>")
    if item.get("language"):
        parts.append(f"<dc:language>{e(item['language'])}</dc:language>")
    rights = {"open": "info:eu-repo/semantics/openAccess",
              "embargo": "info:eu-repo/semantics/embargoedAccess",
              "restricted": "info:eu-repo/semantics/restrictedAccess"}.get(item.get("rights"), "")
    if rights:
        parts.append(f"<dc:rights>{rights}</dc:rights>")
    return ('<metadata><oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/oai_dc/ '
            'http://www.openarchives.org/OAI/2.0/oai_dc.xsd">'
            + "".join(parts) + "</oai_dc:dc></metadata>")


def encode_token(d):
    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode()


def decode_token(t):
    try:
        return json.loads(base64.urlsafe_b64decode(t.encode()).decode())
    except Exception:
        return None


def handle(args, base_url, load_items, load_item, all_sets):
    """args: query params. load_items(filters, offset, limit)->(items, total); load_item(id)->item|None."""
    verb = args.get("verb")
    if verb not in ALLOWED_ARGS:
        return envelope(base_url, {}, error("badVerb", "Illegal or missing verb"))
    required, optional = ALLOWED_ARGS[verb]
    keys = set(args) - {"verb"}
    if "resumptionToken" in keys and keys != {"resumptionToken"}:
        return envelope(base_url, {}, error("badArgument", "resumptionToken is exclusive"))
    if "resumptionToken" not in keys:
        if not required <= keys or keys - required - optional:
            return envelope(base_url, {}, error("badArgument", "Missing or illegal arguments"))
    for k in ("from", "until"):
        if k in args and not DATE_RE.match(args[k]):
            return envelope(base_url, {}, error("badArgument", f"Bad {k} date"))

    if verb == "Identify":
        body = (f"<Identify><repositoryName>{escape(REPO_NAME)}</repositoryName>"
                f"<baseURL>{escape(base_url)}</baseURL><protocolVersion>2.0</protocolVersion>"
                f"<adminEmail>{ADMIN_EMAIL}</adminEmail><earliestDatestamp>{EARLIEST}</earliestDatestamp>"
                "<deletedRecord>no</deletedRecord><granularity>YYYY-MM-DDThh:mm:ssZ</granularity>"
                "</Identify>")
        return envelope(base_url, args, body)

    if verb == "ListMetadataFormats":
        if "identifier" in args and not _get(args["identifier"], load_item):
            return envelope(base_url, args, error("idDoesNotExist", "Unknown identifier"))
        body = ("<ListMetadataFormats><metadataFormat><metadataPrefix>oai_dc</metadataPrefix>"
                "<schema>http://www.openarchives.org/OAI/2.0/oai_dc.xsd</schema>"
                "<metadataNamespace>http://www.openarchives.org/OAI/2.0/oai_dc/</metadataNamespace>"
                "</metadataFormat></ListMetadataFormats>")
        return envelope(base_url, args, body)

    if verb == "ListSets":
        if "resumptionToken" in args:
            return envelope(base_url, args, error("badResumptionToken", "Sets are not paged"))
        body = "<ListSets>" + "".join(
            f"<set><setSpec>{s}</setSpec><setName>{escape(n)}</setName></set>" for s, n in all_sets()
        ) + "</ListSets>"
        return envelope(base_url, args, body)

    if verb == "GetRecord":
        if args["metadataPrefix"] != "oai_dc":
            return envelope(base_url, args, error("cannotDisseminateFormat", "Only oai_dc"))
        item = _get(args["identifier"], load_item)
        if not item:
            return envelope(base_url, args, error("idDoesNotExist", "Unknown identifier"))
        return envelope(base_url, args,
                        f"<GetRecord><record>{header(item)}{oai_dc(item, base_url)}</record></GetRecord>")

    # ListIdentifiers / ListRecords
    if "resumptionToken" in args:
        tok = decode_token(args["resumptionToken"])
        if not tok:
            return envelope(base_url, args, error("badResumptionToken", "Invalid token"))
        params, offset = tok["p"], tok["o"]
    else:
        if args["metadataPrefix"] != "oai_dc":
            return envelope(base_url, args, error("cannotDisseminateFormat", "Only oai_dc"))
        params = {k: args[k] for k in ("from", "until", "set") if k in args}
        offset = 0
    page, total = load_items(params, offset, PAGE_SIZE)
    if not total:
        return envelope(base_url, args, error("noRecordsMatch", "No records match"))
    rows = []
    for it in page:
        rows.append(header(it) if verb == "ListIdentifiers"
                    else f"<record>{header(it)}{oai_dc(it, base_url)}</record>")
    nxt = offset + PAGE_SIZE
    token = ""
    if nxt < total:
        token = (f'<resumptionToken completeListSize="{total}" cursor="{offset}">'
                 f"{encode_token({'p': params, 'o': nxt})}</resumptionToken>")
    elif offset > 0:
        token = f'<resumptionToken completeListSize="{total}" cursor="{offset}"/>'
    return envelope(base_url, args, f"<{verb}>{''.join(rows)}{token}</{verb}>")


def _get(identifier, load_item):
    if not identifier.startswith(ID_PREFIX):
        return None
    try:
        return load_item(int(identifier[len(ID_PREFIX):]))
    except ValueError:
        return None
