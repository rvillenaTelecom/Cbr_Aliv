"""Conexión a SQL Server y transformación de ventas_aliv a formato largo (1 fila por cuota)."""
import os
import urllib.parse

import pandas as pd
import pyodbc
from sqlalchemy import create_engine, event

# Local: Windows Auth contra SQLEXPRESS. Nube (Azure SQL): definir ALIV_SQL_USER / ALIV_SQL_PASSWORD.
SERVER = os.getenv("ALIV_SQL_SERVER", r"localhost\SQLEXPRESS")
DATABASE = os.getenv("ALIV_SQL_DB", "Aliv_DB")
DRIVER = os.getenv("ALIV_SQL_DRIVER", "ODBC Driver 18 for SQL Server")
SQL_USER = os.getenv("ALIV_SQL_USER")
SQL_PASSWORD = os.getenv("ALIV_SQL_PASSWORD", "")
CHARSET = os.getenv("ALIV_SQL_CHARSET", "cp1252")  # codificación de los varchar en la base

# Solo las columnas que usa el dashboard (la tabla tiene 70+, con datos personales sensibles).
COLS_VENTA = [
    "Contrato", "Nombre y Apellidos", "Telefono contacto", "Departamento", "Distrito",
    "Vendedor", "Supervisor", "Canal", "Paquete", "Fecha Activacion", "Estado de Pago",
]
CUOTAS = [1, 2, 3, 4]
COLS_TABLA = ["DNI/Carnet Extraj.", "Usuario"]  # solo para la tabla de gestión
CUOTAS_TABLA = [1, 2, 3]  # la tabla de gestión muestra M1-M3
COLS_LLAMADAS = ["Estado Historial LLamadas", "Usuario Historial LLamadas", "# de llamada", "Fecha Hora Historial LLamadas"]

MONTO_MAX = 2000  # montos mayores son errores de captura (p.ej. un DNI digitado en Deuda)

PAGADO = {"CLIENTE PAGO", "TERCERO PAGO"}
SIN_PAGAR = {"CHURN", "CLIENTE DE BAJA"}


