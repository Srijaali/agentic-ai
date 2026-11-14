
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATE = '2026-11-14'
SOURCES = {}


def source(key, url, description):
    SOURCES[key] = dict(url=url, access_date=DATE, description=description)
    return key


source('oa_nano','https://developers.openai.com/api/docs/models/gpt-5.4-nano','Model specification, API prices, reasoning options and Build limits')
source('oa_mini','https://developers.openai.com/api/docs/models/gpt-5.4-mini','Model specification, API prices and reasoning options')
source('oa_bench','https://openai.com/index/introducing-gpt-5-4-mini-and-nano/','Vendor benchmarks at xhigh, not the assignment non-reasoning setting')
source('oa_cache','https://developers.openai.com/api/docs/guides/prompt-caching','Cache lookup boundaries, retention and model-dependent cache writes')
source('haiku','https://platform.claude.com/docs/en/models/haiku-5-5/overview','Active model, context, output, cache minimum')
source('sonnet','https://platform.claude.com/docs/en/models/sonnet-5-5/overview','Active model and minimum reasoning setting')
source('claude_prices','https://platform.claude.com/docs/en/about-claude/pricing','Standard prices and cache writes')
source('claude_cache','https://platform.claude.com/docs/en/build-with-claude/prompt-caching','Minimum prefix and cache TTL')
source('claude_limits','https://platform.claude.com/docs/en/api/rate-limits','Evaluation tier may be below published Start tier')
source('claude_disable','https://platform.claude.com/cookbook/latency-optimization-latency-optimization','Haiku supports disabled thinking, Sonnet supports between_tools')
source('gemini','https://aistudio.google.com/docs/models/gemini-3.5-flash-lite','Model capabilities and token limits')
source('gemini_price','https://aistudio.google.com/docs/pricing#gemini-3.5-flash-lite','Standard text prices and cache storage')
source('gemini_cache','https://aistudio.google.com/docs/caching?generate-content=true','Context caching requirements')
source('grok','https://docs.x.ai/developers/models/grok-4.7','Current Grok specification and general advertised limits, not verified new-account limits')
source('novita','https://novita.ai/pricing','Public standard inference prices compared with Groq, Together and DeepInfra')
source('deepinfra','https://deepinfra.com/meta-llama/Llama-3.3-70B-Instruct-Turbo','Standard FP8 and discounted Flex prices; comparison uses standard service')
source('together','https://docs.together.ai/docs/serverless/models','Current public provider catalog, context and prices')
source('groq','https://console.groq.com/docs/models','Developer plan limits and advertised throughput, not independently measured TTFT')
source('llama8','https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct','Model card, licence and benchmark setting')
source('llama70','https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct','Model card and BFCL v2 benchmark')
source('qwen27','https://huggingface.co/Qwen/Qwen3.8-27B','Apache 2.0, dense model, disabling thinking and reported benchmarks')
source('deepseek','https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash','Backbone and conditional memory counts; effort range and instruct benchmark setting')
source('minimax','https://huggingface.co/MiniMaxAI/MiniMax-M3.1-Flash','MoE parameter counts and vendor benchmark table')
source('oss','https://huggingface.co/openai/gpt-oss-20b','Apache 2.0 and low/medium/high reasoning')
source('qwen7','https://huggingface.co/Qwen/Qwen2.5-7B-Instruct','Ungated standard GQA model and Apache 2.0 licence')
source('config','https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/resolve/main/config.json','Downloaded original configuration')
source('gpu','https://www.runpod.io/gpu-models/rtx-4090','24 GB GPU; Secure $0.89/hr, Community $0.34/hr, availability varies')
source('aa_nano','https://artificialanalysis.ai/models/gpt-5-4-nano','xhigh benchmark, incompatible with none setting; excluded from latency calculation')
source('aa_haiku','https://artificialanalysis.ai/models/releases/claude-haiku-5-5','Release aggregate uses reasoning setting, excluded from disabled-thinking latency calculation')
source('openaq','https://docs.openaq.org/resources/latest','Latest endpoint semantics and sensorsId mapping')
source('weather','https://open-meteo.com/en/docs','Current weather fields and units')
source('nws','https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml','NWS algorithm; web fetch returned 403, formula also checked by local tests')
source('who','https://www.who.int/news-room/fact-sheets/detail/ambient-(outdoor)-air-quality-and-health','Official air quality health advice')
source('heat','https://www.who.int/news-room/fact-sheets/detail/climate-change-heat-and-health','Official heat and health advice')


