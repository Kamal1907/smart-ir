"""Performance test: 15 UNILAG records plus N synthetic records (load testing only).
Usage: python tests/benchmark_performance.py [N]"""
import asyncio, json, os, random, statistics, subprocess, sys, tempfile, time
import httpx
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp()
env = dict(os.environ, SMARTIR_DB=os.path.join(tmp, "perf.db"), SMARTIR_UPLOADS=os.path.join(tmp, "f"))
t0 = time.time()
subprocess.run([sys.executable, "seed.py", "--demo", str(N)], cwd=ROOT, env=env, check=True, capture_output=True)
load_s = round(time.time() - t0, 1)
srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8011", "--workers", "1", "--log-level", "warning"], cwd=ROOT, env=env)
time.sleep(4)
B = "http://127.0.0.1:8011"
TERMS = ["library", "repository", "lagos", "metadata", "education health", "open access", "university policy", "energy market", "lungfish", "students evaluation"]
def pctl(xs, p): xs = sorted(xs); return round(xs[min(len(xs)-1, int(p/100*len(xs)))], 1)
def stats(xs): return {"n": len(xs), "mean_ms": round(statistics.mean(xs),1), "p50_ms": pctl(xs,50), "p95_ms": pctl(xs,95), "max_ms": round(max(xs),1)}
res = {"records": N + 15, "seed_seconds": load_s, "cpu": os.cpu_count()}
try:
    with httpx.Client(base_url=B, timeout=30) as c:
        c.get("/search?q=warmup")
        def timed(url, k=100):
            out = []
            for i in range(k):
                u = url(i) if callable(url) else url
                s = time.perf_counter(); r = c.get(u); out.append((time.perf_counter()-s)*1000); assert r.status_code == 200, (u, r.status_code)
            return stats(out)
        rnd = random.Random(1)
        res["search_keyword"] = timed(lambda i: f"/search?q={TERMS[i % len(TERMS)]}")
        res["search_faceted"] = timed(lambda i: f"/search?q={TERMS[i % len(TERMS)]}&faculty=Faculty%20of%20Education&year_from=2000")
        res["browse_no_query"] = timed("/search", 50)
        res["item_page"] = timed(lambda i: f"/items/{rnd.randint(1, N)}")
        res["oai_listrecords_page"] = timed("/oai?verb=ListRecords&metadataPrefix=oai_dc", 30)
        res["oai_getrecord"] = timed(lambda i: f"/oai?verb=GetRecord&metadataPrefix=oai_dc&identifier=oai:smartir.unilag.prototype:{rnd.randint(1,N)}", 50)
        # full harvest time
        s = time.perf_counter(); url = "/oai?verb=ListIdentifiers&metadataPrefix=oai_dc"; pages = 0; ids = 0
        while True:
            x = c.get(url).text; pages += 1; ids += x.count("<identifier>")
            import re; m = re.search(r"<resumptionToken[^>]*>([^<]+)</resumptionToken>", x)
            if not m: break
            url = "/oai?verb=ListIdentifiers&resumptionToken=" + m.group(1)
        res["full_harvest_identifiers"] = {"pages": pages, "identifiers": ids, "seconds": round(time.perf_counter()-s, 2)}
    async def load(users=20, per_user=25):
        lat, errors = [], 0
        async with httpx.AsyncClient(base_url=B, timeout=60) as ac:
            async def user(u):
                nonlocal errors
                r = random.Random(u)
                for i in range(per_user):
                    url = r.choice([f"/search?q={r.choice(TERMS)}", f"/items/{r.randint(1, N)}", "/", "/oai?verb=GetRecord&metadataPrefix=oai_dc&identifier=oai:smartir.unilag.prototype:%d" % r.randint(1, N)])
                    s = time.perf_counter(); resp = await ac.get(url); lat.append((time.perf_counter()-s)*1000)
                    if resp.status_code != 200: errors += 1
            s = time.perf_counter(); await asyncio.gather(*(user(u) for u in range(users))); el = time.perf_counter() - s
        return {"users": users, "requests": len(lat), "errors": errors, "seconds": round(el, 2), "throughput_rps": round(len(lat)/el, 1), **stats(lat)}
    res["concurrent_20_users"] = asyncio.run(load(20, 25))
    res["concurrent_50_users"] = asyncio.run(load(50, 20))
finally:
    srv.terminate()
os.makedirs(os.path.join(ROOT, "tests", "results"), exist_ok=True)
json.dump(res, open(os.path.join(ROOT, "tests", "results", f"performance_{N}.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
