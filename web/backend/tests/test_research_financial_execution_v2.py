"""Pure negative native-birth controls; these do not attest an actual Main run."""
import sqlite3
import pytest

from web.backend.research import financial_execution as execution,financial_input as native
from web.backend.research.financial_input_guard import statement_allowed,RESULTS,_write_scope
from web.backend.research.financial_result_v2 import (decode_financial_calculation,result_view_query,
    result_history_query,StoredFinancialResultV2,_validate_stored)
from web.backend.research.financial_policy import FinancialError,FinancialResourceLimit


def test_json_candidate_and_direct_native_constructors_cannot_issue_execution():
    for constructor,args in ((execution.CurrentFinancialExecution,({},)),
        (execution.OwnedFinancialReturnV2,(None,None)),(native.ResolvedOwnerFinancialRegistryV2,({},))):
        with pytest.raises(TypeError):constructor(*args)
    for forged in (object.__new__(execution.CurrentFinancialExecution),object.__new__(native.ResolvedOwnerFinancialRegistryV2)):
        with pytest.raises(PermissionError):forged.require()
    unowned=object.__new__(execution.CurrentFinancialExecution)
    with pytest.raises(PermissionError):unowned.check_deadline()
    with pytest.raises(TypeError):unowned.deadline=10**20
    with pytest.raises(PermissionError):object.__new__(execution.OwnedFinancialReturnV2).stored
    with pytest.raises(PermissionError):execution.execute({'trusted':True},None,None)
    with pytest.raises(FinancialError):_validate_stored({'snapshot':{},'receipt':{}},None)
    assert execution._CONTEXTS==execution._RETURNS==native._RESOLVED_OWNER=={}


def test_fixed_calculate_frame_and_result_write_gate_are_not_data_flags():
    with pytest.raises(PermissionError):execution.begin(*([None]*10))
    with pytest.raises(PermissionError):native.resolve_owner_registry_v2(*([None]*7))
    with pytest.raises(PermissionError):
        with _write_scope(None,None,None,RESULTS,'INSERT',(),request={'trusted':True}):pytest.fail('unreachable')
    assert statement_allowed(None,sqlite3.SQLITE_INSERT,RESULTS,None) is False
    assert statement_allowed(None,sqlite3.SQLITE_UPDATE,RESULTS,None) is False


@pytest.mark.parametrize('raw',[b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1.5}',b'{}',b' '*65537])
def test_new_action_shared_decoder_denies_unsafe_input(raw):
    with pytest.raises((FinancialError,FinancialResourceLimit)):decode_financial_calculation(raw)


@pytest.mark.parametrize('pairs',[[('view','')],[('view','table'),('view','chart')],[('other','secret')]])
def test_read_query_closed_domain(pairs):
    with pytest.raises(FinancialError):result_view_query(pairs)


@pytest.mark.parametrize('pairs',[[('limit','21')],[('limit','01')],[('cursor','')],[('limit','2'),('limit','3')]])
def test_history_query_closed_domain(pairs):
    with pytest.raises(FinancialError):result_history_query(pairs)
