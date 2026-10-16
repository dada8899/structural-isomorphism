"""Synthetic pure adapter consumers only: not real finance, HTTP, ACL or DB tests."""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from tests.test_research_financial import fixture, annual_values, allocation
from web.backend.research import financial_result_adapter as adapter
from web.backend.research import financial_policy
from web.backend.research.financial_policy import canonical, digest, FinancialError, FinancialResourceLimit
from web.backend.research.financial_evaluator import evaluate_financial


def setup(data=None, registry=None):
    if data is None: data, registry = fixture()
    ref = adapter.FinancialRegistryRef(str(uuid4()), 1, digest(registry.data()))
    operation = {"input_revision":1,"expected_research_version":3,"registry_ref":asdict(ref),"request":deepcopy(data)}
    binding = adapter.FinancialResultBinding(str(uuid4()), 1, "f"*64, digest(operation), ref)
    mappings = tuple(adapter.FinancialSourceBinding(s.id, ref, digest(asdict(s))) for s in registry.sources)
    server = adapter.ServerFinancialRegistryRecord(binding.research_id, ref, registry, mappings)
    resolved = adapter.resolve_financial_registry(binding, ref, server)
    return operation, binding, server, resolved


def saved(candidate, resolved):
    metadata = {"id":str(uuid4()),"created_at":"2026-10-17T00:00:00.000000Z","research_version_at_commit":4}
    record = adapter.prepare_financial_record(candidate,resolved,result_id=metadata["id"],created_at=metadata["created_at"],research_version_at_commit=metadata["research_version_at_commit"])
    expected = adapter.FinancialResultExpectation(binding=candidate.binding, snapshot_digest=candidate.snapshot_digest, **metadata)
    return record, expected


