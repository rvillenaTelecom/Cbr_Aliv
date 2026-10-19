import html

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import kpis
from comun import cargar, panel_lateral, rango_por_defecto, seccion

st.title("Dashboard de Empleados")

_, _, gestion = cargar()
gestion = gestion.assign(Gestor=gestion["Gestor"].fillna("(sin gestor)"))
gestion["Supervisor"] = gestion["Supervisor"].fillna("(sin dato)")
gestion["Ultimo estado pago"] = gestion["Ultimo estado pago"].fillna("Sin Estado").str.title()
gestion["Estado (filtro)"] = gestion["Estado llamada"].fillna("(sin estado)")


def filtros():
    vmin, vmax, _ = rango_por_defecto(gestion["Fecha Activacion"])
    # Por defecto, los últimos 30 días de altas: las más recientes aún casi no tienen llamadas.
    desde = max(vmin, vmax - pd.Timedelta(days=30))
    rango = st.date_input("Fecha de alta", (desde, vmax), min_value=vmin, max_value=vmax)
    gestor = st.multiselect("Gestor", sorted(gestion["Gestor"].unique()), placeholder="Todos")
    estado = st.multiselect("Estado historial de llamada", sorted(gestion["Estado (filtro)"].unique()), placeholder="Todos")
    return rango, gestor, estado


rango, gestor, estado = panel_lateral(filtros)
if len(rango) != 2:
    st.info("Elige la fecha final del rango.")
    st.stop()

g = gestion[gestion["Fecha Activacion"].between(pd.Timestamp(rango[0]), pd.Timestamp(rango[1]))]
if gestor:
    g = g[g["Gestor"].isin(gestor)]
if estado:
    g = g[g["Estado (filtro)"].isin(estado)]

if g.empty:
    st.warning("Sin datos para los filtros elegidos.")
    st.stop()

seccion("Gestión de llamadas", f"{rango[0]:%d/%m/%Y} – {rango[1]:%d/%m/%Y} · fecha de alta")
kpis.render_gestion(g)

# ---------- Embudo y detalle por gestor ----------
COLOR_LLAMADA = {"No contactado": "#c1121f", "Sin compromiso": "#a68a00", "Compromiso": "#e9c46a",
                 "Ya pagado": "#2a9d8f", "Otros": "#8d99ae"}


def estilo(fig, titulo, height=400):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=64, b=8),
        title=dict(text=f"<b>{titulo}</b>", x=0, xanchor="left", y=.97, yanchor="top", font=dict(size=15)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


m = kpis.metricas_gestion(g)
embudo = go.Figure(go.Funnel(
    y=["Gestionados", "Contactado", "Ya pagado", "Compromiso"],
    x=[m["gestionados"], m["gestionados"] - m["no_contactado"], m["ya_pagado"], m["compromiso"]],
    textinfo="value+percent initial", textposition="auto", textfont=dict(size=13),
    marker=dict(color=["#6c757d", "#457b9d", "#2a9d8f", "#e9a820"]),
    connector=dict(line=dict(color="rgba(128,128,128,.3)")),
))
embudo.update_yaxes(tickfont=dict(size=13))
estilo(embudo, "Embudo de gestión de cobranza")

seccion("Embudo y detalle por gestor", "de cuántos se llamó a cuántos realmente pagaron")
# La gráfica por gestor se filtra por la fecha y hora de la llamada (Fecha Hora Historial LLamadas),
# no por la fecha de alta: tiene su propio rango de fechas. Gestor y estado sí se respetan.
llamadas_con_fecha = gestion["Fecha llamada"].dropna()
l_min, l_max = llamadas_con_fecha.min().date(), llamadas_con_fecha.max().date()
col_f, _ = st.columns([1, 2])
rango_ll = col_f.date_input("Fecha de llamada (gráfica por gestor)", (max(l_min, l_max - pd.Timedelta(days=30)), l_max),
                            min_value=l_min, max_value=l_max,
                            help="La gráfica 'Resultado de la gestión por gestor' usa la fecha y hora de la llamada, no la fecha de alta.")
if len(rango_ll) != 2:
    st.info("Elige la fecha final del rango de llamadas.")
    st.stop()

gl = gestion[(gestion["Fecha llamada"] >= pd.Timestamp(rango_ll[0])) & (gestion["Fecha llamada"] < pd.Timestamp(rango_ll[1]) + pd.Timedelta(days=1))]
if gestor:
    gl = gl[gl["Gestor"].isin(gestor)]
if estado:
    gl = gl[gl["Estado (filtro)"].isin(estado)]
g_llam = gl.assign(Categoria=kpis.categoria_llamada(gl["Estado llamada"])).dropna(subset=["Categoria"])
por_gestor = g_llam.groupby(["Gestor", "Categoria"]).size().reset_index(name="Clientes")
if por_gestor.empty:
    por_gestor = pd.DataFrame({"Gestor": [], "Categoria": [], "Clientes": []})
orden = por_gestor.groupby("Gestor")["Clientes"].sum().sort_values().index.tolist()  # el mayor queda arriba
apilado = px.bar(por_gestor, y="Gestor", x="Clientes", color="Categoria", orientation="h", text="Clientes",
                 color_discrete_map=COLOR_LLAMADA, category_orders={"Gestor": orden, "Categoria": kpis.CATEGORIAS_LLAMADA})
apilado.update_traces(textposition="inside", insidetextanchor="middle", textfont=dict(color="#fff", size=12))
apilado.update_xaxes(title=None, gridcolor="rgba(128,128,128,.2)")
apilado.update_yaxes(title=None)
apilado.update_layout(uniformtext_minsize=10, uniformtext_mode="hide", bargap=.3,
                      legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="left", x=0, title_text="", font=dict(size=11)))
