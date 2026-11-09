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


def test_signed_price_shape_uses_conservative_cny_bound_and_rejects_staleness():
    basis={"model":"deepseek-flash","currency":"CNY","scale":6,"max_prompt_tokens":1_000_000,
           "max_output_tokens":768,"peak_input_miss_units_per_million":2_000_000,
           "peak_output_units_per_million":8_000_000,
           "source_url":"https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
           "official_document_sha256":"a"*64,"issued_at":100,"valid_until":200}
    def policy(upper):
        return sender.EndpointPolicy("1.1.1.1","b"*64,"c"*64,"d"*64,upper)
    assert sender._parse_price_basis(canonical(basis),policy(2_006_144),now=150)==basis
    # The published whole context is used without assuming an unverified
    # tokenizer, even for the short fixed P1 request.
    for low in (1,999_999):
        with pytest.raises(ContractError,match="external_price_basis_unbound"):
            sender._parse_price_basis(canonical(basis|{"max_prompt_tokens":low}),policy(2_006_144),now=150)
    assert sender._parse_price_basis(canonical(basis),policy(2_129_920),now=150)==basis
    with pytest.raises(ContractError,match="external_canary_upper_exceeded"):
        sender._parse_price_basis(canonical(basis),policy(2_129_921),now=150)
    assert 2_129_920-2_006_144==123_776
    with pytest.raises(ContractError,match="external_price_upper_insufficient"):
        sender._parse_price_basis(canonical(basis),policy(2_006_143),now=150)
    for changed,now in ((basis,200),(basis|{"currency":"USD"},150),
                        (basis|{"source_url":"https://example.invalid/pricing"},150)):
        with pytest.raises(ContractError,match="external_price_basis_unbound"):
            sender._parse_price_basis(canonical(changed),policy(2_006_144),now=now)


@pytest.mark.parametrize("headers,body",[
    (b"Content-Length: 3",b"{}"),  # valid JSON does not excuse truncation
    (b"Content-Length: 2",b"{}x"),
    (b"Content-Length: 2\r\nContent-Length: 2",b"{}"),
    (b"Content-Length: 2\r\nTransfer-Encoding: chunked",b"{}"),
    (b"X-Test: no framing",b"{}"),
    (b"Transfer-Encoding: chunked",b"2\r\n{}\r\n0\r\n"),
    (b"Transfer-Encoding: chunked",b"2\r\n{}\r\n0\r\n\r\nx"),
    (b"Transfer-Encoding: chunked",b"3\r\n{}\r\n0\r\n\r\n"),
    (b"Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked",b"0\r\n\r\n"),
])
def test_possible_send_with_unverified_http_framing_remains_unknown(headers,body):
    with pytest.raises(ContractError,match="external_receipt_framing"):
        sender._strict_reply(b"HTTP/1.1 200 OK\r\n"+headers+b"\r\n\r\n"+body)


def test_exact_http_framing_required_even_without_network():
    assert sender._strict_reply(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}")==b"{}"
    assert sender._strict_reply(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1\r\n{\r\n1\r\n}\r\n0\r\n\r\n")==b"{}"


def test_retirement_waits_for_first_write_lifetime_latch():
    import threading
    entered=threading.Event()
    finished=threading.Event()
    outcomes=[]
    def attempt_retirement():
        entered.set()
        try:production.retire(object(),object())
        except ContractError as error:outcomes.append(str(error))
        finally:finished.set()
    with production.wire_latch():
        worker=threading.Thread(target=attempt_retirement)
        worker.start()
        assert entered.wait(1)
        assert not finished.wait(.05)
    worker.join(1)
    assert not worker.is_alive() and finished.is_set()
    assert outcomes==["external_live_handle_retired"]


def test_unregistered_quote_data_is_never_live_quote_proof():
    from types import SimpleNamespace
    from web.backend.services.external_live_operations import require_offered
    decision=SimpleNamespace(preview_digest="a"*64)
    with pytest.raises(ContractError,match="live_quote_proof_required"):
        require_offered(SimpleNamespace(),object(),None,None,"research",1,None,None,decision)
