"""Offline rules and controlled actual Main; neither mints live authority.

Actual B/C, Linux root metadata and paid sends remain separate integration gates.
"""
from dataclasses import replace
import json
import pickle
import stat
import pytest
from research import native_live_grant as live,plan_native as ports
from research.errors import ResearchError
from research.provider_schemas import canonical,digest


def declaration():
    """Synthetic identifiers: this pure declaration has no resource authority."""
    return dict(protocol='native-live-owner-grant-v1',project_ref='structure-rebuild-v1',state='active',
        grant_id='10000000-0000-4000-8000-000000000001',grant_epoch=1,
        principal_id='10000000-0000-4000-8000-000000000002',auth_generation='a'*32,principal_epoch=1,
        owner_gate_id='10000000-0000-4000-8000-000000000005',database_identity=[1,2],owner_gate_identity=[1,3,1001,384,1],
        flight_identity=[1,4,1001,1001,384,1],account_id='10000000-0000-4000-8000-000000000003',
        economic_binding='10000000-0000-4000-8000-000000000004',credential_incarnation='synthetic-no-key',
        approved_cap_units=300000000,risk_margin_units=2129920,runtime_uid=1001,runtime_gid=1001,
        provider='deepseek',model='deepseek-flash',network_policy='deepseek-fixed-https-v1',
        runtime_digest='c'*64,approved_code_digest='d'*64,purpose_domains=live.fixed_purpose_domains())


def test_grant_pure_decoder_and_common_facts_stable_without_authority():
    value=declaration();a=live.decode_grant(canonical(value));b=live.decode_grant(json.dumps(value,indent=2).encode())
    assert a==b and a.data()==value
    facts=live.stable_facts(a,'e'*64)
    assert facts==live.stable_facts(b,'e'*64) and len(facts)<=16384
    decoded=json.loads(facts)
    assert decoded['grant']==value and decoded['mode']=='native_live'
    assert 'purpose_domain' not in decoded and 'pid' not in decoded
    assert digest(facts)!=digest(live.stable_facts(a,'f'*64))
    assert tuple(live._GRANTS.values())==() and tuple(live._SESSIONS.values())==()


@pytest.mark.parametrize('field,value',[
    ('grant_epoch',True),('grant_epoch',0),('principal_epoch',-1),('approved_cap_units',300000001),
    ('risk_margin_units',0),('provider','other'),('model','other'),('network_policy','loopback'),
    ('protocol','other'),('project_ref','other'),('runtime_uid',False),('runtime_gid',-1),
    ('auth_generation','not-generation'),('runtime_digest','f'*63),('database_identity',[1]),
    ('owner_gate_identity',[1,3,1001,420,1]),('flight_identity',[1,4,1001,1001,384,2]),
    ('state','executable'),('grant_id','not-a-uuid'),('purpose_domains',{}),
])
def test_grant_rejects_unsafe_field(field,value):
    data=declaration();data[field]=value
    with pytest.raises(ValueError):live.decode_grant(canonical(data))


@pytest.mark.parametrize('kind',['unknown','duplicate','float','nan','longint','reverse','extra_domain','wrong_self','bad_utf8','oversize'])
def test_grant_rejects_ambiguous_or_unbounded_wire(kind):
    data=declaration();raw=canonical(data)
    if kind=='unknown':data['extra']=0;raw=canonical(data)
    if kind=='duplicate':raw=raw[:-1]+b',"grant_epoch":1}'
    if kind=='float':raw=raw.replace(b'"grant_epoch":1',b'"grant_epoch":1.0')
    if kind=='nan':raw=raw.replace(b'"grant_epoch":1',b'"grant_epoch":NaN')
    if kind=='longint':raw=raw.replace(b'"grant_epoch":1',b'"grant_epoch":9999999999999999999999999999')
    if kind=='reverse':data['purpose_domains'].reverse();raw=canonical(data)
    if kind=='extra_domain':data['purpose_domains'][0]['extra']=0;raw=canonical(data)
    if kind=='wrong_self':data['purpose_domains'][0]['purpose']=live.EVIDENCE;raw=canonical(data)
    if kind=='bad_utf8':raw=b'\xff'
    if kind=='oversize':raw=b' '*16385
    with pytest.raises((ValueError,UnicodeError)):live.decode_grant(raw)


def metadata():
    directory=live.FileMetadata(1,10,0,0,0o755,2,stat.S_IFDIR,100,1,1)
    chain=(directory,replace(directory,ino=11),replace(directory,ino=12,gid=1001,mode=0o750))
    leaf=live.FileMetadata(1,13,0,1001,0o440,1,stat.S_IFREG,100,1,1)
    return chain,leaf


@pytest.mark.parametrize('kind',['valid','writable_parent','wrong_uid','wrong_group','symlink','hardlink','oversize','bad_directory'])
def test_metadata_rules_are_pure_not_witnesses(kind):
    chain,leaf=metadata()
    if kind=='writable_parent':chain=(replace(chain[0],mode=0o775),*chain[1:])
    if kind=='wrong_uid':leaf=replace(leaf,uid=1001)
    if kind=='wrong_group':leaf=replace(leaf,gid=1002)
    if kind=='symlink':leaf=replace(leaf,kind=stat.S_IFLNK)
    if kind=='hardlink':leaf=replace(leaf,nlink=2)
    if kind=='oversize':leaf=replace(leaf,size=16385)
    if kind=='bad_directory':chain=(*chain[:2],replace(chain[2],mode=0o755))
    if kind=='valid':
        assert live.validate_control_metadata(chain,leaf,runtime_uid=1001,runtime_gid=1001) is None
    else:
        with pytest.raises(ValueError):live.validate_control_metadata(chain,leaf,runtime_uid=1001,runtime_gid=1001)


