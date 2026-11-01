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
FAKTOR_JUAL = 0.978   # perkiraan: harga jual Dana = 97,8% dari harga di web
FAKTOR_BELI = 1.0125  # perkiraan: harga beli Dana = 101,25% dari harga di web


def rp(x):
    return f"Rp{x:,.0f}".replace(",", ".")


def tanda(x):
    return ("-" if x < 0 else "+") + rp(abs(x))


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


def hitung_tabungan(d, tabel, harga_jual_dana=0.0):
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
    dipakai_manual = bool(harga_jual_dana and harga_jual_dana > 0)
    harga_jual = harga_jual_dana if dipakai_manual else harga_kini * FAKTOR_JUAL
    nilai = total_gram * harga_jual
    return {
        "modal": modal,
        "gram": total_gram,
        "rata": modal / total_gram,
        "harga_kini": harga_kini,
        "harga_jual": harga_jual,
        "manual": dipakai_manual,
        "nilai": nilai,
        "untung": nilai - modal,
        "persen": (nilai - modal) / modal * 100,
    }


def simulasi_setor(h, setor, harga_beli_dana=0.0):
    manual = bool(harga_beli_dana and harga_beli_dana > 0)
    harga_beli = harga_beli_dana if manual else h["harga_kini"] * FAKTOR_BELI
    gram_tambah = setor / harga_beli
    gram = h["gram"] + gram_tambah
    modal = h["modal"] + setor
    nilai = gram * h["harga_jual"]
    return {
        "harga_beli": harga_beli,
        "manual": manual,
        "gram_tambah": gram_tambah,
        "gram": gram,
        "modal": modal,
        "rata": modal / gram,
        "nilai": nilai,
        "untung": nilai - modal,
        "persen": (nilai - modal) / modal * 100,
    }


def label(p):
    if p <= MURAH:
        return "🟢 MURAH", "Harga sedang di bagian bawah 3 bulan terakhir. Waktu yang cukup bagus untuk beli."
    if p >= MAHAL:
        return "🔴 MAHAL", "Harga sedang di bagian atas 3 bulan terakhir. Kalau belum mendesak, tunggu dulu."
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
st.caption(
    f"Harga emas sekarang sekitar {rp(hari_ini['rp_gram'])} per gram (data {d.index[-1].date()}). "
    "Angka ini perkiraan dari harga emas dunia, jadi bisa sedikit beda dengan harga di Dana."
)

