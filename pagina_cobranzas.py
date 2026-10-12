import html

import pandas as pd
import plotly.express as px
import streamlit as st

import kpis
from comun import (COLORES, COLORES_ESTADO, ESTADOS, NOMBRE_CORTO, cargar, panel_lateral, rango_por_defecto,
                   seccion, soles)

st.title("Dashboard de Cobranzas")

df, ventas, _ = cargar()

n_mal = int(df["Monto invalido"].sum())
if n_mal:
    st.warning(f"{n_mal} cuotas tienen un monto inválido en origen (parece un DNI en 'Deuda') y se excluyeron del monto.")

# ---------- Filtros ----------
def filtros():
    vmin, vmax, inicio_mes = rango_por_defecto(df["Fecha Activacion"])
    rango = st.date_input("Fecha de activación", (inicio_mes, vmax), min_value=vmin, max_value=vmax)

    def multi(label, col):
        return st.multiselect(label, sorted(df[col].unique()), placeholder="Todos")

    # Orden de los filtros: cuota, estado de pago (de la cuota), departamento, supervisor, vendedor
    sel = {
        "Cuota": multi("Cuota", "Cuota"),
        "Estado": multi("Estado de pago", "Estado"),
        "Departamento": multi("Departamento", "Departamento"),
        "Supervisor": multi("Supervisor", "Supervisor"),
        "Vendedor": multi("Vendedor", "Vendedor"),
    }
    return rango, sel


rango, sel = panel_lateral(filtros)

if len(rango) != 2:
    st.info("Elige la fecha final del rango.")
    st.stop()

f = df[df["Fecha Activacion"].between(pd.Timestamp(rango[0]), pd.Timestamp(rango[1]))]
for col, vals in sel.items():
    if vals and col != "Cuota":
        f = f[f[col].isin(vals)]
f_umbral = f[f["Estado"].isin(ESTADOS)]  # sin filtro de cuota: el umbral se calcula por M1, M2 y M3
if sel["Cuota"]:
    f = f[f["Cuota"].isin(sel["Cuota"])]

if f.empty:
    st.warning("Sin datos para los filtros elegidos.")
    st.stop()

# ---------- KPIs ----------
# Total = cuotas con alguno de los 4 estados (se excluyen pendientes y sin estado).
fe = f[f["Estado"].isin(ESTADOS)]
n_total = len(fe)
cliente = fe[fe["Estado"] == "CLIENTE PAGO"]
deuda_f = fe[fe["Categoria"] == "Deuda"]
n_churn = int((fe["Estado"] == "CHURN").sum())
n_baja = int((fe["Estado"] == "CLIENTE DE BAJA").sum())

seccion("Resumen de cuotas", f"{rango[0]:%d/%m/%Y} – {rango[1]:%d/%m/%Y} · fecha de activación")
kpis.render(fe)

seccion("Calculadora de umbral", "máximo de cuotas sin pagar tolerado por M1, M2 y M3")
kpis.render_umbral(f_umbral)

# ---------- Seguimiento R1 -> R2 -> R3 ----------
# Base: ventas activadas en el rango, con los filtros de departamento, supervisor y vendedor
# (el filtro de cuota y de estado no aplica: aquí se mira el recorrido completo de cada venta).
vb = ventas[ventas["Fecha Activacion"].between(pd.Timestamp(rango[0]), pd.Timestamp(rango[1]))].copy()
for col in ("Supervisor", "Vendedor"):
    vb[col] = vb[col].fillna("(sin dato)")
for col in ("Departamento", "Supervisor", "Vendedor"):
    if sel[col]:
        vb = vb[vb[col].isin(sel[col])]
alcance = ", ".join(x.title() for x in sel["Departamento"]) if sel["Departamento"] else "Todos los departamentos"
seccion("Seguimiento de ventas activas", "cuántas pagaron cada recibo (cliente o tercero)")
kpis.render_flujo(vb, f"{alcance} · activadas {rango[0]:%d/%m/%Y} – {rango[1]:%d/%m/%Y}")

# ---------- Gráficos ----------
seccion("Montos", "soles por estado y por cuota")
with st.container(key="graficas"):
    c1, c2 = st.columns(2, gap="medium")


