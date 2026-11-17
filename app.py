"""ZONA LIBRE: la interfaz de la aplicación (adaptada al caso Brío).
Ya funciona con cualquier modelo exportado con exportar.py. Desde aquí la adaptan a su caso:
cambien textos, orden, gráficos y colores, con ayuda de IA si quieren (PASO 5 de la guía).
Lo único que debe quedar es el pie de página al final.

Para verla en su computador:   streamlit run app.py"""
from pathlib import Path

import pandas as pd
import streamlit as st
import brio

from core import (cargar_config, cargar_metadata, cargar_modelo, cargar_resultados, etiqueta, evaluar,
                  hay_modelo, texto_razon, validar)

config = cargar_config()
st.set_page_config(page_title=config["titulo"], layout="wide")
CARPETA_MODELO = Path(__file__).resolve().parent / "model"


# ---------------------------------------------------------------------------------------------
# Encabezado: título, cliente y descripción vienen de mi_app.py
# ---------------------------------------------------------------------------------------------
col_logo, col_titulo = st.columns([1, 5])
with col_logo:
    try:
        st.image(config["logo"], width=150)
    except Exception:
        pass
with col_titulo:
    st.title(config["titulo"])
    st.caption(f"{config['cliente']} · {config['descripcion']}")


# ---------------------------------------------------------------------------------------------
# Mientras no exporten su modelo, la app muestra la guía en lugar de fallar
# ---------------------------------------------------------------------------------------------
if not hay_modelo():
    st.info("Todavía no hay modelo en la carpeta model/. Sigan la guía del README.")
    st.divider()
    st.caption(config["pie"])
    st.stop()


@st.cache_resource
def recursos():
    return cargar_metadata(), cargar_modelo(), cargar_resultados()


@st.cache_data
def tabla_extra(nombre):
    """Tablas agregadas que exportó la celda 22 (competencia, valor, por equipo)."""
    ruta = CARPETA_MODELO / nombre
    if not ruta.exists():
        return None
    return pd.read_csv(ruta, index_col=0)


meta, modelo, resultados = recursos()
evento = meta["evento"]
unidad = config["unidad"]
m = meta["metricas"]
NOMBRE_PRIORIDAD = {"alta": "🔴 Alta", "media": "🟠 Media", "baja": "🟢 Baja"}

# Brief: "Si al final la regla simple le gana al modelo, la recomendación lo debe decir claramente"
st.info(
    f"**Recomendación:** la **regla simple** decide qué reseñas escalar, porque en la prueba ningún modelo le "
    f"ganó: regla {m['costo_regla']:.0f} frente a modelo {m['costo_modelo']:.0f}, costo {m['unidad_costo']}. "
    "El modelo se usa para **ordenar la cola** por prioridad."
)


def mostrar_resultado(probabilidad, decision, razones):
    """Probabilidad del modelo y sus razones."""
    st.metric(f"Probabilidad de {evento} (modelo)", f"{probabilidad:.0%}")
    if not razones:
        st.caption("Con estos valores ninguna variable mueve la probabilidad frente a un caso típico.")
    else:
        st.markdown("**Lo que más movió la probabilidad del modelo**")
        for r in razones:
            if isinstance(r, dict):
                st.markdown(f"- {texto_razon(r, meta)}")
            else:
                st.markdown(f"- {r}")
        st.caption("Las razones muestran de qué depende la predicción del modelo, no qué pasaría si algo cambiara.")


def formulario_nuevo():
    """Se pega el texto de la reseña y la app calcula sola las 13 variables del modelo (brio.py)."""
    with st.form("nuevo"):
        texto = st.text_area("Texto de la reseña", height=120,
                             placeholder="Ej.: Me robaron la plata y no me llega la transferencia, llevo 3 días")
        estrellas = st.radio("Estrellas", [1, 2, 3], horizontal=True)
        enviado = st.form_submit_button("Evaluar")
    if not enviado:
        return
    if len(texto.split()) < 3:
        st.warning("La reseña es muy corta para decidir si es grave.")
    fila = brio.preparar_resena(texto, estrellas)
    datos, errores, avisos = validar(fila, meta)
    for e in errores:
        st.error(e)
    if errores:
        return
    r = evaluar(modelo, meta, datos)[0]
    escalar = brio.regla(fila) == 1
    equipo = brio.enrutar(fila)
    prioridad = brio.prioridad(escalar, equipo, r["probabilidad"])

    c1, c2, c3 = st.columns(3)
    c1.metric("Decisión (regla simple)", "Escalar" if escalar else "No escalar")
    c2.metric("Equipo sugerido", brio.NOMBRE_EQUIPO[equipo] if escalar else "—")
    c3.metric("Prioridad", NOMBRE_PRIORIDAD[prioridad])
    temas = brio.temas_detectados(fila)
    st.markdown("**Temas detectados en el texto:** " + (", ".join(temas) if temas else "ninguno"))
    mostrar_resultado(r["probabilidad"], r["decision"], r["razones"])
    st.caption("Decide la regla simple; el modelo ordena la cola. Una persona de triaje confirma el equipo.")


