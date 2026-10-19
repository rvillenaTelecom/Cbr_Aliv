"""Login simple con usuarios en .streamlit/secrets.toml (contraseñas con hash PBKDF2)."""
import base64
import hashlib
import hmac
import os
import threading
import time
import uuid

import streamlit as st

ITER = 240_000
MAX_DISPOSITIVOS = 2   # sesiones simultáneas permitidas por usuario
TTL_SESION = 10 * 60   # segundos sin actividad tras los cuales una sesión libera su lugar


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


@st.cache_resource
def _registro() -> dict:
    """Sesiones activas por usuario ({usuario: {id_sesion: última_actividad}}); compartido por todos los navegadores."""
    return {"lock": threading.Lock(), "sesiones": {}}


def _tomar_lugar(reg: dict, usuario: str, sid: str, ahora: float, maximo: int = MAX_DISPOSITIVOS, ttl: float = TTL_SESION) -> bool:
    """Registra o renueva la sesión `sid`. Devuelve False si el usuario ya tiene `maximo` dispositivos activos."""
    with reg["lock"]:
        activas = {s: t for s, t in reg["sesiones"].get(usuario, {}).items() if ahora - t < ttl}
        if sid not in activas and len(activas) >= maximo:
            reg["sesiones"][usuario] = activas
            return False
        activas[sid] = ahora
        reg["sesiones"][usuario] = activas
        return True


def _liberar(usuario: str, sid: str) -> None:
    reg = _registro()
    with reg["lock"]:
        reg["sesiones"].get(usuario, {}).pop(sid, None)


def require_login() -> None:
    """Detiene la app hasta que el usuario inicie sesión (máximo MAX_DISPOSITIVOS a la vez por usuario)."""
    user, sid = st.session_state.get("user"), st.session_state.get("sid")
    if user:
        if _tomar_lugar(_registro(), user, sid, time.time()):  # renueva la actividad de esta sesión
            return
        # Otra pantalla ocupó el lugar mientras esta estaba inactiva.
        st.session_state.pop("user")
        st.warning(f"Tu sesión se cerró: ya hay {MAX_DISPOSITIVOS} dispositivos conectados con este usuario.")

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
            nuevo = uuid.uuid4().hex
            if _tomar_lugar(_registro(), u, nuevo, time.time()):
                st.session_state["user"], st.session_state["sid"] = u, nuevo
                st.rerun()
            st.error(f"Este usuario ya está abierto en {MAX_DISPOSITIVOS} dispositivos. "
                     f"Cierra sesión en uno de ellos (o espera {TTL_SESION // 60} min sin actividad) e inténtalo de nuevo.")
        else:
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
        _liberar(st.session_state["user"], st.session_state.get("sid"))  # libera el lugar de inmediato
        st.session_state.pop("user")
        st.rerun()
