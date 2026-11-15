"""Reproducible assignment arithmetic; no invented timing inputs."""
import csv
import json
import math
from pathlib import Path

from tool_latency_logger import summarize, historical_air_coverage

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs'


def read(name):return json.loads((ROOT/'data'/name).read_text())


def parameters(a):
    digits=a['ROLL_DIGITS']
    if not isinstance(digits,str) or len(digits)<2 or not digits.isascii() or not digits.isdigit():
        raise ValueError('ROLL_DIGITS must be a digit string preserving leading zeros')
    r,d=int(digits[-2:]),sum(map(int,digits))%10
    return dict(R=r,D=d,Q=1500+25*r,N=5+r%4,p=.04+.01*d,H=4+r%4,
                B=1200+10*r,T=10-r%3)


def volumes(a,p):
    rows=[]
    for k in range(1,p['N']+1):
        inp=a['input_base']+a['input_step']*(k-1)
        out=a['final_output'] if k==p['N'] else a['tool_output']
        multiplier=1 if k==p['N'] else 1+p['p']
        rows.append(dict(k=k,input=inp,output=out,attempts=multiplier,
                         expected_input=inp*multiplier,expected_output=out*multiplier))
    qi=sum(r['expected_input'] for r in rows)
    qo=sum(r['expected_output'] for r in rows)
    calls=round(sum(r['attempts'] for r in rows),12)
    month_factor=a['days']-p['H']+a['heat_multiplier']*p['H']
    month_q=p['Q']*month_factor
    peak_qpm=p['Q']*a['heat_multiplier']*a['peak_fraction']/a['peak_minutes']
    return dict(rows=rows,input_query=qi,output_query=qo,calls_query=calls,
                prefix_query=a['prefix']*calls,month_factor=month_factor,month_queries=month_q,
                input_month_M=qi*month_q/1e6,output_month_M=qo*month_q/1e6,
                prefix_month_M=a['prefix']*calls*month_q/1e6,peak_qpm=peak_qpm,
                peak_rpm=peak_qpm*calls,peak_itpm=peak_qpm*qi,peak_otpm=peak_qpm*qo,
                peak_tpm=peak_qpm*(qi+qo))


def api_cost(m,a,p,v):
    inp,out=m['price_input'],m['price_output']
    if inp is None or out is None:return dict(model=m['name'],status='PENDING prices',nocache=None,cache=None)
    # Additional reasoning average is PER ATTEMPT, included in both cost and load.
    reasoning=m.get('reasoning_average')
    extra=(reasoning or 0)*v['calls_query']*v['month_queries']/1e6
    lower=reasoning is None
    base=v['input_month_M']*inp+(v['output_month_M']+extra)*out
    c=m['price_cache']
    eligibility=(m['cache_verified'] and m['cache_min'] is not None and
                 a['prefix']>=m['cache_min'] and c is not None and
                 m['cache_write_multiplier'] is not None)
    effective=0
    ttl_cost=None
    cost=base
    cache_status='No savings credited: minimum or write/lifetime terms not verified'
    if eligibility:
        effective=math.floor(a['prefix']/m['cache_block'])*m['cache_block']
        total=effective*v['calls_query']*v['month_queries']/1e6
        writes=effective*v['month_queries']/1e6
        hits=total-writes
        cost=(v['input_month_M']-total)*inp+writes*inp*m['cache_write_multiplier']+hits*c+(v['output_month_M']+extra)*out
        cache_status='One cold write per query; remaining attempts hit within TTL; conditional scenario'
        if m['cache_ttl']:
            # Shared system/schema prefix, one cache key, fixed expiry windows,
            # continuously active month. This is an assumption, not a hit-rate measurement.
            windows=math.ceil(a['days']*86400/m['cache_ttl'])
            ttl_writes=min(windows,v['month_queries']*v['calls_query'])*effective/1e6
            ttl_cost=(v['input_month_M']-total)*inp+ttl_writes*inp*m['cache_write_multiplier']+(total-ttl_writes)*c+(v['output_month_M']+extra)*out
    elif m['cache_min'] is not None and a['prefix']<m['cache_min']:
        cache_status='No caching: 1500-token prefix below provider minimum'
    return dict(model=m['name'],nocache=base,cache=cost,cache_ttl_window=ttl_cost,eligible_prefix=effective,
        status='LOWER BOUND: reasoning average not verified' if lower else 'Visible-token cost',cache_status=cache_status,
        within_budget_nocache=('not established' if lower and base<=p['B'] else base<=p['B']),
        within_budget_cache=('not established' if lower and cost<=p['B'] else cost<=p['B']),
        rpm_check='not verified' if m['rpm'] is None else ('pass' if m['rpm']>=v['peak_rpm'] else 'exceeds'),
        tpm_check='not verified' if m['tpm'] is None else ('pass visible-token demand' if m['tpm']>=v['peak_tpm'] else 'exceeds even before reasoning'),
        cache_write_rate=inp*m['cache_write_multiplier'] if m['cache_write_multiplier'] is not None else None)


