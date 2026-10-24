import html
import json
from pathlib import Path

from .classifier import classify
from .metrics import summarize, watchdog_experiment
from .models import Run
from .fixtures import recovery_fixture
from .recovery import compare_recovery


def write_report(runs:list[Run],json_path:str,html_path:str)->dict:
    recovery_run, recovery_attempts = recovery_fixture()
    report={"summary":summarize(runs),"watchdog_experiment":watchdog_experiment(runs),
      "recovery_experiment":compare_recovery(recovery_run,recovery_attempts),"runs":[{
      "run_id":r.run_id,"task":r.task,"success":r.success,"failure":classify(r),"timeline":[s.to_dict() for s in r.spans]} for r in runs]}
    Path(json_path).write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    rows="".join(f"<tr><td>{html.escape(r.run_id)}</td><td>{html.escape(r.task)}</td><td>{'yes' if r.success else 'no'}</td><td>{classify(r) or '—'}</td><td>{sum(s.duration_ms for s in r.spans)}</td></tr>" for r in runs)
    body=f"""<!doctype html><meta charset='utf-8'><title>TraceLoom report</title><style>body{{font:16px system-ui;max-width:1000px;margin:2rem auto;color:#18212f}}table{{border-collapse:collapse;width:100%}}td,th{{padding:.6rem;border-bottom:1px solid #ccd}}.metric{{display:inline-block;padding:1rem;margin:.3rem;background:#eef3ff;border-radius:8px}}</style><h1>TraceLoom</h1><p>Offline agent trace report</p><div class='metric'>Runs <b>{report['summary']['runs']}</b></div><div class='metric'>Success rate <b>{report['summary']['success_rate']:.0%}</b></div><div class='metric'>Cost / success <b>${report['summary']['cost_per_success_usd']:.4f}</b></div><h2>Runs</h2><table><tr><th>ID</th><th>Task</th><th>Success</th><th>Failure</th><th>Latency ms</th></tr>{rows}</table>"""
    Path(html_path).write_text(body,encoding="utf-8")
    return report


