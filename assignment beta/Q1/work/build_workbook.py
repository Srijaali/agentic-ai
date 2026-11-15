import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
"""Build a local openpyxl workbook. Excel/LibreOffice recalculates live formulas."""
import csv
import json
import math
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.workbook.properties import CalcProperties
from openpyxl.utils import get_column_letter

from calculations import read, parameters, ROOT, OUT
from tool_latency_logger import summarize


def _make_sections():
    OUT.mkdir(exist_ok=True)
    a=read('assumptions.json');p=parameters(a);models=read('models.json');sources=read('sources.json');timing=summarize()
    wb=Workbook();wb.remove(wb.active)
    inp=wb.create_sheet('Inputs')
    inp.append(['Input or control','Value','Units or status','Source URL','Access date'])
    mapping={}
    values=[('ROLL_DIGITS',a['ROLL_DIGITS'],'0057 only; 23K enrolment-year prefix excluded'),('R',p['R'],'derived last two roll digits'),('D',p['D'],'derived digit sum mod 10'),('days',a['days'],'days/month'),
      ('input_base',a['input_base'],'tokens'),('input_step',a['input_step'],'tokens/call'),
      ('tool_output',a['tool_output'],'tokens'),('final_output',a['final_output'],'tokens'),
      ('prefix',a['prefix'],'tokens'),('heat_multiplier',a['heat_multiplier'],'traffic multiplier'),
      ('peak_fraction',a['peak_fraction'],'fraction'),('peak_minutes',a['peak_minutes'],'minutes'),
      ('gpu_bytes',a['gpu_bytes'],'bytes; conservative decimal 24 GB'),('gpu_hourly',a['gpu_hourly'],'USD/hour Secure Cloud'),
      ('reserve_fraction',a['reserve_fraction'],'fraction'),('service_seconds',a['sizing_service_seconds'],'PENDING actual self-host end-to-end service time'),
      ('sensitivity_seconds',a['sensitivity_service_seconds'],'T-based illustrative scenario; NOT measured'),
      ('timing_complete',int(timing['complete']),'1 only if measurement requirements met'),
      ('pooled_delay',timing['pooled_median_seconds'] if timing['complete'] else None,'PENDING until log complete'),
      ('api_only_delay',timing['api_only_median_seconds'] if timing['complete'] else None,'PENDING until log complete')]
    for key,value,note in values:
        mapping[key]=inp.max_row+1
        s='gpu' if key.startswith('gpu_') else None
        inp.append([key,value,note,sources[s]['url'] if s else 'Assignment specification or measured local log', sources[s]['access_date'] if s else '2026-11-15'])
    def I(key):return f"Inputs!$B${mapping[key]}"
    inp.cell(mapping['ROLL_DIGITS'],2).number_format='@'
    inp.cell(mapping['R'],2,f'=VALUE(RIGHT({I("ROLL_DIGITS")},2))')
    digit_sum='+'.join(f'VALUE(MID({I("ROLL_DIGITS")},{i},1))' for i in range(1,len(a['ROLL_DIGITS'])+1))
    inp.cell(mapping['D'],2,f'=MOD({digit_sum},10)')
    ms=wb.create_sheet('Model inputs')
    headers=['Model','Input USD/M','Output USD/M','Cached USD/M','Cache min','Block','Write multiplier','TTL s','Cache verified',
       'Reasoning tokens/attempt','RPM','TPM','OTPM','Decode tokens/s','TTFT call 1','TTFT call 2','TTFT call 3','TTFT call 4','TTFT call 5','TTFT call 6','Provider','Price URL','Access date','Notes']
    ms.append(headers)
    modelrows={}
    for m in models:
        row=ms.max_row+1;modelrows[m['name']]=row
        src=sources[m['sources'].get('price_input',m['spec_source'])]
        ms.append([m['name'],m['price_input'],m['price_output'],m['price_cache'],m['cache_min'],m['cache_block'],
            m['cache_write_multiplier'],m['cache_ttl'],int(m['cache_verified']),m['reasoning_average'],m['rpm'],m['tpm'],m['otpm'],m['tps'],
            *m.get('ttft_by_call',[None]*6),m['inference_provider'],src['url'],src['access_date'],' '.join(m['notes'])])
    loop=wb.create_sheet('Token and load')
    loop.append(['Metric','Formula result','Explanation'])
    entries=[('R',f'={I("R")}','Derived from ROLL_DIGITS'),('D',f'={I("D")}','Derived from ROLL_DIGITS'),
      ('Q',f'=1500+25*{I("R")}','queries/day'),('N',f'=5+MOD({I("R")},4)','LLM calls/query'),
      ('p',f'=0.04+0.01*{I("D")}','invalid tool-call probability'),('H',f'=4+MOD({I("R")},4)','heatwave days'),
      ('B',f'=1200+10*{I("R")}','USD/month'),('T',f'=10-MOD({I("R")},3)','seconds')]
    L={}
    for key,form,desc in entries:L[key]=loop.max_row+1;loop.append([key,form,desc])
    loop.append([]);loop.append(['Call k','Input tokens','Output tokens','Expected attempts','Expected input','Expected output','Cacheable prefix tokens'])
    first=loop.max_row+1
    for k in range(1,7):
        r=loop.max_row+1
        loop.append([k,f'={I("input_base")}+{I("input_step")}*(A{r}-1)',
            f'=IF(A{r}=$B${L["N"]},{I("final_output")},{I("tool_output")})',
            f'=IF(A{r}=$B${L["N"]},1,1+$B${L["p"]})',f'=B{r}*D{r}',f'=C{r}*D{r}',f'={I("prefix")}*D{r}'])
    end=loop.max_row
    def add(key,form,desc):L[key]=loop.max_row+1;loop.append([key,form,desc])
    add('input_query',f'=SUM(E{first}:E{end})','includes retries')
    add('output_query',f'=SUM(F{first}:F{end})','visible output; reasoning added separately by model')
    add('calls_query',f'=SUM(D{first}:D{end})','includes retries')
    add('prefix_query',f'=SUM(G{first}:G{end})','theoretical cacheable prefix; not guaranteed hits')
    def B(key):return f"'Token and load'!$B${L[key]}"
    add('month_factor',f'={I("days")}-{B("H")}+{I("heat_multiplier")}*{B("H")}','ordinary-day equivalents')
    add('month_queries',f'={B("Q")}*{B("month_factor")}','queries/month')
    for key,base in [('input_month_M','input_query'),('output_month_M','output_query'),('prefix_month_M','prefix_query')]:
        add(key,f'={B(base)}*{B("month_queries")}/1000000','M tokens/month')
    add('peak_qpm',f'={B("Q")}*{I("heat_multiplier")}*{I("peak_fraction")}/{I("peak_minutes")}','uniform arrivals in the 120-minute window')
    add('peak_rpm',f'={B("peak_qpm")}*{B("calls_query")}','LLM requests/min, expected retries')
    add('peak_itpm',f'={B("peak_qpm")}*{B("input_query")}','input tokens/min')
    add('peak_otpm',f'={B("peak_qpm")}*{B("output_query")}','visible output tokens/min')
    add('peak_tpm',f'={B("peak_itpm")}+{B("peak_otpm")}','combined visible-token throughput')
    api=wb.create_sheet('API costs')
    api.append(['Model','Reasoning status','No cache USD','Eligible prefix','Write M tokens','Hit M tokens','Cache USD','No cache budget','Cache budget','RPM comparison','TPM comparison','Caching assumption','TTL writes M','TTL-window cost USD'])
    for m in models:
        r=api.max_row+1;s=modelrows[m['name']]
        def M(col):return f"'Model inputs'!{col}{s}"
        api.append([f'={M("A")}',f'=IF(ISNUMBER({M("J")}),"Includes known reasoning","LOWER BOUND reasoning PENDING")',
          f'=IF(COUNT({M("B")}:{M("C")})<2,"PENDING",{B("input_month_M")}*{M("B")}+({B("output_month_M")}+N({M("J")})*{B("calls_query")}*{B("month_queries")}/1000000)*{M("C")})',
          f'=IF(AND({M("I")}=1,ISNUMBER({M("E")}),{I("prefix")}>={M("E")},ISNUMBER({M("D")}),ISNUMBER({M("G")})),FLOOR({I("prefix")},MAX(1,{M("F")})),0)',
          f'=D{r}*{B("month_queries")}/1000000',f'=D{r}*{B("calls_query")}*{B("month_queries")}/1000000-E{r}',
          f'=IF(NOT(ISNUMBER(C{r})),"PENDING",IF(D{r}=0,C{r},C{r}-(E{r}+F{r})*{M("B")}+E{r}*{M("B")}*{M("G")}+F{r}*{M("D")}))',
          f'=IF(NOT(ISNUMBER(C{r})),"PENDING",IF(C{r}>{B("B")},"Over budget",IF(ISNUMBER({M("J")}),"Within budget","Not established")))',
          f'=IF(NOT(ISNUMBER(G{r})),"PENDING",IF(G{r}>{B("B")},"Over budget",IF(ISNUMBER({M("J")}),"Within budget","Not established")))',
          f'=IF(ISNUMBER({M("K")}),IF({B("peak_rpm")}<={M("K")},"Pass RPM","Exceeds"),"Not verified")',
          f'=IF(ISNUMBER({M("L")}),IF({B("peak_tpm")}<={M("L")},"Pass visible TPM","Exceeds before reasoning"),"Not verified")',
          'One cold write/query; alternative fixed TTL windows shared across queries, continuous traffic, no eviction.',
          f'=IF(AND(D{r}>0,ISNUMBER({M("H")})),MIN({B("calls_query")}*{B("month_queries")},ROUNDUP({I("days")}*86400/MAX(1,{M("H")}),0))*D{r}/1000000,"PENDING")',
          f'=IF(AND(ISNUMBER(M{r}),ISNUMBER(C{r})),C{r}-(E{r}+F{r})*{M("B")}+M{r}*{M("B")}*{M("G")}+(E{r}+F{r}-M{r})*{M("D")},"PENDING")'])
    cfg=read('model_config_values.json')
    for key in ['num_hidden_layers','num_key_value_heads','hidden_size','num_attention_heads','head_dim','intermediate_size','vocab_size']:
        mapping[key]=inp.max_row+1;inp.append([key,cfg[key],'Qwen2.5 7B config',cfg['source_url'],cfg['access_date']])
    mem=wb.create_sheet('GPU memory')
    mem.append(['Metric','Formula result','Units and interpretation'])
    mem.append(['Exact parameters',f'=2*{I("vocab_size")}*{I("hidden_size")}+{I("num_hidden_layers")}*(2*{I("hidden_size")}^2+2*{I("hidden_size")}*{I("num_key_value_heads")}*{I("head_dim")}+3*{I("hidden_size")}*{I("intermediate_size")}+3*{I("hidden_size")}+2*{I("num_key_value_heads")}*{I("head_dim")})+{I("hidden_size")}','Q/K/V biases; untied embeddings; dense architecture'])
    mem.append(['FP16 weight bytes','=B2*2','Ideal weights'])
    mem.append(['INT8 weight bytes','=B2','Ideal weights'])
    mem.append(['INT4 weight bytes','=B2/2','Ideal weights; excludes scales/packing'])
    mem.append(['Longest sequence',f"='Token and load'!B{end}+'Token and load'!C{end}",'input + output at call N'])
    mem.append(['KV bytes/sequence',f'=2*{I("num_hidden_layers")}*{I("num_key_value_heads")}*{I("head_dim")}*B6*2','full-attention FP16 KV'])
    mem.append(['Memory capacity sequences',f'=MAX(0,FLOOR(({I("gpu_bytes")}*(1-{I("reserve_fraction")})-B5)/B7,1))','memory ceiling only; not throughput proof'])
    mem.append(['Peak arrival / second',f'={B("peak_qpm")}/60','queries/s'])
    mem.append(['Little law mean sessions',f'=IF(ISNUMBER({I("service_seconds")}),B9*{I("service_seconds")},"PENDING")','L=lambda W; requires self-host service time'])
    mem.append(['GPUs required', '=IF(ISNUMBER(B10),ROUNDUP(B10/B8,0),"PENDING")','mean-memory lower bound, not queue guarantee'])
    mem.append(['Monthly GPU USD',f'=IF(ISNUMBER(B11),B11*{I("gpu_hourly")}*24*{I("days")},"PENDING")','excludes disk, network, CPU, labour'])
    mem.append(['T sensitivity sessions',f'=B9*{I("sensitivity_seconds")}','scenario, not measured'])
    mem.append(['T sensitivity GPUs','=ROUNDUP(B13/B8,0)','memory floor'])
    mem.append(['T sensitivity USD',f'=B14*{I("gpu_hourly")}*24*{I("days")}','monthly 24/7'])
    lat=wb.create_sheet('Latency')
    lat.append(['Candidate','Call','Input tokens','Output tokens','Expected attempts','TTFT seconds','Decode tokens/s','Reasoning tokens','Expected LLM seconds'])
    ranges={}
    for name in ['GPT-5.4 nano','Claude Haiku 5.5']:
        start=lat.max_row+1;s=modelrows[name]
        for k in range(1,7):
            r=lat.max_row+1;lr=first+k-1;col=get_column_letter(14+k)
            lat.append([name,k,f"='Token and load'!B{lr}",f"='Token and load'!C{lr}",f"='Token and load'!D{lr}",
                f'=IF(ISNUMBER(\'Model inputs\'!{col}{s}),\'Model inputs\'!{col}{s},"PENDING")',
                f'=IF(ISNUMBER(\'Model inputs\'!N{s}),\'Model inputs\'!N{s},"PENDING")',
                f'=IF(ISNUMBER(\'Model inputs\'!J{s}),\'Model inputs\'!J{s},"PENDING")',
                f'=IF(COUNT(F{r}:H{r})=3,E{r}*(F{r}+(D{r}+H{r})/G{r}),"PENDING")'])
        ranges[name]=(start,lat.max_row)
    lat.append([]);lat.append(['Candidate','Sequential total s','API-only sensitivity s','Within T','Architecture change'])
    for name,(start,stop) in ranges.items():
        r=lat.max_row+1
        lat.append([name,f'=IF(AND({I("timing_complete")}=1,COUNT(I{start}:I{stop})={B("N")} ),SUM(I{start}:I{stop})+({B("N")}-1)*{I("pooled_delay")},"PENDING")',
            f'=IF(ISNUMBER(B{r}),B{r}-({B("N")}-1)*{I("pooled_delay")}+({B("N")}-1)*{I("api_only_delay")},"PENDING")',
            f'=IF(ISNUMBER(B{r}),IF(B{r}<={B("T")},"Yes","No"),"PENDING")',
            'Fixed deterministic tool workflow, then one final answer call. Recalculated below.'])
    # ONE architecture change for both candidates: deterministic tool workflow,
    # one final call, same five tool delays, no invalid tool-call retries.
    lat.append(['Changed workflow candidate','Pooled total s','API-only total s','Within T','Changed no-cache monthly USD'])
    for name,(start,stop) in ranges.items():
        r=lat.max_row+1;s=modelrows[name]
        lat.append([name,
          f'=IF(AND({I("timing_complete")}=1,COUNT(F{stop}:H{stop})=3),F{stop}+(D{stop}+H{stop})/G{stop}+({B("N")}-1)*{I("pooled_delay")},"PENDING")',
          f'=IF(ISNUMBER(B{r}),B{r}-({B("N")}-1)*{I("pooled_delay")}+({B("N")}-1)*{I("api_only_delay")},"PENDING")',
          f'=IF(ISNUMBER(B{r}),IF(B{r}<={B("T")},"Yes estimate","No"),"PENDING")',
          f'=IF(COUNT(\'Model inputs\'!B{s}:C{s})=2,(C{stop}*\'Model inputs\'!B{s}+(D{stop}+N(H{stop}))*\'Model inputs\'!C{s})*{B("month_queries")}/1000000,"PENDING")'])
    lat.append(['Nano TTFT basis','AA non-reasoning aggregate 1.34 s reused for all growing inputs; length/load matched TTFT not verified.'])
    lat.append(['Haiku basis','Disabled-thinking TTFT/speed not verified; AA Max values excluded.'])
    lat.append(['Change definition','Fixed deterministic workflow for the five tools followed by one final 600-token LLM call with 6000 input tokens. No parallelism/streaming assumed.'])
    be=wb.create_sheet('Break even sensitivity')
    be.append(['Daily Q','Monthly queries','Peak sessions W=T','GPU count','Self-host USD','Haiku cache API USD','Cheaper option'])
    hr=modelrows['Claude Haiku 5.5']
    ar=hr # API costs rows and model inputs rows align.
    for q in range(0,30001,100):
        r=be.max_row+1
        be.append([q,f'=A{r}*{B("month_factor")}',f'=A{r}*{I("heat_multiplier")}*{I("peak_fraction")}/{I("peak_minutes")}/60*{I("sensitivity_seconds")}',
          f'=ROUNDUP(C{r}/\'GPU memory\'!$B$8,0)',f'=D{r}*{I("gpu_hourly")}*24*{I("days")}',
          f'=A{r}*\'API costs\'!$G${ar}/{B("Q")}',f'=IF(E{r}<F{r},"Self-host sensitivity","API sensitivity")'])
    evidence=wb.create_sheet('Model comparison')
    with (OUT/'model_comparison.csv').open(newline='') as f:
        for row in csv.reader(f):evidence.append(row)
    for ws in wb:
        ws.freeze_panes='B2';ws.auto_filter.ref=ws.dimensions
        ws.sheet_view.showGridLines=False
        for cell in ws[1]:cell.font=Font(name='Calibri',bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='23394D')
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.font=Font(name='Calibri',size=11,color='000000' if cell.data_type=='f' else '235A91')
                cell.alignment=Alignment(vertical='top',wrap_text=True)
                if isinstance(cell.value,(int,float)):cell.number_format='#,##0.000'
                if cell.row%2==0:cell.fill=PatternFill('solid',fgColor='F1F5F8')
        for col in range(1,ws.max_column+1):ws.column_dimensions[get_column_letter(col)].width=24 if col>1 else 34
        for r in range(2,ws.max_row+1):ws.row_dimensions[r].height=46 if ws.title!='Model comparison' else 84
        ws.row_dimensions[1].height=42
        ws.sheet_properties.pageSetUpPr.fitToPage=True
        ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3
        ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
        ws.print_title_rows='1:1'
    inp.column_dimensions['C'].width=60;inp.column_dimensions['D'].width=65
    api.column_dimensions['L'].width=65;ms.column_dimensions['X'].width=80
    ms.column_dimensions['V'].width=65
    for ws in wb:
        for row in ws.iter_rows(min_row=2):
            lines=1
            for cell in row:
                if cell.value is None or cell.data_type=='f':continue
                width=ws.column_dimensions[cell.column_letter].width or 24
                needed=sum(max(1,math.ceil(len(part)/max(8,width-3))) for part in str(cell.value).split('\n'))
                lines=max(lines,needed)
            ws.row_dimensions[row[0].row].height=min(409,max(30,lines*15+12))
    wb.calculation=CalcProperties(calcId=191029,fullCalcOnLoad=True,forceFullCalc=True)
    return wb



