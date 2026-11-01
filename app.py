import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Timing Beli Emas", page_icon="🪙")

OZ_GRAM = 31.1035
CICILAN = 150_000
WINDOW = 90
MURAH, MAHAL = 0.33, 0.67


@st.cache_data(ttl=3600)
def muat_data():
    emas = yf.download("GC=F", period="6y", progress=False, auto_adjust=True)["Close"].squeeze()
    kurs = yf.download("IDR=X", period="6y", progress=False, auto_adjust=True)["Close"].squeeze()
    df = pd.concat([emas, kurs], axis=1, keys=["usd", "kurs"]).dropna()
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


def label(p):
    if p <= MURAH:
        return "🟢 MURAH", "Harga di bagian bawah 3 bulan terakhir. Waktu yang cukup bagus untuk beli."
    if p >= MAHAL:
        return "🔴 MAHAL", "Harga di bagian atas 3 bulan terakhir. Kalau belum mendesak, tunggu dulu."
    return "🟡 BIASA", "Harga di sekitar rata-rata 3 bulan terakhir. Beli sesuai jadwal tidak masalah."


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
c1.metric("Harga perkiraan per gram", f"Rp{hari_ini['rp_gram']:,.0f}".replace(",", "."))
c2.metric("Posisi vs 90 hari", f"{hari_ini['posisi']*100:.0f}%", help="0% = termurah, 100% = termahal")
st.caption(f"Data terakhir: {d.index[-1].date()}. Harga ini turunan dari XAU/USD x kurs, jadi bisa beda dengan harga di Dana (ada selisih jual-beli).")

st.line_chart(d[["rp_gram", "MA30", "MA90"]].tail(180))

st.header("Uji pada data masa lalu")
bt, rata_biasa, rata_pintar = uji_historis(d)
selisih = (rata_biasa - rata_pintar) / rata_biasa * 100
st.write(f"Simulasi {len(bt)} bulan terakhir dengan Rp{CICILAN:,}/bulan:".replace(",", "."))
c3, c4 = st.columns(2)
c3.metric("Beli tiap tanggal 1", f"Rp{rata_biasa:,.0f}/g".replace(",", "."))
c4.metric("Beli saat 'murah'", f"Rp{rata_pintar:,.0f}/g".replace(",", "."), f"{selisih:+.2f}% lebih murah")
st.caption(
    "Selisih kecil atau bahkan negatif itu wajar. Artinya timing bulanan hanya membantu sedikit, "
    "dan yang paling penting tetap konsisten menabung."
)
