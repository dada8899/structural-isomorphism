"""Public schema and actual route declarations agree; no provider calls."""
import json
from pathlib import Path
import importlib.util
from research import plan_schemas as runtime


def test_plan_public_shapes_match_pure_standalone_type_generator_module():
    path=Path(__file__).resolve().parents[1]/'schemas.py'
    spec=importlib.util.spec_from_file_location('plan_public_schema_contract',path)
    public=importlib.util.module_from_spec(spec);spec.loader.exec_module(public)
    for name in ('PlanPreviewRequest','PlanConfirmationRequest','PlanPreviewEnvelope','PlanConfirmationEnvelope','PlanQuote','PlanResult','PlanPreviewResponse','PlanConfirmationResponse','PlanReadResponse'):
        assert getattr(public,name).model_json_schema()==getattr(runtime,name).model_json_schema(),name


def test_plan_actual_http_schema_has_manual_strict_request_and_typed_results():
    from api.research import router
    from fastapi import FastAPI
    app=FastAPI();app.include_router(router,prefix='/api');schema=app.openapi()
    for suffix,model in [('plan-previews','PlanPreviewResponse'),('plan-approvals','PlanConfirmationResponse')]:
        value=schema['paths']['/api/research/{research_id}/'+suffix]['post']
        assert '$ref' not in json.dumps(value['requestBody']) and '$defs' not in json.dumps(value['requestBody'])
        response=value['responses']['200']['content']['application/json']['schema']
        assert response['anyOf']==[{'$ref':'#/components/schemas/'+model},{'$ref':'#/components/schemas/Native'+model}]
        assert len(value['requestBody']['content']['application/json']['schema']['oneOf'])==2
    assert schema['paths']['/api/research/{research_id}/plan-results/{result_ref}']['get']['responses']['200']['content']['application/json']['schema']['anyOf']==[{'$ref':'#/components/schemas/PlanReadResponse'},{'$ref':'#/components/schemas/NativePlanReadResponse'}]