def get_engine():
    if SQL_USER:
        pwd = SQL_PASSWORD.replace("}", "}}")  # escape ODBC
        auth = f"UID={SQL_USER};PWD={{{pwd}}};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    else:
        auth = "Trusted_Connection=yes;TrustServerCertificate=yes;"
    odbc = f"DRIVER={{{DRIVER}}};SERVER={SERVER};DATABASE={DATABASE};{auth}"
    engine = create_engine("mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(odbc), pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def _charset(dbapi_conn, _):
        # Los varchar se guardan en Windows-1252; sin esto el driver los lee como UTF-8 (tildes rotas).
        dbapi_conn.setdecoding(pyodbc.SQL_CHAR, encoding=CHARSET)

    return engine


def _select_sql() -> str:
    cols = [f"[{c}]" for c in dict.fromkeys(COLS_VENTA + COLS_TABLA + COLS_LLAMADAS)]
    for n in CUOTAS:
        cols += [f"[Fecha vencimiento M{n}]", f"[Deuda M{n}]", f"[Estado M{n}]", f"[Fecha pago {n}]"]
    return f"SELECT {', '.join(cols)} FROM dbo.ventas_aliv"


def _fecha(s: pd.Series) -> pd.Series:
    s = s.replace({"NULL": None, "00-00-0000": None, "": None})
    return pd.to_datetime(s, format="%d-%m-%Y", errors="coerce")


def _ventas_ancho(raw: pd.DataFrame) -> pd.DataFrame:
    """Una fila por venta, con M1-M3 en columnas (para la tabla de gestión)."""
    v = pd.DataFrame({"venta_id": raw.index})
    for c in ("DNI/Carnet Extraj.", "Nombre y Apellidos", "Telefono contacto", "Supervisor", "Vendedor"):
        v[c] = raw[c].str.strip()
    v["Fecha Activacion"] = raw["Fecha Activacion"]
    v["Estado de Pago"] = raw["Estado de Pago"]
    for n in CUOTAS_TABLA:
        v[f"Fecha vencimiento M{n}"] = _fecha(raw[f"Fecha vencimiento M{n}"])
        monto = pd.to_numeric(raw[f"Deuda M{n}"], errors="coerce")
        v[f"Deuda M{n}"] = monto.where(monto <= MONTO_MAX)
        v[f"Estado M{n}"] = raw[f"Estado M{n}"].str.strip()
        v[f"Fecha pago {n}"] = _fecha(raw[f"Fecha pago {n}"])
    v["Usuario"] = raw["Usuario"]
    v["Departamento"] = raw["Departamento"].fillna("(sin dato)").str.strip()  # solo para filtrar
    return v


def _gestion(raw: pd.DataFrame) -> pd.DataFrame:
    """Una fila por venta con su último estado de llamada (para la página de empleados)."""
    g = pd.DataFrame({"venta_id": raw.index, "Fecha Activacion": raw["Fecha Activacion"]})
    g["Gestor"] = raw["Usuario Historial LLamadas"].str.strip().str.upper().replace("", None)
    g["Estado llamada"] = raw["Estado Historial LLamadas"].str.strip().replace("", None)
    g["Llamadas"] = pd.to_numeric(raw["# de llamada"], errors="coerce").fillna(0).astype(int)
    g["Fecha llamada"] = pd.to_datetime(raw["Fecha Hora Historial LLamadas"], format="%d-%m-%Y %H:%M:%S", errors="coerce")
    g["Supervisor"] = raw["Supervisor"].str.strip().replace("", None)
    # Último estado de pago, igual que la vista v_ventas_aliv_completa: M3, si no M2, si no M1,
    # saltando "Pendiente recibo anterior" y los vacíos; si no hay ninguno queda sin estado.
    ultimo = pd.Series(None, index=raw.index, dtype="object")
    for n in (1, 2, 3):  # el último que tenga valor sobrescribe al anterior
        est = raw[f"Estado M{n}"].str.strip().replace("", None)
        ultimo = est.where(est.notna() & (est.str.upper() != "PENDIENTE RECIBO ANTERIOR")).combine_first(ultimo)
    g["Ultimo estado pago"] = ultimo
    return g


def load_datos() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(cuotas en formato largo, ventas en formato ancho, gestión de llamadas). Una sola consulta a SQL Server."""
    with get_engine().connect() as con:
        raw = pd.read_sql(_select_sql(), con)
    raw = raw.replace({"NULL": None})
    raw["Fecha Activacion"] = _fecha(raw["Fecha Activacion"])
    return _cuotas_largo(raw), _ventas_ancho(raw), _gestion(raw)


def load_cuotas() -> pd.DataFrame:
    return load_datos()[0]


def _cuotas_largo(raw: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (venta, cuota) con fechas y montos ya tipados."""
    base = raw[COLS_VENTA].copy()
    base["venta_id"] = raw.index

    partes = []
    for n in CUOTAS:
        p = base.copy()
        p["Cuota"] = f"M{n}"
        p["Vencimiento"] = _fecha(raw[f"Fecha vencimiento M{n}"])
        monto = pd.to_numeric(raw[f"Deuda M{n}"], errors="coerce").fillna(0.0)
        p["Monto invalido"] = monto > MONTO_MAX
        p["Monto"] = monto.where(~p["Monto invalido"], 0.0)
        p["Estado"] = raw[f"Estado M{n}"].str.strip()
        p["Fecha pago"] = _fecha(raw[f"Fecha pago {n}"])
        partes.append(p)

    df = pd.concat(partes, ignore_index=True)
    # Cuotas inexistentes: sin vencimiento y sin monto.
    df = df[df["Vencimiento"].notna() | (df["Monto"] > 0)].copy()
    # Pagado = cliente o tercero pagó. Deuda (sin pagar) = churn o cliente de baja.
    # El resto (p.ej. PENDIENTE RECIBO ANTERIOR o sin estado) queda como "Otro".
    df["Categoria"] = "Otro"
    df.loc[df["Estado"].isin(PAGADO), "Categoria"] = "Pagado"
    df.loc[df["Estado"].isin(SIN_PAGAR), "Categoria"] = "Deuda"
    df["Mes activ."] = df["Fecha Activacion"].dt.to_period("M").dt.to_timestamp()
    df["Mes venc."] = df["Vencimiento"].dt.to_period("M").dt.to_timestamp()
    hoy = pd.Timestamp.today().normalize()
    df["Dias vencido"] = (hoy - df["Vencimiento"]).dt.days
    df["Estado"] = df["Estado"].replace("", None).fillna("(sin estado)")
    for c in ("Departamento", "Distrito", "Vendedor", "Supervisor", "Canal", "Paquete"):
        df[c] = df[c].fillna("(sin dato)").str.strip()
    return df
