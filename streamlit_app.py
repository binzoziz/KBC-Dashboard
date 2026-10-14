import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo
from analytics import prepare, occupancy, performance, daily, HOURS

st.set_page_config(page_title='KBC Business Dashboard',page_icon='🎱',layout='wide')
@st.cache_data(ttl=60,show_spinner=False)
def load_data():
    sheet_url='https://docs.google.com/spreadsheets/d/e/2PACX-1vQ28wjkKC-KhZ30fEb5TWzPwTRvgYdGu5vPBfplbcdTBDoEe7XQueCTo_XrSyhMf7h-uQk37gKmDrpd/pub?output=xlsx'
    return pd.read_excel(sheet_url)
@st.cache_data(ttl=60,show_spinner=False)
def load_data_fnb():
    sheet_url_fnb='https://docs.google.com/spreadsheets/d/e/2PACX-1vTRVluG1urQGwOhAvDmtjZCJtKwZCc4SMBC_l3uDWldvOTDmHL5dSU7wH-bsC28EQ/pub?output=xlsx'
    return pd.read_excel(sheet_url_fnb,sheet_name='Master Data')
@st.cache_data(show_spinner=False)
def cached_occupancy(d,start,end): return occupancy(d,start,end)
def rp(v): return 'Rp '+f'{v:,.0f}'.replace(',','.')
def chart(fig):
    fig.update_layout(template='plotly_white',margin=dict(l=15,r=15,t=45,b=20),font=dict(family='Arial'),legend_title_text='',colorway=['#16a34a','#2563eb','#f59e0b','#8b5cf6','#ef4444'])
    st.plotly_chart(fig,width='stretch')
def grid(d): st.dataframe(d,width='stretch',hide_index=True)
def metrics(items):
    for col,(label,value) in zip(st.columns(len(items)),items): col.metric(label,value)
def download(d,name): st.download_button('Unduh CSV',d.to_csv(index=False).encode('utf-8-sig'),name,'text/csv',key=name)

st.markdown('''<style>.block-container{padding-top:1.5rem;max-width:1500px}[data-testid="stMetric"]{border:1px solid rgba(148,163,184,.3);border-radius:14px;padding:14px;background:rgba(22,163,74,.04)}h1{letter-spacing:-1px}</style>''',unsafe_allow_html=True)
st.title('🎱 KBC Business Dashboard')
st.caption('15 meja · 12.00–03.00 WIB · Pendapatan berdasarkan tanggal kalender')
if st.sidebar.button('↻ Refresh Data',width='stretch'):
    load_data.clear();load_data_fnb.clear();st.rerun()
try:
    with st.spinner('Mengambil data Google Sheets…'):
        raw=load_data(); d,health=prepare(raw)
        try:
            raw_f=load_data_fnb(); f,fh=prepare(raw_f,'fnb'); f_error=None
        except Exception as e:
            f=pd.DataFrame(columns=['Date','F&B','Revenue','Cost','Profit','Qty']); fh={}; f_error=str(e)
except Exception as e:
    st.error('Data transaksi belum dapat dibaca. Periksa akses publish Google Sheets dan nama kolom.');st.caption(str(e));st.stop()
if d.empty: st.info('Belum ada transaksi dengan tanggal valid.');st.stop()
st.sidebar.header('Filter periode')
include_test=st.sidebar.checkbox('Sertakan Order TEST',value=False)
base=d if include_test else d[~d['Order'].str.contains(r'\bTEST\b',regex=True)].copy()
if base.empty: st.info('Tidak ada transaksi setelah filter TEST.');st.stop()
lo,hi=base['Date'].min(),base['Date'].max()
preset=st.sidebar.selectbox('Periode',['Tanggal terakhir','7 hari terakhir','Bulan data terakhir','Bulan sebelumnya','Semua data','Custom'],index=1)
start,end=hi,hi
if preset=='7 hari terakhir':start=max(lo,hi-pd.Timedelta(days=6))
if preset=='Bulan data terakhir':start=max(lo,hi.replace(day=1))
if preset=='Bulan sebelumnya':
    end=hi.replace(day=1)-pd.Timedelta(days=1);start=max(lo,end.replace(day=1))
    if end<lo:st.info('Data bulan sebelumnya belum tersedia.');st.stop()
