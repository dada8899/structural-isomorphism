"""Content-only result display, never a worker, current ACL reader or DB writer."""
from dataclasses import dataclass
import json

from . import formula_schemas as scientific
from .formula_policy import POLICY
from .formula_public import FormulaPublicError,_Limit,_fail,_json_data,_ReportedResult,RESULT_CAP


@dataclass(frozen=True,slots=True,init=False)
class FormulaResultView:
    _json:str
    def __init__(self,*args,**kwargs):_fail("use_formula_content_projection")
    def data(self):return json.loads(self._json)


def project_formula_result(payload,*,expected_input=None,expected_output_digest=None):
    """Verify against Core-supplied immutable metadata, not client assertions.

    Expected data must come from a later authorized reader. This helper cannot
    tell where it came from, mint IDs, attest execution or confer any permission.
    """
    reason=None
    try:
        if type(expected_input) is not scientific.FormulaCheckInput:_fail("bound_formula_input_required")
        if type(expected_output_digest) is not str or len(expected_output_digest)!=64 or any(c not in "0123456789abcdef" for c in expected_output_digest):
            _fail("independent_result_digest_required")
        request=scientific.FormulaCheckInput.parse(_json_data(expected_input.data(),64*1024))
        raw=_json_data(payload,RESULT_CAP)
        result=_ReportedResult.model_validate(raw).model_dump(mode="json")
        # No model normalization/coercion may silently change the reported facts.
        if scientific.canonical(result)!=scientific.canonical(raw):_fail("formula_result_shape_changed")
        without_digest={k:v for k,v in result.items() if k!="output_digest"}
        if result["output_digest"]!=expected_output_digest or scientific.digest(without_digest)!=expected_output_digest:
            _fail("formula_result_digest_mismatch")
        binding={"research_id":request.research_id,"input_revision":request.input_revision,"task_id":request.task_id,
            "attempt":request.attempt,"input_digest":request.input_digest,"comparison_scope":request.comparison_scope,"policy_revision":POLICY}
        if any(result[k]!=v for k,v in binding.items()):_fail("formula_result_input_mismatch")
        forms={form.id:form for form in (request.left,request.right) if form}
        refs=[{"id":form.id,"revision":form.revision,"formula_digest":scientific.digest(form.data()),"checked_representation":"validated_AST"} for form in forms.values()]
        if result["formula_refs"]!=refs:_fail("formula_reference_mismatch")
        sources={ref.id:ref for form in forms.values() for ref in form.source_refs}
        expected_sources=[{"id":v.id,"revision":v.revision,"content_digest":v.content_digest,"provenance":v.provenance,"locator":v.locator} for v in sources.values()]
        if result["source_refs"]!=expected_sources:_fail("formula_source_reference_mismatch")
        if [v["check_kind"] for v in result["outcomes"]]!=list(request.requested_checks):_fail("formula_check_set_mismatch")
        for outcome in result["outcomes"]:
            if outcome["check_kind"]!="canonical_transform" and outcome["relation"] not in {"undetermined","not_equivalent"}:
                _fail("formula_relation_outside_check")
            if outcome["check_kind"]!="bounded_numeric" and (outcome["samples"] or outcome["tolerance"] is not None):
                _fail("formula_samples_outside_check")
            if outcome["samples"] and [s["point"] for s in outcome["samples"]]!=list(request.sample_points):
                _fail("formula_sample_set_mismatch")
            if outcome["trace"]:
                if outcome["check_kind"]!="canonical_transform" or request.right is None:_fail("formula_trace_outside_check")
                previous=scientific.digest({"left":request.left.expression.data(),"right":request.right.expression.data(),"scope":request.comparison_scope})
                for step in outcome["trace"]:
                    if step["input_digest"]!=previous:_fail("formula_trace_chain_mismatch")
                    previous=step["output_digest"]
            if outcome["check_kind"]=="bounded_numeric" and outcome["samples"]:
                expected_status="passed" if all(sample["passed"] for sample in outcome["samples"]) else "failed"
                if outcome["status"]!=expected_status:_fail("formula_sample_status_mismatch")
                all_exact=all(sample["comparison"]=="exact" for sample in outcome["samples"])
                if (outcome["tolerance"] is None)!=all_exact:_fail("formula_tolerance_scope_mismatch")
        data={"schema_version":"formula-content-view-v1","comparison_scope":result["comparison_scope"],"policy_revision":result["policy_revision"],
            "content_input_digest":result["input_digest"],"content_output_digest":result["output_digest"],
            "authorization_verified":False,"execution_attested":False,"source_facts_verified":False,"display_checked":False,
            "provided_formula_refs":result["formula_refs"],"reported_resource_guard":result["resource_guard"],
            "formula_displays":[{"side":side,"original_display":form.original_display,"checked_AST":form.expression.data(),
                "symbols":form.data()["symbols"],"declared_assumptions":form.data()["assumptions"],
                "declared_initial_conditions":form.data()["initial_conditions"],"declared_boundary_conditions":form.data()["boundary_conditions"],
                "declaration_assessment":"not_verified_by_public_adapter"} for side,form in (("left",request.left),("right",request.right)) if form],
            "outcomes":result["outcomes"],"limitations":result["limitations"],
            "source_references":[{"id":v["id"],"revision":v["revision"],"content_digest":v["content_digest"],"declared_provenance":v["provenance"],
                "reference_status":"supplied_reference_not_authorized_here","locator_exposed":False} for v in result["source_refs"]],
            "presentation_limits":["Checks refer only to the supplied validated AST, not to original display text.",
                "Reported outcomes are content data; this adapter neither executes nor attests a worker.",
                "Declared assumptions and source references are not verified source or real-world facts.",
                "Numeric agreement at recorded points is not algebraic identity, mechanism evidence or transfer success."]}
        safe=_json_data(data,RESULT_CAP)
        view=object.__new__(FormulaResultView);object.__setattr__(view,"_json",scientific.canonical(safe))
    except FormulaPublicError:raise
    except (_Limit,scientific.FormulaLimit):reason="formula_payload_limit"
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError,UnicodeError):reason="invalid_formula_result"
    if reason:_fail(reason)
    return view
