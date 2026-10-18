"""Saved-source eligibility only. This is neither consent nor send authority."""
from dataclasses import dataclass,asdict
from uuid import UUID

from .authorization import AccountIdentity,AuthorizationGate
from .errors import ResearchError,not_found
from .provider_schemas import canonical,digest


@dataclass(frozen=True,kw_only=True)
class ProviderEligibleExcerpt:
    source_id: str
    source_revision: int
    excerpt_id: str
    title: str
    canonical_url: str
    attribution: str
    extracted_digest: str
    raw_digest: str
    discovery_digest: str
    acquired_at: str
    information_cutoff: str
    start: int
    end: int
    quote: str
    origin: str
    read_scope: str = "author_narrative_subset"
    eligibility_policy: str = "plos-ccby-subset-eligibility-v1"
    target_provider: str = "deepseek"
    target_model: str = "deepseek-flash"
    permission_basis_digest: str
    may_send_to_provider: bool = False

    def __post_init__(self):
        if self.may_send_to_provider is not False:
            raise ValueError("eligibility is not external-send consent")


@dataclass(frozen=True)
class ProviderEligibility:
    research_id: str
    input_revision: int
    research_version: int
    excerpts: tuple[ProviderEligibleExcerpt,...]
    manifest_digest: str
    may_send_to_provider: bool = False

    def __post_init__(self):
        if self.may_send_to_provider is not False:
            raise ValueError("eligibility is not external-send consent")


def read_provider_eligibility(store,identity,research_id,input_revision,research_version,excerpt_ids):
    """Fixed current-owner reader, with no caller-supplied authorizer/flags."""
    from .store import ResearchStore
    from .evidence_repository import EvidenceRepository
    from .source_integration import authorizer,context_for
    if type(store) is not ResearchStore or type(identity) is not AccountIdentity:
        raise PermissionError("canonical source context required")
    if (type(input_revision) is not int or not 1<=input_revision<=2147483647
            or type(research_version) is not int or not 1<=research_version<=2147483647
            or type(excerpt_ids) is not tuple or not 1<=len(excerpt_ids)<=20
            or any(type(ref) is not str for ref in excerpt_ids) or len(set(excerpt_ids))!=len(excerpt_ids)):
        raise ResearchError("INPUT_INVALID",422,"摘录候选范围无效。")
    try:
        for value in (research_id,*excerpt_ids):
            parsed=UUID(value)
            if parsed.version!=4 or str(parsed)!=value:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise not_found() from None
    with store.transaction() as conn:
        gate=AuthorizationGate(store)
        gate.check_account(conn,identity)
        principal=conn.execute("SELECT id FROM research_principals WHERE normalized_email=? AND session_generation=?",(identity.email,identity.generation)).fetchone()
        if not principal:raise not_found()
        control=gate.check(conn,identity,principal[0],research_id)
        if control["current_revision"]!=input_revision or control["version"]!=research_version:
            raise ResearchError("REVISION_CONFLICT",409,"问题版本已变化，请重新预览。")
        repository=EvidenceRepository(conn,authorizer(store,identity=identity))
        result=[]
        for ref in excerpt_ids:
            row=conn.execute("SELECT task_id FROM research_evidence_objects WHERE id=? AND kind='excerpts' AND research_id=? AND input_revision=?",(ref,research_id,input_revision)).fetchone()
            if not row:raise not_found()
            if conn.execute('SELECT version FROM research_schema').fetchone()[0] in (11,12,13,14):
                from .source_guard import check_origin
                try:check_origin(store,conn,row[0])
                except (PermissionError,ResearchError):raise ResearchError('SOURCE_PERMISSION_UNAVAILABLE',409,'旧来源仅可按原权限读取历史；新外发需要当前受保护来源准入。') from None
            context=context_for(conn,row[0])
            try:result.append(repository.provider_eligibility(context,ref))
            except (ValueError,LookupError,PermissionError):
                raise ResearchError("SOURCE_PERMISSION_UNAVAILABLE",409,"当前摘录范围或许可尚不支持付费预览。") from None
        payload={"research_id":research_id,"input_revision":input_revision,"research_version":research_version,"excerpts":[asdict(item) for item in result],"may_send_to_provider":False}
        if len(canonical(payload))>16384:raise ResearchError("PAYLOAD_LIMIT",413,"摘录候选超过预览上限。")
        return ProviderEligibility(research_id,input_revision,research_version,tuple(result),digest(canonical(payload)))


