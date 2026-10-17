#!/usr/bin/env python3
"""Explicit offline bootstrap of the approved private runtime; no accounts."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web/backend'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--offline-bootstrap',action='store_true',
        help='Run only while all runtime consumers are stopped.')
    actions.add_argument('--offline-migrate-auth',action='store_true')
    actions.add_argument('--offline-admit-owner-key')
    parser.add_argument('--reconcile-operation')
    args=parser.parse_args()
    from services.auth_registration import bootstrap_private_runtime,migrate_private_auth_registration,admit_private_gate
    if args.offline_bootstrap:result=bootstrap_private_runtime()
    elif args.offline_migrate_auth:result=migrate_private_auth_registration()
    else:result=admit_private_gate(args.offline_admit_owner_key,operation_id=args.reconcile_operation)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
