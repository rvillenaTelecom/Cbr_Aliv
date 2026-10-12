"""Login simple con usuarios en .streamlit/secrets.toml (contraseñas con hash PBKDF2)."""
import base64
import hashlib
import hmac
import os

import streamlit as st

ITER = 240_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITER)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def _verify(password: str, stored: str) -> bool:
    salt_b64, dk_b64 = stored.split("$")
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), ITER)
    return hmac.compare_digest(dk, base64.b64decode(dk_b64))


def _cargar_usuarios() -> dict:
    """Usuarios desde .streamlit/secrets.toml ([users]) o, en la nube, de ALIV_USERS="user:hash;user2:hash2"."""
    try:
        return dict(st.secrets["users"])
    except Exception:
        pass
    pares = (p.split(":", 1) for p in os.getenv("ALIV_USERS", "").split(";") if ":" in p)
    return {u.strip().lower(): h.strip() for u, h in pares}


def require_login() -> None:
    """Detiene la app hasta que el usuario inicie sesión."""
    if st.session_state.get("user"):
        return

    users = _cargar_usuarios()
    if not users:
        st.error("No hay usuarios configurados. Crea uno con: python make_user.py")
        st.stop()

    st.title("Cobranzas Aliv")
    with st.form("login"):
        u = st.text_input("Usuario").strip().lower()
        p = st.text_input("Contraseña", type="password")
        ok = st.form_submit_button("Ingresar")
    if ok:
        if u in users and _verify(p, users[u]):
            st.session_state["user"] = u
            st.rerun()
        st.error("Usuario o contraseña incorrectos.")
    st.stop()


def render_profile() -> None:
    """Tarjeta de perfil con avatar (va arriba del panel lateral)."""
    user = st.session_state["user"]
    nombre = user.replace(".", " ").replace("_", " ").title()
    st.markdown(
        f"""<div class="perfil-card">
              <div class="perfil-avatar">{nombre[0]}</div>
              <div><div class="perfil-nombre">{nombre}</div>
              <div class="perfil-estado">● Sesión activa</div></div>
            </div>""",
        unsafe_allow_html=True,
    )


def render_logout() -> None:
    """Botón de cerrar sesión (va al pie del panel lateral)."""
    if st.button("Cerrar sesión", width="stretch", icon=":material/logout:"):
        st.session_state.pop("user")
        st.rerun()
