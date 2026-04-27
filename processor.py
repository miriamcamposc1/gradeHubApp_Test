"""
processor.py
Núcleo de procesamiento: leer archivos, hacer fuzzy matching de tareas,
reordenar columnas y generar PDF.

Convención de columnas:
- Cada archivo tiene UNA columna que identifica al alumno (la primera que
  contenga 'nombre' / 'alumno' / 'student'; si no, la primera columna de texto).
- El resto de columnas son tareas / actividades con valores numéricos.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import pandas as pd
from thefuzz import fuzz, process as fuzz_process

# Reportlab es opcional hasta que se exporte un PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)


# Umbral para considerar que dos nombres de tarea son "la misma tarea".
# 85 funciona bien para casos como "Tarea 1: Suma" vs "Tarea1 - sumas".
DEFAULT_FUZZY_THRESHOLD = 85


# ---------- Lectura de archivos ----------

def leer_archivo(file) -> pd.DataFrame:
    """
    Lee CSV o XLSX desde un UploadedFile de Streamlit (o ruta).
    Devuelve DataFrame con columnas tal cual están en el archivo.
    """
    nombre = getattr(file, "name", str(file)).lower()
    if nombre.endswith(".csv"):
        return pd.read_csv(file)
    if nombre.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(file, engine="openpyxl")
    raise ValueError(f"Formato no soportado: {nombre}")


def detectar_columna_alumno(df: pd.DataFrame) -> str:
    """
    Heurística: la columna que represente al alumno.
    Acepta 'Nombre', 'Alumno', 'Student name', etc.
    Si no encuentra, cae a la primera columna no numérica.
    """
    candidatos = [c for c in df.columns if re.search(r"(nombre|alumno|student)", str(c), re.I)]
    if candidatos:
        return candidatos[0]
    for c in df.columns:
        if df[c].dtype == object:
            return c
    return df.columns[0]


def detectar_columna_numero_lista(df: pd.DataFrame) -> str | None:
    """
    Heurística: la columna que represente el número de lista.
    Busca variantes como 'No.', 'Núm', 'N° Lista', '#', 'No. Lista', 'Numero', etc.
    Solo acepta columnas cuyos valores sean mayormente enteros pequeños (1-99).
    Retorna None si no encuentra candidato.
    """
    patron = re.compile(
        r"(n[uú]m|no\.?\s*lista|#|n[°o]\.?\s*(de\s*)?lista|numero\s*de\s*lista|list\s*n)",
        re.I,
    )
    for c in df.columns:
        if patron.search(str(c)):
            return c
    # Fallback: buscar la primera columna numérica con valores 1-99 consecutivos
    for c in df.columns:
        try:
            vals = pd.to_numeric(df[c], errors="coerce").dropna()
            if len(vals) > 0 and vals.min() >= 1 and vals.max() <= 99 and vals.dtype in ("int64", "float64"):
                # Verificar que parezcan números de lista (enteros, mayormente secuenciales)
                enteros = vals.astype(int)
                if (enteros == vals).all() and len(enteros.unique()) == len(enteros):
                    return c
        except (TypeError, ValueError):
            continue
    return None


# ---------- Fuzzy matching de tareas ----------

@dataclass
class MatchTarea:
    """Resultado de mapear una tarea de Classroom contra el orden oficial."""
    classroom: str
    oficial: str | None
    score: int
    nueva: bool  # True si no se encontró match (la tarea no estaba en el orden oficial)


def emparejar_tareas(
    columnas_classroom: list[str],
    columnas_oficial: list[str],
    umbral: int = DEFAULT_FUZZY_THRESHOLD,
) -> list[MatchTarea]:
    """
    Para cada columna de Classroom, busca su mejor correspondencia en el
    Excel Oficial usando token_set_ratio (robusto a orden de palabras y
    pequeñas variaciones tipográficas).

    Lógica:
    1. Si la columna existe literalmente en oficial -> match perfecto.
    2. Si no, se calcula similitud difusa contra cada columna oficial.
    3. Si el mejor score >= umbral, se considera match; si no, se marca
       como "nueva" para que la maestra decida.
    """
    matches: list[MatchTarea] = []
    oficial_disponibles = list(columnas_oficial)

    for col in columnas_classroom:
        if col in oficial_disponibles:
            matches.append(MatchTarea(classroom=col, oficial=col, score=100, nueva=False))
            continue

        if not oficial_disponibles:
            matches.append(MatchTarea(classroom=col, oficial=None, score=0, nueva=True))
            continue

        mejor = fuzz_process.extractOne(
            col, oficial_disponibles, scorer=fuzz.token_set_ratio
        )
        if mejor and mejor[1] >= umbral:
            matches.append(MatchTarea(classroom=col, oficial=mejor[0], score=int(mejor[1]), nueva=False))
        else:
            score = int(mejor[1]) if mejor else 0
            matches.append(MatchTarea(classroom=col, oficial=None, score=score, nueva=True))

    return matches


def emparejar_alumnos(
    nombres_classroom: list[str],
    nombres_oficial: list[str],
    umbral: int = 80,
) -> dict[str, str | None]:
    """
    Mapea cada alumno de Classroom al alumno oficial más parecido.
    Útil cuando Classroom escribe 'García López, Ana' y el Excel 'Ana García L.'.
    """
    resultado: dict[str, str | None] = {}
    for n in nombres_classroom:
        if n in nombres_oficial:
            resultado[n] = n
            continue
        mejor = fuzz_process.extractOne(n, nombres_oficial, scorer=fuzz.token_set_ratio)
        resultado[n] = mejor[0] if (mejor and mejor[1] >= umbral) else None
    return resultado


# ---------- Reordenamiento ----------

def reordenar_segun_plantilla(
    df_classroom: pd.DataFrame,
    plantilla: list[str],
    matches: list[MatchTarea],
    col_alumno: str,
) -> pd.DataFrame:
    """
    Construye un DataFrame nuevo donde:
    - La primera columna es el alumno.
    - Las columnas siguientes siguen EXACTAMENTE el orden de `plantilla`.
    - Si una tarea de la plantilla no estaba en Classroom, queda vacía
      (la maestra la llenará a mano en el data_editor).
    - Las tareas "nuevas" (sin match) se anexan al final para que no se pierdan.

    Esta es la operación clave que la maestra hacía a mano cada vez.
    """
    # 1. Indice classroom_col -> oficial_col según matches
    map_class_a_oficial = {m.classroom: m.oficial for m in matches if m.oficial}
    nuevas = [m.classroom for m in matches if m.nueva]

    # 2. Renombrar columnas matcheadas para que su nombre sea el oficial
    df = df_classroom.rename(columns=map_class_a_oficial).copy()

    # 3. Construir el orden final: alumno + plantilla + nuevas (al final)
    columnas_existentes = set(df.columns)
    orden_final = [col_alumno]
    for col in plantilla:
        if col in columnas_existentes:
            orden_final.append(col)
        else:
            # Crear columna vacía para mantener el formato del Excel Oficial
            df[col] = pd.NA
            orden_final.append(col)
    for col in nuevas:
        if col in df.columns and col not in orden_final:
            orden_final.append(col)

    return df[orden_final]


# ---------- Conciliación de valores ----------

def conciliar_valores(
    df_classroom: pd.DataFrame,
    df_oficial: pd.DataFrame,
    col_alumno_class: str,
    col_alumno_oficial: str,
    map_alumnos: dict[str, str | None],
) -> pd.DataFrame:
    """
    Devuelve un DataFrame "ancho" con la mejor versión combinada:
    - Para cada celda toma el valor de Classroom si existe; si no, el oficial.
    - Marca discrepancias: si ambos existen y difieren, se conserva el de
      Classroom y se anota la diferencia en una columna `_discrepancias`.

    El front (st.data_editor) usará `_discrepancias` para resaltar filas.
    """
    # Normalizar nombres de alumno en Classroom al oficial cuando haya match
    df_c = df_classroom.copy()
    df_c[col_alumno_class] = df_c[col_alumno_class].map(lambda n: map_alumnos.get(n) or n)
    df_c = df_c.rename(columns={col_alumno_class: col_alumno_oficial})

    # Merge por alumno
    merged = pd.merge(
        df_oficial, df_c, on=col_alumno_oficial, how="outer", suffixes=("_oficial", "_classroom")
    )

    # Resolver conflictos celda a celda
    columnas_tareas = [
        c.removesuffix("_oficial")
        for c in merged.columns
        if c.endswith("_oficial") and c != f"{col_alumno_oficial}_oficial"
    ]

    discrepancias: list[str] = []
    for _, row in merged.iterrows():
        diffs = []
        for c in columnas_tareas:
            v_of = row.get(f"{c}_oficial")
            v_cl = row.get(f"{c}_classroom")
            if pd.notna(v_of) and pd.notna(v_cl) and v_of != v_cl:
                diffs.append(f"{c}: oficial={v_of} vs classroom={v_cl}")
        discrepancias.append(" | ".join(diffs))

    # Construir df final priorizando Classroom (valor más reciente)
    salida = pd.DataFrame({col_alumno_oficial: merged[col_alumno_oficial]})
    for c in columnas_tareas:
        salida[c] = merged[f"{c}_classroom"].combine_first(merged[f"{c}_oficial"])
    # Columnas que solo estaban en uno u otro
    for c in merged.columns:
        if c == col_alumno_oficial or c.endswith(("_oficial", "_classroom")):
            continue
        salida[c] = merged[c]

    salida["_discrepancias"] = discrepancias
    return salida


# ---------- Exportación ----------

def df_a_excel_bytes(df: pd.DataFrame, nombre_hoja: str = "Calificaciones") -> bytes:
    """Serializa el DataFrame final a XLSX en memoria."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=nombre_hoja)
    return buffer.getvalue()


def df_a_pdf_bytes(df: pd.DataFrame, titulo: str = "Reporte de calificaciones") -> bytes:
    """
    Genera un PDF tabular usando reportlab. Tamaño A4 horizontal para que
    quepan más columnas. Respeta el orden del DataFrame (= orden de la plantilla).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=20,
        rightMargin=20,
        topMargin=25,
        bottomMargin=25,
    )

    styles = getSampleStyleSheet()
    elementos = [Paragraph(titulo, styles["Title"]), Spacer(1, 12)]

    df_print = df.drop(columns=["_discrepancias"], errors="ignore").fillna("")
    datos = [list(df_print.columns)] + df_print.astype(str).values.tolist()

    tabla = Table(datos, repeatRows=1)
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    elementos.append(tabla)
    doc.build(elementos)
    return buffer.getvalue()
