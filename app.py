import importlib

import streamlit as st

import auth
import db
import kpis

# Streamlit no siempre recarga los módulos auxiliares al editarlos; se fuerza para evitar versiones viejas.
import comun

for _m in (db, auth, kpis, comun):
    importlib.reload(_m)
from auth import require_login

st.set_page_config(page_title="Cobranzas Aliv", layout="wide")
require_login()
st.html(kpis.CSS + comun.ESTILO)

paginas = st.navigation(
    [
        st.Page("pagina_cobranzas.py", title="Dashboard cobranzas", icon=":material/payments:", default=True),
        st.Page("pagina_empleados.py", title="Empleados", icon=":material/support_agent:"),
    ],
    position="top",
)
paginas.run()