# ---------------- tabungan pribadi ----------------
st.header("Tabungan saya")
st.caption(
    "Isi data pembelianmu dari aplikasi Dana. Yang paling penting: kolom Nominal dan kolom Gram "
    "(geser tabel ke kanan kalau kolom Gram tidak kelihatan). Data hilang kalau halaman di-refresh."
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
hj = st.number_input(
    "Harga jual per gram di Dana (opsional)",
    min_value=0.0, value=0.0, step=1000.0,
    help="Di aplikasi Dana, lihat tulisan 'Harga Jual Terbaru'. Kalau dikosongkan, web memakai perkiraan.",
)
h = hitung_tabungan(d, tabel, hj)
if h is None:
    st.info("Isi minimal satu baris pembelian.")
else:
    if h["untung"] < 0:
        st.info(
            f"**Ringkasnya:** kamu sudah setor **{rp(h['modal'])}** dan punya **{h['gram']:.4f} gram** emas. "
            f"Kalau dijual sekarang di Dana kamu dapat sekitar **{rp(h['nilai'])}**, jadi rugi sementara "
            f"**{rp(abs(h['untung']))}** ({abs(h['persen']):.1f}%). Ini belum rugi sungguhan karena belum dijual. "
            "Sebagian karena selisih harga beli dan jual di Dana, sebagian karena harga emas turun sejak kamu beli."
        )
    else:
        st.info(
            f"**Ringkasnya:** kamu sudah setor **{rp(h['modal'])}** dan punya **{h['gram']:.4f} gram** emas. "
            f"Kalau dijual sekarang di Dana kamu dapat sekitar **{rp(h['nilai'])}**, jadi untung sementara "
            f"**{rp(h['untung'])}** ({h['persen']:.1f}%)."
        )
    a, b = st.columns(2)
    a.metric("Uang yang sudah disetor", rp(h["modal"]))
    b.metric("Emas yang dimiliki", f"{h['gram']:.4f} g")
    a.metric("Harga rata-rata belimu per gram", rp(h["rata"]))
    b.metric("Harga jual per gram (Dana)", rp(h["harga_jual"]))
    st.metric("Kalau dijual sekarang dapat", rp(h["nilai"]), f"{tanda(h['untung'])} ({h['persen']:+.2f}%)")
    if not h["manual"]:
        st.caption("Harga jual di atas masih perkiraan. Isi kolom harga jual dari aplikasi Dana supaya persis.")

    # ---------------- simulasi setor ----------------
    st.header("Kalau setor lagi")
    st.caption("Coba berapa pun setoran berikutnya, lihat pengaruhnya ke tabunganmu. Ini hanya simulasi.")
    setor = st.number_input("Mau setor berapa (Rp)", min_value=0.0, value=150000.0, step=10000.0)
    hb = st.number_input(
        "Harga beli per gram di Dana (opsional)",
        min_value=0.0, value=0.0, step=1000.0,
        help="Di aplikasi Dana, lihat tulisan 'Harga Beli Terbaru'. Kalau dikosongkan, web memakai perkiraan.",
    )
    if setor > 0:
        s = simulasi_setor(h, setor, hb)
        st.metric("Emas bertambah", f"+{s['gram_tambah']:.4f} g")
        st.metric("Total emas jadi", f"{s['gram']:.4f} g")
        st.metric(
            "Harga rata-rata belimu jadi",
            rp(s["rata"]),
            tanda(s["rata"] - h["rata"]),
            delta_color="inverse",
            help="Semakin rendah semakin baik. Kalau harga sedang turun, setor lagi akan menurunkan rata-rata belimu.",
        )
        st.metric("Kalau dijual sekarang dapat", rp(s["nilai"]), f"{tanda(s['untung'])} ({s['persen']:+.2f}%)")
        st.caption(
            "Setiap setoran baru langsung terlihat 'rugi' sekitar 3-4% karena selisih harga beli dan jual di Dana. "
            "Itu normal, dan hilang kalau harga emas naik lebih dari selisih itu."
        )

# ---------------- bagian untuk yang penasaran ----------------
with st.expander("📈 Grafik harga 6 bulan terakhir"):
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
    st.caption("rp_gram = harga harian. MA30 dan MA90 = rata-rata 30 dan 90 hari terakhir.")

if h is not None:
    with st.expander("🔮 Kalau harga emas berubah"):
        skenario = pd.DataFrame({
            "Perubahan harga": ["-10%", "-5%", "Tetap", "+5%", "+10%"],
            "Nilai tabungan": [rp(h["nilai"] * (1 + p)) for p in (-0.1, -0.05, 0, 0.05, 0.1)],
            "Untung/rugi": [tanda(h["nilai"] * (1 + p) - h["modal"]) for p in (-0.1, -0.05, 0, 0.05, 0.1)],
        })
        st.table(skenario)
        st.caption("Hanya simulasi 'bagaimana kalau', bukan prediksi.")

with st.expander("🧪 Apakah menunggu harga murah menguntungkan?"):
    bt, rata_biasa, rata_pintar = uji_historis(d)
    selisih = (rata_biasa - rata_pintar) / rata_biasa * 100
    st.write(f"Simulasi {len(bt)} bulan terakhir dengan {rp(CICILAN)} per bulan:")
    st.metric("Beli tiap tanggal 1", rp(rata_biasa) + "/g")
    st.metric("Beli saat lampu hijau", rp(rata_pintar) + "/g", f"{selisih:+.2f}% dibanding tgl 1")
    st.caption(
        "Plus = lebih murah dari beli tiap tanggal 1, minus = lebih mahal. "
        "Selisihnya kecil, jadi yang paling penting tetap konsisten menabung."
    )
