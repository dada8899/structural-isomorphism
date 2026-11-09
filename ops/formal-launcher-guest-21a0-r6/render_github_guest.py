"""Offline 395de hosted-VM unit projection, without executing systemd."""
from hashlib import sha256
import json
from pathlib import Path
import sys

from formal_launcher_envelope import manifest

KB_ENV=("STRUCTURAL_DATA_DIR","STRUCTURAL_MODEL_PATH","STRUCTURAL_PRECOMPUTED_EMBEDDINGS",
        "STRUCTURAL_ARTIFACT_MANIFEST")


def render(unit,entry,*,unit_sha,entry_sha,nonce):
    proof,guest=manifest(unit,entry,unit_sha=unit_sha,entry_sha=entry_sha,nonce=nonce)
    out=[]
    removed=[]
    for row in guest.decode("ascii").splitlines():
        if row.startswith("BindReadOnlyPaths=") or any(row.startswith("Environment="+k+"=") for k in KB_ENV):
            removed.append(row)
            continue
        out.append(row)
    if len(removed)!=6 or sum(row.startswith("BindReadOnlyPaths=") for row in removed)!=2:
        raise PermissionError("unexpected KB projection")
    raw=("\n".join(out)+"\n").encode()
    proof.update({"status":"OFFLINE_GITHUB_HOSTED_UNIT_PROFILE_NOT_EXECUTED",
                  "guest_unit_sha256":sha256(raw).hexdigest(),"kb_expectation":"ARTIFACTS_UNBOUND",
                  "runtime_payload_verified":False,"unit_executed":False,"release_go":False})
    return proof,raw


if __name__=="__main__":
    u,e,us,es,nonce=sys.argv[1:]
    p,_=render(Path(u).read_bytes(),Path(e).read_bytes(),unit_sha=us,entry_sha=es,nonce=nonce)
    print(json.dumps(p,sort_keys=True,indent=2))