class FinancialAdapterTests(unittest.TestCase):
    def make(self, data=None, registry=None):
        operation, binding, server, resolved = setup(data, registry)
        candidate = adapter.evaluate_financial_candidate(operation, resolved, binding)
        record, expected = saved(candidate, resolved)
        return operation, binding, server, resolved, candidate, record, expected

    def project(self, state, view="summary", revision=1):
        _,_,_,resolved,_,record,expected = state
        return adapter.project_financial_result(record, resolved, expected, current_input_revision=revision, view=view)

    def test_actual_evaluator_bridge_and_table_chart_golden(self):
        state = self.make()
        table = self.project(state,"table")["data"]
        chart = self.project(state,"chart")["data"]
        expected = ["100.000000","110.000000","121.000000","133.100000","146.410000","161.051000"]
        self.assertEqual([r["target"]["revenue"]["display"] for r in table["payload"]["scenarios"][0]["years"]],expected)
        revenue = next(v for v in chart["payload"]["chart_spec"]["series"] if v["metric"] == "revenue")
        self.assertEqual(revenue["values"],expected)
        self.assertEqual(table["snapshot_digest"],chart["snapshot_digest"])
        self.assertEqual(chart["snapshot_digest"],chart["payload"]["chart_spec"]["snapshot_digest"])
        self.assertFalse(chart["payload"]["chart_spec"]["connect_nulls"])
        self.assertFalse(chart["payload"]["chart_spec"]["probability_calibrated"])

    def test_digest_domains_are_not_compared_as_same_input(self):
        state = self.make()
        operation,binding,server,_,candidate,_,_=state
        data = json.loads(candidate.canonical_snapshot)
        self.assertEqual(data["input_digest"],digest({"request":operation["request"],"registry":server.registry.data()}))
        self.assertEqual(binding.input_digest,"f"*64)
        self.assertNotEqual(binding.input_digest,data["input_digest"])
        self.assertEqual(self.project(state)["data"]["input_digest"],binding.input_digest)

    def test_curated_and_original_provenance_remain_distinct(self):
        state = self.make()
        source = self.project(state,"table")["data"]["payload"]["evidence"]["sources"][0]
        self.assertEqual(source["kind"],"curated_record")
        self.assertIsNone(source["raw_response_digest"])
        self.assertIsNone(source["extracted_text_digest"])
        self.assertNotIn("retained_original_ref",source)
        data, registry = fixture()
        original = replace(registry.sources[0],kind="historical_original",curated_record_digest=None,curated_commit=None,
            curated_entry_locator=None,raw_response_digest="c"*64,extracted_text_digest="d"*64,retained_original_ref=str(uuid4()))
        original_registry = replace(registry,sources=(original,))
        original_state = self.make(data,original_registry)
        text = canonical(self.project(original_state,"table"))
        self.assertNotIn(original.retained_original_ref,text)
        self.assertIn('historical_original',text)
        self.assertIn("c"*64,text)

    def test_registry_bool_or_client_json_is_not_a_server_record(self):
        operation,binding,server,resolved=setup()
        for fake in (True,asdict(server),{"trusted":True}):
            with self.subTest(fake=type(fake).__name__), self.assertRaises(FinancialError):
                adapter.resolve_financial_registry(binding,binding.registry_ref,fake)
        with self.assertRaises(TypeError): adapter.ResolvedFinancialRegistry()
        with self.assertRaises(TypeError): adapter.ServerFinancialCandidate()

    def test_wrong_research_ref_revision_digest_rejected(self):
        operation,binding,server,_=setup()
        wrongs = [replace(server,research_id=str(uuid4())),replace(server,ref=replace(server.ref,revision=2)),
            replace(server,ref=replace(server.ref,digest="a"*64))]
        for wrong in wrongs:
            with self.subTest(wrong=wrong.ref),self.assertRaises(FinancialError):
                adapter.resolve_financial_registry(binding,binding.registry_ref,wrong)
        changed = replace(server.registry.observations[0],amount=replace(server.registry.observations[0].amount,value="41"))
        with self.assertRaises(FinancialError):
            adapter.resolve_financial_registry(binding,binding.registry_ref,replace(server,registry=replace(server.registry,observations=(changed,)+server.registry.observations[1:])))

    def test_source_mapping_digest_set_and_ref_must_match(self):
        _,binding,server,_=setup()
        link=server.source_bindings[0]
        variants = [(),(link,link),(replace(link,snapshot_digest="c"*64),),
            (replace(link,financial_snapshot_id=str(uuid4())),),(replace(link,registry_ref=replace(link.registry_ref,revision=2)),)]
        for links in variants:
            with self.subTest(links=links),self.assertRaises(FinancialError):
                adapter.resolve_financial_registry(binding,binding.registry_ref,replace(server,source_bindings=links))

    def test_request_scope_and_whole_operation_digest_enforced_before_evaluator(self):
        operation,binding,_,resolved=setup()
        variants=[]
        for key,value in (("input_revision",2),("expected_research_version",4),("trusted",True),("registry",{})):
            wrong=deepcopy(operation);wrong[key]=value;variants.append(wrong)
        wrong=deepcopy(operation);wrong["request"]["scenarios"][0]["remaining_revenue"]["value"]="61";variants.append(wrong)
        with patch.object(adapter,"evaluate_financial",side_effect=AssertionError("must not calculate")) as evaluate:
            for wrong in variants:
                with self.subTest(keys=wrong.keys()),self.assertRaises(FinancialError):
                    adapter.evaluate_financial_candidate(wrong,resolved,binding)
        evaluate.assert_not_called()

    def test_registry_reference_types_rejected_before_actual_evaluator(self):
        operation,binding,_,resolved=setup()
        variants=[]
        for revision in (True,1.0,"1"):
            wrong=deepcopy(operation);wrong["registry_ref"]["revision"]=revision;variants.append(wrong)
        for key,value in (("id","not-a-uuid"),("digest","not-a-digest"),("extra",True)):
            wrong=deepcopy(operation);wrong["registry_ref"][key]=value;variants.append(wrong)
        with patch.object(adapter,"evaluate_financial",wraps=adapter.evaluate_financial) as evaluate:
            for wrong in variants:
                # Matching whole-body digest isolates the typed-ref bug, not a digest mismatch.
                matching_binding=replace(binding,request_digest=digest(wrong))
                with self.subTest(ref=wrong["registry_ref"]),self.assertRaises(FinancialError):
                    adapter.evaluate_financial_candidate(wrong,resolved,matching_binding)
        evaluate.assert_not_called()

    def test_integer_registry_revision_evaluates_and_reopens_unchanged(self):
        operation,binding,_,resolved=setup()
        self.assertIs(type(operation["registry_ref"]["revision"]),int)
        with patch.object(adapter,"evaluate_financial",wraps=adapter.evaluate_financial) as evaluate:
            candidate=adapter.evaluate_financial_candidate(operation,resolved,binding)
            record,expected=saved(candidate,resolved)
            for view in ("summary","table","chart"):
                result=adapter.project_financial_result(record,resolved,expected,current_input_revision=1,view=view)
                self.assertEqual(result["data"]["snapshot_digest"],candidate.snapshot_digest)
                self.assertEqual(result["data"]["request_digest"],binding.request_digest)
        self.assertEqual(evaluate.call_count,1)

    def test_outer_request_digest_is_not_executor_digest(self):
        operation,binding,server,resolved=setup()
        wrong=replace(binding,request_digest=digest({"request":operation["request"],"registry":server.registry.data()}))
        with self.assertRaises(FinancialError): adapter.evaluate_financial_candidate(operation,resolved,wrong)

    def test_registry_and_request_mutation_cannot_change_resolved_or_candidate(self):
        state=self.make()
        operation,_,_,_,candidate,_,_=state
        operation["request"]["scenarios"][0]["remaining_revenue"]["value"]="999"
        public=self.project(state,"table")
        public["data"]["payload"]["scenarios"][0]["years"][0]["target"]["revenue"]["display"]="evil"
        self.assertEqual(self.project(state,"table")["data"]["payload"]["scenarios"][0]["years"][0]["target"]["revenue"]["display"],"100.000000")
        self.assertEqual(hashlib.sha256(candidate.canonical_snapshot.encode()).hexdigest(),candidate.snapshot_digest)

    def test_round_trip_json_reopen_is_projection_only_not_recalculation(self):
        state=self.make();state=list(state)
        state[5]=json.loads(json.dumps(state[5]))
        with patch.object(adapter,"evaluate_financial",side_effect=AssertionError("GET cannot recalculate")) as evaluate:
            for view in ("summary","table","chart"): self.project(state,view)
        evaluate.assert_not_called()
        newer=self.project(state,revision=2)["data"]
        self.assertTrue(newer["is_historical"])
        self.assertEqual(newer["input_revision"],1)
        self.assertEqual(newer["created_at"],state[6].created_at)

    def test_no_client_expected_true_or_unknown_view(self):
        state=self.make();*_,record,expected=state
        for fake in (True,asdict(expected),None):
            with self.subTest(fake=fake),self.assertRaises(FinancialError):
                adapter.project_financial_result(record,state[3],fake,current_input_revision=1)
        with self.assertRaises(FinancialError): self.project(state,view="__dict__")
        with self.assertRaises(FinancialError): self.project(state,revision=True)

    def test_tampered_snapshot_and_self_reported_digest_cannot_replace_expected(self):
        state=list(self.make());record=deepcopy(state[5])
        raw=json.loads(record["canonical_snapshot"])
        raw["scenarios"][0]["years"][0]["target"]["revenue"].update(raw_value="999",display="999.000000")
        record["canonical_snapshot"]=canonical(raw)
        record["snapshot_digest"]=hashlib.sha256(record["canonical_snapshot"].encode()).hexdigest()
        state[5]=record
        with self.assertRaises(FinancialError): self.project(state,"table")

    def test_header_binding_policy_timestamp_version_and_model_flags_rejected(self):
        original=self.make()
        for key,value in (("id",str(uuid4())),("type","model_report"),("model_analysis_ran",True),("u2_goal_status","accepted"),
            ("created_at","2026-10-17T00:00:01.000000Z"),("research_version_at_commit",5)):
            state=list(original);state[5]=deepcopy(state[5]);state[5][key]=value
            with self.subTest(key=key),self.assertRaises(FinancialError): self.project(state)
        for key,value in (("input_digest","e"*64),("input_revision",True),("producer_commit","a"*40),("policy_revision","future")):
            state=list(original);state[5]=deepcopy(state[5]);state[5]["binding"][key]=value
            with self.subTest(binding_key=key),self.assertRaises(FinancialError): self.project(state)

    def rewrite_snapshot(self,state,change):
        state=list(state);state[5]=deepcopy(state[5]);raw=json.loads(state[5]["canonical_snapshot"])
        change(raw);raw=canonical(raw);sha=hashlib.sha256(raw.encode()).hexdigest()
        state[5]["canonical_snapshot"]=raw;state[5]["snapshot_digest"]=sha
        # Emulate corrupt stored bytes with a matching digest: schema checks still apply.
        state[6]=replace(state[6],snapshot_digest=sha)
        return state

    def test_schema_whitelist_reopen_catches_structural_corruption_even_matching_digest(self):
        state=self.make()
        mutations=[lambda x:x.update(unexpected=True),lambda x:x.update(operations_used=True),
            lambda x:x.update(calculation_precision=True),lambda x:x.update(qualifications=[]),
            lambda x:x["scenarios"][0]["years"][0].update(year=True),
            lambda x:x["scenarios"][0]["years"][0]["native"].update(same_as="other"),
            lambda x:x["scenarios"][0]["years"][0]["target"]["revenue"].update(extra="private"),
            lambda x:x["scenarios"][0]["years"][0]["target"]["revenue"].update(unit="ratio"),
            lambda x:x["scenarios"][0]["years"][0]["target"]["composition"]["rows"][0].update(amount=None),
            lambda x:x["scenarios"][0]["years"][0]["target"]["revenue"].update(display="123.000000"),
            lambda x:x["scenarios"][0]["years"][0]["target"]["revenue"].update(observation_refs=[str(uuid4())]),
            lambda x:x["scenarios"][0]["years"][0]["target"]["net_profit"].update(raw_value="1",display="1.000000",basis="derived_conditional")]
        for i,mutate in enumerate(mutations):
            with self.subTest(mutation=i),self.assertRaises(FinancialError):
                self.project(self.rewrite_snapshot(state,mutate),"table")

    def test_registry_request_and_executor_input_snapshot_bindings_rechecked(self):
        state=self.make()
        mutations=[lambda x:x.update(input_digest="f"*64),lambda x:x.update(registry_digest="e"*64),
            lambda x:x["registry_snapshot"]["sources"][0].update(kind="live_original"),
            lambda x:x["request_snapshot"]["scenarios"][0]["remaining_revenue"].update(value="61")]
        for i,mutate in enumerate(mutations):
            with self.subTest(mutation=i),self.assertRaises(FinancialError): self.project(self.rewrite_snapshot(state,mutate))

    def test_missing_conflicted_values_and_insufficient_goal_remain_visible(self):
        state=self.make();table=self.project(state,"table")["data"]
        self.assertEqual(table["u2_goal_status"],"not_met")
        self.assertIsNone(table["payload"]["historical_context"][1]["target_value"]["raw_value"])
        self.assertEqual(table["payload"]["historical_context"][2]["target_value"]["basis"],"conflicted")
        self.assertIsNone(table["payload"]["scenarios"][0]["years"][0]["target"]["net_profit"]["display"])
        self.assertFalse(table["model_analysis_ran"])

    def test_missing_fx_keeps_native_and_chart_null_without_connecting(self):
        data,registry=fixture("USD");state=self.make(data,registry)
        table=self.project(state,"table")["data"]
        row=table["payload"]["scenarios"][0]["years"][0]
        self.assertEqual(row["native"]["revenue"]["display"],"100.000000")
        self.assertIsNone(row["target"]["revenue"]["display"])
        chart=self.project(state,"chart")["data"]["payload"]["chart_spec"]
        self.assertTrue(all(v is None for v in chart["series"][0]["values"]))
        self.assertFalse(chart["connect_nulls"])

    def test_complete_partition_still_never_grants_u2_acceptance(self):
        data,registry=fixture();data["scenarios"][0]["allocations"]=[allocation("1",mode="share")]
        state=self.make(data,registry)
        self.assertIn(self.project(state)["data"]["u2_goal_status"],{"not_met","not_assessed"})

    def test_sensitivity_is_bound_to_variant_and_not_probabilities(self):
        data,registry=fixture();data["sensitivity"]={"scenario_id":"base","parameter_id":"g_2027","points":["0","0.1","0.2"]}
        state=self.make(data,registry)
        chart=self.project(state,"chart")["data"]["payload"]["chart_spec"]
        self.assertEqual([v["point"] for v in chart["sensitivity"]],["0","0.1","0.2"])
        with self.assertRaises(FinancialError):
            self.project(self.rewrite_snapshot(state,lambda x:x["sensitivity"][0].update(case_input_digest="a"*64)),"chart")

    def test_actual_evaluator_resource_limits_are_not_disabled_by_adapter(self):
        operation,binding,_,resolved=setup()
        with patch.object(financial_policy,"MAX_OPERATIONS",2),self.assertRaises(FinancialResourceLimit):
            adapter.evaluate_financial_candidate(operation,resolved,binding)
        with patch.object(adapter,"_monotonic",side_effect=[0,3]),self.assertRaises(FinancialResourceLimit):
            adapter.evaluate_financial_candidate(operation,resolved,binding)

    def test_input_bytes_duplicates_unicode_depth_and_float_are_rejected(self):
        operation,binding,_,resolved=setup()
        for key,value in (("trusted","测"*50000),("expected_research_version",True),("extra",1.2),("extra","\ud800")):
            wrong=deepcopy(operation);wrong[key]=value
            with self.subTest(key=key),self.assertRaises(FinancialError): adapter.evaluate_financial_candidate(wrong,resolved,binding)
        with self.assertRaises(FinancialError): adapter._parse('{"x":1,"x":2}')
        with self.assertRaises(FinancialError): adapter._parse('{"x":NaN}')
        deep=[];at=deep
        for _ in range(40):at.append([]);at=at[0]
        with self.assertRaises(FinancialResourceLimit):adapter._bounded(deep)

    def test_full_record_and_same_as_expansion_have_actual_byte_caps(self):
        data,registry=fixture()
        ids=["advertising","commerce","consumer","enterprise","unallocated"]
        data["categories"]=[{"id":i,"label":i,"definition":"Synthetic partition","dimension":"monetization","excludes":[j for j in ids if j!=i],"kind":"unallocated" if i=="unallocated" else "segment"} for i in ids]
        data["scenarios"][0]["allocations"]=[{"category_id":i,"mode":"share","values":annual_values("alloc_"+i,"0.25")} for i in ids[:-1]]
        base=deepcopy(data["scenarios"][0]);data["scenarios"]=[{**deepcopy(base),"id":i} for i in ("base","slower")]
        state=self.make(data,registry)
        self.assertLessEqual(len(canonical(state[5]).encode()),128*1024)
        self.assertLessEqual(len(canonical(self.project(state,"summary")).encode()),128*1024)
        with self.assertRaises(FinancialResourceLimit): self.project(state,"table")
        self.assertLessEqual(len(canonical(self.project(state,"chart")).encode()),128*1024)
        huge=list(state);huge[5]=deepcopy(state[5]);huge[5]["unexpected"]="测"*50000
        with self.assertRaises(FinancialResourceLimit):self.project(huge)

    def test_computed_record_serializer_rejects_raw_json_and_wrong_commit_version(self):
        state=self.make()
        with self.assertRaises(FinancialError):
            adapter.prepare_financial_record(state[5],state[3],result_id=str(uuid4()),created_at=state[6].created_at,research_version_at_commit=4)
        with self.assertRaises(FinancialError):
            adapter.prepare_financial_record(state[4],state[3],result_id=str(uuid4()),created_at=state[6].created_at,research_version_at_commit=5)

    def test_source_linked_complete_partition_still_only_not_assessed(self):
        data,registry=fixture();scenario=data["scenarios"][0]
        scenario["allocations"]=[allocation("1",mode="share")]
        scenario["remaining_revenue"]["source_refs"]=[registry.sources[0].id]
        for item in scenario["growth"]+scenario["costs"][0]["values"]+scenario["allocations"][0]["values"]:
            item["parameter"]["source_refs"]=[registry.sources[0].id]
        state=self.make(data,registry)
        self.assertEqual(self.project(state)["data"]["u2_goal_status"],"not_assessed")
        self.assertFalse(self.project(state)["data"]["model_analysis_ran"])

    def test_summary_preserves_specific_missing_fx_gap(self):
        data,registry=fixture("USD");state=self.make(data,registry)
        summary=self.project(state)["data"]["payload"]
        self.assertIn("historical_fx_missing",summary["gap_codes"])
        self.assertIn("future_fx_assumption_missing",summary["gap_codes"])

    def test_source_record_link_is_scoped_mapping_not_a_private_original_handle(self):
        operation,binding,server,_=setup()
        link=replace(server.source_bindings[0],source_record_ref=adapter.SourceRecordRef(str(uuid4()),2))
        resolved=adapter.resolve_financial_registry(binding,binding.registry_ref,replace(server,source_bindings=(link,)))
        candidate=adapter.evaluate_financial_candidate(operation,resolved,binding);record,expected=saved(candidate,resolved)
        projection=adapter.project_financial_result(record,resolved,expected,current_input_revision=1,view="table")
        actual=projection["data"]["payload"]["evidence"]["source_bindings"][0]
        self.assertEqual(actual["financial_snapshot_id"],server.registry.sources[0].id)
        self.assertEqual(actual["source_record_ref"],asdict(link.source_record_ref))
        self.assertNotIn("retained_original_ref",actual)

    def test_saved_json_duplicate_noncanonical_and_huge_integer_are_rejected(self):
        state=self.make()
        for variant in (state[4].canonical_snapshot.replace('{','{ ',1),
                        state[4].canonical_snapshot.replace('"amount_unit":"million"','"amount_unit":"million","amount_unit":"million"',1)):
            changed=list(state);changed[5]=deepcopy(state[5]);sha=hashlib.sha256(variant.encode()).hexdigest()
            changed[5]["canonical_snapshot"]=variant;changed[5]["snapshot_digest"]=sha;changed[6]=replace(state[6],snapshot_digest=sha)
            with self.assertRaises(FinancialError):self.project(changed)
        with self.assertRaises(FinancialError):adapter._parse('{"x":'+"9"*5000+'}')

    def test_projection_decimal_rounding_isolated_from_caller_context(self):
        from decimal import localcontext
        state=self.make()
        with localcontext() as context:
            context.prec=2
            context.Emax=2
            context.Emin=-2
            self.assertEqual(self.project(state,"table")["data"]["payload"]["scenarios"][0]["years"][-1]["target"]["revenue"]["display"],"161.051000")

    def test_no_network_model_or_storage_dependencies_in_adapter(self):
        import ast
        from pathlib import Path
        tree=ast.parse(Path(adapter.__file__).read_text())
        imports=[n.module or "" for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]+[a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
        self.assertFalse(any(name.split('.')[0] in {"sqlite3","httpx","requests","socket","subprocess","dotenv","services"} for name in imports))
        with patch("socket.socket",side_effect=AssertionError("no network")),patch("sqlite3.connect",side_effect=AssertionError("no DB")):
            state=self.make();self.project(state,"table")


if __name__ == "__main__":
    unittest.main()
