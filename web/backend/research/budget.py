"""Exact, shared fixture accounting. This module never loads a provider key."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .errors import ResearchError
from .schemas import MAX_MONEY, FixtureResult, Money

POLICY = "c0-fixture-v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def expires(seconds=60):
    return (datetime.now(timezone.utc)+timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def enabled():
    return (os.getenv("STRUCTURAL_ENV","dev").lower() != "prod"
            and os.getenv("STRUCTURAL_RESEARCH_ENABLED","").lower() == "true"
            and os.getenv("STRUCTURAL_C0_ENABLED","").lower() == "true")


def require_enabled():
    if not enabled():
        raise ResearchError("FEATURE_UNAVAILABLE",503,"本机演练尚未开放。")


def money(units):
    return Money(currency="USD",scale=6,amount_units=units).model_dump()


def money_text(units):
    return f"USD {units//1000000}.{units%1000000:06d}（演练）"


def max_cost(price):
    values=[price[k] for k in ("input_rate","output_rate","max_input","max_output","fixed_units")]
    if any(type(v) is not int or not 0<=v<=MAX_MONEY for v in values):
        raise ResearchError("INPUT_INVALID",422,"演练费率无效。")
    left,right=price["input_rate"]*price["max_input"],price["output_rate"]*price["max_output"]
    units=((left+right+999999)//1000000 if price["rounding"]=="ceil_total"
           else (left+999999)//1000000+(right+999999)//1000000)+price["fixed_units"]
    if not 0<=units<=MAX_MONEY:
        raise ResearchError("INPUT_INVALID",422,"演练预留金额超出范围。")
    return units


class BudgetLedger:
    def __init__(self,store):
        self.store=store

    def provision_fixture(self,port,*,ttl_seconds=60,price_ttl_seconds=None):
        """Local test/control only; no HTTP route, real funding or new budget."""
        require_enabled()
        if type(port) is not int or not 1<=port<=65535:
            raise ValueError("fixture port required")
        with self.store.transaction(write=True) as conn:
            existing=conn.execute("SELECT * FROM research_funding_accounts").fetchone()
            if existing:
                if existing["fixture_port"]!=port:
                    raise ResearchError("AUTHORIZATION_STALE",409,"演练绑定已变化。")
                return existing["id"]
            account,binding,snapshot=str(uuid4()),str(uuid4()),str(uuid4())
            conn.execute("""INSERT INTO research_funding_accounts
                (id,binding_id,fixture_port,mode,currency,scale,funding_epoch,cap,status,snapshot_id)
                VALUES(?,?,?,'fixture','USD',6,1,10000,'active',?)""",(account,binding,port,snapshot))
            conn.execute("INSERT INTO research_balance_snapshots (id,account_id,balance,settled_at_observation,local_settlement_cursor,observed_at,expires_at,hard_prepaid,auto_topup_off,postpaid_off) VALUES(?,?,10000,0,0,?,?,1,1,1)",(snapshot,account,now(),expires(ttl_seconds)))
            for operation,units in (("discover_sources",7000),("compose_report",5000)):
                conn.execute("INSERT INTO research_price_revisions (id,account_id,operation,currency,scale,input_rate,output_rate,max_input,max_output,fixed_units,rounding,expires_at) VALUES(?,?,?,'USD',6,0,0,0,0,?,'ceil_total',?)",
                             (str(uuid4()),account,operation,units,expires(ttl_seconds if price_ttl_seconds is None else price_ttl_seconds)))
            return account

    @staticmethod
    def ready_in(conn,task_id):
        step=conn.execute("SELECT * FROM research_steps WHERE task_id=? AND state!='SUCCEEDED' ORDER BY position LIMIT 1",(task_id,)).fetchone()
        account=conn.execute("SELECT * FROM research_funding_accounts WHERE mode='fixture'").fetchone()
        if not step or step["state"] not in ("PENDING","PREPARED") or not account or account["status"]!="active":return False
        snapshot=conn.execute("SELECT * FROM research_balance_snapshots WHERE id=?",(account["snapshot_id"],)).fetchone()
        price=conn.execute("SELECT * FROM research_price_revisions WHERE account_id=? AND operation=?",(account["id"],step["kind"])).fetchone()
        if not snapshot or snapshot["expires_at"]<=now() or not price or price["expires_at"]<=now():return False
        try:amount=max_cost(price)
        except ResearchError:return False
        existing=conn.execute("SELECT * FROM research_reservations WHERE step_id=?",(step["id"],)).fetchone()
        if existing:
            permit=conn.execute("SELECT * FROM research_dispatch_permits WHERE step_id=?",(step["id"],)).fetchone()
            after=max(0,account["settled"]-snapshot["settled_at_observation"])
            return bool(existing["status"]=="HELD" and existing["max_cost"]==amount and existing["funding_epoch"]==account["funding_epoch"] and permit and permit["state"]=="prepared" and permit["expires_at"]>now() and snapshot["balance"]-account["held"]-after>=0)
        after=max(0,account["settled"]-snapshot["settled_at_observation"])
        return account["settled"]+account["held"]+amount<=account["cap"] and snapshot["balance"]-account["held"]-after>=amount

    @staticmethod
    def reserve_in(conn,task,step):
        require_enabled()
        existing=conn.execute("SELECT * FROM research_reservations WHERE step_id=?",(step["id"],)).fetchone()
        if existing:
            return dict(existing)
        account=conn.execute("SELECT * FROM research_funding_accounts WHERE mode='fixture'").fetchone()
        if not account or account["status"] != "active":
            raise ResearchError("BUDGET_UNVERIFIED",503,"演练额度尚未核实，未发起调用。")
        snapshot=conn.execute("SELECT * FROM research_balance_snapshots WHERE id=?",(account["snapshot_id"],)).fetchone()
        price=conn.execute("SELECT * FROM research_price_revisions WHERE account_id=? AND operation=?",(account["id"],step["kind"])).fetchone()
        if (not snapshot or not price or snapshot["expires_at"]<=now() or price["expires_at"]<=now()
                or price["currency"]!=account["currency"] or price["scale"]!=account["scale"]):
            raise ResearchError("BUDGET_UNVERIFIED",503,"演练额度或费率已过期，未发起调用。")
        amount=max_cost(price)
        after_snapshot=max(0,account["settled"]-snapshot["settled_at_observation"])
        if (account["settled"]+account["held"]+amount>account["cap"]
                or snapshot["balance"]-account["held"]-after_snapshot<amount):
            raise ResearchError("BUDGET_EXHAUSTED",429,"演练可用额度不足，未发起调用。")
        rid,pid,dispatch=str(uuid4()),str(uuid4()),str(uuid4())
        conn.execute("""INSERT INTO research_reservations
            (id,account_id,task_id,step_id,operation_key,price_revision,funding_epoch,max_cost,status)
            VALUES(?,?,?,?,?,?,?,?,'HELD')""",(rid,account["id"],task["id"],step["id"],step["id"]+":1",price["id"],account["funding_epoch"],amount))
        conn.execute("INSERT INTO research_dispatch_permits (id,step_id,reservation_id,dispatch_id,input_digest,state,expires_at) VALUES(?,?,?,?,?,'prepared',?)",(pid,step["id"],rid,dispatch,task["input_digest"],expires()))
        conn.execute("UPDATE research_funding_accounts SET held=held+?,version=version+1 WHERE id=?",(amount,account["id"]))
        conn.execute("UPDATE research_steps SET reservation_id=?,state='PREPARED',version=version+1 WHERE id=?",(rid,step["id"]))
        return dict(conn.execute("SELECT * FROM research_reservations WHERE id=?",(rid,)).fetchone())

    @staticmethod
    def dispatch_in(conn,step):
        require_enabled()
        permit=conn.execute("SELECT * FROM research_dispatch_permits WHERE step_id=?",(step["id"],)).fetchone()
        reservation=conn.execute("SELECT * FROM research_reservations WHERE id=?",(step["reservation_id"],)).fetchone()
        if (not permit or permit["state"]!="prepared" or permit["expires_at"]<=now()
                or not reservation or reservation["status"]!="HELD"):
            raise ResearchError("PERMIT_INVALID",409,"外发资格已失效，请核对当前任务。")
        account=conn.execute("SELECT * FROM research_funding_accounts WHERE id=?",(reservation["account_id"],)).fetchone()
        snapshot=conn.execute("SELECT * FROM research_balance_snapshots WHERE id=?",(account["snapshot_id"],)).fetchone()
        price=conn.execute("SELECT * FROM research_price_revisions WHERE id=?",(reservation["price_revision"],)).fetchone()
        if (account["status"]!="active" or account["funding_epoch"]!=reservation["funding_epoch"]
                or not snapshot or snapshot["expires_at"]<=now() or not price or price["expires_at"]<=now()
                or price["operation"]!=step["kind"] or price["currency"]!=account["currency"]
                or price["scale"]!=account["scale"] or max_cost(price)!=reservation["max_cost"]
                or snapshot["balance"]-account["held"]-max(0,account["settled"]-snapshot["settled_at_observation"])<0):
            raise ResearchError("BUDGET_UNVERIFIED",503,"演练额度已变化，未发起调用。")
        conn.execute("UPDATE research_dispatch_permits SET state='consumed' WHERE id=? AND state='prepared'",(permit["id"],))
        conn.execute("UPDATE research_reservations SET status='SENT',version=version+1 WHERE id=? AND status='HELD'",(reservation["id"],))
        conn.execute("UPDATE research_steps SET state='SENDING',version=version+1 WHERE id=?",(step["id"],))
        return dict(permit),dict(account)

    @staticmethod
    def release_prepared_in(conn,task_id):
        rows=conn.execute("SELECT r.* FROM research_reservations r JOIN research_dispatch_permits p ON p.reservation_id=r.id WHERE r.task_id=? AND r.status='HELD' AND p.state='prepared'",(task_id,)).fetchall()
        for row in rows:
            conn.execute("UPDATE research_dispatch_permits SET state='revoked',input_digest=NULL WHERE reservation_id=?",(row["id"],))
            conn.execute("UPDATE research_reservations SET status='RELEASED',version=version+1 WHERE id=?",(row["id"],))
            conn.execute("UPDATE research_funding_accounts SET held=held-?,version=version+1 WHERE id=?",(row["max_cost"],row["account_id"]))

    @staticmethod
    def unknown_in(conn,step_id):
        conn.execute("UPDATE research_reservations SET status='UNKNOWN',version=version+1 WHERE step_id=? AND status='SENT'",(step_id,))
        conn.execute("UPDATE research_steps SET state='UNKNOWN',version=version+1 WHERE id=? AND state IN ('SENDING','AWAITING_RECEIPT')",(step_id,))

    def settle(self,step_id,result):
        """Only a validated fixture response, never a browser fee assertion."""
        result=FixtureResult.model_validate(result)
        with self.store.transaction(write=True) as conn:
            reservation=conn.execute("SELECT * FROM research_reservations WHERE step_id=?",(step_id,)).fetchone()
            permit=conn.execute("SELECT * FROM research_dispatch_permits WHERE step_id=?",(step_id,)).fetchone()
            if (not reservation or not permit or permit["state"]!="consumed"
                    or result.dispatch_id!=permit["dispatch_id"]):
                raise ResearchError("PERMIT_INVALID",409,"收据与已登记调用不一致。")
            financial={k:v for k,v in result.model_dump(mode="json").items() if k!="note"}
            digest=hashlib.sha256(canonical(financial).encode()).hexdigest()
            previous=conn.execute("SELECT * FROM research_billing_receipts WHERE account_id=? AND provider_ref=?",(reservation["account_id"],result.receipt_ref)).fetchone()
            if previous:
                if previous["digest"]!=digest or previous["reservation_id"]!=reservation["id"]:
                    conn.execute("UPDATE research_funding_accounts SET status='blocked' WHERE id=?",(reservation["account_id"],))
                    return False
                return previous["status"]=="known"
            if reservation["status"] not in ("SENT","UNKNOWN"):
                return False
            account=conn.execute("SELECT * FROM research_funding_accounts WHERE id=?",(reservation["account_id"],)).fetchone()
            cost=result.cost.amount_units if result.cost else None
            final=result.final and cost is not None
            overflow=final and account["settled"]+cost>MAX_MONEY
            status="anomaly" if overflow else "known" if final else "nonfinal"
            conn.execute("INSERT INTO research_billing_receipts VALUES(?,?,?,?,?,?,?,?)",(str(uuid4()),reservation["id"],account["id"],result.receipt_ref,digest,cost,status,now()))
            if not final or overflow:
                self.unknown_in(conn,step_id)
                if overflow:conn.execute("UPDATE research_funding_accounts SET status='blocked' WHERE id=?",(account["id"],))
                return False
            conn.execute("UPDATE research_reservations SET status='SETTLED',settled_cost=?,version=version+1 WHERE id=?",(cost,reservation["id"]))
            conn.execute("UPDATE research_funding_accounts SET settled=settled+?,held=held-?,status=?,version=version+1 WHERE id=?",(cost,reservation["max_cost"],"blocked" if cost>reservation["max_cost"] else account["status"],account["id"]))
            return True
