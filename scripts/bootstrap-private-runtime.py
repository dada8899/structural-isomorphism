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
    actions.add_argument('--offline-migrate-first-answers',action='store_true',
        help='Upgrade an existing exact v15 database after a verified durable backup and shutdown.')
    actions.add_argument('--offline-migrate-external-fallback',action='store_true',
        help='Isolated marked v16 fixture only; provisions closed v17 without a provider.')
    actions.add_argument('--offline-admit-owner-key')
    parser.add_argument('--reconcile-operation')
    args=parser.parse_args()
    from services.auth_registration import bootstrap_private_runtime,migrate_private_auth_registration,admit_private_gate
    if args.offline_bootstrap:result=bootstrap_private_runtime()
    elif args.offline_migrate_auth:result=migrate_private_auth_registration()
    elif args.offline_migrate_first_answers:
        from research.first_answer import provision_first_answers_v16
        from services.runtime_paths import private_auth_path
        result=provision_first_answers_v16(private_auth_path())
    elif args.offline_migrate_external_fallback:
        from research.external_first_answer_catalog import provision_isolated_v17
        from research.external_first_answer_file_writer import approve_isolated_file
        from services.runtime_paths import private_auth_path
        result=provision_isolated_v17(approve_isolated_file(private_auth_path()))
    else:result=admit_private_gate(args.offline_admit_owner_key,operation_id=args.reconcile_operation)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
