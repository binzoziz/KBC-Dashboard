import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import plotly.graph_objects as go

st.cache_data(ttl=60)
st.set_page_config(
    page_title="Outlet Dashboard",
    layout="wide"
)

st.title("KBC Revenue Dashboard")

# ==============================
# LOAD DATA
# ==============================

def load_data():
    sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ28wjkKC-KhZ30fEb5TWzPwTRvgYdGu5vPBfplbcdTBDoEe7XQueCTo_XrSyhMf7h-uQk37gKmDrpd/pub?output=xlsx"
    return pd.read_excel(sheet_url)

def load_data_fnb():
    sheet_url_fnb = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTRVluG1urQGwOhAvDmtjZCJtKwZCc4SMBC_l3uDWldvOTDmHL5dSU7wH-bsC28EQ/pub?output=xlsx"
    return pd.read_excel(sheet_url_fnb, sheet_name="Master Data")

data = load_data()
fnb = load_data_fnb()

data["Table"] = pd.to_numeric(data["Table"], errors="coerce").fillna(0)
data["F&B"] = pd.to_numeric(data["F&B"], errors="coerce").fillna(0)
data["Total"] = pd.to_numeric(data["Total"], errors="coerce").fillna(0)

# ==============================
# CLEANING
# ==============================

df = data[[
    "Tanggal",
    "Table Number",
    "Mulai",
    "Selesai",
    "Order",
    "Table",
    "F&B",
    "Total"
]].copy()

# ==============================
# CLEANING TANGGAL SUPER AMAN
# ==============================

df["Tanggal"] = pd.to_datetime(df["Tanggal"], errors="coerce")
# Sekarang baru buat Date
df["Date"] = df["Tanggal"].dt.date

# ======================
# CLEANING DATA FNB
# ======================

fnb["Tanggal"] = pd.to_datetime(fnb["Tanggal"], errors="coerce")
fnb["Tanggal"] = fnb["Tanggal"].dt.date

fnb["Revenue"] = fnb["Sub total"]
fnb["Cost"] = fnb["Modal"] * fnb["Qty"]

fnb["Profit"] = fnb["Revenue"] - fnb["Cost"]

# ==============================
# FILTER BULAN
# ==============================

df["Month"] = df["Tanggal"].dt.month
df["Year"] = df["Tanggal"].dt.year

available_months = (
    df[["Month","Year"]]
    .drop_duplicates()
    .sort_values(["Year","Month"])
)

month_map = {
    1:"Januari",2:"Februari",3:"Maret",4:"April",
    5:"Mei",6:"Juni",7:"Juli",8:"Agustus",
    9:"September",10:"Oktober",11:"November",12:"Desember"
}

available_months["Label"] = available_months.apply(
    lambda x: f"{month_map[x['Month']]} {x['Year']}", axis=1
)

selected_month = st.selectbox(
    "Pilih Bulan",
    available_months["Label"],
    index=len(available_months) - 1
)

selected_row = available_months[
    available_months["Label"] == selected_month
].iloc[0]

selected_month_num = selected_row["Month"]
selected_year = selected_row["Year"]

df = df[
    (df["Month"] == selected_month_num) &
    (df["Year"] == selected_year)
]

# ==============================
# FILTER TANGGAL
# ==============================

min_date = df["Date"].min()
max_date = df["Date"].max()

date_range = st.date_input(
    "Pilih Range Tanggal",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

if len(date_range) != 2:
    st.info("Pilih tanggal awal dan akhir. Jika ingin melihat data 1 hari, klik tanggal yang sama dua kali.")
    st.stop()

start_date, end_date = date_range

df = df[
    (df["Date"] >= start_date) &
    (df["Date"] <= end_date)
]

fnb_filtered = fnb[
    (fnb["Tanggal"] >= start_date) &
    (fnb["Tanggal"] <= end_date)
]

daily_fnb = fnb_filtered.groupby("Tanggal").agg({
    "Revenue":"sum",
    "Profit":"sum",
    "Qty":"sum"
}).reset_index()

daily_fnb = fnb_filtered.groupby("Tanggal").agg({
    "Revenue":"sum",
    "Profit":"sum",
    "Qty":"sum"
}).reset_index()

# ==============================
# DAILY METRICS (CLEAN VERSION)
# ==============================

latest_date = df["Date"].max()
daily_df = df[df["Date"] == latest_date]

st.info(f"Dashboard menggunakan data sampai tanggal {latest_date}")

daily_table = daily_df["Table"].sum()
daily_fnb = daily_df["F&B"].sum()
daily_total = daily_df["Total"].sum()

if daily_total != 0:
    table_pct = daily_table / daily_total * 100
    fnb_pct = daily_fnb / daily_total * 100
else:
    table_pct = 0
    fnb_pct = 0

# ==============================
# MTD METRICS
# ==============================

latest_date = df["Date"].max()

mtd_df = df[
    (df["Tanggal"].dt.month == latest_date.month) &
    (df["Tanggal"].dt.year == latest_date.year)
]

mtd_table = mtd_df["Table"].sum()
mtd_fnb = mtd_df["F&B"].sum()
mtd_total = mtd_df["Total"].sum()

# Hitung persentase
if mtd_total != 0:
    mtd_table_pct = mtd_table / mtd_total * 100
    mtd_fnb_pct = mtd_fnb / mtd_total * 100
else:
    mtd_table_pct = 0
    mtd_fnb_pct = 0

fnb_menu = fnb_filtered.groupby("F&B").agg({
    "Revenue":"sum",
    "Profit":"sum",
    "Qty":"sum"
}).reset_index()

x_mid = fnb_menu["Qty"].mean()
y_mid = fnb_menu["Profit"].mean()

# ==============================
# TOP METRICS DISPLAY
# ==============================

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        "Daily Total Revenue",
        f"Rp {daily_total:,.0f}"
    )

