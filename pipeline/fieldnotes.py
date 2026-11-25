"""Build a local Agent Fieldnotes site from private normalized JSON Lines."""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
from statistics import median
import tempfile
from zoneinfo import ZoneInfo

import insights
import jev
from privacy import load_model, redact
from sources import claude, codex, cursor, records, timestamp

BASE = Path(__file__).resolve().parents[1]
NAMES = {'codex':'Codex','claude':'Claude Code','cursor':'Cursor','zcode':'ZCode','opencode':'OpenCode','mimocode':'Mimocode','omp':'OMP / Pi'}
KINDS = {'prompt','response','turn','tool'}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value,separators=(',',':'))+'\n')


def private_write(path, data):
    with open(path,'wb',opener=lambda p,f:os.open(p,f,0o600)) as stream:
        stream.write(data)


def month(stamp):
    return stamp.strftime('%Y-%m')


def summarize(values):
    values = sorted(values)
    return {'median':median(values),'p90':values[(9*len(values)-1)//10],'max':values[-1]}


def histogram(samples, edges):
    counts = [0]*(len(edges)+1)
    work = [0]*len(counts)
    for _,value in samples:
        i = bisect_right(edges,value)
        counts[i] += 1
        work[i] += value
    values = [value for _,value in samples]
    days = sorted({stamp.date().isoformat() for stamp,_ in samples})
    return dict(summarize(values),n=len(values),counts=counts,work=work,sum=sum(values),
                first_day=days[0],last_day=days[-1],observed_days=len(days))


def review_answers(answer):
    feedback = answer.get('feedback','uncertain')
    steering = answer.get('steering','uncertain')
    return {'use_case':{'choice':answer.get('use_case','unclear')},'feedback':{'choice':feedback},
            'steering':{'choice':steering},'feedback_present':{'noul':int(feedback not in ('uncertain','no_feedback'))},
            'corrective_steering':{'noul':int(steering in ('moderate','heavy'))}}


def normalize(rows):
    unique = {}
    for row in rows:
        if (row.get('kind') not in KINDS or not isinstance(row.get('app'),str)
                or not re.fullmatch(r'[a-z][a-z0-9_-]*',row['app']) or row['app'] in {'all','constructor','prototype'}
                or not all(isinstance(row.get(k),str) and row[k] for k in ('id','conversation'))):
            raise ValueError('Invalid normalized record')
        stamp = timestamp(row.get('time'))
        if not stamp:
            continue
        if row['kind']=='prompt' and (not isinstance(row.get('text'),str) or not row['text'].strip()):
            continue
        row = dict(row,stamp=stamp,end_stamp=timestamp(row.get('end')))
        key = row['app'],row['kind'],row['id']
        old = unique.get(key)
        if old and old['conversation']==row['conversation'] and row['kind']=='response':
            # Streaming frames may carry only a cumulative output update.
            for field in ('input_tokens','cache_read','output_tokens'):
                values = [item[field] for item in (old,row) if type(item.get(field)) is int]
                if values:
                    old[field] = max(values)
            old['stamp'] = max(old['stamp'],row['stamp'])
            if old.get('trigger') and row.get('trigger') and old['trigger']!=row['trigger']:
                old['_conflicting_trigger'] = True
            if not old.get('_conflicting_trigger'):
                old['trigger'] = old.get('trigger') or row.get('trigger')
            continue
        if old and old['conversation']==row['conversation'] and row['kind']=='tool':
            old_terminal = type(old.get('failed')) is bool
            new_terminal = type(row.get('failed')) is bool
            if old_terminal!=new_terminal:
                if new_terminal:
                    unique[key] = row
                continue
        if old and old['conversation']==row['conversation'] and row['kind']=='turn':
            # Re-exports of the same cycle can extend its recorded completion.
            if stamp<old['stamp']:
                old['stamp'],old['time'] = stamp,row['time']
            if row.get('end_stamp') and (not old.get('end_stamp') or row['end_stamp']>old['end_stamp']):
                old['end'],old['end_stamp'] = row.get('end'),row['end_stamp']
            continue
        if old is None or stamp<old['stamp']:
            unique[key] = row
    return sorted(unique.values(),key=lambda row:row['stamp'])


def coverage_summary(rows):
    """Aggregate retained events for the public Method coverage table."""
    cells = defaultdict(lambda: defaultdict(lambda: {'prompts':0,'responses':0,
                                                    'with_tokens':0,'threads':set()}))
    for row in rows:
        if row['kind'] not in {'prompt','response'}:
            continue
        cell = cells[row['app']][month(row['stamp'])]
        if row['kind']=='prompt':
            cell['prompts'] += 1
            cell['threads'].add(row['conversation'])
        else:
            cell['responses'] += 1
            start,end = row.get('input_tokens'),row.get('output_tokens')
            if type(start) is int and type(end) is int and start>=0 and end>=0 and start+end>0:
                cell['with_tokens'] += 1
    return {'apps':{app:{m:dict(prompts=cell['prompts'],threads=len(cell['threads']),
                                 responses=cell['responses'],with_tokens=cell['with_tokens'])
                         for m,cell in months.items()} for app,months in cells.items()},
            'unavailable':[]}


def synthetic():
    for m in (1,2,3):
        for i in range(8):
            first = datetime(2025,m,i+1,10+i,tzinfo=timezone.utc)
            sid = f'demo-{m}-{i}'
            app = ('codex','claude','other_agent')[i%3]
            for j in range(3):
                stamp = first+timedelta(days=j,hours=j)
                pid = f'{sid}-{j}'
                feedback = ('positive','negative','mixed')[i%3]
                yield dict(app=app,kind='prompt',id=pid,conversation=sid,time=stamp.isoformat(),
                           text='Review the synthetic example.' if j==0 else 'Refine the synthetic example.',
                           labels={'use_case':'software_development','feedback':feedback,
                                   'steering':('none','light','moderate','heavy')[i%4],
                                   'autonomy':'execute','interaction':'correction' if j else 'initial_request',
                                   'revision':'incorrect_result' if j else 'none'})
                yield dict(app=app,kind='turn',id=pid,conversation=sid,time=stamp.isoformat(),
                           end=(stamp+timedelta(minutes=4*i+1)).isoformat())
                yield dict(app=app,kind='tool',id=pid,conversation=sid,time=stamp.isoformat(),failed=i%3==0)
                for k in range(m*(i+1)):
                    yield dict(app=app,kind='response',id=f'{pid}-{k}',conversation=sid,trigger=pid,
                               time=(stamp+timedelta(seconds=k+1)).isoformat(),input_tokens=800,
                               cache_read=600,output_tokens=50)


def build(options):
    if options.demo and (options.input or options.jev):
        raise ValueError('The synthetic demo must be built separately from real inputs and Jev')
    if options.jev and not options.pii_model:
        raise ValueError('Real prompt labeling requires --pii-model')
    target = options.out.resolve()
    if target.exists() and not (target / '.fieldnotes-build').is_file():
        raise ValueError('Output directory already exists and was not generated by this pipeline')
    inputs = [p.resolve() for p in options.input]
    if any(p.is_relative_to(target) for p in inputs) or options.private.resolve().is_relative_to(target):
        raise ValueError('Keep inputs and private state outside the generated directory')
    options.private.mkdir(parents=True,exist_ok=True,mode=0o700)
    seed = options.private/'public-id-seed'
    if not seed.exists():
        private_write(seed,secrets.token_bytes(32))
    salt = seed.read_bytes()

    def public_id(prefix,*identity):
        raw = json.dumps(identity,separators=(',',':')).encode()
        return prefix+hmac.new(salt,raw,hashlib.sha256).hexdigest()[:20]

    def inputs_iter():
        if options.demo:
            yield from synthetic()
        for path in inputs:
            with path.open('rb') as stream:
                yield from records(stream)

    rows = normalize(inputs_iter())
    prompts = [r for r in rows if r['kind']=='prompt']
    if not prompts:
        raise ValueError('No dated human prompts found in input')
    seen = Counter(p['id'] for p in prompts)
    if any(n>1 for n in seen.values()):
        raise ValueError('Prompt IDs must be globally unique across adapters')
    prompt_lookup = {p['id']:p for p in prompts}
    by_conversation = defaultdict(list)
    for p in prompts:
        by_conversation[p['app'],p['conversation']].append(p)
    apps = sorted({p['app'] for p in prompts} | {r['app'] for r in rows if r['kind']=='response'})
    snapshot = date.fromisoformat(options.through) if options.through else max(r['stamp'].date() for r in rows)
    if max(r['stamp'].date() for r in rows)>snapshot:
        raise ValueError('The supplied snapshot precedes at least one input event')

    pii_model = load_model(options.pii_model) if options.jev else None
    labeler = jev.Labeler(options.private/'labels.sqlite') if options.jev else None
    cleaned = {p['id']:redact(p['text'],pii_model) for p in prompts} if labeler else {}
    labels = {}
    by_app = {app:{'records':0,'words':0,'threads':0,'monthly':{}} for app in apps}
    monthly_threads = defaultdict(set)
    qualitative = []
    labeled_threads = []
    for (app,sid),group in by_conversation.items():
        by_app[app]['threads'] += 1
        messages = [cleaned.get(p['id']) for p in group]
        first = group[0]['stamp']
        for i,p in enumerate(group):
            answer = p.get('labels',{}) if options.demo else {}
            if labeler and messages[i]:
                answer = labeler([s for s in messages[max(0,i-2):i+1] if s],jev.PROMPT)
            labels[p['id']] = answer
            words = len(p['text'].split())
            a = by_app[app]
            a['records'] += 1
            a['words'] += words
            m = month(p['stamp'])
            monthly_threads[app,m].add(sid)
            entry = a['monthly'].setdefault(m,{'prompts':0,'words':0})
            entry['prompts'] += 1
            entry['words'] += words
        cid = public_id('c',app,sid)
        retained = [s for s in messages if s]
        overall = labeler(retained,jev.THREAD) if labeler and retained else labels[group[-1]['id']]
        label_row = dict(id=cid,app=app,date=month(first),prompt_count=len(group),answers=review_answers(overall))
        labeled_threads.append(label_row)
        for m in sorted({month(p['stamp']) for p in group}):
            in_month = [i for i,p in enumerate(group) if month(p['stamp'])==m]
            current = [messages[i] for i in in_month if messages[i]]
            answer = labeler(current,jev.THREAD) if labeler and current else labels[group[in_month[-1]]['id']]
            qualitative.append(dict(app=app,month=m,prompt_count=len(in_month),answers=review_answers(answer)))

    for (app,m),threads in monthly_threads.items():
        by_app[app]['monthly'][m]['threads'] = len(threads)

    tokens = {app:defaultdict(Counter) for app in apps}
    iteration_totals = {app:defaultdict(set) for app in apps}
    responses_by_month = defaultdict(Counter)
    attributed = defaultdict(list)
    for r in rows:
        app,m = r['app'],month(r['stamp'])
        if app not in tokens:
            continue
        if r['kind']=='turn':
            tokens[app][m]['turns'] += 1
        if r['kind']!='response':
            continue
        responses_by_month[app][m] += 1
        iteration_totals[app][m].add(r['conversation'])
        start,end = r.get('input_tokens'),r.get('output_tokens')
        if type(start) is int and type(end) is int and start>=0 and end>=0 and start+end>0:
            t = tokens[app][m]
            t.update(input_tokens=start,output_tokens=end,total_tokens=start+end,token_coverage=1)
            cached = r.get('cache_read')
            if type(cached) is int and 0<=cached<=start:
                t.update(cache_read=cached,cache_coverage=1)
        p = prompt_lookup.get(r.get('trigger'))
        if p and not r.get('_conflicting_trigger') and p['stamp']<=r['stamp']:
            attributed[p['id']].append(r)

    horizons = {'iterations':defaultdict(lambda:defaultdict(list)),'elapsed':defaultdict(lambda:defaultdict(list))}
    matches = defaultdict(lambda:defaultdict(list))
    for pid,events in attributed.items():
        p = prompt_lookup[pid]
        app,stamp = p['app'],p['stamp']
        elapsed = (max(r['stamp'] for r in events)-stamp).total_seconds()/60
        m = month(stamp)
        matches[app][m].append((p['conversation'],len(events)))
        for target_app in (app,'all'):
            horizons['iterations'][target_app][m].append((stamp,len(events)))
            horizons['elapsed'][target_app][m].append((stamp,elapsed))
    horizon = {}
    for kind,value in horizons.items():
        edges = [6,20,100] if kind=='iterations' else [1,5,30]
        horizon[kind] = {a:{m:histogram(samples,edges) for m,samples in months.items()} for a,months in value.items()}

    cohorts = defaultdict(lambda:defaultdict(list))
    boundary = datetime.combine(snapshot,datetime.min.time(),timezone.utc)
    for (app,sid),group in by_conversation.items():
        first = group[0]['stamp']
        end = first+timedelta(days=7)
        if end>boundary or first.day>15:
            continue
        observed = [p for p in group if p['stamp']<end]
        hours = (observed[-1]['stamp']-first).total_seconds()/3600
        for a in (app,'all'):
            cohorts[month(first)][a].append((hours,len(observed)))
    thread_cohorts = {m:{a:dict(n=len(v),follow_up_day_later=sum(h>=24 for h,_ in v),
                                  user_activity_span=summarize([h for h,_ in v]),
                                  prompts=summarize([n for _,n in v]))
                         for a,v in group.items()} for m,group in sorted(cohorts.items())}
    metrics = dict(snapshot=snapshot.isoformat(),apps=by_app,app_names={a:NAMES.get(a,a.replace('_',' ').title()) for a in apps},
                   token_trends=tokens,total_records=len(prompts),total_threads=len(by_conversation),
                   withheld_texts=sum(s is None for s in cleaned.values()),qual_threads=len(labeled_threads))
    cards = insights.insight_cards(prompts,labels,by_conversation,tokens,
            [r for r in rows if r['kind']=='tool'],[r for r in rows if r['kind']=='turn'],options.timezone)

    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fieldnotes-',dir=target.parent) as temp:
        stage = Path(temp)/'site'
        shutil.copytree(BASE/'web',stage)
        (stage/'.fieldnotes-build').touch()
        write_json(stage/'metrics.json',metrics)
        write_json(stage/'coverage.json',coverage_summary(rows))
        write_json(stage/'conversation-labels.json',labeled_threads)
        write_json(stage/'qualitative-monthly.json',qualitative)
        write_json(stage/'insights/data.json',cards)
        write_json(stage/'agent-iterations.json',{'apps':{a:{'monthly':{
            m:{'iterations':n,'active_conversations':len(iteration_totals[a][m])}
            for m,n in ms.items()}} for a,ms in responses_by_month.items()}})
        write_json(stage/'prompt-react.json',{'snapshot':snapshot.isoformat(),'horizon':horizon,'thread_cohorts':thread_cohorts,
            'apps':{a:{m:dict(prompts=len(xs),iterations=sum(n for _,n in xs),active_conversations=len({c for c,_ in xs}))
                       for m,xs in ms.items()} for a,ms in matches.items()}})
        backup = Path(temp)/'previous'
        if target.exists():
            target.rename(backup)
        try:
            stage.rename(target)
        except OSError:
            if backup.exists():
                backup.rename(target)
            raise
    print(f'Built {len(prompts)} prompt records across {len(by_conversation)} conversations.')


def collect(options):
    sources = options.codex,options.claude,options.cursor
    if not any(sources):
        raise ValueError('Specify at least one source path')
    path = options.out.resolve()
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.exists():
        raise ValueError('Select a fresh path for the private export')
    with open(path,'x',opener=lambda p,f:os.open(p,f,0o600)) as stream:
        count = 0
        for adapter,source in zip((codex,claude,cursor),sources):
            if not source:
                continue
            for row in adapter(source.resolve()):
                if row:
                    stream.write(json.dumps(row,separators=(',',':'))+'\n')
                    count += 1
    print(f'Collected {count} private events.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(required=True)
    reader = commands.add_parser('collect')
    for key in ('codex','claude','cursor'):
        reader.add_argument('--'+key,type=Path)
    reader.add_argument('--out',type=Path,required=True)
    reader.set_defaults(run=collect)
    builder = commands.add_parser('build')
    builder.add_argument('--input',type=Path,action='append',default=[])
    builder.add_argument('--out',type=Path,default=Path('dist'))
    builder.add_argument('--private',type=Path,default=Path('.fieldnotes'))
    builder.add_argument('--timezone',default='UTC',type=lambda s:ZoneInfo(s).key)
    builder.add_argument('--through')
    builder.add_argument('--demo',action='store_true')
    builder.add_argument('--pii-model')
    builder.add_argument('--jev',action='store_true')
    builder.set_defaults(run=build)
    options = parser.parse_args()
    options.run(options)


if __name__=='__main__':
    main()
