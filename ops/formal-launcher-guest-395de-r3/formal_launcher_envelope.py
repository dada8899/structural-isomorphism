"""Pure offline renderer for a disposable Linux guest. Never invokes systemd."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

SOURCE="395de55b082e2cfb73111dbbe73d2571b3319c8d"
RUNTIME="/srv/structural-isomorphism/runtimes/cpython311-cpu-efd2731c4e9e-a3/bin/python"
ELF="/opt/structural-tools/python/cpython-3.11.15-linux-x86_64-gnu/bin/python3.11"
ELF_SHA="6ec402210289b1d16bf3440775d3595e93f92e1e0ec808d4607b85f528592159"
RELEASE="/srv/structural-isomorphism/releases/"+SOURCE
ENTRY=RELEASE+"/scripts/run-formal-main.py"
UNIT="structural-web.service"
FORMAL_UNIT_SHA="1afa5357604eea3dddaea6d83d2ad55b5d47564636fbe93965f29699b5c52202"
FORMAL_ENTRY_SHA="76c6c03c092422a5d46739640041a91ddaafbee1c156470f82bd752fb1f8a44f"
CREDENTIALS=("structural-jwt-secret","structural-sso-secret","structural-privacy-hmac-key",
             "structural-share-token-secret","structural-smtp-password")
GUEST_PREP="/run/structure-formal-launcher-vm-only"
NONCE=re.compile(r"[a-f0-9]{16}")


def sha(raw):return sha256(raw).hexdigest()


def need(ok,reason):
    if not ok:raise ValueError(reason)


def render(production_unit, *, expected_unit_sha, nonce):
    """Bind exact R7-rendered candidate unit and return guest-only bytes."""
    need(NONCE.fullmatch(nonce) and expected_unit_sha==FORMAL_UNIT_SHA
         and sha(production_unit)==expected_unit_sha,"UNIT_OR_NONCE_PIN")
    lines=production_unit.decode("ascii").splitlines()
    argv=[RUNTIME,"-I","-B",ENTRY]
    required=["ExecStart="+" ".join(argv),"WorkingDirectory="+RELEASE,
              "Environment=STRUCTURAL_GIT_SHA="+SOURCE,"User=structural","Group=structural",
              "EnvironmentFile=/etc/structural/structural-web.env","LimitCORE=0","ProtectSystem=strict",
              "NoNewPrivileges=yes","ProtectHome=yes","PrivateTmp=yes","KillMode=control-group",
              "StateDirectory=structural-isomorphism","CacheDirectory=structural-isomorphism",
              "Environment=STRUCTURAL_ENV=prod","Environment=AUTH_DATA_DIR=/var/lib/structural-isomorphism",
              "Environment=STRUCTURAL_SSO_DATA_DIR=/var/lib/structural-isomorphism"]
    need(all(lines.count(k)==1 for k in required) and
         sum(line.startswith("ExecStart") for line in lines)==1 and
         sum(line.startswith("EnvironmentFile=") for line in lines)==1,"FORMAL_ARGV_OR_SERVICE_PROFILE")
    exact_credentials={f"LoadCredentialEncrypted={n}:/etc/credstore.encrypted/structural/{n}" for n in CREDENTIALS}
    credentials=[line for line in lines if line.startswith(("LoadCredential","ImportCredential","SetCredential"))]
    need(set(credentials)==exact_credentials and len(credentials)==len(CREDENTIALS),"FORMAL_CREDENTIAL_SLOTS")
    need(len([line for line in lines if line.startswith("BindReadOnlyPaths=")])==2,"FORMAL_KB_MOUNTS")
    guest=f"{GUEST_PREP}/{nonce}"
    out=[]
    for line in lines:
        if line in ("After=network-online.target","Wants=network-online.target"):continue
        if line=="[Install]":break
        if line=="[Unit]":
            out.extend((line,"ConditionPathExists="+guest+"/GUEST_ONLY"));continue
        if line=="[Service]":
            out.extend((line,"PrivateNetwork=yes","RestrictAddressFamilies=AF_UNIX AF_INET",
                        "IPAddressDeny=any","IPAddressAllow=localhost","CapabilityBoundingSet=",
                        "RuntimeMaxSec=120","StandardOutput=journal","StandardError=journal"))
            continue
        if line.startswith("Description="):line="Description=Disposable VM exact launcher rehearsal only"
        elif line.startswith("Restart="):line="Restart=no"
        elif line.startswith("RestartSec="):continue
        elif line.startswith("EnvironmentFile="):line="EnvironmentFile="+guest+"/synthetic.env"
        elif line in exact_credentials:
            slot=line.split("=",1)[1].split(":",1)[0]
            line=f"LoadCredentialEncrypted={slot}:{guest}/encrypted/{slot}"
        out.append(line)
    raw=("\n".join(out).rstrip()+"\n").encode()
    need(not any(p in raw for p in (b"/etc/credstore.encrypted",b"/etc/structural/structural-web.env",
                                   b"network-online.target",b"[Install]")),"GUEST_INHERITED_PRODUCTION_PATH")
    return raw,argv


def manifest(unit_raw,formal_entry,*,unit_sha,entry_sha,nonce):
    need(entry_sha==FORMAL_ENTRY_SHA and sha(formal_entry)==entry_sha,"FORMAL_ENTRY_PIN")
    guest,argv=render(unit_raw,expected_unit_sha=unit_sha,nonce=nonce)
    return {"status":"OFFLINE_DISPOSABLE_VM_PROFILE_ONLY","runtime_source":SOURCE,"nonce":nonce,
            "canonical_unit_inside_guest":UNIT,"actual_exec_argv":argv,"entry_sha256":entry_sha,
            "formal_unit_sha256":unit_sha,"guest_unit_sha256":sha(guest),"runtime_elf":ELF,
            "runtime_elf_sha256":ELF_SHA,"credential_slots":list(CREDENTIALS),
            "linux_guest_executed":False,"production_executed":False},guest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("unit",type=Path)
    parser.add_argument("entry",type=Path)
    parser.add_argument("unit_sha")
    parser.add_argument("entry_sha")
    parser.add_argument("nonce")
    parser.add_argument("--print-guest-unit",action="store_true")
    a=parser.parse_args()
    proof,guest=manifest(a.unit.read_bytes(),a.entry.read_bytes(),unit_sha=a.unit_sha,entry_sha=a.entry_sha,nonce=a.nonce)
    if a.print_guest_unit:sys.stdout.buffer.write(guest)
    else:print(json.dumps(proof,sort_keys=True,indent=2))


if __name__=="__main__":main()
