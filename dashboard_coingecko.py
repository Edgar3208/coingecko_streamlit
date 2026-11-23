# Tablero de Criptomonedas con CoinGecko API
# Herramientas de Visualización · IDIA223 · Parcial III
# streamlit run dashboard_coingecko.py

import os
from datetime import date, datetime, timedelta, timezone

import matplotlib.pyplot as plt
import pandas as pd
import requests
import seaborn as sns
import streamlit as st

# ─── Paleta del curso ──────────────────────────────────────────────────
GRIS = "#B9C3D1"
AZUL = "#1C4C9A"
ROJO = "#B2182B"
VERDE = "#009E73"
CUALI = ["#E69F00", "#56B4E9", "#009E73", "#0072B2"]
sns.set_theme(style="whitegrid")

API_BASE = "https://api.coingecko.com/api/v3"

st.set_page_config(page_title="Tablero CoinGecko", layout="wide")

def leer_token():
    try:
        if "coingecko_token" in st.secrets:
            return str(st.secrets["coingecko_token"]).strip()
    except Exception:
        pass
    if os.environ.get("coingecko_token"):
        return os.environ["coingecko_token"].strip()
    return None


TOKEN = leer_token()

if TOKEN and len(TOKEN) < 20:
    st.error(
        f"El token tiene {len(TOKEN)} caracteres y parece incompleto. "
        "Verifica que lo hayas copiado completo (ej. CG-xxxxxxxx...) y sin comillas extra."
    )
    st.stop()

if not TOKEN:
    st.error("Falta el token de CoinGecko.")
    st.markdown(
        "1. Pídelo gratis en "
        "https://www.coingecko.com/en/developers/dashboard\n"
        "2. Crea la carpeta `.streamlit` junto a este archivo.\n"
        "3. Dentro, un archivo `secrets.toml` con la línea:\n"
        '   `coingecko_token = "CG-tu-token"`\n'
        "4. Vuelve a cargar esta página."
    )
    st.stop()


# Consulta
@st.cache_data(ttl=3600, show_spinner=False)
def consultar(claves, inicio, fin, moneda, token):
    ts_inicio = int(
        datetime.combine(inicio, datetime.min.time(), tzinfo=timezone.utc).timestamp()
    )
    ts_fin = int(
        datetime.combine(fin, datetime.max.time(), tzinfo=timezone.utc).timestamp()
    )

    tablas = []
    faltantes = {}

    for coin_id in claves:
        url = f"{API_BASE}/coins/{coin_id}/market_chart/range"
        respuesta = requests.get(
            url,
            params={
                "vs_currency": moneda,
                "from": ts_inicio,
                "to": ts_fin,
            },
            headers={
                "x-cg-demo-api-key": token,
                "Accept": "application/json",
                "User-Agent": "UPQ-IDIA224/1.0",
            },
            timeout=60,
        )

        if respuesta.status_code == 401:
            detalle = ""
            try:
                detalle = (
                    respuesta.json()
                    .get("error", {})
                    .get("status", {})
                    .get("error_message", "")
                )
            except Exception:
                pass
            if "time range" in detalle.lower() or "365" in detalle:
                raise PermissionError(
                    "El plan gratuito (Demo) de CoinGecko solo permite consultar los últimos 365 días. "
                    "Ajusta la fecha 'Desde' a menos de un año."
                )
            raise PermissionError(
                "El token de CoinGecko no fue aceptado. Revisa que sea una clave Demo válida (empieza con CG-)."
            )
        if respuesta.status_code == 404:
            raise ValueError(
                f"No se encontró la moneda '{coin_id}'. Usa el ID oficial en minúsculas (ej. bitcoin, ethereum, solana)."
            )
        if respuesta.status_code == 429:
            raise PermissionError("Demasiadas peticiones (límite de CoinGecko). Espera un minuto.")
        respuesta.raise_for_status()

        precios = respuesta.json().get("prices", [])
        if not precios:
            continue

        t = pd.DataFrame(precios, columns=["timestamp_ms", "Valor"])
        t["Fecha"] = pd.to_datetime(t["timestamp_ms"], unit="ms").dt.normalize()

        t = (
            t.sort_values("timestamp_ms")
            .groupby("Fecha", as_index=False)["Valor"]
            .last()
        )

        faltantes[coin_id] = int(t["Valor"].isna().sum())
        t["Clave"] = coin_id
        t["Serie"] = f"{coin_id.capitalize()} ({moneda.upper()})"
        tablas.append(t)

    if not tablas:
        raise ValueError("Ninguna de las criptomonedas devolvió datos en ese rango.")

    df = pd.concat(tablas, ignore_index=True)
    df["Anio"] = df["Fecha"].dt.year
    df["Mes"] = df["Fecha"].dt.month
    return df, faltantes

