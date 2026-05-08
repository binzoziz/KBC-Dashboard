import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import plotly.graph_objects as go

# Konfigurasi Halaman
st.set_page_config(
    page_title="KBC Revenue Dashboard",
    layout="wide"
)

@st.cache_data(ttl=60, show_spinner=False)
def load_data():
    sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ28wjkKC-KhZ30fEb5TWzPwTRvgYdGu5vPBfplbcdTBDoEe7XQueCTo_XrSyhMf7h-uQk37gKmDrpd/pub?output=xlsx"
    return pd.read_excel(sheet_url)

@st.cache_data(ttl=60, show_spinner=False)
def load_data_fnb():
    sheet_url_fnb = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTRVluG1urQGwOhAvDmtjZCJtKwZCc4SMBC_l3uDWldvOTDmHL5dSU7wH-bsC28EQ/pub?output=xlsx"
    return pd.read_excel(sheet_url_fnb, sheet_name="Master Data")

with st.spinner("Fetching Data From Google Sheets..."):
    raw_data = load_data()
    raw_fnb = load_data_fnb()
    
# Load Data Mentah
raw_data = load_data()
raw_fnb = load_data_fnb()

# ==============================
# PRE-PROCESSING
# ==============================
df_all = raw_data.copy()
df_all["Tanggal"] = pd.to_datetime(df_all["Tanggal"], errors="coerce")
df_all = df_all.dropna(subset=["Tanggal"])
df_all["Date"] = df_all["Tanggal"].dt.date
df_all["Table"] = pd.to_numeric(df_all["Table"], errors="coerce").fillna(0)
df_all["F&B"] = pd.to_numeric(df_all["F&B"], errors="coerce").fillna(0)
df_all["Total"] = pd.to_numeric(df_all["Total"], errors="coerce").fillna(0)
df_all["Table Number"] = df_all["Table Number"].astype(str).str.extract("(\d+)").fillna(0).astype(int)

fnb_all = raw_fnb.copy()
fnb_all["Tanggal"] = pd.to_datetime(fnb_all["Tanggal"], errors="coerce")
fnb_all["Date"] = fnb_all["Tanggal"].dt.date
fnb_all["Revenue"] = pd.to_numeric(fnb_all["Sub total"], errors="coerce").fillna(0)
fnb_all["Cost"] = pd.to_numeric(fnb_all["Modal"], errors="coerce").fillna(0) * fnb_all["Qty"]
fnb_all["Profit"] = fnb_all["Revenue"] - fnb_all["Cost"]

# ==============================
# FILTER TANGGAL
# ==============================
st.title("KBC Revenue Dashboard")

min_date_val = df_all["Date"].min()
max_date_val = df_all["Date"].max()

date_range = st.date_input(
    "📅 Choose Date Range",
    value=(min_date_val, max_date_val),
    min_value=min_date_val,
    max_value=max_date_val
)

if len(date_range) != 2:
    st.info("Choose Date Period")
    st.stop()

start_date, end_date = date_range
df = df_all[(df_all["Date"] >= start_date) & (df_all["Date"] <= end_date)].copy()
fnb_filtered = fnb_all[(fnb_all["Date"] >= start_date) & (fnb_all["Date"] <= end_date)].copy()

# Persiapan data waktu untuk Occupancy
df["Mulai_dt"] = pd.to_datetime(df["Date"].astype(str) + " " + df["Mulai"].astype(str), errors='coerce')
df["Selesai_dt"] = pd.to_datetime(df["Date"].astype(str) + " " + df["Selesai"].astype(str), errors='coerce')
df.loc[df["Selesai_dt"] < df["Mulai_dt"], "Selesai_dt"] += pd.Timedelta(days=1)

# ==============================
# METRICS DISPLAY
# ==============================
latest_date = df["Date"].max()
daily_df = df[df["Date"] == latest_date]

st.subheader(f"Daily Statistic ({latest_date})")
c1, c2, c3 = st.columns(3)
c1.metric("Daily Total Revenue", f"Rp {daily_df['Total'].sum():,.0f}")
c2.metric("Daily Table Rev", f"Rp {daily_df['Table'].sum():,.0f}")
c3.metric("Daily F&B Rev", f"Rp {daily_df['F&B'].sum():,.0f}")