with col2:
    st.metric(
        "Table Revenue",
        f"Rp {daily_table:,.0f}",
        f"{table_pct:.1f}%"
    )

with col3:
    st.metric(
        "F&B Revenue",
        f"Rp {daily_fnb:,.0f}",
        f"{fnb_pct:.1f}%"
    )

st.divider()

st.subheader("Month To Date (MTD)")

col4, col5, col6 = st.columns(3)

with col4:
    st.metric(
        "MTD Total Revenue",
        f"Rp {mtd_total:,.0f}"
    )

with col5:
    st.metric(
        "MTD Table Revenue",
        f"Rp {mtd_table:,.0f}",
        f"{mtd_table_pct:.1f}%"
    )

with col6:
    st.metric(
        "MTD F&B Revenue",
        f"Rp {mtd_fnb:,.0f}",
        f"{mtd_fnb_pct:.1f}%"
    )

# ==============================
# CLEAN DATA
# ==============================

df.columns = df.columns.str.strip()

df["Tanggal"] = pd.to_datetime(df["Tanggal"], errors="coerce")
df = df.dropna(subset=["Tanggal"])

df["Date"] = df["Tanggal"].dt.date

df["Table Number"] = (
    df["Table Number"]
    .astype(str)
    .str.extract("(\d+)")
    .astype(int)
)

df["Total"] = (
    df["Total"]
    .astype(str)
    .str.replace(",", "", regex=False)
)

df["Total"] = pd.to_numeric(df["Total"], errors="coerce").fillna(0)

# ==============================
# CREATE DATETIME SESSION
# ==============================

df["Mulai_dt"] = pd.to_datetime(
    df["Tanggal"].astype(str) + " " + df["Mulai"].astype(str),
    errors="coerce"
)

df["Selesai_dt"] = pd.to_datetime(
    df["Tanggal"].astype(str) + " " + df["Selesai"].astype(str),
    errors="coerce"
)

# Handle lewat tengah malam
df.loc[df["Selesai_dt"] < df["Mulai_dt"], "Selesai_dt"] += pd.Timedelta(days=1)

# ==============================
# FILTER DATA BY DASHBOARD DATE
# ==============================

df_filtered = df[
    (df["Date"] >= start_date) &
    (df["Date"] <= end_date)
]

latest_date = df_filtered["Date"].max()
num_days = (end_date - start_date).days + 1

# ==============================
# HEATMAP TABLE
# ==============================

view_mode = st.radio(
    "Heatmap View Mode",
    ["Daily","MTD"],
    horizontal=True
)

df_daily = df_filtered[df_filtered["Date"] == latest_date]
df_mtd = df_filtered

latest_date = df_filtered["Date"].max()

if view_mode == "Daily":

    filtered_df = df_filtered[df_filtered["Date"] == latest_date]

else:  # MTD

    filtered_df = df_filtered

if view_mode == "Daily":

    filtered_df = df_filtered[df_filtered["Date"] == latest_date]

else:  # MTD

    filtered_df = df_filtered

table_heat = (
    filtered_df.groupby("Table Number")["Total"]
    .sum()
    .reset_index()
)

all_tables = pd.DataFrame({"Table Number": range(1,16)})

table_heat = all_tables.merge(
    table_heat,
    on="Table Number",
    how="left"
).fillna(0)

grand_total = table_heat["Total"].sum()

if grand_total > 0:
    table_heat["Pct"] = table_heat["Total"]/grand_total*100
else:
    table_heat["Pct"] = 0

values = table_heat["Pct"].values.reshape(3,5)

text_matrix = []

for i in range(3):

    row = []

    for j in range(5):

        idx = i*5 + j

        table_no = int(table_heat.iloc[idx]["Table Number"])
        pct = table_heat.iloc[idx]["Pct"]

        row.append(f"Table {table_no}<br>{pct:.1f}%")

    text_matrix.append(row)