estilo(apilado, "Resultado de la gestión por gestor").update_layout(margin=dict(l=8, r=8, t=64, b=40))

with st.container(key="graficas"):
    c1, c2 = st.columns(2, gap="medium")
with c1.container(border=True):
    st.plotly_chart(embudo, width="stretch")
with c2.container(border=True):
    st.plotly_chart(apilado, width="stretch")


# ---------- Resumen por gestor ----------
UMBRAL_VERACIDAD = 0.15  # efectividad (ya pagado / gestión) por encima de este valor -> "Revisar"
ORDEN = lambda x: (x == "Sin Asignar", x)  # "Sin Asignar" siempre al final


def tabla(columnas: list[str], filas: list[list[str]], pie: list[str], titulo: str) -> str:
    """Tabla HTML centrada, con encabezado y fila de total fijos."""
    th = "".join(f"<th>{c}</th>" for c in columnas)
    cuerpo = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in f) + "</tr>" for f in filas)
    total = "<tr>" + "".join(f"<td>{x}</td>" for x in pie) + "</tr>"
    return (f"<div class='mt-t'>{titulo}</div><div class='mt-w'><table class='mt c'><thead><tr>{th}</tr></thead>"
            f"<tbody>{cuerpo}</tbody><tfoot>{total}</tfoot></table></div>")


def n(x):  # número entero; vacío si es 0, como en Power BI
    return f"{int(x):,}" if x else ""


def veracidad(efectividad: float, hay_pagos: bool) -> str:
    if not hay_pagos:
        return "<span class='vb vb-ok'>✓ Verídico</span>"
    return ("<span class='vb vb-rev'>⚠ Revisar</span>" if efectividad > UMBRAL_VERACIDAD
            else "<span class='vb vb-ok'>✓ Verídico</span>")


est = g["Estado llamada"].fillna("").str.strip().str.lower()
r = g.assign(
    Gestor=g["Gestor"].replace("(sin gestor)", "Sin Asignar"),
    gestionado=(est != "") & (est != "sin asignar"),
    compromiso=est.isin(kpis.COMPROMISO),
    ya_pagado=est.isin(kpis.YA_PAGADO),
)
r["pagado_2mas"] = r["ya_pagado"] & (r["Llamadas"] >= 2)
res = r.groupby("Gestor").agg(gestion=("gestionado", "sum"), llamadas=("Llamadas", "sum"), compromiso=("compromiso", "sum"),
                              ya_pagado=("ya_pagado", "sum"), pagado_2mas=("pagado_2mas", "sum"))


def fila_llamadas(nombre, x):
    ef = x.ya_pagado / x.gestion if x.gestion else 0
    return [nombre, n(x.gestion), n(x.llamadas), f"{x.llamadas / x.gestion:.1f}" if x.gestion else "", n(x.compromiso),
            n(x.ya_pagado), n(x.pagado_2mas), f"{ef:.1%}" if x.ya_pagado else "",
            f"{x.ya_pagado / x.llamadas * 100:.1f}" if x.ya_pagado and x.llamadas else "",
            veracidad(ef, x.ya_pagado > 0) if x.gestion else ""]


filas1 = [fila_llamadas(i, res.loc[i]) for i in sorted(res.index, key=ORDEN)]
tot = res.sum()
cols1 = ["Usuario historial llamada", "Gestión", "Llamadas", "Llam/Cli", "Compromiso", "Ya pagado",
         "Pagado c/gestión 2+", "Efectividad", "Pagos x 100 llam.", "Veracidad"]

