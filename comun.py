"""Elementos compartidos por las páginas: estilo, colores, carga de datos y panel lateral."""
import os

import pandas as pd
import streamlit as st

import db
from auth import render_logout, render_profile
from db import load_datos

ACENTO = "#c8590f"

ESTILO = """<style>
/* Página */
.block-container { padding-top: 4.5rem; padding-bottom: 4rem; max-width: 1400px; }
[data-testid="stMainBlockContainer"] > div > [data-testid="stVerticalBlock"] { gap: 1rem; }
h1 { font-size: 2rem !important; font-weight: 700 !important; padding: 0 !important; margin: 0 0 .4rem !important; }
[data-testid="stExpander"] { margin-top: .5rem; }
.sub-titulo { opacity: .65; margin: .15rem 0 .5rem; font-size: .95rem; }

/* Encabezado de sección: mismo tamaño y espacio en toda la página */
.sec { display: flex; align-items: baseline; gap: .7rem; margin: 1.6rem 0 .1rem; font-size: 1.15rem; font-weight: 700; }
.sec::before { content: ""; align-self: center; width: 4px; height: 1.15rem; border-radius: 2px; background: __ACENTO__; }
.sec small { font-size: .85rem; font-weight: 400; opacity: .65; }

/* Gráficas lado a lado; se apilan cuando el ancho no alcanza */
.st-key-graficas [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
.st-key-graficas [data-testid="stColumn"] { min-width: 480px; }

/* Tablas de morosidad (paquete / distrito) */
.mt-w { max-height: 400px; overflow: auto; }
.mt { width: 100%; border-collapse: separate; border-spacing: 0; font-size: .84rem; }
.mt th, .mt td { white-space: nowrap; }
.mt th { position: sticky; top: 0; z-index: 2; background: #343a40; color: #fff; padding: .5rem .5rem; text-align: right;
         font-size: .72rem; font-weight: 600; text-transform: uppercase; letter-spacing: .03em; }
.mt th:first-child, .mt td:first-child { text-align: left; }
.mt td { padding: .4rem .5rem; text-align: right; border-bottom: 1px solid rgba(128,128,128,.15); }
.mt td.nom { max-width: 9.5rem; overflow: hidden; text-overflow: ellipsis; }
.mt td.pct { position: relative; min-width: 6.5rem; font-weight: 600; }
.mt td.pct span { position: relative; z-index: 1; }
.mt td.pct i { position: absolute; left: 0; top: 18%; bottom: 18%; border-radius: 3px; background: rgba(231,111,81,.55); }
.mt tbody tr:hover td { background-color: rgba(200,89,15,.12); }
.mt tfoot td { position: sticky; bottom: 0; z-index: 2; font-weight: 700; background: #1f2430; border-top: 2px solid __ACENTO__; border-bottom: none; }
.mt-t { font-weight: 700; font-size: 1rem; margin: 0 0 .5rem; }

/* Variante centrada de las tablas (resumen por gestor) */
.mt.c th, .mt.c td { text-align: center; padding-left: .4rem; padding-right: .4rem; }
.mt.c th { letter-spacing: 0; }
.mt.c th:first-child, .mt.c td:first-child { text-align: left; }
.mt tr.vacio td { opacity: .75; }
.mt .vb { display: inline-block; min-width: 5.4rem; padding: .15rem .6rem; border-radius: .3rem; font-weight: 600; font-size: .8rem; }
.mt .vb-ok { background: #1b8a3a; color: #fff; }
.mt .vb-rev { background: #a68a00; color: #fff; }

/* Filas desplegables (supervisor > estado de llamada) sin JavaScript: casilla oculta + :has() */
.mt .jer-in { display: none; }
.mt tr.hijo { display: none; }
.mt tbody:has(.jer-in:checked) tr.hijo { display: table-row; }
.mt tr.padre label { cursor: pointer; display: inline-block; }
.mt tr.padre .mas::before { content: "⊞"; margin-right: .5rem; opacity: .75; }
.mt tbody:has(.jer-in:checked) tr.padre .mas::before { content: "⊟"; }
.mt tr.padre td { font-weight: 600; }
.mt tr.hijo td { opacity: .85; font-size: .8rem; }
.mt tr.hijo td:first-child { padding-left: 2rem; }

/* Tarjeta contenedora de gráficas */
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: .7rem; }

/* Panel lateral */
[data-testid="stSidebar"] h2 { font-size: 1.05rem; font-weight: 700; padding: 0; margin: .4rem 0 .5rem; }
.st-key-side { min-height: calc(100vh - 6rem); gap: .9rem; }
.st-key-side [data-testid="stWidgetLabel"] p { font-size: .85rem; opacity: .85; }
.st-key-perfil { margin-top: auto; padding-top: .9rem; border-top: 1px solid rgba(128,128,128,.3); }
.perfil-card { display: flex; align-items: center; gap: .75rem; padding-bottom: .9rem; border-bottom: 1px solid rgba(128,128,128,.3); }
.perfil-avatar { width: 2.6rem; height: 2.6rem; border-radius: 50%; background: #2a9d8f; color: #fff;
    display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 1.2rem; flex: none; }
.perfil-nombre { font-weight: 600; line-height: 1.2; }
.perfil-estado { font-size: .78rem; color: #2a9d8f; }
</style>""".replace("__ACENTO__", ACENTO)


def seccion(titulo: str, detalle: str = "") -> None:
    st.markdown(f'<div class="sec">{titulo}<small>{detalle}</small></div>', unsafe_allow_html=True)


COLORES = {"Pagado": "#2a9d8f", "Deuda": "#e76f51"}
COLORES_ESTADO = {
    "CLIENTE PAGO": "#2a9d8f",
    "TERCERO PAGO": "#8ecdc4",
    "CHURN": "#e76f51",
    "CLIENTE DE BAJA": "#9b2226",
}
ESTADOS = list(COLORES_ESTADO)
NOMBRE_CORTO = {"CLIENTE PAGO": "Cliente pagó", "TERCERO PAGO": "Tercero pagó", "CHURN": "Churn", "CLIENTE DE BAJA": "Baja"}


@st.cache_data(ttl=900, show_spinner="Cargando ventas_aliv desde SQL Server…")
def datos(version: float) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # version (mtime de db.py) forma parte de la clave: si cambia la lógica de carga, se recarga sola.
    return load_datos()


def cargar() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(cuotas, ventas, gestión) desde SQL Server; si falla la conexión, muestra el error y detiene la página."""
    try:
        return datos(os.path.getmtime(db.__file__))
    except Exception as e:  # conexión/driver
        st.error(f"No se pudo leer SQL Server: {e}")
        st.stop()


def rango_por_defecto(fechas: pd.Series):
    """(mínimo, máximo, inicio): por defecto se muestra el mes de la última fecha."""
    vmin, vmax = fechas.min().date(), fechas.max().date()
    return vmin, vmax, max(vmin, vmax.replace(day=1))


def panel_lateral(render_filtros):
    """Panel lateral común: perfil arriba, filtros de la página en medio y cerrar sesión al pie."""
    with st.sidebar, st.container(key="side"):
        render_profile()
        st.header("Filtros")
        if st.button("Actualizar datos", icon=":material/refresh:"):
            datos.clear()
            st.rerun()
        filtros = render_filtros()
        with st.container(key="perfil"):
            render_logout()
    return filtros


def soles(x: float) -> str:
    return f"S/ {x:,.0f}"