fig = go.Figure(data=go.Heatmap(

    z=values,
    text=text_matrix,
    texttemplate="%{text}",
    colorscale="Greens",
    xgap=6,
    ygap=6,
    hovertemplate="%{text}<extra></extra>"

))

fig.update_layout(
    template="simple_white",
    height=500,
    xaxis=dict(showticklabels=False),
    yaxis=dict(showticklabels=False)
)

fig.update_yaxes(autorange="reversed")

st.subheader("Table Revenue Heatmap")
st.plotly_chart(fig, use_container_width=True)

# ==============================
# HOURLY OCCUPANCY
# ==============================

view_mode_hour = st.radio(
    "Hourly View Mode",
    ["Daily","MTD"],
    horizontal=True
)

df["Mulai_dt"] = pd.to_datetime(
    df["Tanggal"].astype(str) + " " + df["Mulai"].astype(str),
    errors="coerce"
)

df["Selesai_dt"] = pd.to_datetime(
    df["Tanggal"].astype(str) + " " + df["Selesai"].astype(str),
    errors="coerce"
)

df.loc[df["Selesai_dt"] < df["Mulai_dt"], "Selesai_dt"] += pd.Timedelta(days=1)

hours = list(range(12,24)) + list(range(0,3))

total_tables = 15

hourly_data = []

if view_mode_hour == "Daily":

    if num_days == 1:
        latest_date = start_date
    else:
        latest_date = end_date

    working_df = df_filtered[df_filtered["Date"] == latest_date]

else:

    working_df = df_filtered

for hour in hours:

    active_counts = []

    if view_mode_hour == "Daily":

        start_hour = pd.Timestamp(f"{latest_date} {hour:02d}:00:00")
        end_hour = start_hour + pd.Timedelta(hours=1)

        active = working_df[
            (working_df["Mulai_dt"] <= end_hour) &
            (working_df["Selesai_dt"] >= start_hour)
        ]["Table Number"].nunique()

        active_counts.append(active)

    else:

        for d in working_df["Date"].unique():

            day_df = working_df[working_df["Date"] == d]

            start_hour = pd.Timestamp(f"{d} {hour:02d}:00:00")
            end_hour = start_hour + pd.Timedelta(hours=1)

            active = day_df[
                (day_df["Mulai_dt"] <= end_hour) &
                (day_df["Selesai_dt"] >= start_hour)
            ]["Table Number"].nunique()

            active_counts.append(active)

    avg_active = sum(active_counts)/len(active_counts) if active_counts else 0

    pct = (avg_active/total_tables)*100

    hourly_data.append({

        "Hour":f"{hour:02d}:00",
        "Active":round(avg_active,1),
        "Pct":pct

    })

hourly_df = pd.DataFrame(hourly_data)

fig = go.Figure()

fig.add_trace(go.Bar(

    y=hourly_df["Hour"],
    x=hourly_df["Pct"],
    orientation="h",

    text=[
        f"{p:.0f}% ({a}/15 Table)"
        for p,a in zip(hourly_df["Pct"], hourly_df["Active"])
    ],

    textposition="outside"

))

fig.update_layout(

    template="simple_white",
    height=500,
    xaxis=dict(range=[0,100], title="Occupancy %"),
    yaxis=dict(autorange="reversed")

)

st.subheader(f"Hourly Table Occupancy ({view_mode_hour})")

st.plotly_chart(fig, use_container_width=True)

# ==============================
# DAILY TREND MINGGU BERJALAN
# ==============================

today = pd.Timestamp.today().date()

# Cari Senin minggu ini
latest_date = df["Date"].max()

week_start = latest_date - pd.Timedelta(days=latest_date.weekday())
week_end = week_start + pd.Timedelta(days=6)

# Filter data hanya minggu berjalan
weekly_df = df[
    (df["Date"] >= week_start) &
    (df["Date"] <= week_end)
].copy()

# Tambahkan nama hari
weekly_df["Weekday"] = weekly_df["Tanggal"].dt.day_name()

# Hitung total per hari
weekday_total = (
    weekly_df.groupby("Weekday")["Total"]
    .sum()
    .reindex([
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
    ])
    .reset_index()
)

# Ubah nama hari ke bahasa Indonesia
weekday_total["Weekday"] = weekday_total["Weekday"].map({
    "Monday": "Senin",
    "Tuesday": "Selasa",
    "Wednesday": "Rabu",
    "Thursday": "Kamis",
    "Friday": "Jumat",
    "Saturday": "Sabtu",
    "Sunday": "Minggu"
})