# Matriz clientes: gestor x estado de la llamada
r["Estado"] = g["Estado llamada"].fillna("Sin Asignar").str.title()
mat = r.pivot_table(index="Gestor", columns="Estado", values="venta_id", aggfunc="count", fill_value=0)
mat = mat[sorted(mat.columns, key=ORDEN)]
mat["Total"] = mat.sum(axis=1)
filas2 = [[i] + [n(v) for v in mat.loc[i]] for i in sorted(mat.index, key=ORDEN)]
pie2 = ["Total"] + [n(v) for v in mat.sum()]

seccion("Resumen por gestor", "llamadas, efectividad y estado de los clientes")
with st.container(border=True):
    st.markdown(chr(10).join(l.strip() for l in tabla(cols1, filas1, fila_llamadas("Total", tot), "Resumen usuario · llamadas").splitlines()),
                unsafe_allow_html=True)
with st.container(border=True):
    st.markdown(chr(10).join(l.strip() for l in tabla(["Usuario historial llamada"] + list(mat.columns), filas2, pie2,
                                                  "Resumen usuario · clientes").splitlines()), unsafe_allow_html=True)


# ---------- Resumen por supervisor (con detalle desplegable) y llamadas por estado ----------
def tabla_jerarquica(df: pd.DataFrame, padre: str, hijo: str, columna: str, titulo: str) -> str:
    """Filas padre con total y, al pulsar ⊞, el desglose por 'hijo'. Columnas = valores de 'columna'."""
    cols = sorted(df[columna].unique(), key=ORDEN)
    p = df.pivot_table(index=padre, columns=columna, values="venta_id", aggfunc="count", fill_value=0).reindex(columns=cols, fill_value=0)
    h = df.pivot_table(index=[padre, hijo], columns=columna, values="venta_id", aggfunc="count", fill_value=0).reindex(columns=cols, fill_value=0)
    celdas = lambda fila: "".join(f"<td>{n(v)}</td>" for v in list(fila) + [fila.sum()])
    grupos = ""
    for nombre in sorted(p.index, key=ORDEN):
        hijos = "".join(f"<tr class='hijo'><td>{html.escape(str(k))}</td>{celdas(h.loc[(nombre, k)])}</tr>"
                        for k in sorted(h.loc[nombre].index, key=ORDEN))
        grupos += (f"<tbody><tr class='padre'><td><label><input type='checkbox' class='jer-in'><span class='mas'></span>"
                   f"{html.escape(str(nombre))}</label></td>{celdas(p.loc[nombre])}</tr>{hijos}</tbody>")
    pie = "".join(f"<td>{n(v)}</td>" for v in list(p.sum()) + [p.values.sum()])
    th = "".join(f"<th>{c}</th>" for c in [padre] + cols + ["Total"])
    return (f"<div class='mt-t'>{titulo}</div><div class='mt-w'><table class='mt c'><thead><tr>{th}</tr></thead>"
            f"{grupos}<tfoot><tr><td>Total</td>{pie}</tr></tfoot></table></div>")


r["Estado llamada (tabla)"] = g["Estado llamada"].fillna("Sin Asignar").str.title()
seccion("Resumen por supervisor", "clientes por último estado de pago · pulsa ⊞ para ver el estado de la llamada")
with st.container(border=True):
    st.markdown(chr(10).join(l.strip() for l in tabla_jerarquica(
        r, "Supervisor", "Estado llamada (tabla)", "Ultimo estado pago", "Resumen supervisor · clientes").splitlines()),
        unsafe_allow_html=True)

# Matriz gestor x estado de la llamada, con la SUMA de llamadas (# de llamada)
ll = r.pivot_table(index="Gestor", columns="Estado", values="Llamadas", aggfunc="sum", fill_value=0)
ll = ll[sorted(ll.columns, key=ORDEN)]
ll["Total"] = ll.sum(axis=1)
seccion("Llamadas por gestor y estado", "suma de llamadas realizadas")
with st.container(border=True):
    st.markdown(chr(10).join(l.strip() for l in tabla(
        ["Usuario historial llamada"] + list(ll.columns), [[i] + [n(v) for v in ll.loc[i]] for i in sorted(ll.index, key=ORDEN)],
        ["Total"] + [n(v) for v in ll.sum()], "Resumen usuario · llamadas por estado").splitlines()), unsafe_allow_html=True)
