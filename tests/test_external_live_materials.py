"""Public snapshots/generated signing seeds only; never real materials/keys."""
import base64,copy,hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from web.backend.services import external_price_materials as price,external_startup_materials as startup
from web.backend.services import external_live_sender as sender
HERE=Path(__file__).resolve().parents[1]
SNAPSHOT=HERE.parent/'deepseek-public-current-20261110/pricing-cny.html'

def document():return SNAPSHOT.read_bytes()
def test_official_snapshot_actual_prices_separate_from_ceil():
 raw=document();assert hashlib.sha256(raw).hexdigest()=='6205cf5d53a7903827bf21938eefb6a8ab6041bb5a73fcf43e4bdd6adc8d344b'
 material=price.observe_document(raw,now=100)
 assert material['observation']['actual_peak_input_miss_units_per_million']==2000000
 assert material['observation']['actual_peak_output_units_per_million']==8000000
 assert price.validate_observation(price.canonical(material),price.ceiling_digest(),now=101,upper_units=2129920)['actual_upper_units']==2006144
 refreshed=price.observe_document(raw,now=200)
 assert material['ceiling_sha256']==refreshed['ceiling_sha256'] and price.sha(price.canonical(material))!=price.sha(price.canonical(refreshed))

def test_actual_lower_price_is_not_replaced_by_ceiling():
 raw=document().replace(b'2\xe5\x85\x83',b'1\xe5\x85\x83')
 # The page is UTF8 HTML text; replacement can also affect unrelated rows.
 actual=price.parse_official_document(raw)
 assert actual['actual_peak_input_miss_units_per_million']==1000000
 m=price.observe_document(raw,now=100);assert m['ceiling']==price.ceiling()
 assert price.validate_observation(price.canonical(m),price.ceiling_digest(),now=101,upper_units=2129920)['actual_upper_units']<2006144

@pytest.mark.parametrize('fault',['expired','future','over','mixed','ceil'])
def test_stale_over_ceiling_or_mixed_material_denied(fault):
 m=price.observe_document(document(),now=100)
 if fault=='expired':now=100+86400
 else:now=101
 if fault=='future':m['observation']['issued_at']=102
 if fault=='over':m['observation']['actual_peak_output_units_per_million']=9000000
 if fault=='mixed':m['observation']['official_document_sha256']='0'*64
 if fault=='ceil':m['ceiling']['peak_output_ceil_units_per_million']=9000000
 with pytest.raises((ValueError,price.MaterialError)):price.validate_observation(price.canonical(m),price.ceiling_digest(),now=now,upper_units=2129920)