hoy = date.today()

with st.sidebar:
    st.header("Qué consultar")
    texto = st.text_input(
        "IDs de criptomonedas",
        "bitcoin",
        help="Sepáralos con comas en minúsculas. Ejemplos: bitcoin, ethereum, solana, cardano.",
    )
    moneda = st.selectbox("Moneda de referencia", ["usd", "mxn"], index=0)
    inicio = st.date_input("Desde", hoy - timedelta(days=364))
    fin = st.date_input("Hasta", hoy)
    suavizado = st.slider("Días de media móvil", 1, 90, 30)
    st.caption("Fuente: CoinGecko API · Plan Demo (máx. 365 días)")

claves = [c.strip().lower() for c in texto.split(",") if c.strip()]

if not claves:
    st.info("Escribe al menos un ID de criptomoneda en el panel de la izquierda.")
    st.stop()
if inicio >= fin:
    st.error("La fecha inicial debe ser anterior a la final.")
    st.stop()

with st.spinner("Consultando CoinGecko..."):
    try:
        df, faltantes = consultar(tuple(claves), inicio, fin, moneda, TOKEN)
    except PermissionError as e:
        st.error(str(e))
        st.stop()
    except ValueError as e:
        st.warning(str(e))
        st.stop()
    except requests.exceptions.RequestException as e:
        st.error(f"No se pudo consultar CoinGecko: {e}")
        st.stop()

limpio = df.dropna(subset=["Valor"]).copy()
if limpio.empty:
    st.warning("No hay valores numéricos en ese rango.")
    st.stop()

principal = limpio[limpio["Clave"] == claves[0]].sort_values("Fecha").copy()
titulo_principal = principal["Serie"].iloc[0]


# Encabezado e indicadores
st.title("Tablero de criptomonedas · CoinGecko")
st.caption(
    f"{titulo_principal} · del {inicio} al {fin} · "
    f"consultado el {datetime.now():%d/%m/%Y %H:%M}"
)

primero = principal["Valor"].iloc[0]
ultimo = principal["Valor"].iloc[-1]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Días con dato", len(principal))
c2.metric("Datos faltantes", faltantes.get(claves[0], 0))
c3.metric(
    f"Último precio ({moneda.upper()})",
    f"{ultimo:,.2f}",
    delta=f"{(ultimo / primero - 1) * 100:+.1f} % en el periodo",
)
c4.metric(
    "Mínimo y máximo",
    f"{principal['Valor'].min():,.2f} – {principal['Valor'].max():,.2f}",
)

st.divider()


# Gráficas
izquierda, derecha = st.columns(2)

with izquierda:
    if len(claves) == 1:
        st.subheader("Precio y tendencia")
        principal["Suave"] = principal["Valor"].rolling(suavizado).mean()

        fig, ax = plt.subplots(figsize=(6, 3.4))
        ax.plot(
            principal["Fecha"], principal["Valor"], color=GRIS, linewidth=0.9, label="Precio diario"
        )
        ax.plot(
            principal["Fecha"],
            principal["Suave"],
            color=AZUL,
            linewidth=2,
            label=f"Media móvil {suavizado} días",
        )
        ax.set_xlabel("Fecha")
        ax.set_ylabel(f"Precio ({moneda.upper()})")
        ax.legend(frameon=False)
        st.pyplot(fig)
        plt.close(fig)
    else:
        st.subheader("Comparación en base 100")
        limpio = limpio.sort_values("Fecha")
        limpio["Base100"] = limpio.groupby("Clave")["Valor"].transform(
            lambda s: s / s.iloc[0] * 100
        )

        fig, ax = plt.subplots(figsize=(6, 3.4))
        for i, clave in enumerate(claves):
            parte = limpio[limpio["Clave"] == clave]
            if parte.empty:
                continue
            ax.plot(
                parte["Fecha"],
                parte["Base100"],
                color=CUALI[i % len(CUALI)],
                linewidth=1.8,
                label=clave.capitalize(),
            )
        ax.axhline(100, color="gray", linewidth=0.8)
        ax.set_xlabel("Fecha")
        ax.set_ylabel("Índice base 100")
        ax.legend(frameon=False)
        st.pyplot(fig)
        plt.close(fig)
    st.caption("Muestra como cambia su valor con el paso de los dias")

