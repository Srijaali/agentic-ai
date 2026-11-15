import argparse
import csv
import json
import math
import os
import platform
import statistics
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
KARACHI = ZoneInfo('Asia/Karachi')
TOOLS = ('openaq', 'open_meteo', 'heat_index', 'kb_lookup')
LEGACY_FIELDS = ['run_id', 'utc_time', 'karachi_date', 'tool', 'iteration',
          'elapsed_seconds', 'http_status', 'valid', 'error', 'response_file', 'machine']
FIELDS = LEGACY_FIELDS + ['timing_valid', 'data_requirement_met']


def load_env():
    """Minimal .env support without another dependency; existing environment wins."""
    f = ROOT / '.env'
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.removeprefix('export ').split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


def utc_now():
    return datetime.now(timezone.utc)


def parse_time(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Measurement timestamp has no timezone')
    return dt


def recent(value, now=None):
    age = ((now or utc_now()) - parse_time(value)).total_seconds()
    return -300 <= age <= 3 * 3600


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def heat_index_c(temp_c, rh):
    """NWS procedure, including the initial average and both RH adjustments.

    https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
    The estimate describes shaded, light-wind conditions; it is not a diagnosis.
    """
    if not number(temp_c) or not number(rh) or not 0 <= rh <= 100:
        raise ValueError('Invalid temperature or relative humidity')
    t = temp_c * 9 / 5 + 32
    simple = 0.5 * (t + 61 + (t - 68) * 1.2 + rh * 0.094)
    hi = (simple + t) / 2
    if hi >= 80:
        hi = (-42.379 + 2.04901523*t + 10.14333127*rh - 0.22475541*t*rh
              - 0.00683783*t*t - 0.05481717*rh*rh + 0.00122874*t*t*rh
              + 0.00085282*t*rh*rh - 0.00000199*t*t*rh*rh)
        if rh < 13 and 80 <= t <= 112:
            hi -= ((13-rh)/4) * math.sqrt((17-abs(t-95))/17)
        elif rh > 85 and 80 <= t <= 87:
            hi += ((rh-85)/10) * ((87-t)/5)
    return (hi-32)*5/9


def kb_lookup(query, kb):
    words = set(query.lower().split())
    return sorted(kb, key=lambda x: len(words & set(x['keywords'])), reverse=True)[:2]


class Recorder:
    def __init__(self):
        import requests
        self.run_id = utc_now().strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8]
        self.folder = ROOT / 'raw_responses' / self.run_id
        self.folder.mkdir(parents=True, exist_ok=False)
        self.last_api_end = None
        self.session = requests.Session()
        self.counter = 0

    def api(self, url, params=None, headers=None):
        import requests
        # Wait outside the timed section. One Session, no automatic HTTP retries.
        if self.last_api_end is not None:
            time.sleep(max(0, 1.1 - (time.perf_counter()-self.last_api_end)))
        stamp = utc_now()
        self.counter += 1
        path = self.folder / f'{self.counter:04d}.json'
        status, payload, error, body = None, None, '', ''
        start = time.perf_counter()
        try:
            r = self.session.get(url, params=params, headers=headers, timeout=30)
            body, status = r.text, r.status_code
        except requests.RequestException as exc:
            # Do not serialize exceptions that might include request details.
            error = type(exc).__name__
        elapsed = time.perf_counter()-start
        self.last_api_end = time.perf_counter()
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            if not error:
                error = 'Response was not JSON'
        if status != 200 and not error:
            error = f'HTTP {status}'
        # Store full response body, including non-JSON failures, never headers.
        path.write_text(json.dumps({'url': url, 'params': params, 'utc_time': stamp.isoformat(),
                                   'http_status': status, 'body': body, 'error': error}, indent=2))
        return payload, elapsed, status, error, str(path.relative_to(ROOT)), stamp

    def append(self, tool, iteration, elapsed, status, valid, error, response_file, stamp=None, data_requirement_met=None):
        stamp = stamp or utc_now()
        log = ROOT/'tool_latency_raw.csv'
        new = not log.exists() or log.stat().st_size == 0
        # Never rewrite historical rows. Existing logs retain their original schema;
        # the immutable sidecar records the two independent validity flags.
        columns = FIELDS if new else next(csv.reader(log.open(newline='')))
        record = dict(zip(LEGACY_FIELDS, [self.run_id, stamp.isoformat(),
            stamp.astimezone(KARACHI).date().isoformat(), tool, iteration,
            f'{elapsed:.12f}', status if status is not None else '', int(valid),
            error, response_file, platform.node()+' | '+platform.platform()]))
        record.update(timing_valid=int(valid), data_requirement_met=int(valid if data_requirement_met is None else data_requirement_met))
        with log.open('a', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction='ignore')
            if new:
                writer.writeheader()
            writer.writerow(record)
        with (self.folder/'sample_validity.jsonl').open('a') as handle:
            handle.write(json.dumps(record)+'\n')

    def local(self, tool, iteration, fn):
        stamp = utc_now()
        start = time.perf_counter()
        result, error = None, ''
        try:
            result = fn()
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
        elapsed = time.perf_counter()-start
        self.counter += 1
        path = self.folder / f'{self.counter:04d}_{tool}.json'
        path.write_text(json.dumps({'utc_time': stamp.isoformat(), 'result': result, 'error': error}, indent=2))
        self.append(tool, iteration, elapsed, None, not error, error, str(path.relative_to(ROOT)), stamp)