if preset=='Semua data':start=lo
if preset=='Custom':
    start=pd.Timestamp(st.sidebar.date_input('Mulai',lo.date(),min_value=lo.date(),max_value=hi.date()))
    end=pd.Timestamp(st.sidebar.date_input('Sampai',hi.date(),min_value=lo.date(),max_value=hi.date()))
if start>end:st.sidebar.error('Tanggal mulai melebihi tanggal akhir.');st.stop()
st.sidebar.caption('Cache sumber data: 60 detik. Refresh untuk mengambil ulang. Tanggal terakhir adalah tanggal data, bukan hari ini.')
st.caption(f"Periode: {start:%d %b %Y} – {end:%d %b %Y} · Waktu buka dashboard: {datetime.now(ZoneInfo('Asia/Jakarta')):%d %b %Y %H:%M} WIB")
if f_error:st.warning('Analisis F&B belum tersedia: '+f_error)
s=base[base['Date'].between(start,end)].copy(); fs=f[f['Date'].between(start,end)].copy()
# Keep sessions beginning before the selected date: calendar occupancy must include their spillover.
occ_sessions=base[base['Start'].lt(end+pd.Timedelta(days=1)) & base['End'].gt(start)][['Start','End','Table Number']]
with st.spinner('Menghitung pemakaian meja…'):occ=cached_occupancy(occ_sessions,start,end)
ndays=(end-start).days+1
trend=daily(s,start,end)
tabs=st.tabs(['Ringkasan','Meja & Jam Ramai','Order / Paket','Member / Tamu','F&B & Barang','Detail Data'])
with tabs[0]:
    revenue=s['Total'].sum()
    metrics([('Total pendapatan',rp(revenue)),('Jumlah sesi',f'{len(s):,}'),('Rata-rata / sesi',rp(revenue/len(s) if len(s) else 0)),('Occupancy',f"{occ['Minutes'].sum()/(ndays*15*15*60)*100:.1f}%")])
    prev_start=start-pd.Timedelta(days=ndays);prev_end=start-pd.Timedelta(days=1)
    if prev_start>=lo:
        prev=base.loc[base['Date'].between(prev_start,prev_end),'Total'].sum()
        st.metric('Pendapatan vs periode sebelumnya',rp(revenue),f'{(revenue/prev-1)*100:+.1f}%' if prev>0 else None)
        st.caption(f'Pembanding: {prev_start:%d %b %Y}–{prev_end:%d %b %Y}. Kelengkapan data tetap perlu diperiksa.')
    left,right=st.columns([2,1])
    with left:
        grain=st.selectbox('Tren pendapatan',['Harian','Mingguan','Bulanan'])
        t=trend.set_index('Date')
        if grain!='Harian':t=t.resample('W-MON' if grain=='Mingguan' else 'MS',label='left',closed='left').sum()
        chart(px.line(t.reset_index(),x='Date',y='Pendapatan',markers=True,title='Perkembangan pendapatan'))
    with right:
        metrics([('Rata-rata / hari',rp(revenue/ndays))])
        metrics([('Penjualan F&B & barang',rp(fs['Revenue'].sum()))])
        metrics([('Laba kotor produk',rp(fs['Profit'].sum()))])
        st.caption('Penjualan produk dari sheet F&B tidak ditambahkan lagi ke Total transaksi.')
    st.subheader('Ringkasan harian');grid(trend)