with derecha:
    st.subheader("Caída desde el máximo (Drawdown)")
    max_acumulado = principal["Valor"].cummax()
    drawdown = (principal["Valor"] / max_acumulado - 1) * 100

    peor_dd = drawdown.min()
    fecha_peor = principal.loc[drawdown.idxmin(), "Fecha"]

    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.plot(principal["Fecha"], drawdown, color=ROJO, linewidth=1.4)
    ax.fill_between(principal["Fecha"], drawdown, 0, color=ROJO, alpha=0.16)
    ax.scatter(
        [fecha_peor],
        [peor_dd],
        color=ROJO,
        zorder=5,
        s=35,
        label=f"Peor caída: {peor_dd:.1f}% ({fecha_peor:%d/%m/%Y})",
    )
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Caída desde pico (%)")
    ax.legend(frameon=False, loc="best")
    st.pyplot(fig)
    plt.close(fig)
    st.caption(
        "Mide qué porcentaje por debajo de su punto más alto del periodo se encuentra el precio en cada fecha."
    )

abajo_izq, abajo_der = st.columns(2)
with abajo_izq:
    st.subheader("Distribución de rendimientos diarios")
    principal["Variacion"] = principal["Valor"].pct_change() * 100
    variaciones = principal["Variacion"].dropna()

    media = variaciones.mean()
    p5, p95 = variaciones.quantile([0.05, 0.95])

    fig, ax = plt.subplots(figsize=(6, 3.4))
    sns.histplot(
        variaciones,
        bins=35,
        kde=True,
        color=AZUL,
        alpha=0.25,
        edgecolor="white",
        ax=ax,
    )
    ax.axvline(0, color="gray", linewidth=0.9)
    ax.axvline(media, color=AZUL, linewidth=1.6, linestyle="--", label=f"Media: {media:+.2f}%")
    ax.axvline(p5, color=ROJO, linewidth=1.4, linestyle=":", label=f"Percentil 5%: {p5:+.2f}%")
    ax.axvline(p95, color=VERDE, linewidth=1.4, linestyle=":", label=f"Percentil 95%: {p95:+.2f}%")
    ax.set_xlabel("Variación diaria (%)")
    ax.set_ylabel("Frecuencia (días)")
    ax.legend(frameon=False, fontsize=8.5)
    st.pyplot(fig)
    plt.close(fig)
    st.caption(
        "Muestra la frecuencia de subidas y caídas diarias; las líneas punteadas marcan el 5% de los peores y mejores días."
    )

with abajo_der:
    ventana = max(suavizado, 2)
    st.subheader(f"Volatilidad móvil ({ventana} días)")
    principal["Volatilidad"] = principal["Variacion"].rolling(ventana).std()

    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.plot(
        principal["Fecha"],
        principal["Volatilidad"],
        color=ROJO,
        linewidth=1.6,
        label=f"Desv. estándar móvil ({ventana} días)",
    )
    ax.fill_between(principal["Fecha"], principal["Volatilidad"], color=ROJO, alpha=0.12)
    ax.axhline(
        principal["Volatilidad"].mean(),
        color=AZUL,
        linewidth=1,
        linestyle="--",
        label="Promedio del periodo",
    )
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Volatilidad diaria (% pts)")
    ax.legend(frameon=False)
    st.pyplot(fig)
    plt.close(fig)
    st.caption("Mide la intensidad de los cambios diarios en ventanas recientes.")


# Datos
with st.expander("Ver y descargar los datos"):
    st.dataframe(df)
    st.download_button(
        "Descargar CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"coingecko_{'_'.join(claves)}_{inicio}_{fin}.csv",
        mime="text/csv",
    )