def buscar_en_lista():
    col_id = meta.get("columna_id")
    if resultados is None or not col_id or col_id not in resultados.columns:
        st.info("No exportaron una tabla de resultados con columna_id para buscar.")
        return
    elegido = st.selectbox(f"Busquen {unidad} de la bandeja", resultados[col_id].astype(str))
    fila = resultados[resultados[col_id].astype(str) == elegido].iloc[0]
    st.markdown(f"> {fila['text']}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Decisión (regla simple)", fila["regla"])
    equipo = brio.NOMBRE_EQUIPO.get(fila["equipo_sugerido"], fila["equipo_sugerido"])
    c2.metric("Equipo sugerido", equipo if fila["regla"] == "Escalar" else "—")
    c3.metric("Prioridad", NOMBRE_PRIORIDAD.get(fila["prioridad"], fila["prioridad"]))
    razones = [r for r in str(fila.get("razones", "")).split(" · ") if r and r != "nan"]
    mostrar_resultado(float(fila["probabilidad"]), fila["decision"], razones)


def vista_lista():
    """Bandeja de un día cualquiera: 20 reseñas recientes de billeteras ordenadas por prioridad."""
    if resultados is None:
        st.info("Exporten una tabla de resultados (tabla_resultados en exportar) para ver aquí la lista.")
        return
    st.write("20 reseñas recientes de billeteras (2026), revisadas para quitar datos personales, "
             "en el orden en que las atendería el equipo: primero la prioridad alta.")
    t = resultados.copy()
    t["_orden"] = t["prioridad"].map({"alta": 0, "media": 1, "baja": 2})
    t = t.sort_values(["_orden", "probabilidad"], ascending=[True, False])
    t["Prioridad"] = t["prioridad"].map(NOMBRE_PRIORIDAD)
    t["Equipo sugerido"] = [brio.NOMBRE_EQUIPO.get(e, e) if d == "Escalar" else "—"
                            for e, d in zip(t["equipo_sugerido"], t["regla"])]
    t["Probabilidad (modelo)"] = (t["probabilidad"] * 100).round(0).astype(int).astype(str) + " %"
    vista = t[["caso", "Prioridad", "regla", "Equipo sugerido", "Probabilidad (modelo)", "app", "fecha", "text"]]
    vista = vista.rename(columns={"caso": "Caso", "regla": "Decisión (regla)", "app": "App",
                                  "fecha": "Fecha", "text": "Reseña"})
    opciones = list(NOMBRE_PRIORIDAD.values())
    elegidas = st.multiselect("Prioridad", opciones, default=opciones)
    vista = vista[vista["Prioridad"].isin(elegidas)]
    c1, c2, c3 = st.columns(3)
    c1.metric("Reseñas en la bandeja", len(t))
    c2.metric("Para escalar", int((t["regla"] == "Escalar").sum()))
    c3.metric("Prioridad alta", int((t["prioridad"] == "alta").sum()))
    st.dataframe(vista, width="stretch", hide_index=True)


def vista_competencia():
    """Brief: temas de las reseñas negativas y de las quejas formales por app y por tipo de app."""
    c = tabla_extra("competencia.csv")
    if c is None:
        st.info("No hay tabla de competencia exportada (celda 22 del cuaderno).")
        return
    temas = list(brio.NOMBRE_TEMA)
    resenas = c[["pct_" + t for t in temas]].copy() * 100
    resenas.columns = [brio.NOMBRE_TEMA[t] for t in temas]
    quejas = c[["quejas_pct_" + t for t in temas]].copy() * 100
    quejas.columns = resenas.columns

    st.markdown("**Índice de desafecto digital (2026):** reseñas graves estimadas por cada 1.000 reseñas de "
                "la app. Meta propuesta para Brío: menos de 50, el nivel de Nequi.")
    st.bar_chart(c["indice_desafecto"].sort_values(ascending=False), horizontal=True)

    por = st.radio("Ver por", ["Tipo de app", "App"], horizontal=True)
    if por == "Tipo de app":
        st.markdown("**% de las reseñas negativas que toca cada tema**")
        st.bar_chart(resenas.groupby(c["tipo_app"]).mean(), stack=False)
        st.markdown("**% de las quejas formales (Superfinanciera) por tema**")
        st.bar_chart(quejas.groupby(c["tipo_app"]).mean(), stack=False)
    else:
        st.markdown("**% de las reseñas negativas que toca cada tema**")
        st.dataframe(resenas.round(1), width="stretch")
        st.markdown("**% de las quejas formales (Superfinanciera) por tema**")
        st.dataframe(quejas.round(1), width="stretch")
        st.caption("Movii no tiene quejas formales reportadas en el panel.")

    grupos = "; ".join(f"{g}: {', '.join(sorted(c.index[c['grupo'] == g]))}" for g in sorted(c["grupo"].unique()))
    st.markdown(f"**Grupos de K-Means:** {grupos}")
    st.caption("Las billeteras y neobancos del grupo C2 se quejan más de fraude, atención y acceso; los bancos "
               "del C1, de fallas de la app. Es asociación, no causa. Ninguna de estas apps es cliente de Brío.")


