"""KBC analytics: calendar-date revenue and union-of-interval occupancy."""
import re
from datetime import datetime, time, timedelta
import pandas as pd

HOURS = list(range(12, 24)) + [0, 1, 2]

def number(series):
    def parse(v):
        if pd.isna(v): return 0.0
        if isinstance(v, (int, float)): return float(v)
        s = re.sub(r'[^\d,.\-]', '', str(v))
        if ',' in s and '.' in s: s = s.replace('.', '').replace(',', '.')
        elif re.fullmatch(r'-?\d{1,3}(?:[.,]\d{3})+', s): s = s.replace('.', '').replace(',', '')
        elif ',' in s: s = s.replace(',', '.')
        try: return float(s)
        except ValueError: return float('nan')
    return series.map(parse)

def dates(series):
    def parse(v):
        if pd.isna(v): return pd.NaT
        if isinstance(v, (int, float)): return pd.Timestamp('1899-12-30') + pd.Timedelta(days=v)
        try: return pd.Timestamp(v).normalize()
        except (ValueError, TypeError): return pd.NaT
    return pd.to_datetime(series.map(parse), errors='coerce').dt.normalize()

def clock(v):
    if pd.isna(v): return None
    if isinstance(v, time): return timedelta(hours=v.hour, minutes=v.minute, seconds=v.second)
    if isinstance(v, (datetime, pd.Timestamp)): return timedelta(hours=v.hour, minutes=v.minute, seconds=v.second)
    if isinstance(v, (float, int)): return timedelta(days=float(v) % 1)
    s = str(v).strip()
    for fmt in ['%I:%M:%S %p', '%I:%M %p', '%H:%M:%S', '%H:%M']:
        try:
            t = datetime.strptime(s, fmt)
            return timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
        except ValueError: pass
    return None

def prepare(raw, kind='table'):
    d = raw.copy(); d.columns = d.columns.astype(str).str.strip()
    required = ['Tanggal','Table Number','Tamu','Order','Mulai','Selesai','Total','Table','F&B'] if kind == 'table' else ['Tanggal','F&B','Modal','Qty','Sub total']
    missing = set(required) - set(d.columns)
    if missing: raise ValueError('Kolom tidak ditemukan: ' + ', '.join(sorted(missing)))
    original = len(d)
    d['Date'] = dates(d['Tanggal']); d = d.dropna(subset=['Date']).copy()
    money = ['Total','Table','F&B'] if kind == 'table' else ['Modal','Qty','Sub total']
    issues = {'Tanggal tidak valid': original-len(d)}
    for col in money:
        d[col] = number(d[col]); issues['Angka tidak valid: '+col] = int(d[col].isna().sum()); d[col] = d[col].fillna(0)
    if kind == 'table':
        d['Table Number'] = pd.to_numeric(d['Table Number'].astype(str).str.extract(r'(\d+)', expand=False), errors='coerce')
        for col in ['Tamu','Order']:
            d[col] = d[col].fillna('').astype(str).str.replace(r'\s+', ' ', regex=True).str.strip().str.upper()
        d['Order'] = d['Order'].replace('', 'TANPA ORDER')
        d['Start'] = pd.to_datetime([dt + clock(v) if clock(v) is not None else pd.NaT for dt,v in zip(d['Date'], d['Mulai'])])
        d['End'] = pd.to_datetime([dt + clock(v) if clock(v) is not None else pd.NaT for dt,v in zip(d['Date'], d['Selesai'])])
        cross = d['End'] < d['Start']; d.loc[cross,'End'] += pd.Timedelta(days=1)
        d['Jam'] = (d['End']-d['Start']).dt.total_seconds()/3600
        issues['Waktu tidak valid / durasi nol'] = int((d['Jam'].isna() | d['Jam'].le(0)).sum())
        issues['Nomor meja di luar 1–15'] = int((~d['Table Number'].between(1,15)).sum())
    else:
        d['F&B'] = d['F&B'].fillna('TANPA NAMA').astype(str).str.strip().str.upper()
        d['Revenue'] = d['Sub total']; d['Cost'] = d['Modal']*d['Qty']; d['Profit'] = d['Revenue']-d['Cost']
    return d, issues

def occupancy(sessions, start, end):
    """Intersect all sessions with calendar-hour windows; merge overlapping sessions per table."""
    rows = []
    valid = sessions[sessions['Table Number'].between(1,15) & sessions['End'].gt(sessions['Start'])]
    for day in pd.date_range(start,end):
        for hour in HOURS:
            a = day + pd.Timedelta(hours=hour); b = a+pd.Timedelta(hours=1)
            hit = valid[valid['Start'].lt(b) & valid['End'].gt(a)]
            for table in range(1,16):
                intervals = sorted((max(a,r.Start),min(b,r.End)) for r in hit[hit['Table Number'].eq(table)].itertuples())
                minutes=0.; left=right=None
                for x,y in intervals:
                    if left is None: left,right=x,y
                    elif x <= right: right=max(right,y)
                    else: minutes+=(right-left).total_seconds()/60; left,right=x,y
                if left is not None: minutes+=(right-left).total_seconds()/60
                rows.append({'Date':day,'Hour':f'{hour:02d}:00','Table Number':table,'Minutes':minutes})
    return pd.DataFrame(rows)

def performance(d, key):
    g=d.groupby(key).agg(Sesi=('Total','size'),Pendapatan=('Total','sum'),Jam=('Jam','sum')).reset_index()
    g['Rata-rata / sesi']=g['Pendapatan']/g['Sesi']
    g['Pendapatan / jam']=g['Pendapatan'].div(g['Jam'].where(g['Jam'].gt(0)))
    return g.sort_values('Pendapatan',ascending=False)

def daily(d,start,end,key=None):
    idx=pd.date_range(start,end)
    if key:
        if d.empty: return pd.DataFrame(columns=['Date',key,'Pendapatan','Sesi','Jam'])
        g=d.groupby(['Date',key]).agg(Pendapatan=('Total','sum'),Sesi=('Total','size'),Jam=('Jam','sum'))
        return g.reindex(pd.MultiIndex.from_product([idx,sorted(d[key].unique())],names=['Date',key]),fill_value=0).reset_index()
    return d.groupby('Date').agg(Pendapatan=('Total','sum'),Sesi=('Total','size'),Jam=('Jam','sum')).reindex(idx,fill_value=0).rename_axis('Date').reset_index()