def model(name, kind, developer, provider, spec_source):
    return dict(name=name, kind=kind, developer=developer, inference_provider=provider,
        fields={}, sources={}, access_date=DATE,
        price_input=None, price_output=None, price_cache=None, cache_min=None,
        cache_block=None, cache_write_multiplier=None, cache_ttl=None,
        rpm=None, tpm=None, otpm=None, ttft=None, tps=None,
        reasoning_average=None, reasoning_disabled=False, cache_verified=False,
        spec_source=spec_source, notes=[])


def put(m, field, value, src):
    m['fields'][field] = value
    m['sources'][field] = src


MODELS = []
for suffix, inp, out, cached in [('nano',.20,1.25,.02),('mini',.75,4.5,.075)]:
    s='oa_'+suffix
    m=model('GPT-5.4 '+suffix,'closed-source','OpenAI','OpenAI',s)
    for k,v in dict(parameters='not disclosed',context=400000,max_output=128000,
                    native_tools='yes',structured_json='yes',licence='Proprietary API; commercial self-hosting unavailable',
                    reasoning='reasoning.effort=none; also low, medium, high, xhigh').items(): put(m,k,v,s)
    m.update(price_input=inp,price_output=out,price_cache=cached,reasoning_disabled=True,
             reasoning_average=0, rpm=5000,tpm=2000000)
    for k in ['price_input','price_output','price_cache','rpm','tpm']:m['sources'][k]=s
    m['notes'].append('Published Build tier; confirm account assignment. Benchmark scores below are xhigh, not none.')
    put(m,'benchmark_tool',f'Toolathlon: {35.5 if suffix=="nano" else 42.9}%, xhigh','oa_bench')
    put(m,'benchmark_other',f'GPQA Diamond: {82.8 if suffix=="nano" else 88.0}%, xhigh','oa_bench')
    put(m,'performance_reported','AA xhigh: TTFT 99.00 s, 135 tokens/s; incompatible setting; not used' if suffix=='nano' else 'not verified at none setting','aa_nano' if suffix=='nano' else s)
    m.update(cache_write_multiplier=1,cache_ttl=300)
    m['sources']['cache_write_multiplier']='oa_cache';m['sources']['cache_ttl']='oa_cache'
    m['notes'].append('No extra write premium; in-memory retention typically 5–10 minutes inactive. Request-dependent minimum remains unverified, so no caching savings credited.')
    MODELS.append(m)

for family,inp,out,cache in [('Haiku',.1,.5,.01),('Sonnet',2,10,.1)]:
    s=family.lower();m=model(f'Claude {family} 5.5','closed-source','Anthropic','Anthropic',s)
    for k,v in dict(parameters='not disclosed',context='1M (provider notation)',max_output='128K (provider notation)',
                    native_tools='yes',structured_json='not verified',licence='Proprietary API; commercial self-hosting unavailable',
                    reasoning='thinking.type=disabled; effort=low' if family=='Haiku' else 'thinking.type=between_tools; effort=low; reasoning may remain').items():put(m,k,v,s)
    m.update(price_input=inp,price_output=out,price_cache=cache,cache_min=512,cache_block=1,
             cache_write_multiplier=1.25,cache_ttl=300,cache_verified=True,
             reasoning_disabled=family=='Haiku',reasoning_average=0 if family=='Haiku' else None)
    for k in ['price_input','price_output','price_cache','cache_write_multiplier']:m['sources'][k]='claude_prices'
    for k in ['cache_min','cache_block','cache_ttl']:m['sources'][k]='claude_cache'
    put(m,'new_account_limits','not verified: new organizations may enter Evaluation below published Start limits','claude_limits')
    put(m,'benchmark_tool','not verified: release chart requires numeric extraction','haiku' if family=='Haiku' else 'sonnet')
    put(m,'benchmark_other','not verified at lowest reasoning setting',s)
    put(m,'performance_reported','AA release aggregate: TTFT 176.21 s, 254 tokens/s; incompatible reasoning setting; not used' if family=='Haiku' else 'not verified at lowest setting','aa_haiku' if family=='Haiku' else s)
    m['notes'].append('Published Start has 4,000 RPM, 2M ITPM, 400K OTPM, but is NOT a guaranteed new-account tier.')
    MODELS.append(m)

m=model('Gemini 3.5 Flash-Lite','closed-source','Google','Google','gemini')
for k,v in dict(parameters='not disclosed',context=1048576,max_output=65536,native_tools='yes',structured_json='yes',
                reasoning='lowest setting not verified; thinking supported',licence='Proprietary API; commercial self-hosting unavailable').items():put(m,k,v,'gemini')
