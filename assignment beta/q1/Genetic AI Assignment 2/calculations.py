"""Reproducible assignment arithmetic; no invented timing inputs."""
import csv
import json
import math
from pathlib import Path

from tool_latency_logger import summarize

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs'


def read(name):return json.loads((ROOT/'data'/name).read_text())


def parameters(a):
    r,d=a['R'],a['D']
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
    cost=base
    cache_status='No savings credited: minimum or write/lifetime terms not verified'
    if eligibility:
        effective=math.floor(a['prefix']/m['cache_block'])*m['cache_block']
        total=effective*v['calls_query']*v['month_queries']/1e6
        writes=effective*v['month_queries']/1e6
        hits=total-writes
        cost=(v['input_month_M']-total)*inp+writes*inp*m['cache_write_multiplier']+hits*c+(v['output_month_M']+extra)*out
        cache_status='One cold write per query; remaining attempts hit within TTL; conditional scenario'
    elif m['cache_min'] is not None and a['prefix']<m['cache_min']:
        cache_status='No caching: 1500-token prefix below provider minimum'
    return dict(model=m['name'],nocache=base,cache=cost,eligible_prefix=effective,
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
    return dict(parameters_exact=params,sequence_length=seq,kv_bytes=kv_bytes,
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
    if delay is None or not tps or any(x is None for x in per_call) or reasoning is None:
        return dict(model=m['name'],total_seconds=None,status='PENDING complete tool log and setting-matched TTFT/throughput/reasoning inputs')
    v=volumes(a,p)
    llm=sum(r['attempts']*(per_call[r['k']-1]+(r['output']+reasoning)/tps) for r in v['rows'])
    return dict(model=m['name'],total_seconds=llm+(p['N']-1)*delay,llm_seconds=llm,
        api_only_total=llm+(p['N']-1)*timing['api_only_median_seconds'],status='estimate; no queue/network tail guarantee')


def comparison_csv(models,sources):
    # A single wide table, with each figure paired with its URL and date.
    keys=['parameters','context','max_output','price_input','price_output','price_cache',
          'cache_min','cache_write_multiplier','cache_ttl','rpm','tpm','otpm','performance_reported',
          'benchmark_tool','benchmark_other','native_tools','structured_json','reasoning','licence','new_account_limits']
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


def cost_plot(a,p,v,mem,costs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    # This is explicitly a T=10 s capacity sensitivity, not measured GPU service time.
    haiku=next(x for x in costs if x['model']=='Claude Haiku 5.5')
    rate=haiku['cache']/p['Q']
    service=a['sensitivity_service_seconds']
    sessions_per_q=a['heat_multiplier']*a['peak_fraction']/a['peak_minutes']/60*service
    capacity_q=mem['concurrent_capacity']/sessions_per_q
    gpu_month=a['gpu_hourly']*24*a['days']
    def count(q):return math.ceil(q/capacity_q) if q>0 else 0
    # Analytic interval search handles GPU jumps; equality does not count as cheaper.
    intervals=[]
    for n in range(1,101):
        lo=max((n-1)*capacity_q,n*gpu_month/rate)
        hi=n*capacity_q
        if lo<hi:intervals.append((lo,hi,n))
    qstar=math.floor(intervals[0][0])+1 if intervals else None
    xs=np.linspace(0,max(30000,p['Q']*10),1500)
    ys=np.array([count(q)*gpu_month for q in xs])
    fig,ax=plt.subplots(figsize=(9,5))
    ax.step(xs,ys,where='post',label='Self-hosting GPU memory floor, assumed W = T = 10 s')
    ax.plot(xs,xs*rate,label='Haiku 5.5 API, one cold cache write/query')
    ax.axvline(p['Q'],color='gray',linestyle=':',label=f'Assignment Q = {p["Q"]:,}')
    ax.set(xlabel='Baseline queries per ordinary day Q (heatwave pattern retained)',ylabel='USD per 30-day month',
           title='Conditional cost sensitivity — operational break-even PENDING')
    ax.legend(fontsize=8);ax.grid(alpha=.2);fig.tight_layout()
    fig.savefig(OUT/'monthly_cost_vs_daily_volume.png',dpi=180);plt.close(fig)
    return dict(operational_qstar=None,reason='PENDING self-host service time, throughput and latency-qualified candidate',
        sensitivity_candidate='Claude Haiku 5.5',sensitivity_qstar=qstar,
        sensitivity_first_interval=intervals[0] if intervals else None,
        sensitivity_queries_per_gpu=capacity_q,sensitivity_monthly_per_gpu=gpu_month,
        sensitivity_api_monthly_per_daily_query=rate)


def main():
    OUT.mkdir(exist_ok=True)
    a=read('assumptions.json');p=parameters(a);v=volumes(a,p)
    models=read('models.json');timing=summarize();mem=memory(a,p,v,read('model_config_values.json'))
    costs=[api_cost(m,a,p,v) for m in models]
    candidates=[m for m in models if m['name'] in ('GPT-5.4 nano','Claude Haiku 5.5')]
    result=dict(parameters=p,volumes=v,timing=timing,memory=mem,costs=costs,
                latency=[latency(m,a,p,timing) for m in candidates])
    result['break_even']=cost_plot(a,p,v,mem,costs)
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
        'Tool measurements: PENDING until the two-day requirements are met.\n'
        'Candidate latency, operational GPU count and operational Q*: PENDING.\n'
        'See report.docx, calculations.xlsx, model_comparison.csv and pending_items.txt for the full working and limitations.\n')
    comparison_csv(models,read('sources.json'))
    print(json.dumps({k:result[k] for k in ('parameters','volumes','memory','latency','break_even')},indent=2))
    print('Saved outputs/results.json and cost plot. PENDING items must not be submitted as measured results.')
    return result


if __name__=='__main__':main()