def compact_workbook(source):
    """Keep one visible sheet, remapping every formula to its new cell."""
    import re
    from copy import copy
    from openpyxl.formula.tokenizer import Tokenizer
    from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
    from openpyxl.drawing.image import Image
    target=Workbook(); ws=target.active; ws.title='SaafHawa'
    mapping={}; pending=[]; section_rows={}; cursor=11
    widths=[35,17,19,16,18,17,18,18,17,17,17,23,18,18]
    for col,width in enumerate(widths,1):ws.column_dimensions[get_column_letter(col)].width=width
    ws.merge_cells('A1:N1');ws['A1']='SaafHawa model study — roll number 23K-0057';ws['A1'].font=Font(size=18,bold=True,color='FFFFFF');ws['A1'].fill=PatternFill('solid',fgColor='23394D');ws.row_dimensions[1].height=32
    ws.merge_cells('A2:N2');ws['A2']='Draft • 15 Nov 2026 • PENDING means missing measurements or unverified evidence. Blue numbers are editable inputs.';ws['A2'].alignment=Alignment(wrap_text=True);ws.row_dimensions[2].height=30
    def section(title):
        nonlocal cursor
        cursor+=1;section_rows[title]=cursor
        ws.merge_cells(start_row=cursor,start_column=1,end_row=cursor,end_column=14)
        c=ws.cell(cursor,1,title);c.font=Font(bold=True,color='FFFFFF',size=12);c.fill=PatternFill('solid',fgColor='23394D');ws.row_dimensions[cursor].height=26
        cursor+=1
    def copy_block(name,title,columns=None,row_count=None):
        nonlocal cursor
        old=source[name];section(title)
        columns=columns or [(c,c) for c in range(1,old.max_column+1)]
        for oldrow in range(1,(row_count or old.max_row)+1):
            newrow=cursor;cursor+=1
            maxlines=1
            for oldcol,newcol in columns:
                original=old.cell(oldrow,oldcol);dest=ws.cell(newrow,newcol)
                mapping[(name,original.coordinate)]=dest.coordinate
                if original.data_type=='f':pending.append((dest,original.value,name))
                else:dest.value=original.value
                if name=='API costs' and oldrow>1 and oldcol==12:
                    dest.value='One cold write/query' if read('models.json')[oldrow-2]['cache_verified'] else 'No savings credited'
                dest.alignment=Alignment(vertical='top',wrap_text=True)
                dest.font=Font(name='Calibri',size=10,color='235A91' if isinstance(original.value,(float,int)) else '000000')
                dest.number_format=('#,##0' if isinstance(original.value,(float,int)) and float(original.value).is_integer() else 'General')
                if name=='API costs' and oldcol in (3,7,14):dest.number_format='#,##0.00'
                if oldrow==1 or old.cell(oldrow,1).value in ('Call k','Candidate'):
                    dest.font=Font(bold=True,color='000000',size=10);dest.fill=PatternFill('solid',fgColor='DDE7EF')
                elif oldrow%2==0:dest.fill=PatternFill('solid',fgColor='F2F5F8')
                if original.value is not None and original.data_type!='f':
                    maxlines=max(maxlines,math.ceil(len(str(dest.value))/max(10,widths[newcol-1]-2)))
            # Explanations use the remaining width rather than narrow columns.
            if name in ('GPU memory','Token and load') and oldrow!=1 and not isinstance(old.cell(oldrow,1).value,int) and all(old.cell(oldrow,c).value is None for c in range(4,old.max_column+1)):
                ws.merge_cells(start_row=newrow,start_column=3,end_row=newrow,end_column=14)
                text=old.cell(oldrow,3).value or ''
                maxlines=max(1,math.ceil(len(str(text))/125),math.ceil(len(str(old.cell(oldrow,1).value or ''))/30))
            if name=='Inputs':
                # All original inputs remain editable; source text and date stay adjacent.
                ws.merge_cells(start_row=newrow,start_column=4,end_row=newrow,end_column=12)
                ws.cell(newrow,13,old.cell(oldrow,5).value)
                if oldrow>1:ws.cell(newrow,4,old.cell(oldrow,4).value)
                maxlines=max(2,math.ceil(len(str(old.cell(oldrow,3).value or ''))/17))
            ws.row_dimensions[newrow].height=min(409,max(26,maxlines*13+8))
    copy_block('Inputs','Inputs and configuration',[(1,1),(2,2),(3,3),(4,4),(5,13)])
    copy_block('Token and load','Token volume and peak load')
    copy_block('Model inputs','API inputs — prices, cache terms and limits',[(c,c) for c in range(1,15)])
    copy_block('Model inputs','Candidate timing inputs — six TTFT values for increasing input lengths',[(1,1)]+[(c,c-13) for c in range(15,21)])
    # Both blocks contain the model name. Its last mapping is harmless, but ensure
    # numeric inputs B:N retain their first-block mapping.
    copy_block('API costs','Monthly API costs and rate-limit checks')
    copy_block('GPU memory','Self-hosting memory and GPU cost')
    copy_block('Latency','Sequential latency and deterministic workflow calculation')
    oldbe=source['Break even sensitivity']
    q_values=[0,1000,2925,4191,4192,5000,10000,19337,19338,20000,30000]
    for row,q in enumerate(q_values,2):oldbe.cell(row,1,q)
    copy_block('Break even sensitivity','Cost sensitivity — assumed service time 10 s, not measured',row_count=len(q_values)+1)
    section('Monthly cost curve — conditional sensitivity')
    pic=Image(str(OUT/'monthly_cost_vs_daily_volume.png'));pic.width=900;pic.height=500;ws.add_image(pic,f'A{cursor}')
    for row in range(cursor,cursor+26):ws.row_dimensions[row].height=15
    cursor+=27
    section('Model comparison — source IDs resolve to dated URLs below')
    groups=[(1,1,'Model and provider'),(2,4,'Size and capabilities'),(5,7,'Prices and account limits'),(8,11,'Performance, reasoning and licence'),(12,14,'Evidence')]
    for first,last,label in groups:
        ws.merge_cells(start_row=cursor,start_column=first,end_row=cursor,end_column=last);c=ws.cell(cursor,first,label);c.font=Font(bold=True);c.fill=PatternFill('solid',fgColor='DDE7EF')
    cursor+=1
    models=read('models.json')
    for m in models:
        def field(k):return f"{m['fields'].get(k,'not verified')} [{m['sources'].get(k,m['spec_source'])}]"
        def val(k):return f"{m[k] if m[k] is not None else 'not verified'} [{m['sources'].get(k,m['spec_source'])}]"
        texts=[m['name']+'\n'+m['kind']+'\n'+m['inference_provider'],
            'Parameters: '+field('parameters')+'\nContext: '+field('context')+'\nMax output: '+field('max_output')+'\nTools: '+field('native_tools')+'; JSON: '+field('structured_json'),
            'USD/M input / output / cache: '+val('price_input')+' / '+val('price_output')+' / '+val('price_cache')+'\nRPM / TPM: '+val('rpm')+' / '+val('tpm')+'\n'+field('new_account_limits'),
            'TTFT and speed: '+field('performance_reported')+'\nTool benchmark: '+field('benchmark_tool')+'\nOther benchmark: '+field('benchmark_other')+'\n'+field('reasoning')+'\n'+field('licence'),
            'Per-source ISO access dates below.\n'+ ' '.join(dict.fromkeys([m['spec_source']]+list(m['sources'].values())))+'\nLowest verified standard price among checked providers; global minimum not verified.']
        maxlines=1
        for (first,last,_),text in zip(groups,texts):
            ws.merge_cells(start_row=cursor,start_column=first,end_row=cursor,end_column=last)
            c=ws.cell(cursor,first,text);c.alignment=Alignment(wrap_text=True,vertical='top');c.font=Font(size=10)
            chars=sum(widths[first-1:last])-4
            lines=sum(max(1,math.ceil(len(t)/chars)) for t in text.split('\n'))
            maxlines=max(maxlines,lines)
        ws.row_dimensions[cursor].height=min(409,maxlines*14+14);cursor+=1
    section('Source URLs and ISO access dates')
    for key,entry in read('sources.json').items():
        ws.cell(cursor,1,key);ws.merge_cells(start_row=cursor,start_column=2,end_row=cursor,end_column=14)
        c=ws.cell(cursor,2,entry['url']+' | '+entry['access_date']);c.hyperlink=entry['url'];c.font=Font(color='235A91',size=10);c.alignment=Alignment(wrap_text=True)
        ws.row_dimensions[cursor].height=28;cursor+=1
    # Translate references after every source cell has a destination.
    ref_re=re.compile(r"(?:(?:'(?P<quoted>[^']+)'|(?P<sheet>[^!]+))!)?(?P<start>\$?[A-Z]+\$?\d+)(?::(?P<end>\$?[A-Z]+\$?\d+))?$")
    def translate_ref(ref,context):
        if ':' in ref:
            first,last=ref.split(':',1)
            shared=first.rsplit('!',1)[0].strip("'") if '!' in first else context
            return translate_ref(first,context)+':'+translate_ref(last,shared)
        match=ref_re.fullmatch(ref)
        if not match:raise ValueError('Unsupported formula reference: '+ref)
        sheet=match['quoted'] or match['sheet'] or context
        def one(coord):
            dest=mapping[(sheet,coord.replace('$',''))]
            col,row=coordinate_from_string(dest)
            oldcol,oldrow=coordinate_from_string(coord.replace('$',''))
            absolute_col=coord.startswith('$');absolute_row='$' in coord[len(oldcol)+(1 if absolute_col else 0):]
            return ('$' if absolute_col else '')+col+('$' if absolute_row else '')+str(row)
        value=one(match['start'])
        return value+(':'+one(match['end']) if match['end'] else '')
    for dest,formula,context in pending:
        parts=[]
        for token in Tokenizer(formula).items:
            parts.append(translate_ref(token.value,context) if token.type=='OPERAND' and token.subtype=='RANGE' else token.value)
        dest.value='='+''.join(parts);dest.font=Font(size=10,color='000000')
    labels={source['Token and load'].cell(r,1).value:r for r in range(2,source['Token and load'].max_row+1)}
    summary=[('Input tokens/query','input_query'),('Output tokens/query','output_query'),('Calls/query','calls_query'),
             ('Queries/month','month_queries'),('Input M/month','input_month_M'),('Output M/month','output_month_M'),
             ('Peak queries/min','peak_qpm'),('Peak LLM calls/min','peak_rpm'),('Peak tokens/min','peak_tpm')]
    summary_cells={}
    for index,(label,key) in enumerate(summary):
        row=4+index//3;first=1+(index%3)*5
        # Last summary pair uses K:L for label, M:N for result.
        first=min(first,11);valuecol=first+2
        ws.merge_cells(start_row=row,start_column=first,end_row=row,end_column=first+1)
        ws.cell(row,first,label).font=Font(bold=True,size=10)
        if valuecol<14:ws.merge_cells(start_row=row,start_column=valuecol,end_row=row,end_column=min(valuecol+1,14))
        c=ws.cell(row,valuecol,'='+mapping[('Token and load',f'B{labels[key]}')]);c.number_format=('#,##0' if key in ('input_query','output_query','month_queries') else ('0.0' if key=='calls_query' else '#,##0.00000'));c.font=Font(size=11)
        summary_cells[key]=c.coordinate
        ws.row_dimensions[row].height=27
    ws.merge_cells('A8:N8');ws['A8']='R=57, D=2 from 0057; 23K excluded. Timing: >=20 valid/tool across >=2 Karachi dates. Operational Q* awaits verified RTX 4090 service time and Haiku latency.';ws['A8'].alignment=Alignment(wrap_text=True);ws.row_dimensions[8].height=30
    # Apply the student's worksheet review: no banner or input metadata columns.
    ws['A2']=None;ws.row_dimensions[2].height=5
    input_start=section_rows['Inputs and configuration']+1
    input_end=input_start+source['Inputs'].max_row
    for row in range(input_start,input_end):
        # Keep source/date metadata next to inputs; merge only the notes area.
        if row>input_start:
            ws.row_dimensions[row].height=max(42,ws.row_dimensions[row].height or 0)
    # Extra source metadata is retained so every figure can be traced.
    ws[mapping[('Inputs',f'B{2}')]].number_format='@'
    ws.freeze_panes='B11';ws.sheet_view.showGridLines=False;ws.sheet_view.zoomScale=65
    ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
    ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.print_options.horizontalCentered=True
    target.calculation=CalcProperties(calcId=191029,fullCalcOnLoad=True,forceFullCalc=True)
    (ROOT/'work').mkdir(exist_ok=True)
    (ROOT/'work'/'workbook_cells.json').write_text(json.dumps({'summary':summary_cells,'sections':section_rows,'inputs':{key:dest for (name,key),dest in mapping.items() if name=='Inputs'}},indent=2))
    return target


def main():
    target=compact_workbook(_make_sections())
    dest=OUT/'calculations.xlsx';target.save(dest)
    print('Saved one worksheet:',dest)


if __name__=='__main__':main()