def memory(a,p,v,c):
    h,i,l,kv,heads,vs=(c[k] for k in ['hidden_size','intermediate_size','num_hidden_layers','num_key_value_heads','num_attention_heads','vocab_size'])
    dim=c['head_dim']
    # Qwen2 standard architecture: independent input embedding and lm_head,
    # Q/K/V biases, no output/MLP biases, two RMSNorms/layer and final RMSNorm.
    params=2*vs*h+l*(2*h*h+2*h*kv*dim+3*h*i+2*h+ h+2*kv*dim)+h
    seq=v['rows'][-1]['input']+v['rows'][-1]['output']
    kv_bytes=2*l*kv*dim*seq*2
    weights4=params/2
    capacity=math.floor((a['gpu_bytes']*(1-a['reserve_fraction'])-weights4)/kv_bytes)
    lam=v['peak_qpm']/60
    w=a['sizing_service_seconds']
    sessions=None if w is None else lam*w
    gpus=None if sessions is None else math.ceil(sessions/capacity)
    sensitivity_sessions=lam*a['sensitivity_service_seconds']
    return dict(gpu_name=a.get('gpu_name','NVIDIA RTX 4090 24 GB'),service_time_basis=a.get('service_time_basis','not verified'),
        parameters_exact=params,sequence_length=seq,kv_bytes=kv_bytes,
        fp16_bytes=2*params,int8_bytes=params,int4_bytes=weights4,
        concurrent_capacity=capacity,lambda_peak_per_second=lam,
        service_seconds=w,mean_sessions=sessions,gpus=gpus,
        monthly_gpu_cost=None if gpus is None else gpus*a['gpu_hourly']*24*a['days'],
        sensitivity_sessions=sensitivity_sessions,
        sensitivity_gpus=math.ceil(sensitivity_sessions/capacity),
        sensitivity_monthly_cost=math.ceil(sensitivity_sessions/capacity)*a['gpu_hourly']*24*a['days'])


def latency(m,a,p,timing):
    delay=timing['pooled_median_seconds'] if timing['complete'] else None
    per_call=m.get('ttft_by_call', [None]*p['N'])
    tps=m.get('tps')
    reasoning=m.get('reasoning_average')
    result=dict(model=m['name'],total_seconds=None,api_only_total=None,retry_seconds=None,
        decode_seconds=None,changed_total_seconds=None,changed_api_only_seconds=None,
        status='PENDING setting-matched TTFT/throughput/reasoning inputs',
        architecture='Replace LLM tool planning with one deterministic workflow executing the same five tools, followed by one 600-token LLM answer at 6000 input tokens; no invalid LLM tool calls to retry',
        changed_monthly_cost=None)
    # Changed token costs do not depend on missing timing benchmarks.
    if reasoning is not None and m['price_input'] is not None and m['price_output'] is not None:
        result['changed_monthly_cost']=((a['input_base']+a['input_step']*(p['N']-1))*m['price_input']+
            (a['final_output']+reasoning)*m['price_output'])*volumes(a,p)['month_queries']/1e6
    if m.get('reported_tps'):
        result['reported_speed_decode_floor']=volumes(a,p)['output_query']/m['reported_tps']
        result['reported_speed_caveat']='Diagnostic at the reported benchmark setting; not proof of speed with the selected setting'
    if delay is None:
        result['status']='PENDING complete tool log'
        return result
    if not tps or any(x is None for x in per_call) or reasoning is None:
        return result
    v=volumes(a,p)
    llm=sum(r['attempts']*(per_call[r['k']-1]+(r['output']+reasoning)/tps) for r in v['rows'])
    retry=p['p']*sum(per_call[k-1]+(a['tool_output']+reasoning)/tps for k in range(1,p['N']))
    changed_llm=per_call[-1]+(a['final_output']+reasoning)/tps
    changed_cost=(v['rows'][-1]['input']*m['price_input']+(a['final_output']+reasoning)*m['price_output'])*v['month_queries']/1e6
    result.update(total_seconds=llm+(p['N']-1)*delay,llm_seconds=llm,retry_seconds=retry,
        decode_seconds=v['output_query']/tps,ttft_seconds=sum(r['attempts']*per_call[r['k']-1] for r in v['rows']),
        api_only_total=llm+(p['N']-1)*timing['api_only_median_seconds'],
        changed_total_seconds=changed_llm+(p['N']-1)*delay,
        changed_api_only_seconds=changed_llm+(p['N']-1)*timing['api_only_median_seconds'],
        changed_monthly_cost=changed_cost,status='Estimate using reported non-reasoning aggregate TTFT at every input length; input-length-specific TTFT not verified; no queue/tail guarantee')
    return result