m.update(price_input=.3,price_output=2.5,price_cache=.03)
for k in ['price_input','price_output','price_cache']:m['sources'][k]='gemini_price'
m['notes'].append('Cache storage $1/M token-hour is published; no savings until minimum prefix and lowest thinking settings verified.')
MODELS.append(m)
m=model('Grok 4.7','closed-source','xAI / SpaceXSI','xAI / SpaceXSI','grok')
for k,v in dict(parameters='not disclosed',context=500000,max_output='not verified',native_tools='yes',structured_json='yes',
    reasoning='reasoning_effort=low; also medium, high, xhigh; reasoning remains',licence='Proprietary API; commercial self-hosting unavailable').items():put(m,k,v,'grok')
m.update(price_input=2,price_output=6)
for k in ['price_input','price_output']:m['sources'][k]='grok'
m['notes'].append('General advertised limits 150 requests/s and 50M TPM are not verified for a new paid account.')
MODELS.append(m)

m=model('Llama 3.1 8B Instruct','open-weight','Meta','Novita AI','llama8')
for k,v in dict(parameters='8B nominal dense',context='131072 model; 16K Novita endpoint',max_output='not verified at Novita',
    native_tools='yes',structured_json='not verified at Novita',reasoning='non-reasoning; no reasoning toggle',
    licence='Llama 3.1 Community License; commercial hosting allowed subject to licence and AUP',
    benchmark_tool='BFCL (original card, 0-shot): 76.1%',benchmark_other='MMLU (5-shot): 69.4%').items():put(m,k,v,'llama8')
m.update(price_input=.02,price_output=.05,reasoning_average=0,reasoning_disabled=True)
for k in ['price_input','price_output']:m['sources'][k]='novita'
put(m,'performance_reported','Groq advertises 560 tokens/s; provider mismatch with cheapest Novita endpoint; TTFT not verified','groq')
MODELS.append(m)
m=model('Llama 3.3 70B Instruct Turbo','open-weight','Meta','DeepInfra standard FP8','llama70')
for k,v in dict(parameters='70B nominal dense',context=131072,max_output='not verified at DeepInfra',native_tools='yes',structured_json='yes',
    reasoning='non-reasoning; no reasoning toggle',licence='Llama 3.3 Community License; commercial hosting subject to licence and AUP',
    benchmark_tool='BFCL v2 (0-shot): 77.3%',benchmark_other='HumanEval (0-shot): 88.4%').items():put(m,k,v,'llama70')
m.update(price_input=.1,price_output=.32,reasoning_average=0,reasoning_disabled=True)
for k in ['price_input','price_output']:m['sources'][k]='deepinfra'
m['notes'].append('Flex $0.08/$0.256 is lower but a different service tier; standard used for synchronous comparison. FP8 scores may differ from original card.')
put(m,'performance_reported','Groq advertises 280 tokens/s; provider mismatch; TTFT not verified','groq')
MODELS.append(m)
m=model('Qwen3.8 27B','open-weight','Alibaba Qwen','Novita AI','qwen27')
for k,v in dict(parameters='27B nominal dense',context='262144 native; Novita advertises 977K extended',max_output='not verified endpoint cap',
    native_tools='yes',structured_json='not verified at Novita',reasoning='enable_thinking=False; otherwise low/medium/xhigh',
    licence='Apache 2.0; commercial self-hosting allowed',benchmark_tool='not verified',
    benchmark_other='ParseBench 2 overall: 61.57, FP8 pipeline, thinking disabled').items():put(m,k,v,'qwen27')
m.update(price_input=.42,price_output=3,price_cache=.085,reasoning_disabled=True,reasoning_average=0)
for k in ['price_input','price_output','price_cache']:m['sources'][k]='novita'
put(m,'performance_reported','Groq advertises 450 tokens/s; different provider and context; TTFT not verified','groq')
MODELS.append(m)
m=model('DeepSeek V4.1 Flash','open-weight','DeepSeek','Novita AI / Together AI (tie)','deepseek')
for k,v in dict(parameters='552B backbone + 196B Engram; active 8B prefill / 16B decode; total accounting caveat',
    context=1000000,max_output='not verified endpoint cap',native_tools='yes',structured_json='yes at Together',
    reasoning='reasoning_effort=1 (range 1–100); residual average not verified',licence='not verified',
    benchmark_tool='BankerToolBench: 73.7, comparison reported by MiniMax; effort not verified',
    benchmark_other='Terminal Bench 4.0: 31.2, MiniMax comparison; effort not verified').items():put(m,k,v,'deepseek' if not k.startswith('benchmark') else 'minimax')
