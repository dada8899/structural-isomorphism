from concurrent.futures import ThreadPoolExecutor
import json
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from web.backend.research.external_first_answer_contract import (
    CAP_UNITS, INPUT_SCHEMA, MODEL, OUTPUT_SCHEMA, PROJECT, PROVIDER, PURPOSE, TARGET, ContractError, template_digest,
)
from web.backend.research.external_first_answer_issuer_contract import (
    BALANCE_TARGET, CREDENTIAL_ENTRY, CREDENTIAL_ID, KEY_NAME, PROTOCOL,
    StartupBinding, consume_isolated_startup_once, require_live_startup_issuer,
)
from web.backend.research.provider_schemas import canonical

NOW=1780000010


def uuid():
    return str(uuid4())


@pytest.fixture
def enrollment(tmp_path):
    path=tmp_path.resolve()
    path.chmod(0o700)
    marker=path/"STRUCTURE-EXTERNAL-ISSUER-FIXTURE"
    marker.write_bytes(b"isolated external issuer rehearsal\n")
    marker.chmod(0o600)
    s=path.stat()
    expected=StartupBinding(startup_id=uuid(),source_commit="a"*40,source_manifest_digest="b"*64,
        runtime_closure_digest="c"*64,unit_digest="d"*64,database_dev=11,database_ino=22,
        receipts_dev=s.st_dev,receipts_ino=s.st_ino,schema_version=17,runtime_uid=981,runtime_gid=976,
        owner_principal=uuid(),owner_generation="e"*32,owner_epoch=1,owner_gate_id=uuid(),
        account_id=uuid(),economic_binding="same-structure-economic-account",funding_epoch=1,
        credential_incarnation="same-provider-incarnation",ledger_policy_digest="1"*64,endpoint_policy_digest="2"*64)
    secret=Ed25519PrivateKey.generate()
    public=secret.public_key().public_bytes_raw()
    draft={"protocol":PROTOCOL,"reviewer_key_id":KEY_NAME,"purpose":PURPOSE,"project":PROJECT,
        "provider":PROVIDER,"model":MODEL,"completion_target":TARGET,"balance_target":BALANCE_TARGET,
        "input_schema":INPUT_SCHEMA,"output_schema":OUTPUT_SCHEMA,"template_digest":template_digest(),
        "credential_entry":CREDENTIAL_ENTRY,"credential_id":CREDENTIAL_ID,"cap_units":CAP_UNITS,
        "currency":"CNY","scale":6,"approval_id":uuid(),"issued_at":NOW-10,"expires_at":NOW+30,
        "binding":expected.model_dump(mode="json")}
    def sign(**changes):
        payload=draft|changes
        return canonical({"approval":payload,"signature":secret.sign(canonical(payload)).hex()})
    return path,expected,public,sign


def test_verified_startup_consumes_durable_challenge_once_but_does_not_admit_live(enrollment):
    path,expected,key,sign=enrollment
    receipt=consume_isolated_startup_once(path,sign(),expected,key,now=NOW)
    assert receipt.startup_id==expected.startup_id and receipt.state=="closed"
    assert not (receipt.live_authority or receipt.credential_loaded or receipt.may_reserve or receipt.may_send)
    files=list(path.glob("spent-*.json"))
    assert len(files)==1 and files[0].stat().st_mode&0o777==0o600
    stored=json.loads(files[0].read_bytes())
    assert stored["approval_digest"]==receipt.approval_digest and stored["no_auto_retry"] is True
    assert expected.economic_binding not in files[0].read_text()
    for raw in (sign(),sign(approval_id=uuid())):
        with pytest.raises(ContractError,match="startup_challenge_already_consumed"):
            consume_isolated_startup_once(path,raw,expected,key,now=NOW)
    with pytest.raises(ContractError,match="live_external_issuer_unbound"):
        require_live_startup_issuer()


@pytest.mark.parametrize("field,value",[
    ("purpose","phenomenon_plan_v1"),("provider","openai"),("model","another-model"),
    ("balance_target","https://another.invalid/balance"),("completion_target","http://127.0.0.1/"),
    ("cap_units",CAP_UNITS+1),("credential_id","structural-deepseek-api-key"),
    ("credential_entry","legacy-credential-loader"),("template_digest","f"*64),
    ("expires_at",NOW),("issued_at",NOW+1),("expires_at",NOW+900),
])
def test_even_signed_wrong_scope_cannot_consume_a_startup(enrollment,field,value):
    path,expected,key,sign=enrollment
    with pytest.raises(ContractError,match="startup_approval_rejected"):
        consume_isolated_startup_once(path,sign(**{field:value}),expected,key,now=NOW)
    assert not list(path.glob("spent-*"))


@pytest.mark.parametrize("field,value",[
    ("source_commit","f"*40),("runtime_closure_digest","e"*64),("unit_digest","e"*64),
    ("database_ino",91),("owner_generation","f"*32),("economic_binding","different-account"),
    ("credential_incarnation","different-key"),("funding_epoch",2),("startup_id",uuid()),
])
def test_current_startup_facts_cannot_be_rebound(enrollment,field,value):
    path,expected,key,sign=enrollment
    changed=StartupBinding.model_validate(expected.model_dump()|{field:value})
    with pytest.raises(ContractError,match="startup_approval_rejected"):
        consume_isolated_startup_once(path,sign(),changed,key,now=NOW)
    assert not list(path.glob("spent-*"))


def test_wrong_signer_tampering_and_other_physical_receipt_directory_denied(enrollment):
    path,expected,key,sign=enrollment
    other_key=Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    tampered=json.loads(sign())
    tampered["approval"]["approval_id"]=uuid()
    for raw,pub in ((canonical(tampered),key),(sign(),other_key),(b" "+sign(),key)):
        with pytest.raises(ContractError,match="startup_approval_rejected"):
            consume_isolated_startup_once(path,raw,expected,pub,now=NOW)
    other=path/"second";other.mkdir(mode=0o700)
    with pytest.raises(ContractError,match="issuer_fixture_required"):
        consume_isolated_startup_once(other,sign(),expected,key,now=NOW)


def test_concurrent_consumers_cannot_reopen_the_same_startup(enrollment):
    path,expected,key,sign=enrollment
    raw=sign()
    def attempt():
        try:
            result=consume_isolated_startup_once(path,raw,expected,key,now=NOW)
            return result.state
        except ContractError as error:
            return str(error)
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda _:attempt(),range(2)))==["closed","startup_challenge_already_consumed"]
