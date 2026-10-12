"""Indicadores de cobranza: resumen, barra de composición y detalle por estado."""
import pandas as pd
import streamlit as st

ESTADOS = {  # estado de la cuota -> (etiqueta, color)
    "CLIENTE PAGO": ("Cliente pagó", "#2a9d8f"),
    "TERCERO PAGO": ("Tercero pagó", "#8ecdc4"),
    "CHURN": ("Churn", "#e76f51"),
    "CLIENTE DE BAJA": ("Cliente de baja", "#9b2226"),
}
ACTIVOS = ("CLIENTE PAGO", "TERCERO PAGO")
SIN_PAGAR = ("CHURN", "CLIENTE DE BAJA")

CSS = """<style>
.kp-grid{display:grid;gap:.75rem;margin:0 0 .75rem}.kp-grid:last-child{margin-bottom:0}
.kp-card{background:rgba(128,128,128,.10);border-radius:.6rem;padding:.9rem 1.1rem;border-left:5px solid var(--c,#888);display:flex;flex-direction:column;gap:.15rem}
.kp-lbl{font-size:.8rem;opacity:.75;text-transform:uppercase;letter-spacing:.04em}
.kp-big{font-size:1.9rem;font-weight:700;line-height:1.2}
.kp-sub{font-size:.88rem;opacity:.85}
.kp-pct{font-weight:600}
.fl{display:grid;grid-template-columns:1.1fr auto 1fr 1fr 1fr;gap:.75rem;align-items:stretch}
.fl-card{border-radius:.6rem;padding:1rem .8rem;text-align:center;display:flex;flex-direction:column;justify-content:center;gap:.2rem;
  background:rgba(42,157,143,.16);border:1px solid rgba(42,157,143,.45)}
.fl-base{background:rgba(128,128,128,.10);border:1px solid rgba(128,128,128,.35)}
.fl-n{font-size:2rem;font-weight:700;line-height:1.15}
.fl-l{font-size:.95rem;font-weight:600}
.fl-s{font-size:.78rem;opacity:.8;line-height:1.35}
.fl-warn{color:#e9c46a;font-weight:600}
.fl-arrow{align-self:center;font-size:1.6rem;opacity:.55;padding:0 .1rem}
@media (max-width:1150px){.fl{grid-template-columns:1fr 1fr}.fl-arrow{display:none}.fl-base{grid-column:1/-1}}
.kp-ok{--c:#2a9d8f}.kp-bad{--c:#e76f51}
.kp-badge{display:inline-block;align-self:flex-start;margin-top:.4rem;padding:.1rem .55rem;border-radius:1rem;font-size:.8rem;font-weight:600;
  background:color-mix(in srgb,var(--c) 22%,transparent);color:var(--c)}
.kp-bar{display:flex;height:.9rem;border-radius:.5rem;overflow:hidden;margin:0 0 .75rem}
.kp-bar div{height:100%}
</style>"""


def _metricas(fe: pd.DataFrame) -> dict:
    total_n = len(fe)

    def agrega(estados):
        s = fe[fe["Estado"].isin(estados)]
        return {"n": len(s), "monto": float(s["Monto"].sum()), "pct": len(s) / total_n if total_n else 0.0}

    m = {e: agrega([e]) for e in ESTADOS}
    m["ACTIVOS"], m["SIN_PAGAR"] = agrega(ACTIVOS), agrega(SIN_PAGAR)
    m["TOTAL"] = {"n": total_n, "monto": float(fe["Monto"].sum()), "pct": 1.0}
    return m


def _s(x): return f"S/ {x:,.0f}"
def _p(x): return f"{x:.1%}"


def _card(label, d, color, big="monto"):
    principal = _s(d["monto"]) if big == "monto" else f'{d["n"]:,}'
    return (f'<div class="kp-card" style="--c:{color}"><div class="kp-lbl">{label}</div>'
            f'<div class="kp-big">{principal}</div>'
            f'<div class="kp-sub">{d["n"]:,} cuotas · <span class="kp-pct">{_p(d["pct"])}</span></div></div>')