m.update(price_input=.3,price_output=1.2,price_cache=.006)
for k in ['price_input','price_output','price_cache']:m['sources'][k]='novita'
MODELS.append(m)
m=model('MiniMax M3.1 Flash','open-weight','MiniMax','Together AI','minimax')
for k,v in dict(parameters='approximately 428B total / 23B active',context='1000000 model; 1048576 Together listing',max_output='not verified',
    native_tools='yes',structured_json='yes at Together',reasoning='lowest setting and residual token average not verified',licence='not verified',
    benchmark_tool='BankerToolBench: 76.2; vendor evaluation setting not verified',
    benchmark_other='Terminal Bench 4.0: 38.1; vendor evaluation setting not verified').items():put(m,k,v,'minimax')
m.update(price_input=.15,price_output=.6,price_cache=.015)
for k in ['price_input','price_output','price_cache']:m['sources'][k]='together'
MODELS.append(m)
m=model('GPT OSS 20B','open-weight','OpenAI','Groq','oss')
for k,v in dict(parameters='not verified total and active',context=131072,max_output=65536,native_tools='yes',structured_json='yes',
    reasoning='reasoning_effort=low; also medium/high; reasoning remains',licence='Apache 2.0; commercial self-hosting allowed').items():put(m,k,v,'oss' if k in ('parameters','reasoning','licence') else 'groq')
m.update(price_input=.075,price_output=.3,rpm=1000,tpm=250000)
for k in ['price_input','price_output','rpm','tpm']:m['sources'][k]='groq'
put(m,'performance_reported','Groq advertises 1000 tokens/s; lowest-effort TTFT not verified','groq')
MODELS.append(m)
m=model('Qwen2.5 7B Instruct','open-weight','Alibaba Qwen','not verified current public endpoint','qwen7')
for k,v in dict(parameters='7,615,616,512 dense; derived from downloaded configuration',context='32768 default; 131072 with YaRN',max_output=8192,
    native_tools='supported through tool template; endpoint support not verified',structured_json='JSON generation; constrained schema is server-dependent',
    reasoning='non-reasoning; no reasoning toggle',licence='Apache 2.0; commercial self-hosting allowed').items():put(m,k,v,'qwen7')
m.update(reasoning_disabled=True,reasoning_average=0)
m['sources']['parameters']='config'
m['notes'].append('Additional self-hosting case. API costs PENDING because current price was not verified.')
MODELS.append(m)

for m in MODELS:
    for k in ['benchmark_tool','benchmark_other','performance_reported','new_account_limits']:
        if k not in m['fields']:put(m,k,'not verified',m['spec_source'])
    m['notes'].append('Lowest verified standard price among providers checked; a global lowest price is not verified. Batch and Flex excluded.')


def main():
    d=ROOT/'data';d.mkdir(exist_ok=True)
    (d/'models.json').write_text(json.dumps(MODELS,indent=2))
    (d/'sources.json').write_text(json.dumps(SOURCES,indent=2))
    (d/'assumptions.json').write_text(json.dumps(dict(R=57,D=2,days=30,input_base=2000,input_step=800,
        tool_output=350,final_output=600,prefix=1500,heat_multiplier=5,peak_fraction=.35,peak_minutes=120,
        gpu_bytes=24_000_000_000,gpu_hourly=.89,reserve_fraction=.1,
        sizing_service_seconds=None,sensitivity_service_seconds=10,
        cache_policy='one cold prefix write per query, subsequent calls/retries hit within TTL; explicit sensitivity, not measured'),indent=2))
    (d/'advisories.json').write_text(json.dumps([
        dict(id='WHO_HEAT',keywords=['heat','children','outdoor','elderly'],
             text='Keep cool, drink water and avoid strenuous activity during the hottest hours. Check on vulnerable people.',
             source_url=SOURCES['heat']['url'],access_date=DATE),
        dict(id='WHO_AIR',keywords=['pollution','air','children','pm25','asthma'],
             text='Air pollution increases health risks. Reduce exposure and consult official local advisories, especially for vulnerable groups.',
             source_url=SOURCES['who']['url'],access_date=DATE)],indent=2))
    print('Evidence files created; unresolved figures explicitly marked not verified.')


if __name__=='__main__':main()