with tabs[1]:
    st.caption('Occupancy = menit terpakai ÷ menit tersedia. Interval bertumpuk pada meja yang sama dihitung sekali. Jam di luar operasional tidak masuk occupancy.')
    choice=st.selectbox('Warna peta meja',['Total pendapatan','Jam terpakai','Occupancy %'])
    p=performance(s,'Table Number').set_index('Table Number').reindex(range(1,16)).fillna(0).reset_index()
    actual=occ.groupby('Table Number')['Minutes'].sum().reindex(range(1,16),fill_value=0)
    p['Jam terpakai']=actual.values/60;p['Occupancy %']=actual.values/(ndays*15*60)*100
    key={'Total pendapatan':'Pendapatan','Jam terpakai':'Jam terpakai','Occupancy %':'Occupancy %'}[choice]
    values=p[key].to_numpy().reshape(3,5)
    texts=[[(f'Meja {r*5+c+1}<br>'+ (rp(values[r,c]) if key=='Pendapatan' else f'{values[r,c]:.1f}')) for c in range(5)] for r in range(3)]
    fig=go.Figure(go.Heatmap(z=values,text=texts,texttemplate='%{text}',colorscale='Greens',xgap=8,ygap=8,hovertemplate='%{text}<extra></extra>'))
    fig.update_layout(height=380,xaxis=dict(showticklabels=False),yaxis=dict(showticklabels=False,autorange='reversed'));chart(fig)
    a,b=st.columns(2)
    with a:
        h=occ.groupby('Hour')['Minutes'].sum().reindex([f'{x:02}:00' for x in HOURS]).reset_index();h['Occupancy %']=h['Minutes']/(ndays*15*60)*100
        chart(px.bar(h,x='Hour',y='Occupancy %',title='Rata-rata occupancy per jam',range_y=[0,100]))
    with b:
        pivot=occ.groupby(['Date','Hour'])['Minutes'].sum().div(15*60).mul(100).unstack().reindex(columns=[f'{x:02}:00' for x in HOURS])
        fig=go.Figure(go.Heatmap(z=pivot.values,x=pivot.columns,y=pivot.index.strftime('%d %b %Y'),zmin=0,zmax=100,colorscale='Greens',hovertemplate='%{y} · %{x}<br>%{z:.1f}%<extra></extra>'));fig.update_layout(title='Occupancy tanggal × jam',height=400);chart(fig)
    grid(p.sort_values('Pendapatan',ascending=False));st.caption('Pendapatan meja memakai Total termasuk F&B pada transaksi. Jam pada kolom Jam adalah durasi sesi penuh; Jam terpakai adalah pemakaian dalam periode dan jam buka.')
with tabs[2]:
    st.subheader('Perkembangan harian setiap Order')
    names=sorted(s['Order'].unique());selected=st.multiselect('Order yang dibandingkan',names,default=names[:min(4,len(names))])
    metric=st.selectbox('Metrik Order',['Pendapatan','Sesi','Jam'])
    ot=daily(s,start,end,'Order');ot=ot[ot['Order'].isin(selected)]
    if len(ot):chart(px.line(ot,x='Date',y=metric,color='Order',markers=True,title=f'{metric} per hari'))
    else:st.info('Pilih Order untuk melihat tren.')
    p=performance(s,'Order');grid(p);download(p,'order_performance.csv')
    st.caption('Pendapatan memakai Total transaksi. Pendapatan/jam juga dapat mencakup F&B. Paket dibandingkan dengan mempertimbangkan hari ketersediaan; grafik tidak membuktikan pengaruh promo secara langsung.')
with tabs[3]:
    st.caption('Identitas berdasarkan nama Tamu yang dinormalisasi. Nama sama digabung; status member tidak dapat dipastikan tanpa daftar member. Kunjungan = jumlah tanggal berbeda.')
    known=base[~base['Tamu'].isin(['','-','NAN','NONE','NULL','GUEST','TAMU','WALK IN','WALK-IN'])]
    guests=known[known['Date'].between(start,end)]
    first=known.groupby('Tamu')['Date'].min()
    gp=guests.groupby('Tamu').agg(Kunjungan=('Date','nunique'),Sesi=('Total','size'),Pendapatan=('Total','sum'),Terakhir=('Date','max')).reset_index()
    gp['Pertama tercatat']=gp['Tamu'].map(first);gp['Jenis']=gp['Pertama tercatat'].ge(start).map({True:'Baru dalam data',False:'Kembali'})
    metrics([('Tamu teridentifikasi',str(len(gp))),('Baru dalam data',str(gp['Jenis'].eq('Baru dalam data').sum())),('Tamu kembali',str(gp['Jenis'].eq('Kembali').sum())),('Cakupan nama',f'{len(guests)/len(s)*100:.1f}%' if len(s) else '0%')])
    query=st.text_input('Cari nama Tamu')
    grid(gp[gp['Tamu'].str.contains(query.upper(),regex=False)].sort_values('Pendapatan',ascending=False))
    if len(gp):
        name=st.selectbox('Riwayat pelanggan',sorted(gp['Tamu']))
        chart(px.bar(daily(guests[guests['Tamu'].eq(name)],start,end),x='Date',y='Pendapatan',title='Pendapatan pelanggan per hari'))
        grid(known[known['Tamu'].eq(name)][['Date','Order','Table Number','Total']].sort_values('Date',ascending=False))
    download(gp,'tamu_performance.csv')