# Buat chart
fig_weekday = px.bar(
    weekday_total,
    x="Weekday",
    y="Total",
    text=weekday_total["Total"].apply(lambda x: f"Rp {x:,.0f}"),
    title=f"Daily Trend Current Week ({week_start} s/d {week_end})",
    labels={"Total": "Total Revenue", "Weekday": "Hari"}
)

fig_weekday.update_layout(
    template="simple_white",
    yaxis_tickprefix="Rp ",
    xaxis_title="Hari",
    yaxis_title="Total Revenue"
)

st.plotly_chart(fig_weekday, use_container_width=True)

# # ==============================
# # Quadrant
# # ==============================

# if not fnb_menu.empty:
#     x_mid = fnb_menu["Qty"].mean()
#     y_mid = fnb_menu["Profit"].mean()
    
# fig = px.scatter(
#     fnb_menu,
#     x="Qty",
#     y="Profit",
#     title=f"Quadrant Trend Current Week ({min_date} s/d {max_date})",
#     text="F&B",
#     size="Revenue"
# )

# fig.add_vline(x=x_mid, line_dash="dash")
# fig.add_hline(y=y_mid, line_dash="dash")

# st.plotly_chart(fig, use_container_width=True)
# # st.plotly_chart(fig)

# ==============================
# Quadrant Update (With All 4 Labels)
# ==============================

if not fnb_menu.empty:
    # 1. Hitung Profit Margin (%)
    fnb_menu["Margin %"] = (fnb_menu["Profit"] / fnb_menu["Revenue"]) * 100
    fnb_menu["Margin %"] = fnb_menu["Margin %"].fillna(0)

    # 2. Hitung Titik Tengah (Benchmark)
    # Ini menentukan di mana garis horizontal dan vertikal berpotongan
    x_mid = fnb_menu["Qty"].mean()
    y_mid = fnb_menu["Margin %"].mean()
    
    # 3. Buat Chart
    fig_quad = px.scatter(
        fnb_menu,
        x="Qty",
        y="Margin %",
        title=f"F&B Performance Quadrant ({start_date} - {end_date})",
        text="F&B",
        size="Revenue",
        color="Margin %", # Tambah warna biar lebih indikatif
        color_continuous_scale="RdYlGn", # Merah ke Hijau
        labels={"Margin %": "Margin (%)", "Qty": "Jumlah Terjual"},
        hover_data={"Margin %": ":.2f"} # Merapikan format di hover
    )

    # 4. TAMBAHKAN GARIS PEMBAGI (Dashed gray lines)
    fig_quad.add_vline(x=x_mid, line_dash="dash", line_color="gray", opacity=0.7)
    fig_quad.add_hline(y=y_mid, line_dash="dash", line_color="gray", opacity=0.7)

    # 5. TAMBAHKAN LABEL UNTUK KEEMPAT KUADRAN
    
    # Posisi label akan kita taruh di ujung-ujung sumbu agar tidak menutupi titik data
    max_qty = fnb_menu["Qty"].max()
    min_qty = fnb_menu["Qty"].min()
    max_margin = fnb_menu["Margin %"].max()
    min_margin = fnb_menu["Margin %"].min()

    # Kanan Atas: Laku & Untung Gede (STARS)
    fig_quad.add_annotation(x=max_qty, y=max_margin, text="HIGH VOLUME HIGH MARGIN", showarrow=False, yshift=15, font=dict(color="green", size=14))
    
    # Kiri Atas: Untung Gede tapi Kurang Laku (UNDERPRICED / HIDDEN GEMS)
    fig_quad.add_annotation(x=min_qty, y=max_margin, text="LOW VOLUME HIGH MARGIN", showarrow=False, yshift=15, font=dict(color="#FF8C00", size=13)) # DarkOrange

    # Kanan Bawah: Laku tapi Untung Tipis (WORKHORSES / VOLUME DRIVE)
    fig_quad.add_annotation(x=max_qty, y=min_margin, text="HIGH VOLUME LOW MARGIN", showarrow=False, yshift=-15, font=dict(color="blue", size=13))

    # Kiri Bawah: Gak Laku & Untung Tipis (DOGS / MENU SLEEPERS)
    # --- INI YANG KITA TAMBAHKAN ---
    fig_quad.add_annotation(x=min_qty, y=min_margin, text="LOW VOLUME LOW MARGIN", showarrow=False, yshift=-15, font=dict(color="red", size=13))

    # 6. Finalisasi Tampilan
    fig_quad.update_traces(textposition='top center') # Nama menu muncul di atas titik
    fig_quad.update_layout(
        template="simple_white",
        yaxis_ticksuffix="%", # Tambah tanda % di sumbu y
        height=600 # Sesuaikan tinggi
    )

    st.subheader("Analisis Kuadran Menu F&B")
    st.plotly_chart(fig_quad, use_container_width=True)
else:
    st.warning("Belum ada data F&B untuk periode ini.")

