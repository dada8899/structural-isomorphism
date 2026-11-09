"""Existing short self-observation APIs, no new purpose or worker birth.

Standalone against the pre-question-draft source. No draft producer imports,
controlled grant installation, provider calls, Source calls or schema changes.
"""
import json
import pytest
from .test_research_persistence import stack,post,login
from research import ResearchStore
from research.schemas import bounded_text
from api import auth


def _original_observation(original,*,confirmed):
    # The UI may build this only after a visible original-text adoption action.
    # This is the user's text, never a claim of model structuring.
    return dict(entry='phenomenon',original_input=original,objective='',summary=original,
        variables=[],constraints=[],unknowns=[],confirmed=confirmed)


def test_summary_normalization_never_replaces_the_exact_original_outbound():
    from research.schemas import ProblemInput
    from research.phenomenon_plan import make_plan_manifest
    from research.plan_preview_codec import plan_preview_request
    original=' e\u0301 原话中的温度恢复过程。\n '
    problem=ProblemInput.model_validate(_original_observation(original,confirmed=True))
    assert problem.original_input==original and problem.summary!=original
    encoded=plan_preview_request(make_plan_manifest(dict(input_kind='user_observation_summary',summary=problem.original_input)))
    assert json.loads(json.loads(encoded.raw)['messages'][1]['content'])['input']['summary']==original


def test_short_original_explicit_adoption_uses_existing_save_revision_and_pure_native_input(stack):
    """Real ASGI/Auth/storage plus pure encoding; no funding or worker birth."""
    from research.service import ResearchService
    from research.plan_runtime import _input
    from research.plan_native_runtime import quote
    from research.errors import ResearchError
    from .test_research_paid_producers import identity
    original='一个物体温度恢复到环境温度的过程，是否与电容放电对应？请比较公式，告诉我能借用什么、什么时候不能用。'
    client,_=stack
    unconfirmed=_original_observation(original,confirmed=False)
    saved=post(client,'/api/research',dict(problem=unconfirmed),'original-save')
    assert saved.status_code==200,saved.text
    rid=saved.json()['data']['research']['id']
    store=ResearchStore(auth._store());service=ResearchService(store);actor=identity(client)
    pid=service._principal(actor)
    with store.transaction() as conn:
        with pytest.raises(ResearchError) as error:_input(conn,service,actor,pid,rid,1,1)
        assert error.value.code=='INPUT_INVALID'
    adopted=post(client,'/api/research/'+rid+'/revisions',
        dict(expected_revision=1,problem=_original_observation(original,confirmed=True)),'explicit-original-adoption')
    assert adopted.status_code==200,adopted.text
    value=adopted.json()['data']
    assert value['research_version']==2 and value['current_problem']['confirmed'] is True
    assert value['current_problem']['original_input']==original and value['current_problem']['objective']==''
    assert value['current_problem']['variables']==value['current_problem']['constraints']==value['current_problem']['unknowns']==[]
    assert client.get('/api/research/'+rid).json()['data']['current_problem']==value['current_problem']
    with store.transaction() as conn:
        before={table:conn.execute('SELECT count(*) FROM '+table).fetchone()[0]
            for table in ('research_tasks','research_funding_accounts','research_plan_native_runs')}
        _,_,encoded=_input(conn,service,actor,pid,rid,2,2)
        payload=json.loads(json.loads(encoded.raw)['messages'][1]['content'])
        assert payload['input']['summary']==original
        assert {table:conn.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in before}==before
        assert all(count==0 for count in before.values())
    actual_quote=quote()
    assert (actual_quote.purpose,actual_quote.provider,actual_quote.model)==('phenomenon_plan_v1','deepseek','deepseek-flash')
    # A quote is pure information; it grants no funding and sends nothing.
    assert actual_quote.approved_upper_units>0
    stale=post(client,'/api/research/'+rid+'/revisions',
        dict(expected_revision=1,problem=_original_observation('另一个本人现象自述，等待确认新版本。',confirmed=True)),'stale-original-adoption')
    assert stale.status_code==409 and client.get('/api/research/'+rid).json()['data']['current_problem']['original_input']==original
    original_cookie=client.cookies.get('phase_session')
    login(client,'different-owner@example.test')
    assert client.get('/api/research/'+rid).status_code==404
    client.cookies.set('phase_session',original_cookie)


@pytest.mark.parametrize('original',['x','长'*1001,'😀'*4000])
def test_full_original_kept_when_existing_short_observation_scope_does_not_fit(original):
    from research.phenomenon_plan import make_plan_manifest
    from research.schemas import ProblemInput
    preserved=bounded_text(original,4000,1,normalize=False)
    with pytest.raises(ValueError):make_plan_manifest(dict(input_kind='user_observation_summary',summary=original))
    with pytest.raises(ValueError):ProblemInput.model_validate(_original_observation(original,confirmed=True))
    assert preserved==original


@pytest.mark.parametrize('original',['请研究 https://example.test/article 的第三方来源。','请运行 `python -c print(1)` 并整理结果。'])
def test_obvious_external_or_code_content_never_enters_own_observation_plan(stack,original):
    from research.service import ResearchService
    from research.plan_runtime import _input
    from research.errors import ResearchError
    from .test_research_paid_producers import identity
    client,_=stack
    saved=post(client,'/api/research',dict(problem=_original_observation(original,confirmed=True)),'unsupported-purpose')
    assert saved.status_code==200
    rid=saved.json()['data']['research']['id']
    store=ResearchStore(auth._store());service=ResearchService(store);actor=identity(client)
    pid=service._principal(actor)
    with store.transaction() as conn:
        with pytest.raises(ResearchError) as error:_input(conn,service,actor,pid,rid,1,1)
        assert error.value.code=='INPUT_INVALID'
        assert conn.execute('SELECT count(*) FROM research_tasks').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM research_plan_native_runs').fetchone()[0]==0
    assert client.get('/api/research/'+rid).json()['data']['current_problem']['original_input']==original