def vista_valor():
    c1, c2, c3 = st.columns(3)
    c1.metric("Costo con el modelo", f"{m['costo_modelo']:,.0f}".replace(",", "."))
    c2.metric("Costo con la regla simple", f"{m['costo_regla']:,.0f}".replace(",", "."))
    ahorro = m["costo_regla"] - m["costo_modelo"]
    c3.metric("Ahorro del modelo frente a la regla", f"{ahorro:,.0f}".replace(",", "."))
    st.caption(f"Costos {m['unidad_costo']}, en 200 reseñas de prueba (desde julio de 2025).")
    st.markdown(f"**Regla simple:** {m['regla_simple']}.")
    if "intervalo_diferencia" in m:
        a, b = m["intervalo_diferencia"]
        st.markdown(f"Intervalo de 95 % del ahorro: de {a:.0f} a {b:.0f}. Como incluye el cero, no se puede "
                    "afirmar que el modelo le gane a la regla: **por eso decide la regla**.")

    st.markdown("**Lo que debe esperar Brío**")
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Negativas por día", m.get("Negativas por día (Brío)", "—"))
    d2.metric("Escaladas por día", m.get("Escaladas por día (Brío)", "—"))
    d3.metric("Graves por día", m.get("Graves por día (Brío)", "—"))
    d4.metric("Analistas necesarios", m.get("Analistas necesarios", "—"))
    st.caption(f"Supuesto: {m.get('Usuarios supuestos de Brío (millones)', 5)} millones de usuarios, con la tasa "
               "de reseñas negativas por usuario de Nequi y DaviPlata en 2026. Un analista revisa 40 reseñas al "
               "día; en un día pico llegan unas 2,6 veces más.")
    e = tabla_extra("por_equipo.csv")
    if e is not None and "Escaladas por día (Brío)" in e.columns:
        st.markdown("**Reseñas escaladas por equipo (por día)**")
        st.bar_chart(e.rename(index=brio.NOMBRE_EQUIPO)["Escaladas por día (Brío)"], horizontal=True)
    v = tabla_extra("valor.csv")
    if v is not None:
        st.markdown("**Solo billeteras (como Brío)**")
        st.dataframe(v, width="stretch")


def vista_regla():
    st.markdown(f"""
1. **¿Se escala?** Decide la **regla simple**: {m['regla_simple'].lower()}.
2. **¿A qué equipo?** Al del tema más grave que toque la reseña: fraude → plata → cobros → acceso → fallas →
   atención. Sin tema, va a «otro». Una persona de triaje confirma el equipo.
3. **¿Con qué prioridad?** **Alta** si hay plata en riesgo (fraude, pagos o cobros) o el modelo da 50 % o más;
   **media**, el resto de las escaladas. Si llegan más de las que se pueden atender, la alta va el mismo día.
4. **El modelo** (regresión logística sobre el texto y 12 variables) da la probabilidad de grave. Se usa para
   ordenar la cola, no para decidir. Su regla propia sería:
""")
    filas = []
    limites = [0.0] + meta["umbrales"] + [1.0]
    for i, d in enumerate(meta["decisiones"]):
        filas.append({f"Probabilidad de {evento}": f"{limites[i]:.0%} a {limites[i + 1]:.0%}", "El modelo diría": d})
    st.table(pd.DataFrame(filas))
    st.caption(f"Modelo entrenado con {meta['n_entrenamiento']} reseñas etiquetadas por el equipo; "
               f"exportado el {meta['fecha_exportacion']}.")


# ---------------------------------------------------------------------------------------------
# Cuerpo de la app. PASO 5: adapten pestañas, textos y gráficos a lo que necesita su cliente.
# ---------------------------------------------------------------------------------------------
if config["interfaz"] == "html":
    from core.web import construir_html
    st.iframe(construir_html(), height=820)
    with st.expander(f"Evaluar {unidad} nuevo"):
        formulario_nuevo()
else:
    nombres = [f"Evaluar {unidad}", "Bandeja del día", "Competencia", "Cuánto vale el modelo", "Cómo decide"]
    pestanas = st.tabs(nombres)
    with pestanas[0]:
        modo = st.radio("¿Qué quieren hacer?", ["Pegar una reseña", "Buscar en la bandeja"], horizontal=True)
        if modo == "Pegar una reseña":
            formulario_nuevo()
        else:
            buscar_en_lista()
    with pestanas[1]:
        vista_lista()
    with pestanas[2]:
        vista_competencia()
    with pestanas[3]:
        vista_valor()
    with pestanas[4]:
        vista_regla()


# Pie de página: debe quedar (atribuciones y advertencias de su caso, en mi_app.py)
st.divider()
st.caption(config["pie"])
