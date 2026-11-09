"""Download public lock-admitted distributions only; never install or build."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json,os
from pathlib import Path
import re,sys
from urllib.parse import urlparse
from urllib.request import urlopen

plan=json.loads(Path("LOCK-DISTRIBUTION-PLAN.json").read_bytes())
out=Path("verified-public-distributions")
out.mkdir(mode=0o700,exist_ok=True)
if out.is_symlink() or out.resolve()!=Path.cwd()/out:raise SystemExit("REFUSED_DIRECTORY")
def valid_host(url):
 p=urlparse(url)
 return p.scheme=="https" and p.hostname in ("files.pythonhosted.org","download-r2.pytorch.org") and p.port is None
def download(row):
 name=row["filename"]; digest=row["sha256"]; url=row["url"]; data=out/name
 assert re.fullmatch(r"[A-Za-z0-9_.+-]+",name) and re.fullmatch(r"[a-f0-9]{64}",digest) and valid_host(url)
 if data.exists():
  assert not data.is_symlink() and data.is_file()
  with data.open("rb") as f: actual=sha256(f.read()).hexdigest()
  assert actual==digest
  return dict(filename=name,sha256=digest,size=data.stat().st_size,kind=row["kind"])
 partial=out/(name+".part")
 try:
  with urlopen(url,timeout=35) as response, partial.open("xb") as file:
   assert valid_host(response.geturl())
   total=0; h=sha256()
   while buf:=response.read(1024*1024):
    total+=len(buf)
    if total>350_000_000:raise ValueError("PUBLIC_ARTIFACT_TOO_LARGE")
    file.write(buf);h.update(buf)
   assert total>0 and ("size" not in row or total==row["size"]) and h.hexdigest()==digest
   file.flush();os.fsync(file.fileno())
  os.link(partial,data)
  return dict(filename=name,sha256=digest,size=total,kind=row["kind"])
 except Exception as e:
  return dict(filename=name,error=type(e).__name__,code=getattr(e,"code",None))
 finally:
  partial.unlink(missing_ok=True)
with ThreadPoolExecutor(max_workers=8) as pool:
 rows=list(pool.map(download,plan["results"]))
status="PUBLIC_INPUT_DISTRIBUTIONS_VERIFIED_NO_WHEEL_BUILD" if all("sha256" in x for x in rows) else "PUBLIC_INPUTS_INCOMPLETE"
Path("PUBLIC-DISTRIBUTION-VERIFICATION.json").write_text(json.dumps({"status":status,"rows":rows},sort_keys=True,indent=2)+"\n")
for row in rows:
 if "error" in row:print(row)
print(status,len(rows),sum(x.get("size",0) for x in rows))
raise SystemExit(0 if status.startswith("PUBLIC_INPUT_DISTRIBUTIONS") else 1)