def comparison_csv(models,sources):
    # A single wide table, with each figure paired with its URL and date.
    keys=['parameters','context','max_output','price_input','price_output','price_cache',
          'cache_min','cache_write_multiplier','cache_ttl','rpm','tpm','otpm','performance_reported',
          'benchmark_tool','benchmark_other','native_tools','structured_json','reasoning','licence','new_account_limits',
          'reported_ttft','reported_tps','ttft','tps','reasoning_average']
    rows=[]
    for m in models:
        row={k:m[k] for k in ['name','kind','developer','inference_provider']}
        for k in keys:
            val=m['fields'].get(k,m.get(k))
            row[k]='not verified' if val is None else val
            src=sources[m['sources'].get(k,m['spec_source'])]
            row[k+'_source_url']=src['url'];row[k+'_access_date']=src['access_date']
        row['notes']=' '.join(m['notes']);rows.append(row)
    for folder in [ROOT/'data',OUT]:
        with (folder/'model_comparison.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)


def break_even(a,p,v,mem,costs,latencies):
    """Select only from two fully evaluated candidates; never assume missing latency passes."""
    complete=all(x['total_seconds'] is not None and x['changed_total_seconds'] is not None for x in latencies)
    selected=None
    if complete:
        options=[]
        for lat,cost in zip(latencies,[next(c for c in costs if c['model']==x['model']) for x in latencies]):
            original=lat['total_seconds']<=p['T']
            options.append(dict(model=lat['model'],seconds=lat['total_seconds'] if original else lat['changed_total_seconds'],
                                monthly_cost=cost['cache'] if original else lat['changed_monthly_cost']))
        eligible=[x for x in options if x['seconds']<=p['T']]
        selected=min(eligible,key=lambda x:x['monthly_cost']) if eligible else min(options,key=lambda x:x['seconds'])
    service=mem['service_seconds']
    def crossing(rate,w):
        capacity=mem['concurrent_capacity']/(a['heat_multiplier']*a['peak_fraction']/a['peak_minutes']/60*w)
        gpu_month=a['gpu_hourly']*24*a['days']
        if rate<=0 or gpu_month/rate>=capacity:return None
        # Strict inequality and integer daily volume; avoid crossing at a GPU jump.
        for n in range(1,10001):
            q=max(math.floor((n-1)*capacity)+1,math.floor(n*gpu_month/rate)+1)
            if q<=n*capacity:return q
        return None
    qstar=None if selected is None or service is None else crossing(selected['monthly_cost']/p['Q'],service)
    return dict(operational_qstar=qstar,selected_candidate=selected,
        reason='PENDING RTX 4090 service-time evidence and both candidates at the selected reasoning settings' if selected is None or service is None else 'Peak Little law mean-memory sizing; throughput and queue tails require validation',
        sensitivity_candidate='Claude Haiku 5.5',sensitivity_qstar=crossing(next(c['cache'] for c in costs if c['model']=='Claude Haiku 5.5')/p['Q'],a['sensitivity_service_seconds']),
        sensitivity_queries_per_gpu=mem['concurrent_capacity']/(a['heat_multiplier']*a['peak_fraction']/a['peak_minutes']/60*a['sensitivity_service_seconds']),
        sensitivity_monthly_per_gpu=a['gpu_hourly']*24*a['days'],
        sensitivity_api_monthly_per_daily_query=next(c['cache'] for c in costs if c['model']=='Claude Haiku 5.5')/p['Q'])


def cost_plot(a,p,v,mem,costs,be):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    verified=mem['service_seconds'] is not None and be['selected_candidate'] is not None
    service=mem['service_seconds'] if verified else a['sensitivity_service_seconds']
    capacity=mem['concurrent_capacity']/(a['heat_multiplier']*a['peak_fraction']/a['peak_minutes']/60*service)
    end=max(30000,p['Q']*10)
    # Exact GPU jump coordinates, rather than a sampled staircase with shifted boundaries.
    jumps=np.arange(1,math.ceil(end/capacity)+1)*capacity
    xs=np.unique(np.concatenate(([0,.000001,end],jumps[jumps<end],np.nextafter(jumps[jumps<end],np.inf))))
    ys=np.ceil(xs/capacity)*a['gpu_hourly']*24*a['days']
    fig,ax=plt.subplots(figsize=(9,5))
    ax.plot(xs,ys,label=f'RTX 4090 memory sizing, W={service:g} s'+(' assumed' if not verified else ''))
    compare=([be['selected_candidate']] if verified else [dict(model=c['model'],monthly_cost=c['cache']) for c in costs if c['model'] in ('GPT-5.4 nano','Claude Haiku 5.5')])
    for c in compare:ax.plot([0,end],[0,end*c['monthly_cost']/p['Q']],label=c['model']+' API')
    ax.axvline(p['Q'],color='gray',linestyle=':',label=f'Q = {p["Q"]:,}')
    ax.set(xlabel='Baseline queries per ordinary day Q; heatwave pattern retained',ylabel='USD per 30-day month',
           title='Operational cost comparison' if verified else 'Operational break-even PENDING | W=10 s illustration only')
    ax.legend(fontsize=8);ax.grid(alpha=.2);fig.tight_layout()
    fig.savefig(OUT/'monthly_cost_vs_daily_volume.png',dpi=180);plt.close(fig)


def evidence_outputs(result,models,sources):
    # Derived audit only: preserve the original timing CSV byte for byte.
    with (ROOT/'tool_latency_raw.csv').open(newline='') as handle, (OUT/'timing_audit.csv').open('w',newline='') as output:
        writer=csv.DictWriter(output,fieldnames=['run_id','tool','iteration','utc_time','timing_valid','data_requirement_met','response_file','finding'])
        writer.writeheader()
        for row in csv.DictReader(handle):
            coverage=historical_air_coverage(row) if row['tool']=='openaq' else None
            valid=row.get('timing_valid') or row['valid']
            writer.writerow(dict(run_id=row['run_id'],tool=row['tool'],iteration=row['iteration'],utc_time=row['utc_time'],
                timing_valid=valid,data_requirement_met=('not verified' if coverage is None else int(coverage)) if row['tool']=='openaq' else 'not applicable to PM coverage',
                response_file=row['response_file'],finding=('Saved response matching timestamp unavailable or sensor map not verified' if coverage is None else ('Recent dual pollutant data' if coverage else 'Recent PM2.5 AND PM10 not established')) if row['tool']=='openaq' else 'Original timing validation retained'))
    missing=[]
    for m in models:
        fields=[]
        for key in ['parameters','context','max_output','native_tools','structured_json','reasoning','licence','benchmark_tool','benchmark_other','performance_reported','new_account_limits']:
            val=m['fields'].get(key)
            if val is None or 'not verified' in str(val).lower():fields.append(key)
        for key in ['price_input','price_output','price_cache','cache_min','cache_block','cache_write_multiplier','cache_ttl','rpm','tpm','ttft','tps','reasoning_average']:
            if m.get(key) is None:fields.append(key)
        if fields:missing.append(m['name']+': '+', '.join(fields))
    missing += ['All models: lowest public price globally not verified; only checked-provider standard rates compared.',
                'RTX 4090 4-bit Qwen2.5-7B service time at peak concurrency: not verified; operational GPU count, cost and Q* PENDING.',
                'Haiku disabled-thinking TTFT and speed: not verified; second candidate and comparison selection PENDING.',
                'Nano TTFT per growing input length: not verified; constant aggregate TTFT is an explicit estimation assumption.',
                'Recent PM10: coverage gap. Historical raw-response coverage not verified for '+str(result['timing']['air_quality_coverage'].get('not_verified',0))+' OpenAQ samples.',
                'Model currency: older releases are retained; current endpoint availability and whether each qualifies as current at submission need review.']
    (OUT/'pending_items.txt').write_text('NOT VERIFIED evidence register — checked 2026-11-15\n\n'+'\n'.join(missing)+'\n')
    timing=result['timing']
    checks=[('Parameters page','DONE','R and D derived from ROLL_DIGITS; all derived values; first-page prefix exclusion note.'),
      ('Section 1 model selection','DONE','13 models: 6 closed / 7 open; 4 closed / 5 open developers; inference providers named.'),
      ('Section 1 current at submission','NOT VERIFIED','Availability/release currency of every endpoint at original submission is not established.'),
      ('Section 1.1 parameters including total/active MoE','NOT VERIFIED','Published counts retained; GPT OSS rounded; see model evidence register.'),
      ('Section 1.2 context and max output','NOT VERIFIED','Some endpoint-specific maximum outputs remain unresolved.'),
      ('Section 1.3 named provider input/output/cache prices','NOT VERIFIED','Qwen2.5 public price filled; cached prices and global minimum claims unresolved.'),
      ('Section 1.4 new-paid RPM/TPM','NOT VERIFIED','Published Build and Groq Developer numbers present; other account-specific quotas unresolved.'),
      ('Section 1.5 reported TTFT and tokens/s','NOT VERIFIED','Dated reported figures added for 12 models; Qwen speed on A100 only, TTFT missing; setting/provider matches listed.'),
      ('Section 1.6 two benchmarks including tool use','NOT VERIFIED','Vendor scores filled where available; Gemini, Grok, GPT OSS and Qwen2.5 gaps remain listed.'),
      ('Section 1.7 tools JSON reasoning','NOT VERIFIED','Endpoint-specific JSON/tool support and residual reasoning averages have gaps.'),
      ('Section 1.8 licence and commercial hosting','NOT VERIFIED','MiniMax commercial terms not verified; other reported terms included.'),
      ('Section 1 single table with per-figure URL/date','DONE','Report table uses dated source IDs; full per-field URLs/dates in CSV and workbook.'),
      ('Section 1 two-unverified-values paragraph','DONE','Haiku disabled TTFT and new Anthropic account quotas with impact explained.'),
      ('Section 2 show working','DONE','Per-call rows and token, cost, load, memory and step-function equations included.'),
      ('Section 2.1 expected and monthly tokens','DONE','25080 input / 2455 output per query; 146250 monthly queries.'),
      ('Section 2.2 API costs and caching','NOT VERIFIED','All 13 priced; eligibility and reasoning gaps prevent full cache/budget claims; both write scenarios shown.'),
      ('Section 2.3 peak load and rate limits','NOT VERIFIED','Peak arithmetic done; exact new-account feasibility remains incomplete.'),
      ('Section 2.4 attention architecture and config values','DONE','Qwen2.5 full-attention GQA; original config preserved and derived head_dim=128.'),
      ('Section 2.4 config screenshot','PENDING (needs me)','Embed your screenshot in the report placeholder.'),
      ('Section 2.4.1 FP16 8-bit 4-bit weights','DONE','Architecture-derived weights and overhead caveat.'),
      ('Section 2.4.2 KV per longest sequence','DONE','6600 tokens; 378470400 bytes.'),
      ('Section 2.4.3 GPU concurrent capacity','DONE','RTX 4090 24 GB, 10% reserve, 47 sequences memory ceiling.'),
      ('Section 2.4.4 operational GPU count','NOT VERIFIED','Little law implemented; RTX 4090 service-time basis missing. W=10 illustration is separate.'),
      ('Section 2.5 step cost break-even and realism','NOT VERIFIED','Step function and regenerated plot done; operational Q* awaits service time and second candidate latency.'),
      ('Section 2.6 raw timing minimum','DONE' if timing['complete'] else 'PENDING (needs me)','45/tool on Nov 14 and Nov 15; no third day needed.' if timing['complete'] else '; '.join(timing['missing'])),
      ('Section 2.6 pooled median and API sensitivity','DONE' if timing['complete'] else 'PENDING (needs me)','Observation-weighted pooled/API-only medians, fragility and machine check.'),
      ('Section 2.6 sequential latency retries and one change','NOT VERIFIED','Nano estimated and changed workflow recalculated; Haiku disabled figures missing; no guessed result.'),
      ('Submission Word or PDF report','DONE','outputs/report.docx; includes parameters, comparison, calculations and plot; screenshot remains pending.'),
      ('Submission spreadsheet or notebook','DONE','outputs/calculations.xlsx; one worksheet; plain Python builders, no notebooks.'),
      ('Submission raw timing log','DONE' if timing['complete'] else 'PENDING (needs me)','tool_latency_raw.csv retained unchanged with saved response audit limitations documented.'),
      ('Submission AI declaration','DONE','ai_declaration.txt corrected to describe actual assistance and remaining review.'),
      ('Final student review','PENDING (needs me)','Review report, source gaps, screenshot and declaration before submission; review required before commit or push.')]
    result['checklist']=[dict(item=i,status=s,evidence=e) for i,s,e in checks]
    (OUT/'submission_checklist.md').write_text('# Assignment Q1 completion checklist\n\n'+
        '\n'.join(f'- **{status}** — {item}: {evidence}' for item,status,evidence in checks)+'\n')


def main():
    OUT.mkdir(exist_ok=True)
    a=read('assumptions.json');p=parameters(a);v=volumes(a,p)
    models=read('models.json');timing=summarize();mem=memory(a,p,v,read('model_config_values.json'))
    costs=[api_cost(m,a,p,v) for m in models]
    candidates=[m for m in models if m['name'] in ('GPT-5.4 nano','Claude Haiku 5.5')]
    result=dict(parameters=p,volumes=v,timing=timing,memory=mem,costs=costs,
                latency=[latency(m,a,p,timing) for m in candidates])
    result['break_even']=break_even(a,p,v,mem,costs,result['latency'])
    cost_plot(a,p,v,mem,costs,result['break_even'])
    evidence_outputs(result,models,read('sources.json'))
    (OUT/'results.json').write_text(json.dumps(result,indent=2))
    (OUT/'answers.txt').write_text(
        'SAAFHAWA — CURRENT CALCULATED ANSWERS\n'
        'Research draft. Measurements and listed model evidence gaps remain PENDING.\n\n'
        f'R={p["R"]}, D={p["D"]}, Q={p["Q"]}, N={p["N"]}, p={p["p"]}, H={p["H"]}, B=${p["B"]}, T={p["T"]} seconds\n\n'
        f'Expected input/query: {v["input_query"]:,.0f} tokens\n'
        f'Expected output/query: {v["output_query"]:,.0f} tokens\n'
        f'Expected calls/query: {v["calls_query"]}\n'
        f'Monthly queries: {v["month_queries"]:,}\n'
        f'Monthly input: {v["input_month_M"]:,.6f} million tokens\n'
        f'Monthly output: {v["output_month_M"]:,.6f} million tokens\n'
        f'Monthly prefix material: {v["prefix_month_M"]:,.6f} million tokens (not guaranteed cache hits)\n\n'
        f'Peak queries/minute: {v["peak_qpm"]:,.6f}\n'
        f'Peak LLM requests/minute: {v["peak_rpm"]:,.6f}\n'
        f'Peak combined tokens/minute: {v["peak_tpm"]:,.6f} before residual reasoning\n\n'
        f'Qwen2.5 7B parameters derived from config: {mem["parameters_exact"]:,}\n'
        f'Longest sequence: {mem["sequence_length"]:,} tokens\n'
        f'FP16 KV per sequence: {mem["kv_bytes"]:,} bytes\n'
        f'24 GB 4090 memory ceiling: {mem["concurrent_capacity"]} sequences; compute throughput not demonstrated\n\n'
        f'Tool timing complete: {timing["complete"]}; pooled median {timing["pooled_median_seconds"] if timing["complete"] else "PENDING"} s; API-only {timing["api_only_median_seconds"] if timing["complete"] else "PENDING"} s.\n'
        f'Candidate latency: '+json.dumps(result['latency'])+'\n'
        'Operational GPU count and Q*: PENDING until verified service time and both candidate latencies exist.\n'
        'See report.docx, calculations.xlsx, model_comparison.csv and pending_items.txt for the full working and limitations.\n')
    comparison_csv(models,read('sources.json'))
    print(json.dumps({k:result[k] for k in ('parameters','volumes','memory','latency','break_even')},indent=2))
    print('Saved outputs/results.json and cost plot. PENDING items must not be submitted as measured results.')
    return result


if __name__=='__main__':main()
