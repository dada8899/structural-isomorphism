"""Pure DOC framing/data controls. No native send/profile positive is minted."""
from dataclasses import asdict,replace
import math
import http.client
import io

import pytest

from research.source_document_raw import (DocWireTarget,catalog,decode_doc_wire,doc_ipc,decode_doc_ipc,
    request_output_data,decode_commitment,RAW_CAP)
from research.source_document_access import (material_data,material_bytes,validate_material,APPROVED_FROM,
    approved_references,DocRequestWitness)
from research.source_policy import (_doc_response,_network_get,ActualDocOutcome,ActualTransportRetirement,
    require_doc_outcome,require_doc_retirement,SourceFailure,_doc_header,_ResponseSocket,HEADER_CAP)
from research.source_sec_access import DocRequestFlight
from research.source_spawn import SourceSpawnProcess
from research.evidence_schemas import canonical,sha256
from web.backend.tests.test_source_document_raw import data_records,uid,T,H


def wire_data():
    profile,rights=approved_references()
    return DocWireTarget(record_schema='DocWireTarget-v1',target=catalog()[0],access_profile_ref=profile,
        rights_digest=rights,request_id=uid(5),dispatch_id=uid(6),task_id=uid(2),write_epoch=1,slot_epoch=1,
        attempted_at=T,user_agent='StructureResearch/1 codec@example.invalid',valid_from=APPROVED_FROM,
        expires_at='2026-11-22T22:24:04Z',send_not_after=12.5)


def test_wire_codec_is_private_data_and_direct_network_or_process_is_denied():
    wire=wire_data()
    assert decode_doc_wire(asdict(wire))==wire
    assert 'example.invalid' not in repr(wire)
    assert wire.job_digest==sha256(canonical(asdict(wire)).encode())
    with pytest.raises(PermissionError):_network_get(wire)
    with pytest.raises(PermissionError):SourceSpawnProcess((None,wire,_network_get,None,12.5,(1,2,3,384,1)))
    for change in ({'send_not_after':True},{'send_not_after':math.inf},{'slot_epoch':True},{'user_agent':'bad\r\nheader'}):
        with pytest.raises(ValueError):replace(wire,**change)
    altered=asdict(wire);altered['extra']=True
    with pytest.raises(ValueError):decode_doc_wire(altered)


def test_public_material_codec_does_not_supply_approved_identity_or_runtime_authority():
    data=material_data(APPROVED_FROM,'StructureResearch/1 codec@example.invalid')
    encoded=material_bytes(data)
    assert validate_material(encoded)==data
    assert sha256(encoded)!=approved_references()[0].digest
    for alter in ('bool_revision','extra','expiry'):
        changed=material_data(APPROVED_FROM,'StructureResearch/1 codec@example.invalid')
        if alter=='bool_revision':changed['revision']=True
        elif alter=='extra':changed['ready']=True
        else:changed['network_identity']['expires_at']='2026-11-23T22:24:04Z'
        with pytest.raises(ValueError):validate_material(material_bytes(changed))


class ResponseData:
    """A pure parsed-header/body example, never a socket or native result."""
    def __init__(self,status=200,body=b'<html>codec</html>',headers=None):
        self.status,self.body,self.reads=status,body,[]
        self.headers={'Content-Type':'text/html','Content-Length':str(len(body))} if headers is None else headers
    def getheader(self,key):return self.headers.get(key)
    def read(self,cap):self.reads.append(cap);return self.body[:cap]


@pytest.mark.parametrize('status',[302,403,429,500])
def test_non200_observation_never_reads_body_or_assigns_complete_hash(status):
    data=ResponseData(status=status)
    observation,raw=_doc_response(wire_data(),data,T)
    assert not data.reads and raw==b'' and observation.http_status==status
    assert not observation.body_complete and observation.raw_length is None and observation.raw_sha256 is None
    assert observation.observed_failure_at is not None


@pytest.mark.parametrize('status',[200,403])
@pytest.mark.parametrize('headers',[{'Content-Length':'invalid'},{'Content-Encoding':'x'*65}])
def test_malformed_headers_keep_limited_actual_status_without_body(status,headers):
    data=ResponseData(status=status,headers=headers)
    with pytest.raises(SourceFailure) as observed:_doc_response(wire_data(),data,T)
    assert observed.value.http_status==status and not data.reads


@pytest.mark.parametrize('headers,body,code,complete,lower',[
    ({'Content-Type':'text/html'},b'<html>codec</html>','none',True,None),
    ({'Content-Type':'text/html'},b'<html>CAPTCHA</html>','access_denied',True,None),
    ({'Content-Type':'text/plain'},b'codec','invalid_source',True,None),
    ({'Content-Type':'text/html','Content-Encoding':'gzip'},b'encoded','invalid_source',False,None),
    ({'Content-Type':'text/html','Content-Length':str(RAW_CAP+1)},b'not-read','limit',False,None),
    ({'Content-Type':'text/html'},b'x'*(RAW_CAP+1),'limit',False,RAW_CAP+1),
    ({'Content-Type':'text/html','Transfer-Encoding':'chunked','Content-Length':'4'},b'body','invalid_source',False,None),
],ids=["identity","quarantine","media","encoding","declared-limit","stream-limit","ambiguous-framing"])
def test_data_framing_full_raw_or_explicit_no_body(headers,body,code,complete,lower):
    observation,raw=_doc_response(wire_data(),ResponseData(body=body,headers=headers),T)
    assert (observation.safe_code,observation.body_complete,observation.observed_lower_bound)==(code,complete,lower)
    if complete:assert raw==body and observation.raw_length==len(body) and observation.raw_sha256==sha256(body)
    else:assert raw==b'' and observation.raw_sha256 is None
    packet=doc_ipc(observation)
    assert len(packet)<=4096 and decode_doc_ipc(packet,wire_data())==observation
    assert b'example.invalid' not in packet