def barras(data, x, color, mapa, orden, titulo):
    """Barras agrupadas con etiqueta de monto. Con muchas barras la etiqueta se abrevia (92k) y va vertical."""
    data = data.copy()
    if color == "Estado":  # nombres cortos para que la leyenda quepa en una fila
        data[color] = data[color].map(NOMBRE_CORTO)
        mapa = {NOMBRE_CORTO[k]: v for k, v in mapa.items()}
        orden = [NOMBRE_CORTO[k] for k in orden]
    muchas = len(data) > 8
    fig = px.bar(data, x=x, y="Monto", color=color, color_discrete_map=mapa,
                 category_orders={color: orden}, barmode="group", text="Monto")
    fig.update_traces(texttemplate="%{y:.2s}" if muchas else "S/ %{y:,.0f}", textposition="outside",
                      textfont_size=11 if muchas else 11, textangle=-90 if muchas else 0, cliponaxis=False)
    fig.update_yaxes(tickprefix="S/ ", tickformat=",.0f", title=None, rangemode="tozero",
                     gridcolor="rgba(128,128,128,.2)")
    fig.update_xaxes(title=None)
    fig.update_layout(
        height=400, bargap=.25, bargroupgap=.06, margin=dict(l=8, r=8, t=84, b=8),
        title=dict(text=f"<b>{titulo}</b>", x=0, xanchor="left", y=.97, yanchor="top", font=dict(size=15)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text="",
                    font=dict(size=11), tracegroupgap=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


mes = fe.groupby(["Mes activ.", "Estado"], as_index=False)["Monto"].sum()
fig1 = barras(mes, "Mes activ.", "Estado", COLORES_ESTADO, ESTADOS, "Monto por estado de pago")
fig1.update_xaxes(tickformat="%b %Y", dtick="M1")
cuo = fe.groupby(["Cuota", "Categoria"], as_index=False)["Monto"].sum()
fig2 = barras(cuo, "Cuota", "Categoria", COLORES, ["Pagado", "Deuda"], "Deuda y pagado por cuota")

with c1.container(border=True):
    st.plotly_chart(fig1, width="stretch")
with c2.container(border=True):
    st.plotly_chart(fig2, width="stretch")

# ---------- Morosidad por paquete y distrito ----------
def tabla_mora(data: pd.DataFrame, col: str, titulo: str, minimo: int) -> str:
    """Cuotas sin pagar (churn + baja) por paquete o distrito, con barra en el % y total al pie."""
    sin = data["Categoria"] == "Deuda"
    g = pd.DataFrame({
        "Total": data.groupby(col).size(),
        "Sin pagar": sin.groupby(data[col]).sum(),
        "Monto": data["Monto"].where(sin, 0).groupby(data[col]).sum(),
    })
    g["Pct"] = g["Sin pagar"] / g["Total"]
    g = g[g["Total"] >= minimo].sort_values(["Pct", "Sin pagar"], ascending=False)
    tot_n, tot_s, tot_m = len(data), int(sin.sum()), float(data["Monto"].where(sin, 0).sum())
    top = max(g["Pct"].max(), 0.0001) if len(g) else 1
    filas = "".join(
        f"<tr><td class='nom' title='{html.escape(str(i))}'>{html.escape(str(i))}</td><td>{int(r.Total):,}</td>"
        f"<td>{int(r['Sin pagar']):,}</td><td class='pct'><i style='width:{r.Pct / top * 100:.1f}%'></i><span>{r.Pct:.1%}</span></td>"
        f"<td>S/ {r.Monto:,.0f}</td></tr>"
        for i, r in g.iterrows()
    )
    pie = (f"<tr><td>Total</td><td>{tot_n:,}</td><td>{tot_s:,}</td><td>{tot_s / tot_n:.1%}</td><td>S/ {tot_m:,.0f}</td></tr>"
           if tot_n else "")
    return (f"<div class='mt-t'>{titulo}</div><div class='mt-w'><table class='mt'><thead><tr><th>{col}</th><th>Total</th>"
            f"<th>Sin pagar</th><th>% sin pagar</th><th>S/ sin pagar</th></tr></thead><tbody>{filas}</tbody>"
            f"<tfoot>{pie}</tfoot></table></div>")


seccion("Morosidad por paquete y distrito", "% de cuotas sin pagar (churn + baja) · de mayor a menor")
minimo = st.columns([1, 4])[0].number_input(
    "Mínimo de cuotas por fila", 1, 10_000, 30, 10, key="min_mora",
    help="Oculta paquetes y distritos con pocas cuotas, para que unos pocos casos no distorsionen el %.")
m1, m2 = st.columns(2, gap="medium")
for colum, campo, titulo in ((m1, "Paquete", "Detalle paquete"), (m2, "Distrito", "Detalle distrito")):
    with colum.container(border=True):
        st.markdown(tabla_mora(fe, campo, titulo, int(minimo)), unsafe_allow_html=True)

# ---------- Cuadro por equipo (supervisor) ----------
seccion("Cuotas por equipo", "conteo de cuotas por estado de pago · ordenado por total")
cuadro = (fe.pivot_table(index="Supervisor", columns="Estado", values="Monto", aggfunc="size", fill_value=0)
          .reindex(columns=ESTADOS, fill_value=0))
cuadro["Total general"] = cuadro.sum(axis=1)
cuadro = cuadro.sort_values("Total general", ascending=False, kind="stable")
cuadro.loc["Total general"] = cuadro.sum()
cuadro.index.name = "Equipos"
cuadro.columns = [c.title() if c in ESTADOS else c for c in cuadro.columns]


def tabla_equipos(t: pd.DataFrame) -> str:
    """Tabla HTML con encabezados de color, números centrados y total fijo al pie."""
    cols = list(t.columns)
    colores = {**{e.title(): c for e, c in COLORES_ESTADO.items()}, "Total general": "#495057"}
    oscuro = {"Tercero Pago"}  # fondo claro -> texto oscuro
    celda = lambda v: "" if v == 0 else f"{v:,.0f}"
    th = "".join(
        f'<th style="background:{colores[c]};color:{"#0b2f2b" if c in oscuro else "#fff"}">{c}</th>' for c in cols
    )
    filas = "".join(
        f"<tr><td class='eq'>{html.escape(str(idx))}</td>"
        + "".join(f"<td{' class=tg' if c == 'Total general' else ''}>{celda(r[c])}</td>" for c in cols)
        + "</tr>"
        for idx, r in t.iloc[:-1].iterrows()
    )
    pie = t.iloc[-1]
    pie_html = "<tr><td class='eq'>Total general</td>" + "".join(f"<td>{celda(pie[c])}</td>" for c in cols) + "</tr>"
    return f"""<style>
    .eqw{{max-height:520px;overflow:auto;border-radius:.7rem;border:1px solid rgba(128,128,128,.25)}}
    .eqt{{width:100%;border-collapse:separate;border-spacing:0;font-size:.92rem}}
    .eqt th{{position:sticky;top:0;z-index:2;padding:.6rem .8rem;text-align:center;font-weight:600;
            text-transform:uppercase;font-size:.78rem;letter-spacing:.03em}}
    .eqt th:first-child{{background:#c8590f;color:#fff;text-align:left}}
    .eqt td{{padding:.45rem .8rem;text-align:center;border-bottom:1px solid rgba(128,128,128,.15)}}
    .eqt td.eq{{text-align:left;white-space:nowrap}}
    .eqt td.tg{{font-weight:700;background:rgba(128,128,128,.12)}}
    .eqt tbody tr:nth-child(even) td{{background-color:rgba(128,128,128,.06)}}
    .eqt tbody tr:nth-child(even) td.tg{{background-color:rgba(128,128,128,.16)}}
    .eqt tbody tr:hover td{{background-color:rgba(200,89,15,.15)}}
    .eqt tfoot td{{position:sticky;bottom:0;z-index:2;font-weight:700;font-size:1rem;background:#1f2430;
                  border-top:2px solid #c8590f;border-bottom:none}}
    </style>
    <div class="eqw"><table class="eqt"><thead><tr><th>Equipos</th>{th}</tr></thead>
    <tbody>{filas}</tbody><tfoot>{pie_html}</tfoot></table></div>"""


# Sin sangría: en Markdown 4 espacios al inicio de línea se leen como bloque de código.
st.markdown("\n".join(l.strip() for l in tabla_equipos(cuadro).splitlines()), unsafe_allow_html=True)

# ---------- Detalle para gestión ----------
seccion("Cartera por gestionar")
ids = deuda_f.groupby("venta_id")["Monto"].sum().rename("Deuda total")
gest = ventas.join(ids, on="venta_id", how="inner").sort_values(["Fecha Activacion", "Deuda total"], ascending=[True, False])
gest = gest.drop(columns=["venta_id", "Departamento"], errors="ignore")
st.markdown(f'<div class="sub-titulo">{len(gest):,} clientes con deuda · {soles(gest["Deuda total"].sum())}</div>',
            unsafe_allow_html=True)

cfg = {"Deuda total": st.column_config.NumberColumn(format="S/ %.2f"),
       "Fecha Activacion": st.column_config.DateColumn("Fecha activación", format="DD/MM/YYYY")}
for n in (1, 2, 3):
    cfg[f"Deuda M{n}"] = st.column_config.NumberColumn(format="S/ %.2f")
    cfg[f"Fecha vencimiento M{n}"] = st.column_config.DateColumn(f"Vencimiento M{n}", format="DD/MM/YYYY")
    cfg[f"Fecha pago {n}"] = st.column_config.DateColumn(f"Fecha pago M{n}", format="DD/MM/YYYY")
st.dataframe(gest, width="stretch", hide_index=True, column_config=cfg)
st.download_button("Descargar CSV", gest.to_csv(index=False).encode("utf-8-sig"), "cartera_por_gestionar.csv")
