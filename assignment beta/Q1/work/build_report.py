"""Optional local report export. Run through run_all.py from the project root."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import re
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from calculations import ROOT,OUT,read


def num(value,digits=2):return 'PENDING' if value is None else f'{value:,.{digits}f}'


def grid(doc,headers,rows,widths=None,fontsize=9):
    t=doc.add_table(rows=1,cols=len(headers));t.style='Table Grid';t.autofit=False
    if widths:
        for column,width in zip(t.columns,widths):column.width=Inches(width)
    for c,value in zip(t.rows[0].cells,headers):
        c.text=value
        shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'DDE7EF');c._tc.get_or_add_tcPr().append(shade)
        for r in c.paragraphs[0].runs:r.bold=True
    repeat=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for values in rows:
        row=t.add_row()
        for c,value in zip(row.cells,values):c.text=str(value)
        no_split=OxmlElement('w:cantSplit');row._tr.get_or_add_trPr().append(no_split)
    for row in t.rows:
        for j,c in enumerate(row.cells):
            if widths:c.width=Inches(widths[j])
            for p in c.paragraphs:
                p.paragraph_format.space_after=Pt(3)
                p.paragraph_format.line_spacing=1.0
                for r in p.runs:r.font.size=Pt(fontsize)
    doc.add_paragraph().paragraph_format.space_after=Pt(0)
    return t


def main():
    d=json.loads((OUT/'results.json').read_text());p=d['parameters'];v=d['volumes'];mem=d['memory'];be=d['break_even']
    models=read('models.json');sources=read('sources.json');cfg=read('model_config_values.json');timing=d['timing']
    doc=Document();s=doc.sections[0]
    s.page_width=Inches(8.27);s.page_height=Inches(11.69)
    s.top_margin=s.bottom_margin=Inches(.6);s.left_margin=s.right_margin=Inches(.65)
    for style in ['Normal','Title','Subtitle','Heading 1','Heading 2']:
        doc.styles[style].font.name='Calibri';doc.styles[style].font.color.rgb=RGBColor(0,0,0)
    doc.styles['Normal'].font.size=Pt(10.5);doc.styles['Normal'].paragraph_format.space_after=Pt(5)
    doc.styles['Normal'].paragraph_format.line_spacing=1.02
    doc.styles['Title'].font.size=Pt(22)
    doc.styles['Heading 1'].font.size=Pt(13);doc.styles['Heading 1'].paragraph_format.space_before=Pt(9)
    def para(text):doc.add_paragraph(text)
    def heading(text):doc.add_heading(text,1)
    doc.add_paragraph('SaafHawa model deployment study','Title')
    para('AI4015 Assignment Beta Q1 • Syeda Rija Ali • Roll number 23K-0057 • Updated 15 November 2026')
    para('I would start with a paid API for a small pilot. The token costs support that choice, but the final decision needs real latency measurements and an accuracy check in English and Roman Urdu. This draft separates completed calculations from missing evidence.')
    grid(doc,['Parameter','Working','Result'],[
        ['R and D','R = int("0057"[-2:]); D = (0+0+5+7) mod 10','R = 57; D = 2'],['Q','1500 + 25(57)','2,925 queries/day'],
        ['N','5 + (57 mod 4)','6 calls/query'],['p','0.04 + 0.01(2)','0.06'],
        ['H','4 + (57 mod 4)','5 heatwave days/month'],['B','1200 + 10(57)','$1,770/month'],
        ['T','10 − (57 mod 3)','10 seconds']],[1.0,3.0,2.95],9.5)
    para('D was computed from ROLL_DIGITS = 0057; the 23K enrolment-year batch prefix was excluded by the student’s stated interpretation.')
    heading('1 Token volume and retries')
    para('For call k, input Iₖ = 2000 + 800(k − 1). Calls 1–5 output 350 tokens and are attempted 1 + p = 1.06 times on average. Call 6 outputs 600 tokens and is attempted once. Invalid attempts still cost tokens; only the successful attempt triggers a tool.')
    grid(doc,['Call','Input','Output','Attempts','Expected input','Expected output'],[
        [r['k'],r['input'],r['output'],r['attempts'],num(r['expected_input'],0),num(r['expected_output'],0)] for r in v['rows']],fontsize=9)
    para('Input/query = (2000 + 2800 + 3600 + 4400 + 5200) × 1.06 + 6000 = 25,080.\nOutput/query = 5 × 350 × 1.06 + 600 = 2,455. Calls/query = 5 × 1.06 + 1 = 6.3.\nCacheable prefix/query = 1500 × 6.3 = 9,450 tokens; these are not guaranteed cache hits.')
    para('Monthly queries = 2925[(30 − 5) + 5(5)] = 146,250.\nInput = 25,080 × 146,250 = 3,667,950,000 = 3,667.95 M tokens.\nOutput = 2455 × 146,250 = 359,043,750 = 359.04375 M tokens.\nPrefix material = 9450 × 146,250 = 1,382,062,500 = 1,382.0625 M tokens.')
    doc.add_page_break()
    heading('2 Model comparison')
    para('The table contains six closed-source models from four developers and six open-weight API models from five developers. Qwen2.5 7B is an extra self-hosting case. Prices are USD per million text tokens. Source IDs resolve to URLs at the end; each source ID has its ISO access date in the Sources list. Missing figures remain “not verified”. The full field-by-field URLs are also in model_comparison.csv and the single-sheet workbook.')
    para('Prices are the lowest verified standard rates among the providers checked, not a verified global minimum. Discounted Batch/Flex service is excluded. A model’s original benchmark score may differ at a quantized endpoint or lower reasoning setting. No paid model inference tests were run.')
    rows=[]
    for m in models:
        def f(key):return f"{m['fields'].get(key,'not verified')} [{m['sources'].get(key,m['spec_source'])}; {sources[m['sources'].get(key,m['spec_source'])]['access_date']}]"
        def x(key):return f"{m[key] if m[key] is not None else 'not verified'} [{m['sources'].get(key,m['spec_source'])}; {sources[m['sources'].get(key,m['spec_source'])]['access_date']}]"
        spec='Parameters: '+f('parameters')+'\nContext / max output: '+f('context')+' / '+f('max_output')+'\nTools / JSON: '+f('native_tools')+' / '+f('structured_json')+'\nReasoning: '+f('reasoning')+'\nLicence: '+f('licence')
        terms='Inference: '+m['inference_provider']+'\nInput / output / cache USD/M: '+x('price_input')+' / '+x('price_output')+' / '+x('price_cache')+'\nNew paid RPM / TPM: '+x('rpm')+' / '+x('tpm')+'\nTTFT and speed: '+f('performance_reported')+'\nTool benchmark: '+f('benchmark_tool')+'\nOther benchmark: '+f('benchmark_other')
        rows.append([m['name']+'\n'+m['kind']+'\n'+m['developer'],spec,terms])
    grid(doc,['Model','Model details','API and performance evidence'],rows,[1.05,2.9,3.0],8.5)
    para('Two important values remain unverified: Haiku 5.5 first-token latency with thinking disabled, and the exact limits assigned to a newly paid Anthropic Evaluation account. Without them I cannot claim that the service meets 10 seconds or handles peak traffic. The table lists the other gaps. High-effort benchmark results do not prove low-effort accuracy.')
    heading('3 API costs and cache assumptions')
    para('Without caching, C₀ = MᵢPᵢ + (Mₒ + Mᵣ)Pₒ. Here Mᵢ = 3667.95 and Mₒ = 359.04375. If a model still reasons, add 6.3r output tokens/query, where r is its cited reasoning average per attempt. An unknown r makes the displayed cost a lower bound.')
    para('Cache scenario: one cold prefix write per query; later attempts hit within the cache lifetime. For an eligible prefix L, W = L × 146250 / 10⁶ and K = L × 5.3 × 146250 / 10⁶. Then Ccache = (Mᵢ − W − K)Pᵢ + WPwrite + KPcache + (Mₒ + Mᵣ)Pₒ. Write prices replace ordinary input billing. Below-minimum prefixes receive no caching; unverified eligibility receives no credited savings.')
    costrows=[]
    for c in d['costs']:
        status=c['status'];status='Reasoning cost missing' if status.startswith('LOWER') else ('Price missing' if c['nocache'] is None else 'Known output tokens')
        def budget(value):return 'PENDING' if value is None else ('not established' if value=='not established' else ('within' if value else 'over'))
        costrows.append([c['model'],num(c['nocache']),num(c['cache']),budget(c.get('within_budget_nocache'))+' / '+budget(c.get('within_budget_cache')),status])
    grid(doc,['Model','No cache $','Cache case $','Budget no/cache','Basis'],costrows,[2.0,.9,.9,1.5,1.65],9)
    para('Example: Haiku C₀ = 3667.95(0.10) + 359.04375(0.50) = $546.316875. Its 512-token minimum permits 1500 tokens; five-minute writes cost 1.25× input ($0.125/M), reads $0.01/M. W = 219.375 M and K = 1162.6875 M. Ccache = 2285.8875(0.10) + 219.375(0.125) + 1162.6875(0.01) + 359.04375(0.50) = $447.159375. [claude_prices; claude_cache]')
    para('Sonnet uses the same 512-token minimum and five-minute 1.25× write rule, but at $2 input, $2.50 write, $0.10 read and $10 output; its cached visible-token cost is $8826.91875 before residual reasoning. One-hour Claude writes cost 2× input. OpenAI 5.4 has no extra write premium and typically 5–10 minutes inactive retention, but the accessed minimum is request-dependent. Gemini lists $1/M cached-token-hours of storage; its eligibility remains unverified. Other provider write terms, minima and lifetimes are not verified, so no savings are credited. Full per-model cache inputs remain visible in the workbook. [claude_prices; claude_cache; oa_cache; gemini_price]')
    para('Cache-write sensitivity: the main cache case assumes one cold write per query. The alternate case shares one system/schema prefix across queries with one cold write per fixed TTL window, continuous traffic and no eviction. For 300-second TTL, ceil(30×86400/300)=8640 writes/month, rather than 146250. Reads refresh TTL at some providers, so this fixed-window case is a stated scenario, not a measured hit rate. Wttl = min(total attempts, number of windows)×L/10^6; replace W in the same cost equation. No savings are credited where cache eligibility is not verified.')
    grid(doc,['Model','Write per query $','Write per TTL window $'],[[c['model'],num(c['cache']),num(c.get('cache_ttl_window')) if c.get('eligible_prefix') else 'No credited savings'] for c in d['costs']],[3.15,1.9,1.9],9)
    heading('4 Peak load')
    para('Assume uniform arrivals in the two-hour heatwave window. Heatwave traffic = 5 × 2925 = 14,625/day. Window traffic = 35% × 14,625 = 5118.75. Therefore QPM = 5118.75 / 120 = 42.65625; LLM RPM = 42.65625 × 6.3 = 268.734375. Input TPM = 1,069,818.75; output TPM = 104,721.09375; combined TPM = 1,174,539.84375, before residual reasoning.')
    para('Published OpenAI Build quotas (5000 RPM, 2M TPM) pass this visible-token arithmetic; account assignment still needs checking. Groq GPT OSS 20B passes its 1000 RPM limit but exceeds 250,000 TPM even on input alone. Other exact new-account quotas remain unverified. Anthropic’s published Start quotas are not guaranteed Evaluation-account limits, so launch capacity is not established. [oa_nano; oa_mini; groq; claude_limits]')
    para('New OpenAI paid Build accounts qualify after $5 in credit purchases but have a $500 monthly usage cap. Passing RPM/TPM does not establish monthly service feasibility: the original nano loop costs more than this cap. Account access and assigned quotas still require console review. [oa_limits]')
    heading('5 Self-hosting memory')
    para('I use Qwen2.5 7B Instruct because its standard full-attention GQA configuration is publicly downloadable. The saved config gives 28 layers, 4 KV heads, hidden size 3584, 28 attention heads, intermediate size 18944, vocabulary 152064 and untied embeddings. Head dimension = 3584/28 = 128. The default 32768 positions cover the required 6600 tokens. [config; qwen7]')
    para('With h=3584, i=18944, V=152064, L=28, K=4 and d=128, the architecture gives P = 2Vh + L(2h² + 2hKd + 3hi + 3h + 2Kd) + h = 7,615,616,512 parameters. This includes untied embeddings, Q/K/V biases and RMSNorm weights. Ideal weights: FP16 = 2P = 15.231233024 GB; INT8 = P = 7.615616512 GB; INT4 = P/2 = 3.807808256 GB. Quantization scales and packing can add memory.')
    para('Longest sequence = 6000 + 600 = 6600. FP16 KV = 2 × 28 × 4 × 128 × 6600 × 2 = 378,470,400 bytes/sequence (0.352478 GiB). For a 24 GB RTX 4090, using conservative decimal GB and reserving 10%: capacity = floor[(21.6×10⁹ − 3,807,808,256) / 378,470,400] = 47 sequences. This is a memory ceiling, not measured throughput. [gpu]')
    para('Little’s law gives mean sessions = λW, where λ = 42.65625/60 = 0.7109375 queries/s and W is actual Qwen2.5 7B service time on the RTX 4090 at the chosen precision and load. GPUs = ceil(0.7109375W/47). W is not verified, so operational GPUs and monthly cost remain PENDING. At explicitly assumed W=10 s, sessions=7.109375, memory sizing gives one GPU and $640.80/month. This is an illustration, not an operational result. Compute throughput and tail queueing can require more GPUs.')
    para('The Qwen team reports 141.98 tokens/s on an A100 80GB with vLLM 0.6.3, GPTQ-Int4, batch size 1, 6144 input and 2048 generated tokens. That is a different GPU and load; it cannot establish RTX 4090 service time or 47-session throughput. The missing RTX 4090 measurement is retained in the evidence register. [qwen_speed]')
    para('Saved data/config.json: num_hidden_layers=28; num_key_value_heads=4; hidden_size=3584; num_attention_heads=28; intermediate_size=18944; vocab_size=152064; tie_word_embeddings=false; max_position_embeddings=32768; use_sliding_window=false. Derived head_dim=128 is in data/model_config_values.json. [config]')
    para('PENDING STUDENT SCREENSHOT — insert your screenshot of data/config.json and derived head_dim here. Keep the relevant values and source URL/access date visible. The text above is not a substitute for the required screenshot.')
    heading('6 Break even and latency')
    para('Runpod quotes $0.89/GPU-hour for Secure Cloud RTX 4090; 24×30=720 hours gives $640.80/GPU-month. Community Cloud is listed at $0.34/hour but is a different offering. Storage, CPU, network, labour and redundancy are excluded. [gpu; accessed 2026-11-15]')
    para('For ordinary-day volume q, peak λ(q)=1.75q/7200. Cself(q)=640.8×ceil[1.75qW/(7200×47)] for q>0; Cself(0)=0. Capi(q)=q×Capi(Q)/Q. In GPU interval ((n−1)qcap,nqcap], qcap=7200×47/(1.75W), the API crossing must satisfy q>n×640.8/API_slope within that same interval. Use strict integer crossings; do not smooth over GPU jumps.')
    para('Candidate selection is implemented as follows: evaluate each original loop, use its changed workflow if it exceeds T, then choose the cheaper candidate meeting T; if neither meets T, use the lower-latency candidate. If either candidate is unevaluated, selection remains PENDING. The changed workflow uses its recalculated token cost, rather than the old six-call cost. Operational Q* additionally requires the RTX 4090 service-time basis.')
    para(f"The plot shows the W=10 s illustration only. Conditional Haiku first crossing = {be['sensitivity_qstar']} ordinary-day queries/day; GPU capacity = {num(be['sensitivity_queries_per_gpu'],3)} queries/day. Operational Q* is PENDING. A few thousand daily queries may be possible in Karachi, but no adoption forecast was supplied and this conditional crossing does not establish deployment feasibility.")
    doc.add_picture(str(OUT/'monthly_cost_vs_daily_volume.png'),width=Inches(6.7))
    para('The two provisional candidates are GPT-5.4 nano with reasoning.effort=none and Haiku 5.5 with thinking disabled. Let fₘ(Iₖ) be TTFT at growing input length Iₖ, sₘ output tokens/s, rₘ residual reasoning tokens/attempt and d the completed pooled median. Lₘ=Σₖaₖ[fₘ(Iₖ)+(Oₖ+rₘ)/sₘ]+5d. Expected retry delay=pΣₖ₌₁⁵[fₘ(Iₖ)+(350+rₘ)/sₘ]. Tools execute once after each successful call, not after invalid attempts.')
    grid(doc,['Candidate','Original pooled s','API-only s','Retry contribution s','Changed pooled s'],[[x['model'],num(x['total_seconds']),num(x['api_only_total']),num(x['retry_seconds']),num(x['changed_total_seconds'])] for x in d['latency']],[1.7,1.3,1.2,1.4,1.35],9)
    nano=d['latency'][0]
    para(f"Nano uses AA non-reasoning TTFT=1.34 s and speed=115 tokens/s. Applying the aggregate TTFT to all six input lengths is an explicit approximation; length-specific prefill and load effects are not verified. Base no-retry LLM time=6×1.34+2350/115=28.474783 s; retry contribution={num(nano['retry_seconds'],6)} s. Total=6.3×1.34+2455/115+5d={num(nano['total_seconds'],6)} s; API-only={num(nano['api_only_total'],6)} s. Decode alone is {num(nano['decode_seconds'],6)} s, exceeding T. [perf_0]")
    para('ONE proposed architectural change: replace LLM tool planning with a fixed deterministic workflow, then make one final 600-token LLM answer call at 6000 input tokens. Keep the same five tool executions; no independent parallelism or streaming is added. Invalid LLM tool calls disappear, so the modeled retry contribution becomes zero. This changes the hypothetical architecture, not the experiment pipeline or main workload arithmetic. It is suitable only after the area/time/risk fields are resolved; unresolved requests need clarification and are outside the estimate.')
    para(f"Lchanged=f(6000)+600/s+5d. Nano: 1.34+600/115+5d={num(nano['changed_total_seconds'],6)} s, or {num(nano['changed_api_only_seconds'],6)} s using API-only delay. Monthly visible-token cost for this changed nano workflow without credited caching={num(nano['changed_monthly_cost'])} USD. Under the aggregate-TTFT approximation it can plausibly meet T, but setting/input/load-matched measurements must validate that claim.")
    para('Haiku disabled-thinking TTFT and tokens/s remain not verified. Its AA Max setting reports TTFT=182.97 s and 254 tokens/s; those values are excluded from the disabled-thinking estimate. At that reported speed, 2455/254=9.665354 s is a decode-only diagnostic before TTFT/tools, not a disabled-mode result. After the same change, Lchanged=fdisabled(6000)+600/sdisabled+5d remains PENDING. A cheap price alone cannot establish that it meets T. [perf_2]')
    heading('7 Measurements and decision')
    cpath=ROOT/'data/coverage_latest.json'
    if cpath.exists():
        c=json.loads(cpath.read_text())
        para(f"The discovery run at {c['checked_at_utc']} checked {c['station_count']} locations within 25 km of 24.8607, 67.0011. Selected recent PM2.5 station: {c['selected_station_id']}. A live station with both PM2.5 and PM10 was not found. Returned PM10 readings were dated in 2024. Raw responses and data/coverage_latest.json preserve the evidence; stale PM10 must not be presented as live data.")
    grid(doc,['Tool','Timing valid','Karachi dates','Median s'],[[tool,info['successful'],', '.join(info['by_day']),num(info['median_seconds'],9)] for tool,info in timing['per_tool'].items()],[1.4,1.0,3.0,1.55],9)
    para(f"Timing completion: {timing['complete']}. Requirement: at least 20 valid samples per tool total, spread over at least two Karachi calendar dates per tool. Fifteen per day is advice only. Existing data have 15/tool on Nov 14 and 30/tool on Nov 15; no third day is required. Machine mismatch={timing['machine_mismatch']}. The logger excludes its 1.1-second pacing delay and uses perf_counter for local tools.")
    para(f"Headline pooled median={num(timing['pooled_median_seconds'] if timing['complete'] else None,9)} s; API-only sensitivity={num(timing['api_only_median_seconds'] if timing['complete'] else None,9)} s. These are medians of all valid observations, not four tool medians. The pooled median is fragile: half the samples are near-zero local calls, so it lies between local work and the fastest API observation. Any imbalance in sample counts can move it sharply.")
    para(f"Timing validity is separate from the data requirement of recent PM2.5 AND PM10. Coverage audit: {timing['air_quality_coverage']}. Fourteen original response paths could not be matched to saved responses with the same timestamp, so those coverage flags are not verified. Original CSV rows are retained; no data, timings or timestamps were fabricated. New measurements record both flags in sample_validity.jsonl beside the responses. See timing_audit.csv for historical evidence gaps.")
    para('My provisional choice is an API pilot, with deterministic calculations, timestamped source data, explicit PM10 gaps and officer review of municipal summaries. A final deployment choice still needs low-reasoning accuracy tests, verified account limits and self-host throughput. Daily-summary token volume was not supplied, so its extra cost is excluded. The model table and pending_items.txt retain the unresolved evidence. AI assistance is disclosed in ai_declaration.txt.')
    heading('8 Assignment completion checklist')
    para('DONE means the specified work or artifact exists. PENDING (needs me) identifies student actions. NOT VERIFIED identifies unresolved evidence, including outputs that must remain PENDING rather than guessed. The following checklist is generated from the same results as outputs/submission_checklist.md.')
    for item in d['checklist']:
        para(item['status']+' — '+item['item']+': '+item['evidence'])
    heading('Sources')
    para('Access dates are recorded per source below; refreshed evidence was accessed on 2026-11-15. A source beside “not verified” identifies a page checked, not proof of a missing number. The CSV retains the full per-field mapping.')
    cited_text=' '.join(node.text or '' for node in doc.element.iter(qn('w:t')))
    cited={part.strip() for group in re.findall(r'\[([^\]]+)\]',cited_text) for part in group.split(';')}
    for key,sr in sources.items():
        if key not in cited:continue
        p1=doc.add_paragraph(f'[{key}] Accessed {sr["access_date"]}: {sr["url"]}')
        p1.paragraph_format.space_after=Pt(0)
        for run in p1.runs:run.font.size=Pt(8.5)
    for parent in [doc.element,doc.styles.element]:
        for border in list(parent.iter(qn('w:pBdr'))):border.getparent().remove(border)
    footer=doc.sections[0].footer.paragraphs[0];footer.alignment=2
    footer.add_run('SaafHawa • draft • ')
    page=OxmlElement('w:fldSimple');page.set(qn('w:instr'),'PAGE');footer._p.append(page)
    doc.save(OUT/'report.docx')
    print('Saved concise portrait report:',OUT/'report.docx')


if __name__=='__main__':main()