@pytest.mark.parametrize('body',[b'',b'short'])
def test_declared_length_premature_eof_is_unknown_not_known_policy_rejection(body):
    response=ResponseData(body=body,headers={'Content-Type':'text/html','Content-Length':'8'})
    with pytest.raises(SourceFailure) as unknown:_doc_response(wire_data(),response,T)
    assert unknown.value.http_status==200 and response.reads==[RAW_CAP+1]


@pytest.mark.parametrize('error',[OSError('synthetic read'),TimeoutError('synthetic timeout'),http.client.IncompleteRead(b'partial',8)])
def test_interrupted_body_keeps_known_status_but_creates_no_output_observation(error):
    class Interrupted(ResponseData):
        def read(self,cap):raise error
    with pytest.raises(SourceFailure) as unknown:_doc_response(wire_data(),Interrupted(),T)
    assert unknown.value.http_status==200 and unknown.value.__cause__ is error


@pytest.mark.parametrize('status',[100,101,103])
def test_doc_interim_is_rejected_before_any_final_header_read(status):
    initial=f'HTTP/1.1 {status} Interim\r\n\r\n'.encode()
    with pytest.raises(SourceFailure) as unknown:_doc_header(initial)
    assert unknown.value.http_status==status


@pytest.mark.parametrize('size',[HEADER_CAP,HEADER_CAP+1])
def test_doc_complete_final_header_exact_bound_and_no_trusted_oversize(size):
    fixed=b'HTTP/1.1 200 OK\r\nX-Padding: '+b'\r\nContent-Length: 0\r\n\r\n'
    header=b'HTTP/1.1 200 OK\r\nX-Padding: '+b'x'*(size-len(fixed))+b'\r\nContent-Length: 0\r\n\r\n'
    assert len(header)==size
    if size==HEADER_CAP:assert _doc_header(header)==200
    else:
        with pytest.raises(SourceFailure):_doc_header(header)


def test_original_paper_parser_still_skips_100_and_reads_final_body():
    prefix=b'HTTP/1.1 100 Continue\r\n\r\n'
    final=b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 6\r\n\r\n<html>'
    class BytesOnly:
        def __init__(self):self.stream=io.BytesIO(final)
        def recv(self,count):return self.stream.read(count)
    response=http.client.HTTPResponse(_ResponseSocket(BytesOnly(),prefix))
    try:
        response.begin()
        assert response.status==200 and response.read()==b'<html>'
    finally:response.close()


def test_ipc_foreign_job_and_unknown_native_capabilities_are_rejected():
    wire=wire_data();observation,_=_doc_response(wire,ResponseData(),T)
    with pytest.raises(ValueError):decode_doc_ipc(doc_ipc(replace(observation,job_digest=H)),wire)
    for factory in (ActualDocOutcome,ActualTransportRetirement,DocRequestFlight,DocRequestWitness):
        with pytest.raises((PermissionError,TypeError)):factory(True,True,True)
    with pytest.raises(PermissionError):require_doc_outcome(True,True)


@pytest.mark.parametrize('status,body,headers',[
    (200,b'<html>codec</html>',None),(200,b'<html>captcha</html>',None),(403,b'rejected',None),(302,b'redirect',None)])
def test_expected_first_commitment_data_recomputes_exact_refs_without_native_permission(status,body,headers):
    plan,_,receipt,_=data_records();wire=wire_data()
    observation,raw=_doc_response(wire,ResponseData(status,body,headers),T)
    retirement=replace(receipt.retirement,job_digest=wire.job_digest)
    row={'id':uid(5),'dispatch_id':uid(6),'task_id':plan.task_id,'chain_id':uid(8),'step_id':uid(9),
        'semantic':'fetch_source','target_digest':sha256(canonical({'host':wire.host,'path':wire.path}).encode()),
        'ordinal':1,'write_epoch':1,'outcome':'SENDING','execution_closed':0,'closure_ref':None,'closure_proof':None,
        'owner_gate_identity':'[1,2,501,384,1]','task_gate_identity':'[1,3,501,384,1]','started_at':T}
    artifact,result,c=request_output_data(plan,row,observation,retirement,artifact_ref=uid(4) if raw else None,
        receipt_ref=uid(7),admission_digest=H,producer_code_digest=H)
    assert decode_commitment(canonical(c))==c
    assert (artifact is None)==(status!=200)
    assert result.output_variant==('failed_no_body' if status!=200 else 'quarantined_complete' if b'captcha' in body else 'complete_candidate')
    assert c['result']['request_outcome']==('SUCCEEDED' if result.output_variant=='complete_candidate' else 'FAILED')
    # A fully consistent data commitment still cannot mint native permission.
    with pytest.raises(PermissionError):require_doc_outcome(c,plan)
    with pytest.raises(ValueError):request_output_data(plan,dict(row,outcome='SUCCEEDED'),observation,retirement,
        artifact_ref=uid(4) if raw else None,receipt_ref=uid(7),admission_digest=H,producer_code_digest=H)
