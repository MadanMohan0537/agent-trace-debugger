import argparse
import json

from .fixtures import sample_runs
from .report import write_report
from .store import TraceStore


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
    args=parser.parse_args(argv)
    if args.command=="purge":
        deleted=TraceStore(args.db).purge_expired(args.now_ms)
        print(json.dumps({"deleted_run_ids":deleted,"deleted":len(deleted)},indent=2))
        return 0
    report=demo(args.db,args.json,args.html,args.ttl_ms,args.now_ms)
    print(json.dumps({"summary":report["summary"],"privacy":report["privacy"]},indent=2))
    return 0


if __name__=="__main__": raise SystemExit(main())

