"""Explicit bounded local worker; no daemon or arbitrary commands."""
import argparse


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true",required=True)
    parser.add_argument("--task")
    args=parser.parse_args()
    from api import auth
    from .store import ResearchStore
    from .runner import ResearchRunner
    result=ResearchRunner(ResearchStore(auth._store())).run_once(args.task)
    print(result)


if __name__=="__main__":
    main()
