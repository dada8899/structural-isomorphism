"""Spawn-safe dev component reopen/fault entrypoints; no Main capability."""
from pathlib import Path
import json
import os


def component_store(path):
    from services.auth_store import AuthStore
    from research import ResearchStore
    path = Path(path)
    assert os.environ['STRUCTURAL_ENV'] == 'test'
    assert os.environ['AUTH_DEV_MODE'] == 'true'
    assert Path(os.environ['AUTH_DATA_DIR']) == path.parent
    store = ResearchStore(AuthStore(path))
    assert not store._formal_mode() and not store.auth_store._private_auth
    with store.transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0] == 14
    return store


def reopen(path, task_id, output):
    from research import ResearchRunner
    from research.authorization import AuthorizationGate
    store = component_store(path)
    with AuthorizationGate(store).source_task_gate(task_id) as lease:
        identity = lease.identity
    state = ResearchRunner(store).run_once(task_id)
    Path(output).write_text(json.dumps({'state': state, 'identity': identity}))


def crash_after_claim(path, task_id, proof):
    from functools import partial
    from research import ResearchRunner, source_workflow
    from research.source_policy import PinnedPublicTransport
    from .source_http_fixture import get_local
    from .research_component_fixture import after_native_commit
    store = component_store(path)
    with after_native_commit(store, caller=source_workflow.run_source_once.__code__,
            query='SELECT started FROM research_source_runs WHERE task_id=?', parameters=(task_id,),
            expected=(1,), action=lambda: os._exit(81), proof_path=proof):
        ResearchRunner(store, source_transport=PinnedPublicTransport(_worker=partial(get_local, 0))).run_once(task_id)
    raise AssertionError('owned claim kill point was not reached')


def read_plan(path, rid, ref, cookie, output):
    from fastapi.testclient import TestClient
    from .test_research_persistence import app
    component_store(path)
    with TestClient(app()) as client:
        client.cookies.set('phase_session', cookie)
        response = client.get('/api/research/' + rid + '/plan-results/' + ref)
        assert response.status_code == 200, response.text
        Path(output).write_text(json.dumps(response.json(), sort_keys=True, ensure_ascii=False))


def archived_formula_read(project, owned, path, original):
    """Run the real archived12 consumer, separate from current Main15 admission."""
    import subprocess
    import sys
    import hashlib
    from .plan_v12_reference import reconstruct
    from .method_v13_reference import historical_bytes
    project, owned = Path(project), Path(owned)
    package, _, manifest = reconstruct(project, owned / 'reader12')
    # The immutable R12 plan producer never reads a formula. Its consumer
    # needs these four formula-only dependencies already pinned by Source10.
    closure = json.loads(manifest.read_text())['files']
    formula = json.loads((project / 'web/backend/tests/reference/source_v10/manifest.json').read_text())['files']
    for name in ('formula_check', 'formula_policy', 'formula_public', 'formula_result_adapter'):
        relative = 'web/backend/research/' + name + '.py'
        assert relative not in closure and formula[relative]['source'] == 'current_exact'
        raw = historical_bytes(project, relative, formula[relative]['sha256'])
        assert hashlib.sha256(raw).hexdigest() == formula[relative]['sha256']
        (package / relative).write_bytes(raw)
        closure[relative] = formula[relative]
    consumer_manifest = owned / 'reader12-consumer-closure.json'
    consumer_manifest.write_text(json.dumps({'files': closure}, sort_keys=True))
    output = owned / 'reader12-result.json'
    environment = dict(os.environ, REVIEW_SOURCE_ROOT=str(package),
                       ARCHIVED12_ROOT=str(package), ARCHIVED12_MANIFEST=str(consumer_manifest))
    roots = [str(package / 'web/backend'), str(package)]
    guard = sys.modules.get('audit_bootstrap')
    if guard is not None:
        roots.insert(0, str(Path(guard.__file__).parent))
    environment['PYTHONPATH'] = os.pathsep.join(roots)
    with (owned / 'reader12.log').open('wb') as log:
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), 'archived12',
                                str(path), str(original), str(output)], cwd=package,
                               env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=20)
    assert child.returncode == 0, (owned / 'reader12.log').read_text()
    result = json.loads(output.read_text())
    assert result['schema_version'] == 12 and result['source_hashes_verified']
    return result