def complete_attribution(raw,snapshot):
    """Fail closed unless a complete creator/year credit is in articleinfo.

    The caller has independently reverified the publisher licence and v2 scope;
    this narrow metadata reader neither grants a licence nor changes extraction.
    """
    import re
    from html.parser import HTMLParser
    class Citation(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True);self.stack=[];self.values=[];self.parts=None;self.nodes=0
        def handle_starttag(self,tag,pairs):
            self.nodes+=1
            if self.nodes>50000 or len(self.stack)>128 or len({k for k,_ in pairs})!=len(pairs):raise ValueError('attribution structure limit')
            attrs=dict(pairs);tokens=attrs.get('id','')+' '+attrs.get('class','')
            blocked=tag in {'nav','aside','footer','blockquote','q','script','style','template','noscript','iframe','form'} or re.search(r'(?:^|[\s_-])(?:comments?|discussion|references?|ref-list|user-content)(?:$|[\s_-])',tokens,re.I) is not None
            blocked=blocked or any(item[2] for item in self.stack)
            owned=(tag=='div' and 'articleinfo' in attrs.get('class','').split()
                and any(a.get('id')=='artText' for _,a,_,_ in self.stack)
                and any(t=='section' and 'article-body' in a.get('class','').split() for t,a,_,_ in self.stack) and not blocked)
            if tag=='p' and self.stack and self.stack[-1][3] and not blocked:self.parts=[]
            if tag not in {'meta','br','hr','img','input','link','area','base','col','embed','param','source','track','wbr'}:self.stack.append((tag,attrs,blocked,owned))
        def handle_data(self,text):
            if self.parts is not None and not any(item[2] for item in self.stack):
                self.parts.append(text)
                if sum(map(len,self.parts))>2000:raise ValueError('bounded citation required')
        def handle_endtag(self,tag):
            if tag=='p' and self.parts is not None:
                self.values.append(re.sub(r'\s+',' ',''.join(self.parts)).strip());self.parts=None
            if self.stack and self.stack[-1][0]==tag:self.stack.pop()
            elif any(item[0]==tag for item in self.stack):raise ValueError('ambiguous attribution markup')
    parser=Citation();parser.feed(raw.decode('utf-8'));parser.close()
    values=[value for value in parser.values if value.lower().startswith('citation:') and snapshot.doi in value]
    if len(values)!=1:raise PermissionError('unambiguous creator credit required')
    match=re.match(r'^Citation:\s*(.+?\([12][0-9]{3}\))\s+',values[0],re.I)
    if not match or snapshot.title.casefold() in match.group(1).casefold():raise PermissionError('creator/year attribution unavailable')
    result=f'{match.group(1)} — {snapshot.canonical_url} — CC BY 4.0'
    if len(result)>400:raise PermissionError('complete credit exceeds supported packet scope')
    return result


def read_confirmed_provider_packet(conn,store,identity,authority):
    from .paid_approval import PaidPacketAuthority
    from .provider_schemas import EvidencePacket
    from .evidence_repository import EvidenceRepository
    from .source_integration import authorizer,context_for
    if type(authority) is not PaidPacketAuthority:raise PermissionError('actual paid consent required')
    binding=authority.require(conn,'packet')
    repository=EvidenceRepository(conn,authorizer(store,identity=identity));handles=[];candidates=[]
    for index,ref in enumerate(binding.source_refs):
        row=conn.execute("SELECT task_id FROM research_evidence_objects WHERE id=? AND kind='excerpts' AND research_id=? AND input_revision=?",(ref,binding.research_id,binding.input_revision)).fetchone()
        if not row:raise not_found()
        context=context_for(conn,row[0]);candidates.append(asdict(repository.provider_eligibility(context,ref)))
        handles.append(repository.confirmed_provider_handle(context,ref,authority,'e'+str(index+1)))
    if digest(canonical(candidates))!=binding.source_manifest_digest:raise PermissionError('approved source manifest changed')
    return EvidencePacket(context=binding.context,handles=tuple(handles))


def read_preview_manifest(conn,store,identity,research_id,input_revision,research_version,excerpt_ids,summary):
    """Current owner, complete attribution, no permission DTO or fake context."""
    from .evidence_repository import EvidenceRepository
    from .store import ResearchStore
    from pathlib import Path
    import sqlite3
    from .source_integration import authorizer,context_for
    if type(store) is not ResearchStore or type(identity) is not AccountIdentity or not isinstance(conn,sqlite3.Connection) or not conn.in_transaction:
        raise PermissionError('canonical preview read transaction required')
    database=next((row[2] for row in conn.execute('PRAGMA database_list') if row[1]=='main'),None)
    if not database or Path(database).resolve()!=store.path:raise PermissionError('canonical preview database required')
    gate=AuthorizationGate(store);gate.check_account(conn,identity)
    principal=conn.execute('SELECT id FROM research_principals WHERE normalized_email=? AND session_generation=?',(identity.email,identity.generation)).fetchone()
    if not principal:raise not_found()
    control=gate.check(conn,identity,principal[0],research_id)
    if control['current_revision']!=input_revision or control['version']!=research_version:raise ResearchError('REVISION_CONFLICT',409,'问题版本已变化。')
    import json
    original=conn.execute('SELECT problem_json FROM research_revisions WHERE research_id=? AND revision=?',(research_id,input_revision)).fetchone()
    if not original or json.loads(original[0])['summary']!=summary:raise ResearchError('REVISION_CONFLICT',409,'预览摘要必须来自当前保存的问题。')
    if type(excerpt_ids) is not tuple or not 1<=len(excerpt_ids)<=20 or any(type(ref) is not str for ref in excerpt_ids) or len(set(excerpt_ids))!=len(excerpt_ids):raise ResearchError('INPUT_INVALID',422,'摘录范围无效。')
    repository=EvidenceRepository(conn,authorizer(store,identity=identity));sources=[];handles=[]
    for index,ref in enumerate(excerpt_ids):
        row=conn.execute("SELECT task_id FROM research_evidence_objects WHERE id=? AND kind='excerpts' AND research_id=? AND input_revision=?",(ref,research_id,input_revision)).fetchone()
        if not row:raise not_found()
        try:candidate,handle=repository.preview_provider_handle(context_for(conn,row[0]),ref,'e'+str(index+1))
        except (ValueError,LookupError,PermissionError):raise ResearchError('SOURCE_PERMISSION_UNAVAILABLE',409,'预览需要完整有效的署名、许可与读取范围。') from None
        fields=('source_id','source_revision','excerpt_id','title','canonical_url','raw_digest','extracted_digest','discovery_digest',
            'permission_basis_digest','start','end','quote','read_scope','acquired_at','information_cutoff','may_send_to_provider')
        display={name:getattr(candidate,name) for name in fields};display['attribution']=handle.attribution
        display['information_cutoff']=display['information_cutoff'][:10]
        sources.append(display);handles.append(handle.model_dump())
    return {'problem_summary':summary,'sources':sources,'handles':handles}
