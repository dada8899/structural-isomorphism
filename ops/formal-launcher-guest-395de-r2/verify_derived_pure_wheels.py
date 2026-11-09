"""Validate two independently built public pure wheels; never imports package code."""
import base64,csv,hashlib,io,json,re,stat,sys,zipfile
from pathlib import Path,PurePosixPath

PREFIXES={"jieba-0.42.1","langdetect-1.0.9"}
NAME=re.compile(r"(jieba-0\.42\.1|langdetect-1\.0\.9)-(?:py3|py2\.py3)-none-any\.whl")


def sha(buf):return hashlib.sha256(buf).hexdigest()


def verify(path):
    matched=NAME.fullmatch(path.name)
    if not matched or not path.is_file() or path.is_symlink() or path.stat().st_size>40_000_000:
        raise ValueError("unexpected wheel")
    prefix=matched[1]+".dist-info"
    rows={}
    total=0
    with zipfile.ZipFile(path) as arc:
        for entry in arc.infolist():
            n=entry.filename
            parts=PurePosixPath(n)
            if (not parts.parts or parts.is_absolute() or ".." in parts.parts or "\\" in n or n in rows
                    or stat.S_ISLNK(entry.external_attr>>16) or entry.is_dir()
                    or n.lower().endswith((".so",".dylib",".dll",".pyd",".pyc",".pth"))):
                raise ValueError("unsafe/nonpure wheel member")
            total+=entry.file_size
            if total>150_000_000:raise ValueError("wheel size")
            data=arc.read(entry)
            if data[:4] in (b"\x7fELF",b"\xcf\xfa\xed\xfe",b"\xfe\xed\xfa\xcf") or data[:2]==b"MZ":
                raise ValueError("native executable")
            rows[n]=(data,hashlib.sha256(data).digest())
        wheel=rows[prefix+"/WHEEL"][0].decode()
        if "Root-Is-Purelib: true" not in wheel.splitlines() or not any(line in
                ("Tag: py3-none-any","Tag: py2-none-any") for line in wheel.splitlines()):
            raise ValueError("not pure")
        record=prefix+"/RECORD"
        records={}
        for name,digest,size in csv.reader(io.StringIO(rows[record][0].decode())):
            if name in records or name not in rows:raise ValueError("unexpected RECORD row")
            expected=("","") if name==record else (
                "sha256="+base64.urlsafe_b64encode(rows[name][1]).decode().rstrip("="),str(len(rows[name][0])))
            if (digest,size)!=expected:raise ValueError("wheel RECORD mismatch")
            records[name]=True
        if set(records)!=set(rows):raise ValueError("incomplete RECORD")
    return {"filename":path.name,"sha256":sha(path.read_bytes()),"entries":len(rows),
            "source_distribution":matched[1]}


def inventory(directory):
    files=sorted(Path(directory).glob("*.whl"))
    rows=[verify(f) for f in files]
    if {r["source_distribution"] for r in rows}!=PREFIXES or len(rows)!=2:
        raise ValueError("exact two source builds required")
    return rows


if __name__=="__main__":
    first,second=sys.argv[1:]
    a,b=inventory(first),inventory(second)
    if a!=b:raise ValueError("independent wheel hashes differ")
    print(json.dumps({"status":"DERIVED_PURE_WHEELS_BYTE_REPRODUCED_NOT_RUNTIME_GO",
                      "wheels":a},sort_keys=True,indent=2))
