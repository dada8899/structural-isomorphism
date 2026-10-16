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
            context=context_for(conn,row[0])
            try:result.append(repository.provider_eligibility(context,ref))
            except (ValueError,LookupError,PermissionError):
                raise ResearchError("SOURCE_PERMISSION_UNAVAILABLE",409,"当前摘录范围或许可尚不支持付费预览。") from None
        payload={"research_id":research_id,"input_revision":input_revision,"research_version":research_version,"excerpts":[asdict(item) for item in result],"may_send_to_provider":False}
        if len(canonical(payload))>16384:raise ResearchError("PAYLOAD_LIMIT",413,"摘录候选超过预览上限。")
        return ProviderEligibility(research_id,input_revision,research_version,tuple(result),digest(canonical(payload)))