def load_cli():
 s=importlib.util.spec_from_file_location('root_cli',HERE/'scripts/maintain-external-live-materials.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def test_new_overprice_atomically_supersedes_old_valid_not_silently_reused(monkeypatch):
 cli=load_cli();writes=[]
 monkeypatch.setattr(cli.materials,'load_approved_pair',lambda:{'price_ceiling_sha256':cli.prices.ceiling_digest()})
 raw=document().replace(b'8\xe5\x85\x83',b'9\xe5\x85\x83')
 monkeypatch.setattr(cli,'fetch_official',lambda d:raw)
 monkeypatch.setattr(cli.materials,'replace_root_material',lambda path,raw:writes.append(json.loads(raw)))
 result=cli.refresh_price();assert result['status']=='EXTERNAL_CLOSED_PRICE_OVER_CEILING' and writes[-1]['status']=='closed'

def test_startup_missing_input_closes_previous_approval_and_does_not_read_seed(monkeypatch):
 cli=load_cli();events=[]
 monkeypatch.setattr(cli.materials,'replace_root_material',lambda path,raw:events.append(json.loads(raw)))
 monkeypatch.setattr(cli.materials,'load_approved_pair',lambda:(_ for _ in ()).throw(FileNotFoundError()))
 monkeypatch.setattr(cli,'read_signer_seed',lambda:pytest.fail('no secret before approved deployment comparison'))
 assert cli.fresh_startup()['status']=='EXTERNAL_CLOSED_STARTUP_MATERIAL'
 assert events==[{'status':'external_closed','reason':'fresh_startup_pending'}]

def test_pure_module_import_does_not_import_issuer_or_crypto():
 code="import importlib.util,sys;"+''.join("s=importlib.util.spec_from_file_location('m',"+repr(str(HERE/'web/backend/services'/name))+");m=importlib.util.module_from_spec(s);s.loader.exec_module(m);" for name in ('external_price_materials.py','external_startup_materials.py'))+"assert not any(n.startswith('cryptography') or 'issuer_contract' in n for n in sys.modules)"
 p=subprocess.run([sys.executable,'-I','-S','-B','-c',code],capture_output=True,timeout=5)
 assert p.returncode==0 and p.stdout==b'' and p.stderr==b''

def test_legacy17_raw_price_digest_still_exact(monkeypatch):
 raw=b'public legacy proof';policy=SimpleNamespace(price_basis_sha256='0'*64)
 monkeypatch.setattr(sender.production,'_fixed_file',lambda *args:raw)
 with pytest.raises(Exception,match='price_basis_unbound'):sender._price_window(SimpleNamespace(schema_version=17),policy,now=100)


def test_startup_ids_fresh_but_binding_and_operation_spent_untouched():
 d={'approval_template':{'binding':{'schema_version':18,'account_id':'same'}}}
 a=startup.fresh_payload(d,now=100);b=startup.fresh_payload(d,now=101)
 assert a['binding']['startup_id']!=b['binding']['startup_id'] and a['approval_id']!=b['approval_id']
 assert a['binding']['account_id']==b['binding']['account_id']=='same' and a['expires_at']-a['issued_at']==120
 assert d=={'approval_template':{'binding':{'schema_version':18,'account_id':'same'}}}


def manifest_fixture():
 source='a'*40;path='/srv/structural-isomorphism/releases/'+source+'/web/backend/main.py';runtime='/srv/structural-isomorphism/runtimes/a4'
 row={'sha256':'c'*64,'bytes':1,'mode':0o640,'uid':0,'gid':976};files={path:dict(row)}
 origins={n:runtime+'/lib/python3.11/site-packages/'+n+'.py' for n in ('cryptography','cffi','_cffi_backend','pycparser')}
 for name in origins.values():files[name]=dict(row)
 files['/opt/python']=dict(row,sha256='d'*64,mode=0o755,gid=0)
 fixed=('/etc/systemd/system/structural-web.service','/etc/ssl/certs/ca-certificates.crt','/etc/structural/external-first-answer-source.json','/etc/structural/external-first-answer-economic-binding.json')
 for name in fixed:files[name]=dict(row)
 checks=sorted((n,r['sha256']) for n,r in files.items() if n.startswith(runtime+'/') or n=='/opt/python')
 digest=startup.sha(json.dumps(checks,separators=(',',':'),ensure_ascii=False).encode())
 return {'schema':'external-live-approved-deployment-v1','reviewer_public_key_hex':'b'*64,
  'approval_template':{'binding':{'schema_version':18,'source_commit':source,'unit_digest':'c'*64,'source_manifest_digest':'c'*64,'runtime_closure_digest':digest}},
  'files':files,'purpose_snapshot':{'status':'active'},'price_ceiling_sha256':price.ceiling_digest(),
  'runtime_root':runtime,'interpreter':'/opt/python','signature_origins':origins}

def test_fixed_pair_match_tamper_and_partial_pair_denied():
 d=manifest_fixture();raw=startup.canonical(d);pin=startup.sha(raw)
 assert startup.approved_manifest(raw,pin)==d
 for body,expected in ((raw+b' ',pin),(raw,'0'*64),(b'{}',pin)):
  with pytest.raises(startup.MaterialError):startup.approved_manifest(body,expected)

def test_expected_material_comparison_never_learns_changed_bytes(monkeypatch):
 d=manifest_fixture();d['files']={'/approved':{'sha256':startup.sha(b'x'),'bytes':1,'mode':0o640,'uid':0,'gid':0}}
 with pytest.raises(startup.MaterialError,match='approved_deployment_changed'):
  startup.verify_expected_files(d,reader=lambda *a,**k:b'y')


def test_signer_unavailable_to_web_and_no_provider_secret_in_root_unit():
 root=(HERE/'docs/deployment/structural-external-startup-material.service').read_text()
 assert 'User=root' in root and 'PrivateNetwork=yes' in root and startup.SIGNER_ID in root
 assert 'structural-external-first-answer-deepseek-key' not in root and '||' not in root
 timer=(HERE/'docs/deployment/structural-external-price-refresh.timer').read_text();assert 'OnUnitActiveSec=6h' in timer

def test_price_window18_reads_latest_generation_even_same_ceiling(monkeypatch):
 current=[price.canonical(price.observe_document(document(),now=100))]
 monkeypatch.setattr(sender.production,'_fixed_file',lambda *a:current[0])
 policy=SimpleNamespace(price_basis_sha256=price.ceiling_digest(),upper_units=2129920)
 first=sender._price_window(SimpleNamespace(schema_version=18),policy,now=101)
 current[0]=price.canonical(price.observe_document(document(),now=200))
 second=sender._price_window(SimpleNamespace(schema_version=18),policy,now=201)
 assert first['observation_sha256']!=second['observation_sha256'] and first['valid_until']!=second['valid_until']
 current[0]=price.canonical(price.closed_material('over_ceiling',now=202))
 with pytest.raises(Exception,match='price_basis_unbound'):sender._price_window(SimpleNamespace(schema_version=18),policy,now=203)

def test_invalidation_failure_is_not_reported_closed_success(monkeypatch):
 cli=load_cli()
 monkeypatch.setattr(cli.materials,'replace_root_material',lambda *a:(_ for _ in ()).throw(OSError('synthetic IO failure')))
 with pytest.raises(OSError):cli.fresh_startup()

def test_signing_helper_no_caller_selected_deployment_or_payload(monkeypatch):
 cli=load_cli();events=[]
 monkeypatch.setattr(cli.materials,'load_approved_pair',lambda:(_ for _ in ()).throw(cli.materials.MaterialError('missing approved pair')))
 monkeypatch.setattr(cli,'read_signer_seed',lambda:pytest.fail('no seed read before fixed approved pair'))
 with pytest.raises(cli.materials.MaterialError):cli.sign_fresh_approved_startup()
 with pytest.raises(TypeError):cli.sign_fresh_approved_startup({'fake':'deployment'},{'fake':'payload'})

def test_fresh_signed_startups_use_existing_once_contract_and_do_not_clear_operation_spent(tmp_path):
 from uuid import uuid4
 from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
 from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
 from web.backend.research.external_first_answer_issuer_contract import OwnerKeyStartupBinding,consume_isolated_startup_once
 from web.backend.research.external_first_answer_contract import template_digest
 from web.backend.research.provider_schemas import canonical
 tmp_path.chmod(0o700);marker=tmp_path/'STRUCTURE-EXTERNAL-ISSUER-FIXTURE';marker.write_bytes(b'isolated external issuer rehearsal\n');marker.chmod(0o600)
 s=tmp_path.stat();u=lambda:str(uuid4())
 binding={'source_commit':'a'*40,'source_manifest_digest':'b'*64,'runtime_closure_digest':'c'*64,'unit_digest':'d'*64,
  'database_dev':1,'database_ino':2,'receipts_dev':s.st_dev,'receipts_ino':s.st_ino,'schema_version':18,'runtime_uid':981,'runtime_gid':976,
  'owner_principal':u(),'owner_generation':'e'*32,'owner_epoch':1,'owner_gate_id':u(),'account_id':u(),'economic_binding':'local-opaque-binding',
  'funding_epoch':1,'credential_incarnation':u(),'ledger_policy_digest':'1'*64,'endpoint_policy_digest':'2'*64,
  'credential_source':'owner_supplied','authorization_event_ref':u(),'payer_identity_status':'unknown','payer_id':None}
 d={'approval_template':{'protocol':'external-first-answer-startup-approval-v1','reviewer_key_id':'external-first-answer-startup-review-v1',
  'purpose':'external-first-answer-question-v1','project':'structure-rebuild-v1','provider':'deepseek','model':'deepseek-flash',
  'completion_target':'https://api.deepseek.com/chat/completions','balance_target':'https://api.deepseek.com/user/balance',
  'input_schema':'external-first-answer-question-only-v1','output_schema':'external-first-answer-unverified-candidate-v1',
  'template_digest':template_digest(),'credential_entry':'run-formal-main-external-first-answer-v1','credential_id':'structural-external-first-answer-deepseek-key',
  'cap_units':300000000,'currency':'CNY','scale':6,'binding':binding}}
 secret=Ed25519PrivateKey.generate();public=secret.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
 spent=tmp_path/('spent-operation-'+'f'*64);spent.write_text('f'*64+'\n');spent.chmod(0o600)
 ids=[]
 for now in (1780000010,1780000011):
  payload=startup.fresh_payload(d,now=now);expected=OwnerKeyStartupBinding.model_validate(payload['binding']);ids.append(expected.startup_id)
  raw=canonical({'approval':payload,'signature':secret.sign(canonical(payload)).hex()})
  receipt=consume_isolated_startup_once(tmp_path,raw,expected,public,now=now)
  assert receipt.state=='closed' and not receipt.credential_loaded and not receipt.may_send
  with pytest.raises(Exception,match='already_consumed'):consume_isolated_startup_once(tmp_path,raw,expected,public,now=now)
 assert len(set(ids))==2 and len(list(tmp_path.glob('spent-*.json')))==2
 assert spent.read_text()=='f'*64+'\n'

def test_lower_actual_price_does_not_reduce_approved_worst_case_bound():
 raw=document().replace(b'2\xe5\x85\x83',b'1\xe5\x85\x83')
 m=price.observe_document(raw,now=100)
 with pytest.raises(price.MaterialError,match='upper_insufficient'):
  price.validate_observation(price.canonical(m),price.ceiling_digest(),now=101,upper_units=1500000)


def test_linux_service_groups_caps_are_minimal_and_db_read_is_not_implied_by_group():
 root=(HERE/'docs/deployment/structural-external-startup-material.service').read_text()
 priceunit=(HERE/'docs/deployment/structural-external-price-refresh.service').read_text()
 assert 'User=root' in root and 'Group=976' in root and 'CapabilityBoundingSet=CAP_DAC_READ_SEARCH' in root
 assert 'CAP_DAC_OVERRIDE' not in root and 'CAP_CHOWN' not in root
 assert 'Group=976' in priceunit and 'CapabilityBoundingSet=\n' in priceunit and 'CAP_DAC_READ_SEARCH' not in priceunit
 fragment=(HERE/'docs/deployment/structural-web-external-materials.main-unit.fragment').read_text()
 assert 'NOT A SYSTEMD DROP-IN' in fragment and 'Never install under *.service.d' in fragment
 assert not (HERE/'docs/deployment/structural-web-external-materials.conf').exists()

def test_signer_wrong_current_release_fails_before_crypto_or_seed(monkeypatch):
 cli=load_cli();d=manifest_fixture()
 monkeypatch.setattr(cli,'ROOT',Path('/srv/structural-isomorphism/releases/'+'f'*40))
 monkeypatch.setattr(cli.materials,'load_approved_pair',lambda:d)
 monkeypatch.setattr(cli,'read_signer_seed',lambda:pytest.fail('wrong release must not read secret'))
 with pytest.raises(cli.materials.MaterialError,match='signer_current_release_mismatch'):cli.sign_fresh_approved_startup()

def test_signer_self_and_helpers_must_be_source_closed(monkeypatch):
 cli=load_cli();d=manifest_fixture();source=d['approval_template']['binding']['source_commit'];approved=Path('/srv/structural-isomorphism/releases')/source
 monkeypatch.setattr(cli,'ROOT',approved);monkeypatch.setattr(cli.Path,'resolve',lambda p,strict=True:p)
 monkeypatch.setattr(cli,'__file__',str(approved/'scripts/maintain-external-live-materials.py'))
 monkeypatch.setattr(cli.materials,'__file__',str(approved/'web/backend/services/external_startup_materials.py'))
 monkeypatch.setattr(cli.prices,'__file__',str(approved/'web/backend/services/external_price_materials.py'))
 doc={'source_sha':source,'members':[]};body=cli.materials.canonical(doc)
 d['approval_template']['binding']['source_manifest_digest']=cli.materials.sha(body)
 d['files']['/etc/structural/external-first-answer-source.json']['bytes']=len(body)
 monkeypatch.setattr(cli.materials,'fixed_file',lambda *a,**k:body)
 with pytest.raises(cli.materials.MaterialError,match='signer_own_source_not_approved'):cli.verify_signing_source_root(d)

def test_approved_zero_byte_file_is_valid_but_pair_is_never_empty():
 d=manifest_fixture();path=d['runtime_root']+'/lib/python3.11/site-packages/empty/py.typed'
 d['files'][path]={'sha256':startup.sha(b''),'bytes':0,'mode':0o640,'uid':0,'gid':976}
 checks=sorted((n,r['sha256']) for n,r in d['files'].items() if n.startswith(d['runtime_root']+'/') or n==d['interpreter'])
 d['approval_template']['binding']['runtime_closure_digest']=startup.sha(json.dumps(checks,separators=(',',':'),ensure_ascii=False).encode())
 body=startup.canonical(d);assert startup.approved_manifest(body,startup.sha(body))==d
 with pytest.raises(startup.MaterialError):startup.approved_manifest(b'',startup.sha(b''))

def test_empty_expected_file_is_read_with_explicit_permission(monkeypatch):
 d=manifest_fixture();d['files']={'/approved-empty':{'sha256':startup.sha(b''),'bytes':0,'mode':0o640,'uid':0,'gid':976},'/etc/structural/external-first-answer-source.json':{'sha256':startup.sha(b'x'),'bytes':1,'mode':0o640,'uid':0,'gid':976}}
 calls=[]
 def reader(path,limit,**kw):
  calls.append((str(path),kw.get('allow_empty')))
  if str(path)=='/approved-empty':return b''
  raise startup.MaterialError('stop after real empty row')
 monkeypatch.setattr(startup.Path,'stat',lambda *a,**k:SimpleNamespace(st_uid=0,st_gid=976))
 with pytest.raises(startup.MaterialError,match='stop after real empty row'):startup.verify_expected_files(d,reader=reader)
 assert calls[0]==('/approved-empty',True)