def test_missing_c_rejects_before_control_file_or_flight_io(monkeypatch):
    calls=[]
    def forbidden(*args,**kwargs):calls.append(True);raise AssertionError('control file IO before actual C')
    monkeypatch.setattr(live.os,'open',forbidden)
    with pytest.raises(ResearchError) as error:live.read_native_live_grant(object(),main_context={'ready':True})
    assert error.value.code=='FUNDING_CLOSED' and calls==[]
    with pytest.raises(ResearchError):live.claim_live_flight(object(),declaration(),main_context=object())
    assert calls==[]


@pytest.mark.parametrize('factory', ['grant','flight','session','authority','bootstrap'])
def test_direct_dto_or_factory_token_cannot_mint_live_resources(factory):
    if factory=='grant':
        with pytest.raises(TypeError):live.NativeLiveGrantWitness(None,None,None,(),None,None,_factory=live._FACTORY)
    elif factory=='flight':
        with pytest.raises(TypeError):live.NativeLiveFlightLease(None,None,None,None,_factory=live._FACTORY)
    elif factory=='session':
        with pytest.raises(TypeError):live.NativeLiveSession(None,None,None,None,None,b'{}',None,_factory=live._FACTORY)
    elif factory=='authority':
        with pytest.raises(PermissionError):ports._live_authority(declaration(),object())
    else:
        with pytest.raises(ResearchError) as error:ports.bootstrap_native_owner_authority(object())
        assert error.value.code=='FUNDING_CLOSED'


def test_partial_cleanup_attempts_every_owned_item_without_erasing_errors():
    visited=[]
    class Owned:
        def __init__(self,name,fail):self.name,self.fail=name,fail
        def close(self):
            visited.append(self.name)
            if self.fail:raise OSError('synthetic close fault')
    assert live._close_all((Owned('first',True),Owned('second',False),Owned('third',True)))==('OSError','OSError')
    assert visited==['first','second','third']
    failure=live.NativeLiveStartFailure(object(),(),uncertain=True)
    with pytest.raises(TypeError):pickle.dumps(failure)


def test_missing_code_closure_never_becomes_synthetic_approval(tmp_path,monkeypatch):
    # Pure fixed-path hashing over owned bytes, never a grant/factory positive.
    assert len(live.APPROVED_PATHS)==len(set(live.APPROVED_PATHS))==25
    root=tmp_path/'synthetic-closure'
    for relative in live.APPROVED_PATHS:
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'# synthetic hash input only\n')
    monkeypatch.setattr(live,'__file__',str(root/'web/backend/research/native_live_grant.py'))
    expected=digest(canonical({path:digest((root/path).read_bytes()) for path in live.APPROVED_PATHS}))
    assert live.approved_code_digest()==expected
    (root/live.APPROVED_PATHS[-1]).unlink()
    with pytest.raises(ResearchError) as error:live.approved_code_digest()
    assert error.value.code=='FUNDING_CLOSED'


def test_actual_controlled_owner_missing_live_ports_never_rebinds_or_writes_ledger(tmp_path):
    from .test_research_evidence_method_plan import actual
    from .test_research_evidence_method_native import installed
    from .test_research_funded_plan import provider
    with actual(tmp_path) as (_,_,store,actor),provider() as (server,calls),installed(store,actor,server) as resource:
        def snapshot():
            with store.transaction() as conn:
                assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==15
                return tuple(tuple(row) for table in ('research_plan_native_funding','research_funding_accounts')
                    for row in conn.execute('SELECT * FROM '+table+' ORDER BY rowid'))
        before=snapshot()
        for action in (
            lambda:live.read_native_live_grant(store,main_context={'ready':True,'owner':actor.principal if hasattr(actor,'principal') else 'synthetic'}),
            lambda:live.bind_live_authority(store,declaration(),{'flight':True},{'credential':True},main_context=object()),
            lambda:ports.revoke_live_funding(store,{'session':True},lifecycle_scope={'action':'revoke'}),
            lambda:ports.mint_runtime_permit(resource.permit.provision,purpose=live.SELF),
        ):
            with pytest.raises((ResearchError,PermissionError)):action()
        assert before==snapshot() and calls==[]
        assert ports.installation(store)[1] is resource and resource.mode=='controlled_fixture'
        assert ports.live_session(store) is None


def test_live_native_capability_classes_have_no_callback_dictionary():
    for cls in (live.NativeLiveSession,live.NativeLiveGrantWitness,live.NativeLiveFlightLease,
                ports.OwnerFundingAuthorityLease,ports.NativePlanProvision,ports.NativeRuntimePermit):
        # Uninitialized layout observation only; no registry, scope or authority.
        assert not hasattr(object.__new__(cls),'__dict__')


def test_credential_message_is_exact_canonical_input_without_key_or_authority():
    value=declaration();data=live.decode_grant(canonical(value))
    message=live._credential_message(data)
    assert type(message) is bytes and message==canonical(['native-live-credential-v1',value])
    value['state']='revoke_requested'
    with pytest.raises(ValueError):live._credential_message(live.decode_grant(canonical(value)))
    with pytest.raises(ValueError):live._credential_message({'grant':True})


def test_credential_bootstrap_and_pairing_never_accept_dto_or_unregistered_exact_objects():
    for grant,flight in ((declaration(),{'flight':True}),
            (object.__new__(live.NativeLiveGrantWitness),object.__new__(live.NativeLiveFlightLease))):
        with pytest.raises(ResearchError) as error:live.credential_bootstrap_binding(grant,flight,main_context={'ready':True})
        assert error.value.code=='FUNDING_CLOSED'
    for session in ({'credential':True},object(),object.__new__(live.NativeLiveSession)):
        assert live.credential_session_binding(session,object()) is False
