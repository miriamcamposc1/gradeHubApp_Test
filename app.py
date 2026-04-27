"""
app.py
Interfaz Streamlit del Hub de Sincronización de Calificaciones.

Flujo principal:
1. Configurar grupo + plantilla de orden (una sola vez por grupo).
2. Subir archivo de Classroom y Excel Oficial.
3. La app hace fuzzy matching de tareas y reordena Classroom.
4. La maestra revisa/edita en st.data_editor (con discrepancias resaltadas).
5. Descarga Excel y/o PDF listo para imprimir.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

import database as db
import processor as proc

# ---------- Ambiente activo ----------
STREAMLIT_ENV = os.environ.get("STREAMLIT_ENV", "dev")

st.set_page_config(
    page_title="Hub de Calificaciones",
    page_icon="📘",
    layout="wide",
)

# Banner de ambiente (visible solo en dev/qa para evitar confusiones)
if STREAMLIT_ENV == "dev":
    st.caption("🟢 **Ambiente: DEV** — ejecución local")
elif STREAMLIT_ENV == "qa":
    st.warning("🟡 **Ambiente: QA** — datos de prueba", icon="🧪")

db.init_db()


# ---------- Sidebar: gestión de grupos ----------

st.sidebar.title("📚 Grupos")

with st.sidebar.expander("➕ Crear grupo nuevo"):
    nuevo_nombre = st.text_input("Nombre del grupo", key="nuevo_grupo_nombre")
    nuevo_ciclo = st.text_input("Ciclo escolar (opcional)", key="nuevo_grupo_ciclo")
    if st.button("Crear", key="btn_crear_grupo"):
        if nuevo_nombre.strip():
            db.crear_grupo(nuevo_nombre.strip(), nuevo_ciclo.strip() or None)
            st.success(f"Grupo '{nuevo_nombre}' creado.")
            st.rerun()

grupos = db.listar_grupos()
if not grupos:
    st.sidebar.info("Crea tu primer grupo para empezar.")
    st.title("📘 Hub de Calificaciones")
    st.write("Crea un grupo en la barra lateral para comenzar.")
    st.stop()

opciones = {f"{g['nombre']} ({g['ciclo'] or 's/c'})": g["id"] for g in grupos}
seleccion = st.sidebar.selectbox("Grupo activo", list(opciones.keys()))
grupo_id = opciones[seleccion]

# Obtener datos del grupo seleccionado para edición
_grupo_actual = next(g for g in grupos if g["id"] == grupo_id)

with st.sidebar.expander("✏️ Editar grupo"):
    edit_nombre = st.text_input("Nombre", value=_grupo_actual["nombre"], key="edit_grupo_nombre")
    edit_ciclo = st.text_input("Ciclo escolar", value=_grupo_actual["ciclo"] or "", key="edit_grupo_ciclo")
    col_save, col_del = st.columns(2)
    with col_save:
        if st.button("💾 Guardar", key="btn_editar_grupo"):
            if edit_nombre.strip():
                db.editar_grupo(grupo_id, edit_nombre.strip(), edit_ciclo.strip() or None)
                st.success("Grupo actualizado.")
                st.rerun()
    with col_del:
        if st.button("🗑️ Eliminar", key="btn_eliminar_grupo", type="primary"):
            db.eliminar_grupo(grupo_id)
            st.success("Grupo eliminado.")
            st.rerun()


# ---------- Pestañas principales ----------

tab_alumnos, tab_plantilla, tab_sync, tab_historial = st.tabs(
    ["👩‍🎓 Alumnos", "🧩 Plantilla de orden", "🔄 Sincronizar", "📜 Historial"]
)


# ---------- Tab Alumnos ----------

with tab_alumnos:
    st.subheader("Alumnos del grupo")
    alumnos = db.listar_alumnos(grupo_id)
    if alumnos:
        df_alumnos = pd.DataFrame(alumnos)
        cols_show = ["numero_lista", "nombre", "identificador"]
        cols_show = [c for c in cols_show if c in df_alumnos.columns]
        st.dataframe(df_alumnos[cols_show], use_container_width=True)
    else:
        st.info("Aún no hay alumnos. Agrégalos manualmente o impórtalos desde un archivo.")

    col1, col2 = st.columns(2)
    with col1:
        with st.form("form_alumno"):
            nombre = st.text_input("Nombre completo")
            ident = st.text_input("Identificador / matrícula (opcional)")
            if st.form_submit_button("Agregar alumno") and nombre.strip():
                db.agregar_alumno(grupo_id, nombre.strip(), ident.strip() or None)
                st.success("Alumno agregado.")
                st.rerun()

    with col2:
        st.write("**Importar lista desde archivo**")
        archivo_alumnos = st.file_uploader(
            "CSV o XLSX con columna de nombres",
            type=["csv", "xlsx"],
            key="import_alumnos",
        )
        if archivo_alumnos:
            df_imp = proc.leer_archivo(archivo_alumnos)
            col_nombre = proc.detectar_columna_alumno(df_imp)
            col_num_lista = proc.detectar_columna_numero_lista(df_imp)

            st.write(f"Columna de nombre detectada: `{col_nombre}`")
            if col_num_lista:
                st.write(f"Columna de No. de lista detectada: `{col_num_lista}`")
            else:
                st.caption("No se detectó columna de número de lista.")

            # Vista previa
            cols_preview = [col_nombre] + ([col_num_lista] if col_num_lista else [])
            st.dataframe(df_imp[cols_preview].head(10), use_container_width=True)

            if st.button("Importar"):
                nombres = df_imp[col_nombre].astype(str).tolist()
                nums = (
                    pd.to_numeric(df_imp[col_num_lista], errors="coerce")
                    .apply(lambda x: int(x) if pd.notna(x) else None)
                    .tolist()
                    if col_num_lista
                    else None
                )
                db.agregar_alumnos_bulk(grupo_id, nombres, numeros_lista=nums)
                st.success(f"Se importaron {len(df_imp)} alumnos.")
                st.rerun()


# ---------- Tab Plantilla de orden ----------

with tab_plantilla:
    st.subheader("Plantilla de orden de columnas (Excel Oficial)")
    st.caption(
        "Define el orden exacto en que tus columnas deben aparecer. La app "
        "reordenará automáticamente los archivos de Classroom para que coincidan."
    )

    plantilla_actual = db.obtener_plantilla(grupo_id)

    modo = st.radio(
        "¿Cómo defines la plantilla?",
        ["Detectar desde un Excel Oficial existente", "Editar manualmente"],
        horizontal=True,
    )

    if modo == "Detectar desde un Excel Oficial existente":
        archivo = st.file_uploader(
            "Sube tu Excel Oficial (la app tomará sus columnas como orden canónico)",
            type=["csv", "xlsx"],
            key="upload_plantilla",
        )
        if archivo:
            df = proc.leer_archivo(archivo)
            col_alumno = proc.detectar_columna_alumno(df)
            cols_tareas = [c for c in df.columns if c != col_alumno]
            st.write(f"Columna de alumno detectada: `{col_alumno}`")
            st.write("Columnas (tareas) detectadas:")
            st.code(" | ".join(cols_tareas))
            if st.button("Guardar como plantilla"):
                db.guardar_plantilla(grupo_id, cols_tareas)
                st.success("Plantilla guardada.")
                st.rerun()
    else:
        texto = "\n".join(plantilla_actual)
        editado = st.text_area(
            "Una columna por línea (en el orden que quieras)",
            value=texto,
            height=300,
        )
        if st.button("Guardar plantilla"):
            cols = [l.strip() for l in editado.splitlines() if l.strip()]
            db.guardar_plantilla(grupo_id, cols)
            st.success("Plantilla guardada.")
            st.rerun()

    if plantilla_actual:
        st.write("**Plantilla actual:**")
        st.write(pd.DataFrame({"Orden": plantilla_actual}))


# ---------- Tab Sincronizar ----------

with tab_sync:
    st.subheader("Sincronizar Classroom ⇄ Excel Oficial")

    plantilla = db.obtener_plantilla(grupo_id)
    if not plantilla:
        st.warning("Primero define una Plantilla de orden en la pestaña anterior.")
        st.stop()

    col_a, col_b = st.columns(2)
    with col_a:
        archivo_class = st.file_uploader(
            "📥 Archivo exportado desde Google Classroom",
            type=["csv", "xlsx"],
            key="up_class",
        )
    with col_b:
        archivo_oficial = st.file_uploader(
            "📊 Excel Oficial actual (opcional, para conciliar)",
            type=["csv", "xlsx"],
            key="up_oficial",
        )

    umbral = st.slider(
        "Umbral de similitud para emparejar tareas (fuzzy matching)",
        50, 100, proc.DEFAULT_FUZZY_THRESHOLD,
        help="Más alto = más estricto. 85 funciona bien para la mayoría de casos.",
    )

    if archivo_class:
        df_class = proc.leer_archivo(archivo_class)
        col_alumno_class = proc.detectar_columna_alumno(df_class)
        cols_class = [c for c in df_class.columns if c != col_alumno_class]

        # ---- Fuzzy match de tareas: Classroom -> Plantilla oficial ----
        matches = proc.emparejar_tareas(cols_class, plantilla, umbral=umbral)

        st.markdown("### 🔍 Mapeo de tareas (fuzzy matching)")
        st.caption(
            "Revisa cómo se mapearon las columnas. Las marcadas como 'nueva' "
            "no estaban en tu plantilla y se anexarán al final."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Classroom": m.classroom,
                        "→ Oficial": m.oficial or "(sin match)",
                        "Score": m.score,
                        "Estado": "✅ match" if not m.nueva else "🆕 nueva",
                    }
                    for m in matches
                ]
            ),
            use_container_width=True,
        )

        # ---- Reordenar Classroom según plantilla ----
        df_reordenado = proc.reordenar_segun_plantilla(
            df_class, plantilla, matches, col_alumno_class
        )

        # ---- Conciliación opcional con Excel Oficial ----
        if archivo_oficial:
            df_oficial = proc.leer_archivo(archivo_oficial)
            col_alumno_of = proc.detectar_columna_alumno(df_oficial)

            map_alumnos = proc.emparejar_alumnos(
                df_reordenado[col_alumno_class].astype(str).tolist(),
                df_oficial[col_alumno_of].astype(str).tolist(),
            )
            df_final = proc.conciliar_valores(
                df_reordenado, df_oficial, col_alumno_class, col_alumno_of, map_alumnos
            )
        else:
            df_final = df_reordenado.copy()
            df_final["_discrepancias"] = ""

        st.markdown("### ✏️ Edición y confirmación")
        st.caption(
            "Edita cualquier celda antes de exportar. La columna `_discrepancias` "
            "marca filas donde Classroom y el Excel Oficial diferían."
        )

        # Resaltar filas con discrepancias
        def _highlight(row):
            return [
                "background-color: #fff3cd" if row.get("_discrepancias") else ""
                for _ in row
            ]

        df_editado = st.data_editor(
            df_final,
            use_container_width=True,
            num_rows="dynamic",
            key="editor_final",
        )

        # ---- Exportación ----
        st.markdown("### 📤 Exportar")
        c1, c2, c3 = st.columns(3)

        df_export = df_editado.drop(columns=["_discrepancias"], errors="ignore")

        with c1:
            st.download_button(
                "⬇️ Descargar Excel",
                data=proc.df_a_excel_bytes(df_export),
                file_name=f"calificaciones_{seleccion}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with c2:
            st.download_button(
                "🖨️ Descargar PDF",
                data=proc.df_a_pdf_bytes(df_export, titulo=f"Calificaciones — {seleccion}"),
                file_name=f"calificaciones_{seleccion}.pdf",
                mime="application/pdf",
            )
        with c3:
            if st.button("💾 Guardar en historial"):
                # Convertir a formato largo para SQLite
                col_alumno_final = df_export.columns[0]
                largo = []
                for _, row in df_export.iterrows():
                    alumno = row[col_alumno_final]
                    if pd.isna(alumno):
                        continue
                    for c in df_export.columns[1:]:
                        valor = row[c]
                        if pd.notna(valor):
                            try:
                                largo.append(
                                    {"alumno": str(alumno), "tarea": str(c), "valor": float(valor)}
                                )
                            except (TypeError, ValueError):
                                pass
                # Asegurar que los alumnos existan
                db.agregar_alumnos_bulk(grupo_id, df_export[col_alumno_final].astype(str).tolist())
                db.registrar_calificaciones(grupo_id, largo, fuente="classroom")
                st.success(f"Se guardaron {len(largo)} registros en el historial.")


# ---------- Tab Historial ----------

with tab_historial:
    st.subheader("Historial de calificaciones registradas")
    historial = db.historial_grupo(grupo_id)
    if historial:
        st.dataframe(pd.DataFrame(historial), use_container_width=True)
    else:
        st.info("Aún no hay registros para este grupo.")
