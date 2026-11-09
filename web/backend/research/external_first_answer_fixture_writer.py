"""Shared-account atomic writer rehearsal. In-memory SQLite only, no sender.

This exercises the proposed write/consume transaction against the existing
account table shape. It cannot attach to a production/file-backed database
or register in Main. Native Financial9 hooks remain untouched.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
import sqlite3

from .external_first_answer_contract import (
    CAP_UNITS, MIN_RISK_MARGIN_UNITS, ContractError, compare_confirmation,
    parse_unverified_candidate,
)
from .external_first_answer_state import DDL, GUARD, TABLE, _COLUMNS
from .provider_schemas import canonical, digest


@dataclass(frozen=True, slots=True)
class FixtureGrant:
    scope: object
    quote: object
    preview: object = field(repr=False)
    account_id: str
    binding: str
    epoch: int
    balance: int
    valid_until: int


class FixtureWriter:
    def __init__(self, conn):
        if type(conn) is not sqlite3.Connection or conn.in_transaction:
            raise ContractError("isolated_fixture_required")
        self.conn = conn
        self._expect = None
        self._money = None
        self._verify_database()
        conn.execute("PRAGMA foreign_keys=ON")
        conn.create_function(GUARD, 3, self._allow_run)
        conn.create_function("external_fixture_money_allowed", 6, self._allow_money)
        conn.execute("""CREATE TEMP TRIGGER external_fixture_money BEFORE UPDATE ON main.research_funding_accounts
            WHEN external_fixture_money_allowed(OLD.id,OLD.held,NEW.held,OLD.upper_booked,NEW.upper_booked,NEW.version)!=1
            BEGIN SELECT RAISE(ABORT,'external fixture money denied'); END""")

    def _verify_database(self):
        databases = {name:path for _,name,path in self.conn.execute("PRAGMA database_list")}
        if databases.get("main") != "" or set(databases)-{"main","temp"}:
            raise ContractError("isolated_fixture_required")

    def _allow_run(self, operation, before, after):
        return int(self.conn.in_transaction and self._expect == (operation, before, after))

    def _allow_money(self, *row):
        return int(self.conn.in_transaction and self._money == row)

    @contextmanager
    def _transaction(self):
        self._verify_database()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    @staticmethod
    def grant(scope, raw, preview, quote, confirmation, *, balance, now, balance_until):
        approved = compare_confirmation(preview,scope,raw,quote,confirmation,now=now)
        if type(balance) is not int or balance<0 or type(balance_until) is not int or not now<balance_until<=now+60:
            raise ContractError("fixture_balance_invalid")
        return FixtureGrant(scope,quote,approved,quote.account_id,quote.economic_binding,
                            quote.funding_epoch,balance,balance_until)

    def _fence(self, grant, scope):
        if type(grant) is not FixtureGrant or scope != grant.scope:
            raise ContractError("revision_or_owner_changed")
        current=self.conn.execute("""SELECT c.owner_id,c.current_revision,c.version,c.owner_epoch,c.acl_epoch,
                    p.session_generation,p.epoch,r.digest
              FROM research_controls c JOIN research_principals p ON p.id=c.owner_id
              JOIN research_revisions r ON r.research_id=c.id AND r.revision=c.current_revision
              WHERE c.id=? AND p.status='active' AND c.lifecycle='active'""",(scope.research_id,)).fetchone()
        if current is None or tuple(current)!=(scope.principal_id,scope.input_revision,scope.research_version,
                scope.owner_epoch,scope.acl_epoch,scope.auth_generation,scope.principal_epoch,scope.problem_digest):
            raise ContractError("revision_or_owner_changed")

    def _account(self, grant):
        row=self.conn.execute("""SELECT id,binding_id,funding_epoch,settled,held,upper_booked,version
               FROM research_funding_accounts WHERE id=? AND provider='deepseek' AND currency='CNY'
                 AND mode='live' AND scale=6 AND status='unverified' AND cap=0""",(grant.account_id,)).fetchone()
        if row is None or tuple(row[:3])!=(grant.account_id,grant.binding,grant.epoch):
            raise ContractError("shared_account_changed")
        return tuple(row)

    def _row(self, run_id, grant):
        row=self.conn.execute("SELECT "+",".join(_COLUMNS)+" FROM "+TABLE+" WHERE id=?",(run_id,)).fetchone()
        if row is None:
            raise ContractError("operation_unavailable")
        data=dict(zip(_COLUMNS,row))
        if (data["scope_digest"],data["preview_digest"],data["request_digest"],data["quote_digest"],
                data["account_id"],data["funding_epoch"]) != (digest(canonical(grant.scope.model_dump())),
                grant.preview.preview_digest,grant.preview.request_digest,digest(canonical(grant.quote.model_dump())),
                grant.account_id,grant.epoch):
            raise ContractError("operation_binding_changed")
        return data

    def _change(self, before, **changes):
        after=before|changes|{"version":before["version"]+1}
        self._expect=("UPDATE",self._image(before),self._image(after))
        try:
            keys=tuple(changes)+("version",)
            affected=self.conn.execute("UPDATE "+TABLE+" SET "+",".join(k+"=?" for k in keys)
                +" WHERE id=? AND version=?",tuple(after[k] for k in keys)+(before["id"],before["version"])).rowcount
            if affected!=1:raise ContractError("operation_CAS_failed")
        finally:self._expect=None

    @staticmethod
    def _image(row):
        return canonical([row[name] for name in _COLUMNS]).decode()

    def _update_money(self, account, *, held, booked):
        if held<0 or booked<account[5]:
            raise ContractError("shared_ledger_delta_invalid")
        self._money=(account[0],account[4],held,account[5],booked,account[6]+1)
        try:
            affected=self.conn.execute("""UPDATE research_funding_accounts SET held=?,upper_booked=?,version=version+1
                          WHERE id=? AND version=?""",(held,booked,account[0],account[6])).rowcount
            if affected!=1:raise ContractError("shared_ledger_CAS_failed")
        finally:self._money=None

    def confirm(self, run_id, grant, scope):
        with self._transaction():
            self._fence(grant,scope)
            self._account(grant)
            fields=(run_id,scope.research_id,scope.principal_id,scope.input_revision,scope.research_version,
                digest(canonical(scope.model_dump())),grant.preview.preview_digest,grant.preview.request_digest,
                digest(canonical(grant.quote.model_dump())),grant.account_id,grant.epoch,grant.quote.upper_units,
                "confirmed",1,None,None,None,None)
            self._expect=("INSERT",None,self._image(dict(zip(_COLUMNS,fields))))
            try:self.conn.execute("INSERT INTO "+TABLE+" VALUES("+",".join("?" for _ in fields)+")",fields)
            finally:self._expect=None

    def reserve(self, run_id, grant, scope, *, now):
        with self._transaction():
            self._fence(grant,scope)
            run=self._row(run_id,grant)
            if run["state"]!="confirmed" or not grant.quote.issued_at<=now<min(grant.quote.valid_until,grant.valid_until):
                raise ContractError("reserve_unavailable")
            if self.conn.execute("SELECT 1 FROM "+TABLE+" WHERE account_id=? AND state IN ('consumed','unknown')",(grant.account_id,)).fetchone():
                raise ContractError("reconcile_original_only")
            account=self._account(grant)
            settled,held,booked=account[3:6]
            upper=run["upper_units"]
            if settled+held+booked+upper>CAP_UNITS or grant.balance-MIN_RISK_MARGIN_UNITS-held-booked<upper:
                raise ContractError("shared_budget_exhausted")
            self._update_money(account,held=held+upper,booked=booked)
            self._change(run,state="reserved",reservation_ref=run_id)

    def consume(self, run_id, grant, scope, *, now):
        with self._transaction():
            self._fence(grant,scope)
            run=self._row(run_id,grant)
            account=self._account(grant)
            if run["state"]!="reserved" or account[4]<run["upper_units"] or not grant.quote.issued_at<=now<min(grant.quote.valid_until,grant.valid_until):
                raise ContractError("consume_unavailable")
            if self.conn.execute("SELECT 1 FROM "+TABLE+" WHERE account_id=? AND state IN ('consumed','unknown')",(grant.account_id,)).fetchone():
                raise ContractError("reconcile_original_only")
            if digest(grant.preview.raw_request)!=run["request_digest"]:
                raise ContractError("request_bytes_changed")
            self._change(run,state="consumed")
        return grant.preview.raw_request

    def finish(self, run_id, grant, scope, *, candidate=None):
        """None represents an unconfirmed fixture receipt, not zero cost."""
        with self._transaction():
            run=self._row(run_id,grant)
            if run["state"]!="consumed":
                raise ContractError("reconcile_original_only")
            if candidate is None:
                self._change(run,state="unknown")
                return "unknown"
            self._fence(grant,scope)
            account=self._account(grant)
            parsed=parse_unverified_candidate(candidate)
            body=canonical(parsed)
            candidate_digest=digest(body)
            receipt=digest(canonical({"fixture":True,"request":run["request_digest"],"body":candidate_digest}))
            self._update_money(account,held=account[4]-run["upper_units"],booked=account[5]+run["upper_units"])
            self._change(run,state="returned",receipt_digest=receipt,candidate_digest=candidate_digest,candidate_json=body.decode())
            return "returned"

    def read(self, run_id, grant, scope):
        with self._transaction():
            self._fence(grant,scope)
            run=self._row(run_id,grant)
            if run["state"]!="returned" or digest(run["candidate_json"].encode())!=run["candidate_digest"]:
                raise ContractError("result_unavailable")
            return run["candidate_json"]