st.divider()

st.subheader(f"Chosen Period Statistic ({start_date} - {end_date})")
c4, c5, c6 = st.columns(3)
c4.metric("Period Total Revenue", f"Rp {df['Total'].sum():,.0f}")
c5.metric("Period Table Rev", f"Rp {df['Table'].sum():,.0f}")
c6.metric("Period F&B Rev", f"Rp {df['F&B'].sum():,.0f}")

st.divider()

# ==============================
# HEATMAP TABLE
# ==============================
st.subheader("Table Revenue Heatmap")
view_mode_heat = st.radio("Heatmap View", ["Daily", "Date Period"], horizontal=True, key="heat_mode")

heat_source = daily_df if view_mode_heat == "Daily" else df
total_rev = heat_source["Total"].sum()

table_heat = heat_source.groupby("Table Number")["Total"].sum().reset_index()
all_tables = pd.DataFrame({"Table Number": range(1, 16)})
table_heat = all_tables.merge(table_heat, on="Table Number", how="left").fillna(0)

z_vals = table_heat["Total"].values.reshape(3, 5)
txt_vals = []
for i in range(3):
    row = []
    for j in range(5):
        idx = i*5 + j
        row_data = table_heat.iloc[idx]
        val = row_data['Total']
        pct = (val / total_rev * 100) if total_rev > 0 else 0
        row.append(f"Table {int(row_data['Table Number'])}<br>Rp {val:,.0f}<br><b>({pct:.1f}%)</b>")
    txt_vals.append(row)

fig_heat = go.Figure(data=go.Heatmap(
    z=z_vals, text=txt_vals, texttemplate="%{text}",
    colorscale="Greens", xgap=5, ygap=5, hovertemplate="%{text}<extra></extra>"
))
fig_heat.update_layout(height=450, xaxis=dict(showticklabels=False), yaxis=dict(showticklabels=False, autorange="reversed"))
st.plotly_chart(fig_heat, use_container_width=True)

# ==============================
# HOURLY OCCUPANCY (DENGAN FILTER)
# ==============================
st.subheader("Hourly Table Occupancy")
view_mode_occ = st.radio("Mode Tampilan Occupancy", ["Daily", "Date Period"], horizontal=True, key="occ_mode")

occ_source = daily_df if view_mode_occ == "Daily" else df
unique_dates = occ_source["Date"].unique()
hours = list(range(12, 24)) + list(range(0, 3))
hourly_list = []

for h in hours:
    daily_counts = []
    for d in unique_dates:
        h_start = pd.Timestamp(f"{d} {h:02d}:00:00")
        h_end = h_start + pd.Timedelta(hours=1)
        # Filter session yang overlap dengan jam ini
        active = occ_source[(occ_source["Date"] == d) & 
                            (occ_source["Mulai_dt"] < h_end) & 
                            (occ_source["Selesai_dt"] > h_start)]["Table Number"].nunique()
        daily_counts.append(active)
    
    avg_active = np.mean(daily_counts) if daily_counts else 0
    pct = (avg_active/15)*100
    label_text = f"{pct:.1f}% ({avg_active:.1f}/15)"
    hourly_list.append({"Hour": f"{h:02d}:00", "Pct": pct, "Label": label_text})

hourly_df = pd.DataFrame(hourly_list)
fig_hour = px.bar(hourly_df, y="Hour", x="Pct", orientation='h', text="Label",
                 color="Pct", color_continuous_scale="Blues", range_x=[0, 115])
fig_hour.update_traces(textposition='outside')
fig_hour.update_layout(yaxis=dict(autorange="reversed"), height=600)
st.plotly_chart(fig_hour, use_container_width=True)