with tabs[4]:
    metrics([('Penjualan produk',rp(fs['Revenue'].sum())),('Modal produk',rp(fs['Cost'].sum())),('Laba kotor',rp(fs['Profit'].sum())),('Margin',f"{fs['Profit'].sum()/fs['Revenue'].sum()*100:.1f}%" if fs['Revenue'].sum()>0 else '—')])
    if fs.empty:st.info('Tidak ada data produk pada periode ini.')
    else:
        fp=fs.groupby('F&B').agg(Qty=('Qty','sum'),Revenue=('Revenue','sum'),Cost=('Cost','sum'),Profit=('Profit','sum')).reset_index();fp['Margin %']=fp['Profit'].div(fp['Revenue'].where(fp['Revenue'].gt(0)))*100
        a,b=st.columns(2)
        with a:chart(px.bar(fp.nlargest(15,'Revenue').sort_values('Revenue'),x='Revenue',y='F&B',orientation='h',title='15 produk dengan penjualan tertinggi'))
        with b:
            positive=fp[fp['Revenue'].gt(0)&fp['Qty'].ge(0)]
            if len(positive):
                fig=px.scatter(positive,x='Margin %',y='Qty',size='Revenue',hover_name='F&B',color='Margin %',color_continuous_scale='RdYlGn',title='Popularitas × margin produk')
                fig.add_vline(x=positive['Margin %'].median(),line_dash='dash');fig.add_hline(y=positive['Qty'].median(),line_dash='dash');chart(fig)
        grid(fp.sort_values('Revenue',ascending=False));download(fp,'fnb_performance.csv')
        chosen=st.multiselect('Tren produk',sorted(fp['F&B']),default=fp.nlargest(3,'Revenue')['F&B'].tolist())
        ft=fs[fs['F&B'].isin(chosen)].groupby(['Date','F&B'])['Revenue'].sum()
        if chosen:
            ft=ft.reindex(pd.MultiIndex.from_product([pd.date_range(start,end),chosen],names=['Date','F&B']),fill_value=0).reset_index()
            chart(px.line(ft,x='Date',y='Revenue',color='F&B',markers=True,title='Penjualan produk harian'))
        st.caption('Seluruh item sheet F&B ditampilkan, termasuk membership dan aksesori. Laba kotor belum dikurangi biaya operasional.')
with tabs[5]:
    query=st.text_input('Cari Tamu atau Order',key='detail_search')
    detail=s[s['Tamu'].str.contains(query.upper(),regex=False)|s['Order'].str.contains(query.upper(),regex=False)]
    cols=['Date','Table Number','Tamu','Order','Mulai','Selesai','Table','F&B','Total','Jam']
    grid(detail[cols].sort_values('Date',ascending=False));download(detail[cols],'transaksi_kbc.csv')
    with st.expander('Kualitas data & definisi metrik'):
        grid(pd.DataFrame([{'Sumber':'Table','Pemeriksaan':k,'Baris':v} for k,v in health.items()]+[{'Sumber':'F&B','Pemeriksaan':k,'Baris':v} for k,v in fh.items()]))
        st.write('Tanggal teks mengikuti format bulan/hari/tahun seperti contoh 12/03/2025 = 3 Desember 2025. Kolom tanggal Excel asli dibaca langsung. Satu baris transaksi dihitung satu sesi; tanpa nomor invoice, jumlah invoice unik tidak dapat dipastikan. Data tanggal kosong tidak masuk analisis. Nol pada tren dapat berarti tidak ada transaksi atau data belum dimasukkan.')
