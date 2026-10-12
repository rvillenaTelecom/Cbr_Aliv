"""Agrega un usuario a .streamlit/secrets.toml:  python make_user.py"""
import getpass
import pathlib
import re

from auth import hash_password

path = pathlib.Path(".streamlit/secrets.toml")
user = input("Usuario: ").strip().lower()
if not re.fullmatch(r"[a-z0-9_.-]+", user):
    raise SystemExit("Usuario inválido (solo letras, números, _ . -)")
pw = getpass.getpass("Contraseña: ")
if len(pw) < 8 or pw != getpass.getpass("Repite la contraseña: "):
    raise SystemExit("Contraseñas distintas o menores a 8 caracteres.")

text = path.read_text(encoding="utf-8") if path.exists() else ""
if "[users]" not in text:
    text += "\n[users]\n"
text = re.sub(rf'^{re.escape(user)}\s*=.*\n?', "", text, flags=re.M)
text = text.replace("[users]\n", f'[users]\n{user} = "{hash_password(pw)}"\n', 1)
path.write_text(text, encoding="utf-8")
print(f"Usuario '{user}' guardado.")
