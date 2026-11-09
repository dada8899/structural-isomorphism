"""Independent stdlib-only prehash before entering the controller import path."""
import hashlib,json,os,re,runpy,stat,sys
from pathlib import Path

def need(x):
 if not x:raise SystemExit("HOLD_BOOTSTRAP_REFUSED")

def read(path,limit):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
 with os.fdopen(fd,"rb") as f:
  s=os.fstat(f.fileno())
  need(stat.S_ISREG(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022 and s.st_nlink==1 and 0<s.st_size<=limit)
  raw=f.read(limit+1);after=path.stat(follow_symlinks=False)
  key=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
  need(len(raw)==s.st_size and key(s)==key(os.fstat(f.fileno()))==key(after))
  return raw

if __name__=="__main__":
 need(sys.platform=="linux" and os.geteuid()==0 and sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode)
 root=Path(__file__).resolve().parent
 for parent in (root,*root.parents):
  meta=parent.stat(follow_symlinks=False)
  need(stat.S_ISDIR(meta.st_mode) and meta.st_uid==0 and not meta.st_mode&0o022)
 manifest,pin,*remaining=sys.argv[1:]
 need(re.fullmatch(r"[a-f0-9]{64}",pin))
 data=read(Path(manifest),8192);need(hashlib.sha256(data).hexdigest()==pin)
 expected=json.loads(data)
 names={"guest_bootstrap.py","guest_once.py","formal_launcher_envelope.py","render_github_guest.py",
        "verify_derived_pure_wheels.py","runtime-linux-cpu.lock","PUBLIC-DISTRIBUTION-VERIFICATION.json"}
 need(set(expected)==names)
 for name,digest in expected.items():
  need(re.fullmatch(r"[a-f0-9]{64}",digest) and hashlib.sha256(read(root/name,262144)).hexdigest()==digest)
 sys.path.insert(0,str(root));target=root/"guest_once.py"
 sys.argv=[str(target),*remaining]
 runpy.run_path(str(target),run_name="__main__")
