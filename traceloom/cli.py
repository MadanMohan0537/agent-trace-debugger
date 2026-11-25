import argparse
import json

from .fixtures import sample_runs
from .report import write_report
from .store import TraceStore
from .fixtures import recovery_fixture
from .privacy import PrivacyPolicy
from .sufficiency import diagnostic_sufficiency_canary


def demo(db_path:str,json_path:str,html_path:str,ttl_ms:int|None=None,now_ms:int=0)->dict:
    store=TraceStore(db_path)
    for run in sample_runs(): store.ingest(run,ingested_at_ms=now_ms,ttl_ms=ttl_ms)
    return write_report(store.runs(),json_path,html_path,store.privacy_summary())


def main(argv=None)->int:
    parser=argparse.ArgumentParser(prog="traceloom")
    sub=parser.add_subparsers(dest="command",required=True)
    command=sub.add_parser("demo",help="ingest scripted traces and create reports")
    command.add_argument("--db",default="traceloom.db"); command.add_argument("--json",default="report.json"); command.add_argument("--html",default="report.html")
    command.add_argument("--ttl-ms",type=int,default=None,help="optional deterministic retention period")
    command.add_argument("--now-ms",type=int,default=0,help="injected ingestion time for reproducible runs")
    purge=sub.add_parser("purge",help="delete traces whose deterministic TTL has expired")
    purge.add_argument("--db",default="traceloom.db")
    purge.add_argument("--now-ms",type=int,required=True,help="injected current time")
    canary=sub.add_parser("policy-canary",help="gate privacy policy on diagnostic decision preservation")
    canary.add_argument("--input-fields",default=",".join(PrivacyPolicy().input_allowlist),help="comma-separated input allowlist")
    canary.add_argument("--output-fields",default=",".join(PrivacyPolicy().output_allowlist),help="comma-separated output allowlist")
    canary.add_argument("--max-decision-losses",type=int,default=0)
    canary.add_argument("--output",default="policy-canary.json")
    args=parser.parse_args(argv)
    if args.command=="purge":
        deleted=TraceStore(args.db).purge_expired(args.now_ms)
        print(json.dumps({"deleted_run_ids":deleted,"deleted":len(deleted)},indent=2))
        return 0
    if args.command=="policy-canary":
        policy=PrivacyPolicy(
            tuple(item for item in args.input_fields.split(",") if item),
            tuple(item for item in args.output_fields.split(",") if item),
        )
        recovery_run, attempts=recovery_fixture()
        result=diagnostic_sufficiency_canary(
            sample_runs(),recovery_run,attempts,policy,
            max_decision_losses=args.max_decision_losses,
        )
        with open(args.output,"w",encoding="utf-8") as handle:
            json.dump(result,handle,indent=2); handle.write("\n")
        print(json.dumps({key:result[key] for key in ("accepted","decision_checks","decision_losses")},indent=2))
        return 0 if result["accepted"] else 2
    report=demo(args.db,args.json,args.html,args.ttl_ms,args.now_ms)
    print(json.dumps({"summary":report["summary"],"privacy":report["privacy"]},indent=2))
    return 0


if __name__=="__main__": raise SystemExit(main())