def _render(m):
    """Resumen (total / activos / sin pagar), barra de composición y detalle por estado."""
    t = m["TOTAL"]
    barra = "".join(f'<div style="width:{m[e]["pct"]*100:.2f}%;background:{ESTADOS[e][1]}" '
                    f'title="{ESTADOS[e][0]} {_p(m[e]["pct"])}"></div>' for e in ESTADOS)
    resumen = (
        f'<div class="kp-grid" style="grid-template-columns:repeat(auto-fit,minmax(190px,1fr))">'
        f'{_card("Total cuotas", t, "#6c757d", big="n")}'
        f'{_card("Activos (cliente + tercero)", m["ACTIVOS"], "#2a9d8f")}'
        f'{_card("Sin pagar (churn + baja)", m["SIN_PAGAR"], "#e76f51")}</div>'
    )
    leyenda = "".join(
        f'<div class="kp-card" style="--c:{ESTADOS[e][1]}"><div class="kp-lbl">{ESTADOS[e][0]}</div>'
        f'<div class="kp-big" style="font-size:1.5rem">{_p(m[e]["pct"])}</div>'
        f'<div class="kp-sub">{m[e]["n"]:,} · {_s(m[e]["monto"])}</div></div>' for e in ESTADOS)
    st.markdown(f'{resumen}<div class="kp-bar">{barra}</div>'
                f'<div class="kp-grid" style="grid-template-columns:repeat(auto-fit,minmax(140px,1fr))">{leyenda}</div>',
                unsafe_allow_html=True)


def render(fe: pd.DataFrame) -> None:
    _render(_metricas(fe))


UMBRALES = {"M1": 4.5, "M2": 3.5, "M3": 2.5}  # % del total de cuotas que se tolera sin pagar


def render_umbral(fe: pd.DataFrame) -> None:
    """Calculadora de umbral: máximo de cuotas sin pagar tolerado por M1, M2 y M3 (% del total de cuotas)."""
    tarjetas_ph = st.container()  # las tarjetas van arriba; el ajuste de % queda debajo
    with st.expander("Ajustar % de umbral (sobre el total de cuotas)"):
        cols = st.columns(3)
        pct = {m: cols[i].number_input(f"{m} (%)", 0.0, 100.0, v, 0.5, key=f"umbral_{m}")
               for i, (m, v) in enumerate(UMBRALES.items())}

    tarjetas = ""
    for m, p in pct.items():
        s = fe[fe["Cuota"] == m]
        total = len(s)
        sin_pagar = int(s["Estado"].isin(SIN_PAGAR).sum())
        umbral = round(total * p / 100)
        exceso = sin_pagar - umbral
        ok = exceso <= 0
        badge = (f"✔ Dentro del umbral · margen {-exceso:,}" if ok else f"⚠ Excede por {exceso:,} cuotas")
        tarjetas += (
            f'<div class="kp-card {"kp-ok" if ok else "kp-bad"}"><div class="kp-lbl">{m} · umbral {p:g}% de {total:,}</div>'
            f'<div class="kp-big">{umbral:,}</div>'
            f'<div class="kp-sub">Sin pagar: <b>{sin_pagar:,}</b> ({sin_pagar / total:.1%} del total)</div>'
            f'<span class="kp-badge">{badge}</span></div>' if total else
            f'<div class="kp-card"><div class="kp-lbl">{m}</div><div class="kp-sub">Sin cuotas en el filtro</div></div>'
        )
    tarjetas_ph.markdown(f'<div class="kp-grid" style="grid-template-columns:repeat(auto-fit,minmax(190px,1fr))">{tarjetas}</div>',
                         unsafe_allow_html=True)


def render_flujo(base: pd.DataFrame, detalle: str) -> None:
    """Seguimiento de las ventas activas: cuántas pagaron el recibo 1, 2 y 3 (cliente o tercero).

    Un recibo cuenta como emitido si tiene un estado real (pagó, churn o baja). Además se avisa cuando un recibo ya
    debería haber vencido (vencimiento de R1 + n-1 meses) y la base no trae datos: así no se confunde con "nadie pagó".
    """
    n_base = len(base)
    hoy = pd.Timestamp.today().normalize()
    reales = ACTIVOS + SIN_PAGAR
    tarjetas, prev = "", None
    for n in (1, 2, 3):
        estado = base[f"Estado M{n}"]
        emitido = estado.isin(reales)
        pagaron = int(estado.isin(ACTIVOS).sum())
        n_emit = int(emitido.sum())
        venc = base["Fecha vencimiento M1"] + pd.DateOffset(months=n - 1)  # vencimiento esperado de Rn
        sin_dato = int(((venc < hoy) & ~emitido).sum())
        proximo = venc[venc >= hoy].min()
        aviso = (f"<br><span class='fl-warn'>⚠ {sin_dato:,} con R{n} vencido y sin datos en la base</span>" if sin_dato else "")
        if n_emit == 0:
            num = "--"
            sub = ("sin datos cargados" if sin_dato else
                   f"vence el {proximo:%d/%m/%Y}" if pd.notna(proximo) else "sin recibos emitidos")
        else:
            num = f"{pagaron:,}"
            sub = f"{pagaron / n_base:.1%} de la base" if n_base else ""
            if prev:
                sub += f" · {pagaron / prev:.1%} de R{n - 1}"
            if n_emit != n_base:  # si todas las ventas ya tienen el recibo, la línea sería repetida
                sub += f"<br>{pagaron / n_emit:.1%} de {n_emit:,} con R{n} emitido"
            prev = pagaron
        tarjetas += (f'<div class="fl-card"><div class="fl-n">{num}</div><div class="fl-l">Pagaron R{n}</div>'
                     f'<div class="fl-s">{sub}{aviso}</div></div>')
    st.markdown(
        f'<div class="fl"><div class="fl-card fl-base"><div class="fl-n">{n_base:,}</div>'
        f'<div class="fl-l">Ventas activas</div><div class="fl-s">{detalle}</div></div>'
        f'<div class="fl-arrow">➜</div>{tarjetas}</div>',
        unsafe_allow_html=True,
    )


