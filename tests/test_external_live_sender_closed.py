"""Production sender rejects fixture and unregistered handles before any I/O."""
import pytest

from web.backend.research.external_first_answer_contract import ContractError
from web.backend.research.provider_schemas import canonical
from web.backend.services import external_live_production as production
from web.backend.services import external_live_sender as sender
from web.backend.services.external_live_issuer import RehearsalCredential,ExternalSenderHandle


@pytest.mark.parametrize("handle",[None,RehearsalCredential(),object.__new__(ExternalSenderHandle),object.__new__(production._LiveHandle)])
def test_no_credential_or_socket_for_fixture_or_unregistered_live_handle(monkeypatch,handle):
    def forbidden(*_):
        pytest.fail("no socket, transport, file or ledger call before real live handle")
    monkeypatch.setattr(sender,"_exchange",forbidden)
    monkeypatch.setattr(sender,"_trust",forbidden)
    monkeypatch.setattr(sender.socket,"socket",forbidden)
    with pytest.raises(ContractError,match="real_external_live_handle_required"):
        sender.run_once(object(),handle,None,None,None,1,1,None,None,None,None)


def test_consumed_state_without_post_commit_process_ticket_is_not_send_permission():
    with pytest.raises(ContractError,match="external_consumption_ticket_required"):
        sender._Ticket(None,"record-with-consumed-state",b"{}")


@pytest.mark.parametrize("raw",[
    {"is_available":True,"balance_infos":[{"currency":"USD","total_balance":"3"}]},
    {"is_available":True,"balance_infos":[{"currency":"CNY","total_balance":3}]},
    {"is_available":True,"balance_infos":[{"currency":"CNY","total_balance":"3.0000001"}]},
    {"is_available":True,"balance_infos":[{"currency":"CNY","total_balance":"3"},{"currency":"CNY","total_balance":"3"}]},
])
def test_balance_requires_exact_official_cny_decimal_shape(raw):
    with pytest.raises(ContractError,match="official_balance_unverified"):
        sender._balance_units(canonical(raw))


def test_uncertain_usage_does_not_produce_a_bookable_candidate():
    with pytest.raises(ContractError,match="external_usage_unknown"):
        sender._candidate(canonical({"id":"possible-send","model":"deepseek-flash","choices":[],"usage":None}))
    assert sender._balance_units(canonical({"is_available":True,"balance_infos":[
        {"currency":"CNY","total_balance":"3.000001"}]}))==3_000_001
