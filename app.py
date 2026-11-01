from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Timing Beli Emas", page_icon="🪙")

OZ_GRAM = 31.1035
CICILAN = 150_000
WINDOW = 90
MURAH, MAHAL = 0.33, 0.67


def rp(x):
    return f"Rp{x:,.0f}".replace(",", ".")


@st.cache_data(ttl=300)
def muat_data():
    emas = yf.download("GC=F", period="6y", progress=False, auto_adjust=True)["Close"].squeeze()
    kurs = yf.download("IDR=X", period="6y", progress=False, auto_adjust=True)["Close"].squeeze()
    df = pd.concat([emas, kurs], axis=1, keys=["usd", "kurs"]).dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def hitung(df):
    d = df.copy()
    d["rp_gram"] = d["usd"] * d["kurs"] / OZ_GRAM
    d["posisi"] = d["rp_gram"].rolling(WINDOW).apply(
        lambda w: (w[:-1] < w[-1]).mean(), raw=True
    )
    d["MA30"] = d["rp_gram"].rolling(30).mean()
    d["MA90"] = d["rp_gram"].rolling(90).mean()
    return d.dropna()


def uji_historis(d, bulan=36):
    d = d.copy()
    d["bln"] = d.index.to_period("M")
    baris = []
    for b, m in d.groupby("bln"):
        beli_tgl1 = m["rp_gram"].iloc[0]
        murah = m[m["posisi"] <= MURAH]
        beli_pintar = murah["rp_gram"].iloc[0] if len(murah) else m["rp_gram"].iloc[-1]
        baris.append((str(b), beli_tgl1, beli_pintar))
    bt = pd.DataFrame(baris, columns=["bulan", "tgl1", "pintar"]).tail(bulan)
    rata = lambda k: len(bt) * CICILAN / (CICILAN / bt[k]).sum()
    return bt, rata("tgl1"), rata("pintar")


def harga_pada(d, tgl):
    s = d.loc[:pd.Timestamp(tgl), "rp_gram"]
    return s.iloc[-1] if len(s) else d["rp_gram"].iloc[0]


def hitung_tabungan(d, tabel):
    t = tabel.dropna(subset=["Tanggal", "Nominal (Rp)"]).copy()
    t = t[t["Nominal (Rp)"] > 0]
    if t.empty:
        return None
    gram = []
    for _, r in t.iterrows():
        g = r["Gram (opsional)"]
        if pd.notna(g) and g > 0:
            gram.append(float(g))
        else:
            gram.append(r["Nominal (Rp)"] / harga_pada(d, r["Tanggal"]))
    modal = float(t["Nominal (Rp)"].sum())
    total_gram = sum(gram)
    harga_kini = d["rp_gram"].iloc[-1]
    nilai = total_gram * harga_kini
    return {
        "modal": modal,
        "gram": total_gram,
        "rata": modal / total_gram,
        "harga_kini": harga_kini,
        "nilai": nilai,
        "untung": nilai - modal,
        "persen": (nilai - modal) / modal * 100,
    }


def label(p):
    if p <= MURAH:
        return "🟢 MURAH", "Harga di bagian bawah 3 bulan terakhir. Waktu yang cukup bagus untuk beli."
    if p >= MAHAL:
        return "🔴 MAHAL", "Harga di bagian atas 3 bulan terakhir. Kalau belum mendesak, tunggu dulu."
    return "🟡 BIASA", "Harga di sekitar rata-rata 3 bulan terakhir. Beli sesuai jadwal tidak masalah."


# ---------------- tampilan ----------------
st.title("🪙 Timing Beli Emas")
st.caption("Alat bantu belajar, bukan ramalan dan bukan saran keuangan.")

try:
    d = hitung(muat_data())
except Exception as e:
    st.error(f"Gagal mengambil data: {e}")
    st.stop()

hari_ini = d.iloc[-1]
judul, saran = label(hari_ini["posisi"])
st.subheader(judul)
st.write(saran)
c1, c2 = st.columns(2)
c1.metric("Harga perkiraan per gram", rp(hari_ini["rp_gram"]))
c2.metric("Posisi vs 90 hari", f"{hari_ini['posisi']*100:.0f}%", help="0% = termurah, 100% = termahal")
st.caption(f"Data terakhir: {d.index[-1].date()}. Harga ini turunan dari XAU/USD x kurs, jadi bisa beda dengan harga di Dana (ada selisih jual-beli).")

