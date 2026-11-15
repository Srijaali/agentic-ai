import csv
import math
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from openpyxl import load_workbook
from calculations import read, parameters, volumes, memory, OUT, latency, api_cost, break_even
from tool_latency_logger import FIELDS, TOOLS, summarize, heat_index_c, latest_values


def main():
    a=read('assumptions.json');p=parameters(a);v=volumes(a,p)
    assert p==dict(R=57,D=2,Q=2925,N=6,p=.06,H=5,B=1770,T=10)
    assert 'D' not in a and a['ROLL_DIGITS']=='0057'
    assert parameters(dict(a,ROLL_DIGITS='0001'))['D']==1
    assert v['input_query']==25080 and v['output_query']==2455
    assert math.isclose(v['calls_query'],6.3)
    assert v['month_queries']==146250
    # Independent decimal reconciliation, including the theoretical shared prefix.
    assert Decimal('25080')*Decimal('146250')==Decimal('3667950000')
    assert Decimal('2455')*Decimal('146250')==Decimal('359043750')
    assert Decimal('1500')*Decimal('6.3')*Decimal('146250')==Decimal('1382062500')
    assert math.isclose(v['peak_qpm'],42.65625)
    assert math.isclose(v['peak_tpm'],1174539.84375)
    assert math.isclose(heat_index_c(20,50),19.68055555555556,abs_tol=1e-9)
    assert math.isclose(heat_index_c((90-32)*5/9,70),(105.9220206-32)*5/9,abs_tol=1e-6)
    try:heat_index_c(30,120);raise AssertionError('Invalid humidity accepted')
    except ValueError:pass
    now=datetime.now(timezone.utc)
    payload={'results':[{'sensorsId':1,'value':10,'datetime':{'utc':(now-timedelta(hours=4)).isoformat()}},
                         {'sensorsId':2,'value':20,'datetime':{'utc':now.isoformat()}}]}
    values=latest_values(payload,{1:'pm25',2:'pm10'})
    assert not values['pm25']['recent'] and values['pm10']['recent']
    with tempfile.TemporaryDirectory(prefix='saafhawa_test_') as temp:
        f=Path(temp)/'TEST_ONLY.csv'
        with f.open('w',newline='') as h:
            w=csv.DictWriter(h,fieldnames=FIELDS);w.writeheader()
            for day in ['2026-11-14','2026-11-15']:
                for tool in TOOLS:
                    for i in range(1 if day.endswith('14') else 19):
                        w.writerow(dict(run_id='SYNTHETIC_UNIT_TEST',karachi_date=day,tool=tool,
                            iteration=i,elapsed_seconds=.1 if tool in TOOLS[:2] else .000001,valid=1,
                            machine='TEST_A' if day.endswith('14') else 'TEST_B'))
        result=summarize(f)
        assert result['complete']
        assert result['machine_mismatch'] and not result['missing']
        assert math.isclose(result['pooled_median_seconds'],.0500005)
        assert result['api_only_median_seconds']==.1
        with f.open('a',newline='') as h:
            csv.DictWriter(h,fieldnames=FIELDS).writerow(dict(tool='openaq',valid=0,elapsed_seconds=99))
        assert summarize(f)['pooled_median_seconds']==result['pooled_median_seconds']
    cfg=read('model_config_values.json');mem=memory(a,p,v,cfg)
    assert mem['sequence_length']==6600 and mem['kv_bytes']==378470400
    assert mem['concurrent_capacity']>0
    assert mem['concurrent_capacity']==47 and mem['gpus'] is None
    models=read('models.json');nano=models[0]
    timing=dict(complete=True,pooled_median_seconds=.1,api_only_median_seconds=.3)
    estimate=latency(nano,a,p,timing)
    assert math.isclose(estimate['total_seconds'],6.3*1.34+2455/115+.5)
    assert math.isclose(estimate['retry_seconds'],.06*5*(1.34+350/115))
    assert estimate['changed_total_seconds']<10<estimate['total_seconds']
    assert latency(nano,a,p,dict(timing,complete=False))['total_seconds'] is None
    haiku=next(m for m in models if m['name']=='Claude Haiku 5.5')
    cost=api_cost(haiku,a,p,v)
    assert math.isclose(cost['cache'],447.159375)
    assert math.isclose(cost['cache_ttl_window'],423.42165)
    costs=[api_cost(m,a,p,v) for m in models]
    assert break_even(a,p,v,mem,costs,[estimate,latency(haiku,a,p,timing)])['operational_qstar'] is None
    # Synthetic unit-test candidate: do not write this to research inputs.
    second=dict(latency(haiku,a,p,timing),total_seconds=8,changed_total_seconds=7,changed_monthly_cost=100)
    chosen=break_even(a,p,v,dict(mem,service_seconds=10),costs,[estimate,second])
    assert chosen['selected_candidate']['model']=='GPT-5.4 nano'
    assert chosen['selected_candidate']['monthly_cost']==estimate['changed_monthly_cost']
    assert chosen['operational_qstar']==6573
    wb=load_workbook(OUT/'calculations.xlsx')
    assert wb.sheetnames == ['SaafHawa']
    assert wb['SaafHawa']['C4'].value.startswith('=')
    assert len(read('models.json'))>=12
    for ws in wb:
        for row in ws:
            for cell in row:
                if cell.data_type=='f':assert '#REF!' not in cell.value
    print('PASS: token/load arithmetic, NWS branches, freshness validation, pooled/API medians, invalid-row exclusion, memory formula, workbook formula presence.')
    print('Live spreadsheet engine recalculation and final visual QA are separate checks; formula presence alone is not recalculation proof.')


if __name__=='__main__':main()
