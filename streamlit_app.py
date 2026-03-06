import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import plotly.graph_objects as go

st.set_page_config(
    page_title="Outlet Dashboard",
    layout="wide"
)

st.title("Outlet Revenue Dashboard")

# ==============================
# LOAD DATA
# ==============================

data = pd.read_excel("LAPORAN MARET.xlsx")

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
# HEATMAP TABLE
# ==============================

df.columns = df.columns.str.strip()

df["Tanggal"] = pd.to_datetime(df["Tanggal"], errors="coerce")
df["Date"] = df["Tanggal"].dt.date

# Gunakan Table Number (bukan Table)
df["Table Number"] = (
    df["Table Number"]
    .astype(str)
    .str.extract("(\d+)")
    .astype(int)
)

# Pastikan Total numeric
df["Total"] = (
    df["Total"]
    .astype(str)
    .str.replace(",", "", regex=False)
)

df["Total"] = pd.to_numeric(df["Total"], errors="coerce").fillna(0)

view_mode = st.radio("View Mode", ["Daily", "MTD"], horizontal=True)

today = df["Date"].max()

if view_mode == "Daily":
    filtered_df = df[df["Date"] == today]
else:
    filtered_df = df[
        (df["Tanggal"].dt.month == today.month) &
        (df["Tanggal"].dt.year == today.year)
    ]

table_heat = (
    filtered_df.groupby("Table Number")["Total"]
    .sum()
    .reset_index()
)

all_tables = pd.DataFrame({"Table Number": range(1, 16)})

table_heat = all_tables.merge(
    table_heat,
    on="Table Number",
    how="left"
).fillna(0)

grand_total = table_heat["Total"].sum()

if grand_total > 0:
    table_heat["Pct"] = table_heat["Total"] / grand_total * 100
else:
    table_heat["Pct"] = 0

values = table_heat["Pct"].values.reshape(3, 5)

text_matrix = []

for i in range(3):
    row = []
    for j in range(5):
        idx = i * 5 + j
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

# INI YANG FIX
fig.update_yaxes(autorange="reversed")

st.plotly_chart(fig, use_container_width=True)

# # ==============================
# # TABLE PER HOUR (DAILY + MTD)
# # ==============================

# view_mode = st.radio(
#     "Hourly View Mode",
#     ["Daily", "MTD"],
#     horizontal=True
# )

# # Pastikan tanggal format benar
# df["Tanggal"] = pd.to_datetime(df["Tanggal"], errors="coerce")
# df["Date"] = df["Tanggal"].dt.date

# latest_date = df["Date"].max()
# latest_month = df["Tanggal"].dt.month.max()
# latest_year = df["Tanggal"].dt.year.max()

# # Gabungkan tanggal + jam mulai
# df["Mulai"] = pd.to_datetime(
#     df["Tanggal"].dt.strftime("%Y-%m-%d") + " " + df["Mulai"].astype(str),
#     errors="coerce"
# )

# df["Selesai"] = pd.to_datetime(
#     df["Tanggal"].dt.strftime("%Y-%m-%d") + " " + df["Selesai"].astype(str),
#     errors="coerce"
# )

# hours = list(range(12, 24)) + list(range(0, 3))  # 12 AM to 4 AM
# total_tables = 15
# hourly_data = []

# if view_mode == "Daily":
#     working_df = df[df["Date"] == latest_date]
# else:
#     working_df = df[
#         (df["Tanggal"].dt.month == latest_month) &
#         (df["Tanggal"].dt.year == latest_year)
#     ]

# for hour in hours:
#     active_counts = []

#     # Kalau Daily → hanya 1 hari
#     if view_mode == "Daily":
#         start_hour = pd.Timestamp(f"{latest_date} {hour:02d}:00:00")
#         end_hour = start_hour + pd.Timedelta(hours=1)

#         active_tables = working_df[
#             (working_df["Mulai"] <= end_hour) &
#             (working_df["Selesai"] >= start_hour)
#         ]["Table Number"].nunique()

#         active_counts.append(active_tables)

#     # Kalau MTD → hitung per hari lalu rata-rata
#     else:
#         for single_date in working_df["Date"].unique():

#             day_df = working_df[working_df["Date"] == single_date]

#             start_hour = pd.Timestamp(f"{single_date} {hour:02d}:00:00")
#             end_hour = start_hour + pd.Timedelta(hours=1)

#             active_tables = day_df[
#                 (day_df["Mulai"] <= end_hour) &
#                 (day_df["Selesai"] >= start_hour)
#             ]["Table Number"].nunique()

#             active_counts.append(active_tables)

#     avg_active = sum(active_counts) / len(active_counts) if active_counts else 0
#     pct = (avg_active / total_tables) * 100

#     hourly_data.append({
#         "Hour": f"{hour:02d}:00",
#         "Active": round(avg_active, 1),
#         "Pct": pct
#     })

# hourly_df = pd.DataFrame(hourly_data)

# fig = go.Figure()

# fig.add_trace(go.Bar(
#     y=hourly_df["Hour"],
#     x=hourly_df["Pct"],
#     orientation="h",
#     text=[
#         f"{p:.0f}% ({a}/15 Table)"
#         for p, a in zip(hourly_df["Pct"], hourly_df["Active"])
#     ],
#     textposition="outside"
# ))

# fig.update_layout(
#     template="simple_white",
#     height=500,
#     xaxis=dict(range=[0,100], title="Occupancy %"),
#     yaxis=dict(autorange="reversed"),
#     margin=dict(l=40, r=40, t=40, b=40)
# )

# st.subheader(f"Hourly Table Occupancy ({view_mode})")
# st.plotly_chart(fig, use_container_width=True)

# ==============================
# TABLE PER HOUR (DAILY + MTD)
# ==============================

view_mode = st.radio(
    "Hourly View Mode",
    ["Daily", "MTD"],
    horizontal=True
)

df["Tanggal"] = pd.to_datetime(df["Tanggal"], errors="coerce")
df = df.dropna(subset=["Tanggal"])

df["Date"] = df["Tanggal"].dt.date

# gabungkan tanggal + jam
df["Mulai_dt"] = pd.to_datetime(df["Tanggal"].astype(str) + " " + df["Mulai"].astype(str), errors="coerce")
df["Selesai_dt"] = pd.to_datetime(df["Tanggal"].astype(str) + " " + df["Selesai"].astype(str), errors="coerce")

# handle lewat tengah malam
df.loc[df["Selesai_dt"] < df["Mulai_dt"], "Selesai_dt"] += pd.Timedelta(days=1)

latest_date = df["Date"].max()

hours = list(range(12,24)) + list(range(0,3))
total_tables = 15

hourly_data = []

if view_mode == "Daily":
    working_df = df[df["Date"] == latest_date]
else:
    latest_ts = df["Tanggal"].max()
    working_df = df[
        (df["Tanggal"].dt.month == latest_ts.month) &
        (df["Tanggal"].dt.year == latest_ts.year)
    ]

for hour in hours:

    active_counts = []

    if view_mode == "Daily":

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

st.subheader(f"Hourly Table Occupancy ({view_mode})")
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