grafik = d[["rp_gram", "MA30", "MA90"]].tail(180).reset_index()
grafik.columns = ["tanggal", "rp_gram", "MA30", "MA90"]
panjang = grafik.melt("tanggal", var_name="garis", value_name="harga")
st.altair_chart(
    alt.Chart(panjang).mark_line().encode(
        x=alt.X("tanggal:T", title=None),
        y=alt.Y("harga:Q", scale=alt.Scale(zero=False), title="Rp per gram"),
        color=alt.Color("garis:N", title=None),
    ),
    use_container_width=True,
)

# ---------------- tabungan pribadi ----------------
st.header("Tabungan saya")
st.caption(
    "Isi pembelianmu di tabel (tap sel untuk mengubah, tambah baris di bawah tabel). "
    "Data hanya ada di layar ini dan hilang kalau halaman di-refresh. "
    "Untuk hasil lebih akurat, isi kolom Gram sesuai riwayat di Dana."
)
awal = pd.DataFrame({
    "Tanggal": [date.today() - timedelta(days=60), date.today() - timedelta(days=30)],
    "Nominal (Rp)": [150000.0, 150000.0],
    "Gram (opsional)": [float("nan"), float("nan")],
})
tabel = st.data_editor(
    awal,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "Tanggal": st.column_config.DateColumn("Tanggal", format="DD/MM/YYYY"),
        "Nominal (Rp)": st.column_config.NumberColumn("Nominal (Rp)", min_value=0, step=10000),
        "Gram (opsional)": st.column_config.NumberColumn("Gram (opsional)", min_value=0.0, format="%.4f"),
    },
)
h = hitung_tabungan(d, tabel)
if h is None:
    st.info("Isi minimal satu baris pembelian.")
else:
    a, b = st.columns(2)
    a.metric("Total modal", rp(h["modal"]))
    b.metric("Total emas", f"{h['gram']:.4f} g")
    a.metric("Rata-rata harga belimu", rp(h["rata"]) + "/g")
    b.metric("Harga sekarang", rp(h["harga_kini"]) + "/g")
    st.metric(
        "Nilai tabungan sekarang (perkiraan)",
        rp(h["nilai"]),
                f"{'-' if h['untung'] < 0 else '+'}{rp(abs(h['untung']))} ({h['persen']:+.2f}%)",
    )
    st.caption(
        "Ini untung/rugi di atas kertas. Kalau kamu menjual di Dana, harga jualnya lebih rendah dari harga beli "
        "(ada selisih), jadi angka nyata bisa lebih kecil. Kalau harga turun, cicilan bulan depan dapat lebih "
        "banyak gram, dan rata-rata harga belimu ikut turun."
    )
    st.subheader("Kalau harga berubah")
    skenario = pd.DataFrame({
        "Perubahan harga": ["-10%", "-5%", "Tetap", "+5%", "+10%"],
        "Nilai tabungan": [rp(h["nilai"] * (1 + p)) for p in (-0.1, -0.05, 0, 0.05, 0.1)],
        "Untung/rugi": [rp(h["nilai"] * (1 + p) - h["modal"]) for p in (-0.1, -0.05, 0, 0.05, 0.1)],
    })
    st.table(skenario)
    st.caption("Ini hanya simulasi 'bagaimana kalau', bukan prediksi.")

# ---------------- uji historis ----------------
st.header("Uji pada data masa lalu")
bt, rata_biasa, rata_pintar = uji_historis(d)
selisih = (rata_biasa - rata_pintar) / rata_biasa * 100
st.write(f"Simulasi {len(bt)} bulan terakhir dengan {rp(CICILAN)}/bulan:")
c3, c4 = st.columns(2)
c3.metric("Beli tiap tanggal 1", rp(rata_biasa) + "/g")
c4.metric("Beli saat 'murah'", rp(rata_pintar) + "/g", f"{selisih:+.2f}% dibanding tgl 1")
st.caption(
    "Tanda plus = lebih murah dari beli tiap tanggal 1, tanda minus = lebih mahal. "
    "Selisih kecil atau negatif itu wajar: timing bulanan hanya membantu sedikit, "
    "dan yang paling penting tetap konsisten menabung."
)