def rows_from(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
        raise ValueError('Missing results array')
    return payload['results']


def latest_values(payload, sensor_map, now=None):
    values = {}
    for row in rows_from(payload):
        param = sensor_map.get(row.get('sensorsId'))
        if param in ('pm25', 'pm10') and number(row.get('value')) and row['value'] >= 0:
            timestamp = row.get('datetime', {}).get('utc')
            try:
                live = recent(timestamp, now)
            except (TypeError, ValueError, AttributeError):
                live = False
            record = {'value': row['value'], 'utc_time': timestamp, 'recent': live}
            if param not in values or (live and not values[param]['recent']):
                values[param] = record
    return values


def discover(rec):
    key = os.environ.get('OPENAQ_API_KEY')
    if not key:
        raise RuntimeError('OPENAQ_API_KEY is missing. Add it to .env or your environment.')
    headers = {'X-API-Key': key}
    locations, page, complete = [], 1, True
    while True:
        data, _, status, error, _, _ = rec.api('https://api.openaq.org/v3/locations',
            {'coordinates': '24.8607,67.0011', 'radius': 25000, 'limit': 100, 'page': page}, headers)
        if error:
            raise RuntimeError('OpenAQ location discovery failed: '+error)
        batch = rows_from(data)
        locations.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    candidates = []
    for loc in locations:
        sensor_map = {s['id']: s.get('parameter', {}).get('name') for s in loc.get('sensors', [])}
        if not ({'pm25', 'pm10'} & set(sensor_map.values())):
            continue
        data, _, status, error, response, _ = rec.api(
            f"https://api.openaq.org/v3/locations/{loc['id']}/latest", {'limit': 1000}, headers)
        if error:
            complete = False
            values = {}
        else:
            try:
                values = latest_values(data, sensor_map)
                if len(rows_from(data)) >= 1000:
                    complete = False
            except ValueError:
                values, complete = {}, False
        candidates.append({'id': loc['id'], 'name': loc.get('name'),
            'sensor_map': sensor_map, 'latest': values, 'response_file': response,
            'error': error, 'last_reported': loc.get('datetimeLast')})
    both = [x for x in candidates if all(x['latest'].get(p, {}).get('recent') for p in ('pm25', 'pm10'))]
    pm25 = [x for x in candidates if x['latest'].get('pm25', {}).get('recent')]
    selected = (both or pm25 or candidates or [None])[0]
    report = {'run_id': rec.run_id, 'checked_at_utc': utc_now().isoformat(),
              'coordinates': [24.8607, 67.0011], 'radius_m': 25000, 'recency_hours': 3,
              'discovery_complete': complete, 'station_count': len(locations),
              'live_both_pm25_pm10': bool(both) if complete else (True if both else 'not verified'),
              'live_pm10_any_station': any(x['latest'].get('pm10', {}).get('recent') for x in candidates),
              'selected_station_id': selected['id'] if selected else None, 'candidates': candidates}
    path = rec.folder/'coverage_report.json'
    path.write_text(json.dumps(report, indent=2))
    (ROOT/'data').mkdir(exist_ok=True)
    (ROOT/'data'/'coverage_latest.json').write_text(json.dumps(report, indent=2))
    print('Coverage report:', path.relative_to(ROOT))
    print('Live station with BOTH PM2.5 and PM10:', report['live_both_pm25_pm10'])
    print('Selected station:', report['selected_station_id'])
    if not both:
        print('PM10 coverage: no verified live dual-pollutant station. Never substitute stale data.')
    return selected


def validate_weather(payload):
    if not isinstance(payload, dict):
        raise ValueError('Weather response is not an object')
    cur = payload.get('current', {})
    units = payload.get('current_units', {})
    expected = {'temperature_2m': '°C', 'relative_humidity_2m': '%', 'wind_speed_10m': 'km/h'}
    for name, unit in expected.items():
        if not number(cur.get(name)) or units.get(name) != unit:
            raise ValueError('Weather field or unit invalid: '+name)
    if payload.get('timezone') != 'Asia/Karachi' or not 0 <= cur['relative_humidity_2m'] <= 100:
        raise ValueError('Weather timezone or humidity invalid')
    stamp = datetime.fromisoformat(cur['time']).replace(tzinfo=KARACHI)
    if abs((utc_now()-stamp).total_seconds()) > 3*3600:
        raise ValueError('Weather reading is stale')
    return cur


def measure(samples):
    rec = Recorder()
    station = discover(rec)
    headers = {'X-API-Key': os.environ['OPENAQ_API_KEY']}
    kb = json.loads((ROOT/'data'/'advisories.json').read_text())
    for iteration in range(1, samples+1):
        if station:
            data, elapsed, status, error, response, stamp = rec.api(
                f"https://api.openaq.org/v3/locations/{station['id']}/latest", {'limit': 1000}, headers)
            try:
                values = latest_values(data, station['sensor_map']) if not error else {}
                if not values:
                    error = error or 'No valid mapped particulate measurement in API response'
            except ValueError as exc:
                error = str(exc)
            coverage = not error and all(values.get(p, {}).get('recent') for p in ('pm25', 'pm10'))
            rec.append('openaq', iteration, elapsed, status, not error, error, response, stamp, coverage)
        data, elapsed, status, error, response, stamp = rec.api('https://api.open-meteo.com/v1/forecast',
            {'latitude': 24.8607, 'longitude': 67.0011,
             'current': 'temperature_2m,relative_humidity_2m,wind_speed_10m',
             'timezone': 'Asia/Karachi', 'temperature_unit': 'celsius', 'wind_speed_unit': 'kmh'})
        weather = None
        if not error:
            try:
                weather = validate_weather(data)
            except (ValueError, KeyError, TypeError) as exc:
                error = str(exc)
        rec.append('open_meteo', iteration, elapsed, status, not error, error, response, stamp)
        if weather is not None:
            rec.local('heat_index', iteration, lambda: heat_index_c(
                weather['temperature_2m'], weather['relative_humidity_2m']))
        rec.local('kb_lookup', iteration, lambda: kb_lookup('heat pollution children outdoor', kb))
        print(f'Sample {iteration}/{samples} recorded')
    if station is None:
        print('OpenAQ samples PENDING: no recent PM2.5 station found. Other tools were measured.')
    summary()


def summarize(log=None):
    log = Path(log or ROOT/'tool_latency_raw.csv')
    by_tool, by_day = defaultdict(list), defaultdict(Counter)
    attempted = Counter()
    machines, runs, coverage = set(), defaultdict(set), Counter()
    validity = {}
    if log.parent == ROOT:
        for sidecar in (ROOT/'raw_responses').glob('*/sample_validity.jsonl'):
            for line in sidecar.read_text().splitlines():
                entry = json.loads(line)
                validity[(entry['run_id'], entry['tool'], str(entry['iteration']))] = entry
    if log.exists():
        with log.open(newline='') as f:
            for row in csv.DictReader(f):
                attempted[row['tool']] += 1
                machine = row.get('machine', '')
                if machine:
                    machines.add(machine); runs[row.get('run_id', '')].add(machine)
                detail = validity.get((row.get('run_id'), row['tool'], row.get('iteration')), row)
                timing_valid = str(detail.get('timing_valid') or row.get('valid')) == '1'
                if not timing_valid:
                    continue
                try:
                    value = float(row['elapsed_seconds'])
                except (ValueError, TypeError):
                    continue
                if not math.isfinite(value) or value < 0:
                    continue
                try:
                    day = parse_time(row['utc_time']).astimezone(KARACHI).date().isoformat() if row.get('utc_time') else row['karachi_date']
                    datetime.strptime(day, '%Y-%m-%d')
                except (ValueError, TypeError, KeyError):
                    continue
                by_tool[row['tool']].append(value)
                by_day[row['tool']][day] += 1
                met = detail.get('data_requirement_met')
                if met == '':met = None
                if row['tool'] == 'openaq':
                    coverage['timing_valid'] += 1
                    if met is None:
                        met = historical_air_coverage(row) if log.parent == ROOT else None
                    coverage['data_requirement_met' if str(met) in ('1', 'True') else ('data_requirement_not_met' if met is not None else 'not_verified')] += 1
    dates = set.intersection(*(set(by_day[t]) for t in TOOLS))
    # Twenty total per tool, spread across at least two dates per tool. Fifteen
    # per day is collection advice, never a completion gate.
    complete = all(len(by_tool[t]) >= 20 and len(by_day[t]) >= 2 for t in TOOLS)
    all_values = [v for t in TOOLS for v in by_tool[t]]
    api_values = by_tool['openaq'] + by_tool['open_meteo']
    missing = [f'{t}: {max(0,20-len(by_tool[t]))} more valid samples; {max(0,2-len(by_day[t]))} more Karachi dates'
               for t in TOOLS if len(by_tool[t]) < 20 or len(by_day[t]) < 2]
    return {'complete': complete, 'qualifying_karachi_dates': sorted(dates), 'missing': missing,
            'machines': sorted(machines), 'machine_mismatch': len(machines) > 1,
            'machines_by_run': {r: sorted(m) for r,m in runs.items()},
            'air_quality_coverage': dict(coverage),
            'per_tool': {t: {'successful': len(by_tool[t]), 'attempted': attempted[t],
                            'by_day': dict(by_day[t]),
                            'median_seconds': statistics.median(by_tool[t]) if by_tool[t] else None} for t in TOOLS},
            'pooled_median_seconds': statistics.median(all_values) if all_values else None,
            'api_only_median_seconds': statistics.median(api_values) if api_values else None}


def historical_air_coverage(row):
    """Audit saved readings at collection time, without altering original rows."""
    try:
        response = ROOT/row['response_file']
        if not response.exists():
            response = ROOT/'raw_responses'/Path(row['response_file']).name
        saved = json.loads(response.read_text())
        if saved['utc_time'] != row['utc_time']:
            return None  # Never silently match a different run's response.
        payload = json.loads(saved['body'])
        reports = [ROOT/'raw_responses'/row['run_id']/'coverage_report.json', ROOT/'data/coverage_latest.json']
        station = next(iter(rows_from(payload)), {}).get('locationsId')
        for report in reports:
            if not report.exists():continue
            candidates = json.loads(report.read_text()).get('candidates', [])
            for candidate in candidates:
                if candidate['id'] == station:
                    mapping = {int(k): v for k,v in candidate['sensor_map'].items()}
                    values = latest_values(payload, mapping, parse_time(row['utc_time']))
                    return all(values.get(p, {}).get('recent') for p in ('pm25', 'pm10'))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def summary():
    result = summarize()
    print(json.dumps(result, indent=2))
    if not result['complete']:
        print('PENDING: '+ '; '.join(result['missing']))
    else:
        print('DONE: >=20 valid timing samples/tool across >=2 Karachi dates/tool. No additional day required.')
    print('Machine field differs across runs:', result['machine_mismatch'])
    print('PM2.5 AND PM10 coverage is independent of timing completion:', result['air_quality_coverage'])
    print('Pooled median is observation-weighted, not the median of four medians. It is fragile:')
    print('two very fast local tools can place it between local and API measurements. Compare API-only median.')
    return result


def main():
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['discover', 'measure', 'summary', 'status'])
    parser.add_argument('--samples', type=int, default=15)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error('--samples must be positive')
    if args.command in ('summary', 'status'):
        summary()
    elif args.command == 'discover':
        discover(Recorder())
    else:
        measure(args.samples)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc))