# ==============================
# F&B QUADRANT
# ==============================
st.subheader("F&B Quadrant")
if not fnb_filtered.empty:
    fnb_menu = fnb_filtered.groupby("F&B").agg({"Revenue":"sum", "Profit":"sum", "Qty":"sum"}).reset_index()
    fnb_menu["Margin %"] = (fnb_menu["Profit"] / fnb_menu["Revenue"]) * 100
    
    fig_quad = px.scatter(
        fnb_menu, x="Margin %", y="Qty", text="F&B", size="Revenue",
        color="Margin %", color_continuous_scale="RdYlGn",
        title=f"Analisis Menu: {start_date} - {end_date}"
    )
    fig_quad.add_vline(x=fnb_menu["Margin %"].mean(), line_dash="dash", line_color="gray")
    fig_quad.add_hline(y=fnb_menu["Qty"].mean(), line_dash="dash", line_color="gray")
    fig_quad.update_traces(textposition='top center')
    st.plotly_chart(fig_quad, use_container_width=True)

# ==============================
# TREND ANALYSIS (STRICT NORMALIZATION)
# ==============================
st.divider()
st.subheader("📈 Revenue Growth Trend")

c_trend1, c_trend2, c_trend3 = st.columns([1, 1, 1])
with c_trend1:
    trend_metric = st.selectbox("Select Metric", ["Total", "Table", "F&B"], key="tm_select")
with c_trend2:
    time_grain = st.radio("Breakdown by", ["Weekly", "Monthly"], horizontal=True, key="tg_radio")

# 1. Persiapan Data Mentah
df_trend = df.copy()
# Pastikan benar-benar format datetime dan hilangkan jam/menit/detik (normalize)
df_trend['Tanggal_Clean'] = pd.to_datetime(df_trend['Date']).dt.normalize()

if time_grain == "Monthly":
    # Tarik ke tanggal 1 tiap bulan
    df_trend['Period_Date'] = df_trend['Tanggal_Clean'].dt.to_period('M').dt.to_timestamp()
else:
    # PAKSA: Setiap tanggal dikurangi jumlah hari sejak hari Senin terakhir
    # Ini cara paling manual dan akurat untuk memastikan semua lari ke hari Senin
    df_trend['Period_Date'] = df_trend['Tanggal_Clean'] - pd.to_timedelta(df_trend['Tanggal_Clean'].dt.dayofweek, unit='D')

# 2. Agregasi
trend_data = df_trend.groupby('Period_Date')[trend_metric].sum().reset_index()

# 3. Handle Start Date 01 Dec 2025 (Jika belum ada atau ingin dipastikan ada)
start_target = pd.Timestamp("2025-12-01").normalize()
if start_target not in trend_data['Period_Date'].values:
    new_row = pd.DataFrame({'Period_Date': [start_target], trend_metric: [0]})
    trend_data = pd.concat([new_row, trend_data], ignore_index=True)

# 4. Sorting & Labeling
trend_data = trend_data.sort_values('Period_Date').reset_index(drop=True)
if time_grain == "Monthly":
    trend_data['Period_Label'] = trend_data['Period_Date'].dt.strftime('%b %Y')
else:
    trend_data['Period_Label'] = trend_data['Period_Date'].dt.strftime('%d %b %Y')

# 5. Filter Zoom-in Bulan
with c_trend3:
    if time_grain == "Weekly":
        month_list = trend_data['Period_Date'].dt.strftime('%B %Y').unique().tolist()
        month_options = ["All Time"] + month_list
        selected_month = st.selectbox("Filter by Month (Weekly)", month_options)
        
        if selected_month != "All Time":
            trend_data = trend_data[trend_data['Period_Date'].dt.strftime('%B %Y') == selected_month]

# 6. Plotting
fig_trend = px.line(
    trend_data, 
    x='Period_Label', 
    y=trend_metric,
    markers=True,
    text=[f"Rp {v:,.0f}" for v in trend_data[trend_metric]],
    title=f"Movement of {trend_metric} ({time_grain})"
)

fig_trend.update_traces(textposition="top center", line_width=3, line_color="#1f77b4")
fig_trend.update_layout(
    xaxis_title="Week Starting (Monday)",
    yaxis_title="Revenue (Rp)",
    height=500,
    xaxis={'type': 'category'} # Memaksa Plotly tidak membuat skala waktu sendiri
)

st.plotly_chart(fig_trend, use_container_width=True)