def _archived12(path, original, output):
    """Historical synthetic HTTP only, using the immutable R12 code closure.

    Its old fixture feature overrides remain confined to that archived process,
    as in the existing historical producers. No current binding is admitted.
    """
    import hashlib
    import sys
    from urllib.parse import parse_qs, urlsplit
    root = Path(os.environ['ARCHIVED12_ROOT']).resolve()
    manifest = json.loads(Path(os.environ['ARCHIVED12_MANIFEST']).read_text())['files']
    def verified_sources():
        hashes = {}
        for name, module in tuple(sys.modules.items()):
            if name.split('.')[0] not in ('api', 'services', 'research') and not name.startswith('web.backend'):
                continue
            source = Path(module.__file__).resolve()
            assert source.is_relative_to(root) and source.suffix == '.py', 'mixed historical consumer'
            relative = source.relative_to(root).as_posix()
            sha = hashlib.sha256(source.read_bytes()).hexdigest()
            assert manifest[relative]['sha256'] == sha
            hashes[relative] = sha
        return hashes
    verified_sources()
    path = Path(path)
    assert os.environ['STRUCTURAL_ENV'] == 'prod'
    from services import runtime_paths as paths
    paths.STATE_ROOT = path.parent
    paths.CACHE_ROOT = path.parent.parent / 'cache'
    paths.LOG_ROOT = path.parent / 'logs'
    beta = 'https://beta.structural.bytedance.city'
    os.environ.update(AUTH_ENABLED='true', AUTH_SITE_ROLE='beta', AUTH_LINK_BASE_URL=beta,
        JWT_SECRET='source11-history-synthetic-secret-0123456789',
        STRUCTURAL_SSO_SECRET='source11-history-synthetic-secret-0123456789',
        SMTP_HOST='fixture.invalid', SMTP_PORT='587', SMTP_FROM_EMAIL='sender@example.invalid',
        ADMIN_NOTIFICATION_EMAIL='admin@example.invalid', AUTH_TRUSTED_PROXY_IPS='127.0.0.1', AUTH_DEV_MODE='false')
    from api import auth, research
    from research import ResearchStore, source_integration
    from services.auth_store import AuthStore
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    mail = []
    auth._send_email = lambda to, subject, text: mail.append(text)
    research.enabled = lambda: True
    source_integration.enabled = lambda: True
    app = FastAPI()
    app.include_router(auth.router, prefix='/api')
    app.include_router(research.router, prefix='/api')
    verified_sources()
    original = json.loads(Path(original).read_text())
    with TestClient(app, base_url=beta) as client:
        request = client.post('/api/auth/request-link', json={'email': 'fresh@example.invalid'}, headers={'origin': beta})
        assert request.status_code == 200, request.text
        token = parse_qs(urlsplit(mail[-1].strip().split()[-1]).query)['token'][0]
        verified = client.post('/api/auth/verify', json={'token': token}, headers={'origin': beta})
        assert verified.status_code == 200, verified.text
        reopened = client.get(f"/api/research/{original['rid']}/formula-results/{original['ref']}")
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()['data'] == original['result']
        history = client.get('/api/research/' + original['rid']).json()['data']
        assert history['formula_check']['result_ref'] == original['ref']
        assert history['formula_check']['formula_result_recorded_at'] == original['result']['metadata']['formula_result_recorded_at']
        refused = client.post('/api/research/' + original['rid'] + '/source-tasks', json={
            'schema_version': 'structure-research-v1', 'contract_revision': 'b1-candidate-01', 'data': {
                'input_revision': 1, 'expected_research_version': original['research_version'], 'approval_ref': original['old_approval']}},
            headers={'origin': beta, 'idempotency-key': 'do-not-retrosign-old-source'})
        assert refused.status_code == 409 and refused.json()['error']['code'] == 'SOURCE_PERMISSION_UNAVAILABLE', refused.text
    with ResearchStore(AuthStore(path)).transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0] == 12
        assert conn.execute('SELECT count(*) FROM research_formula_runs').fetchone()[0] == 1
        assert conn.execute('SELECT count(*) FROM research_source_resources').fetchone()[0] == 0
    Path(output).write_text(json.dumps({'schema_version': 12, 'source_hashes_verified': verified_sources(),
                                      'reopened': reopened.json()['data'], 'history': history,
                                      'refused_status': refused.status_code, 'refused_code': refused.json()['error']['code']}))


if __name__ == '__main__':
    import sys
    assert sys.argv[1] == 'archived12'
    _archived12(*sys.argv[2:])
