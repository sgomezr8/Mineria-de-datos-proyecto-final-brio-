"""ZONA LIBRE: lo propio del caso Brío que usa la app.
Convierte el texto de una reseña nueva en las mismas columnas con que se entrenó el modelo,
y aplica la regla simple, el enrutamiento a equipos y la prioridad del cuaderno (secciones 7, 9, 18 y 20.4)."""
import re
import unicodedata

import numpy as np
import pandas as pd

# Palabras clave de cada tema. Las columnas tema_ venían calculadas en los datos del curso;
# estas expresiones las reconstruyen y coinciden con las originales en 99,3 % a 99,9 % de las 164.047 negativas.
TEMAS_REGEX = {
    "tema_fraude": r"\b(?:robo|robos|robar|roban|robaron|robado|robada|robando|ladr\w*|estaf\w*|fraud\w*"
                   r"|desaparec(?:e|en|io|ieron|ido|ida)\b|hacke\w*|suplant\w*)|no reconoce|sin autoriz",
    "tema_fallas_app": r"\b(?:lent\w*|actualiz\w*|desactualiz\w*|error\w*|caid\w*|falla\w*|fallan|no funciona\w*"
                       r"|no sirve|no abre|se cierra|no carga|se queda)",
    "tema_plata_no_llega": r"\b(?:dinero\w*|plata\b|transfer\w*|retir\w*|saldo\w*|cajero\w*|devol\w*|devuel\w*"
                           r"|descont\w*|reembols\w*|consign\w*|reten\w*)|no (?:me )?(?:ha )?llega",
    "tema_acceso_bloqueo": r"\b(?:ingresar\b|clave\w*|cedula\w*|codigo\w*|identidad|contrasen\w*|bloque\w*"
                           r"|desbloque\w*|registr\w*|verific\w*|validar|biometr\w*|selfie|civil|iniciar sesion)"
                           r"|no (?:me )?deja entrar",
    "tema_cobros": r"\b(?:cobr\w*|intereses|interes\b|comision\w*|costo\w*|tarifa\w*|cuota de manejo)",
    "tema_atencion": r"\b(?:respuesta\w*|atencion|soporte\w*|asesor\w*|chat\w*|llamar\b|llamada\w*|llamado\w*"
                     r"|pqr\w*|servicio al cliente|nadie responde)",
}
TEMAS = list(TEMAS_REGEX)

# Las mismas variables construidas de la sección 7 del cuaderno (función preparar)
DINERO = r"\$|\d|plata|dinero|saldo|transfer|descont|descuent|cobr|consign|retir|reembols"
ESPERA = (r"hace .{0,10}(hora|dia|semana|mes)|desde (ayer|hace)|llevo .{0,10}(hora|dia|semana|mes)"
          r"|(una|dos|tres|\d+) (horas|dias|semanas|meses)")

# Regla simple (sección 9), enrutamiento (sección 18) y prioridad (sección 20.4)
TEMAS_REGLA = ["tema_fraude", "tema_plata_no_llega", "tema_acceso_bloqueo", "tema_cobros"]
EQUIPO_DE_TEMA = {
    "tema_fraude": "seguridad_fraude",
    "tema_plata_no_llega": "pagos_transferencias",
    "tema_cobros": "cobros_tarifas",
    "tema_acceso_bloqueo": "acceso_identidad",
    "tema_fallas_app": "tecnologia_app",
    "tema_atencion": "servicio_cliente",
}
ORDEN_TEMAS = ["tema_fraude", "tema_plata_no_llega", "tema_cobros", "tema_acceso_bloqueo",
               "tema_fallas_app", "tema_atencion"]
EQUIPOS_PLATA = ["seguridad_fraude", "pagos_transferencias", "cobros_tarifas"]
PROB_ALTA = 0.5

NOMBRE_EQUIPO = {
    "seguridad_fraude": "Seguridad y fraude",
    "pagos_transferencias": "Pagos y transferencias",
    "acceso_identidad": "Acceso e identidad",
    "tecnologia_app": "Tecnología de la app",
    "cobros_tarifas": "Cobros y tarifas",
    "servicio_cliente": "Servicio al cliente",
    "otro": "Otro",
}
NOMBRE_TEMA = {
    "fraude": "Fraude", "fallas_app": "Fallas de la app", "plata_no_llega": "Plata que no llega",
    "acceso_bloqueo": "Acceso o bloqueo", "cobros": "Cobros", "atencion": "Atención",
}


def normalizar(texto):
    """Minúsculas y sin tildes, como la columna texto_n de los datos."""
    texto = unicodedata.normalize("NFKD", str(texto).lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def preparar_resena(texto, estrellas):
    """Una fila con las 13 columnas de entrada del modelo, a partir del texto que pega el usuario."""
    texto = str(texto)
    texto_n = normalizar(texto)
    n_palabras = len(texto.split())
    fila = {"texto_n": texto_n, "score": int(estrellas), "n_palabras": n_palabras}
    for tema, patron in TEMAS_REGEX.items():
        fila[tema] = int(re.search(patron, texto_n) is not None)
    fila["menciona_dinero"] = int(re.search(DINERO, texto_n) is not None)
    fila["menciona_espera"] = int(re.search(ESPERA, texto_n) is not None)
    fila["pct_mayusculas"] = len(re.findall(r"[A-ZÁÉÍÓÚÑ]", texto)) / max(n_palabras, 1)
    fila["n_exclamaciones"] = texto.count("!")
    columnas = ["texto_n", "score", "n_palabras"] + TEMAS + ["menciona_dinero", "menciona_espera",
                                                             "pct_mayusculas", "n_exclamaciones"]
    return pd.DataFrame([fila])[columnas]


def regla(fila):
    """1 si la regla simple escala la reseña."""
    return int(fila[TEMAS_REGLA].sum(axis=1).iloc[0] + fila["menciona_dinero"].iloc[0] > 0)


def enrutar(fila):
    """Equipo del tema más grave que toca la reseña; sin tema va a 'otro'."""
    for tema in ORDEN_TEMAS:
        if fila[tema].iloc[0] == 1:
            return EQUIPO_DE_TEMA[tema]
    return "otro"


def prioridad(escalar, equipo, probabilidad):
    """alta: escalada con plata en riesgo o probabilidad >= 0,5; media: escalada; baja: no escalada."""
    if escalar and (equipo in EQUIPOS_PLATA or probabilidad >= PROB_ALTA):
        return "alta"
    if escalar:
        return "media"
    return "baja"


def temas_detectados(fila):
    return [NOMBRE_TEMA[t.replace("tema_", "")] for t in TEMAS if fila[t].iloc[0] == 1]