# ---------- Página de empleados: gestión de llamadas ----------
# Estados del historial de llamadas (se comparan sin importar mayúsculas, como en DAX).
YA_PAGADO = {"ya pagado"}
COMPROMISO = {"contesta - compromiso", "contesta - nuevo compromiso", "si hay compromiso"}
NO_CONTACTADO = {"no contesta", "no recibe llamadas", "no responde corta", "numero equivocado"}


def metricas_gestion(g: pd.DataFrame) -> dict:
    """Medidas A_M del modelo de Power BI, calculadas sobre las ventas (una fila por venta)."""
    est = g["Estado llamada"].fillna("").str.strip().str.lower()
    gestionada = (est != "") & (est != "sin asignar")  # <> "Sin Asignar" y <> BLANK()
    n_gest = int(gestionada.sum())
    no_contactado = int(est.isin(NO_CONTACTADO).sum())
    return {
        "ventas": len(g),
        "gestionados": n_gest,
        "llamadas": int(g["Llamadas"].sum()),
        "ya_pagado": int(est.isin(YA_PAGADO).sum()),
        "compromiso": int(est.isin(COMPROMISO).sum()),
        "no_contactado": no_contactado,
        "tasa_contacto": (n_gest - no_contactado) / n_gest if n_gest else 0.0,
    }


def render_gestion(g: pd.DataFrame) -> None:
    m = metricas_gestion(g)
    n = m["gestionados"]
    pct = lambda x: f"{x / n:.1%}" if n else "–"

    def card(label, big, sub, color):
        return (f'<div class="kp-card" style="--c:{color}"><div class="kp-lbl">{label}</div>'
                f'<div class="kp-big">{big}</div><div class="kp-sub">{sub}</div></div>')

    tarjetas = (
        card("Clientes gestionados", f"{n:,}", f"{n / m['ventas']:.1%} de {m['ventas']:,} ventas" if m["ventas"] else "", "#6c757d")
        + card("Total llamadas", f"{m['llamadas']:,}", f"{m['llamadas'] / n:.1f} por cliente gestionado" if n else "", "#457b9d")
        + card("Llamada ya pagado", f"{m['ya_pagado']:,}", f"{pct(m['ya_pagado'])} de los gestionados", "#2a9d8f")
        + card("Llamada compromiso", f"{m['compromiso']:,}", f"{pct(m['compromiso'])} de los gestionados", "#e9c46a")
        + card("% Tasa de contacto", f"{m['tasa_contacto']:.1%}",
               f"{n - m['no_contactado']:,} contactados · {m['no_contactado']:,} no contactados", "#c8590f")
    )
    st.markdown(f'<div class="kp-grid" style="grid-template-columns:repeat(auto-fit,minmax(190px,1fr))">{tarjetas}</div>',
                unsafe_allow_html=True)


SIN_COMPROMISO = {"contesta - no hay compromiso", "no hay compromiso"}
CATEGORIAS_LLAMADA = ["No contactado", "Sin compromiso", "Compromiso", "Ya pagado", "Otros"]


def categoria_llamada(estado: pd.Series) -> pd.Series:
    """Agrupa el estado del historial de llamadas en 5 categorías (las ventas sin gestión quedan fuera)."""
    est = estado.fillna("").str.strip().str.lower()
    cat = pd.Series("Otros", index=est.index)  # contesta teléfono 1/2, incumple compromiso/promesa
    cat[est.isin(NO_CONTACTADO)] = "No contactado"
    cat[est.isin(SIN_COMPROMISO)] = "Sin compromiso"
    cat[est.isin(COMPROMISO)] = "Compromiso"
    cat[est.isin(YA_PAGADO)] = "Ya pagado"
    cat[(est == "") | (est == "sin asignar")] = None
    return cat
