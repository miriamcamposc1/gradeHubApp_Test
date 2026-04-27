"""
database.py
Capa de persistencia con SQLite.

Responsabilidades:
- Inicializar el esquema (grupos, alumnos, plantillas de orden, historial de calificaciones).
- CRUD básico para que la app no toque SQL crudo.
- Persistir el "Orden Oficial" de columnas por grupo (clave de la app: cómo
  reordenar lo que sale de Classroom para que cuadre con el Excel Oficial).
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterable

# Por defecto la BD vive dentro del volumen montado por docker-compose.
DB_PATH = os.environ.get("GRADES_DB_PATH", "/data/grades.db")


@contextmanager
def get_conn(db_path: str = DB_PATH):
    """Context manager que garantiza commit/close incluso ante excepciones."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str = DB_PATH) -> None:
    """Crea las tablas si no existen. Idempotente: seguro llamar en cada arranque."""
    with get_conn(db_path) as conn:
        c = conn.cursor()

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS grupos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                ciclo TEXT,
                creado_en TEXT NOT NULL
            )
            """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS alumnos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grupo_id INTEGER NOT NULL,
                nombre TEXT NOT NULL,
                identificador TEXT,
                numero_lista INTEGER,
                FOREIGN KEY (grupo_id) REFERENCES grupos (id) ON DELETE CASCADE,
                UNIQUE (grupo_id, nombre)
            )
            """
        )

        # Migración: agregar numero_lista si la tabla ya existía sin esa columna
        cols = [r[1] for r in conn.execute("PRAGMA table_info(alumnos)").fetchall()]
        if "numero_lista" not in cols:
            c.execute("ALTER TABLE alumnos ADD COLUMN numero_lista INTEGER")

        # plantillas_orden: una fila por grupo. "columnas" guarda el orden
        # canónico (lista JSON) que la maestra quiere ver en su Excel Oficial.
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS plantillas_orden (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                grupo_id INTEGER NOT NULL UNIQUE,
                columnas TEXT NOT NULL,
                actualizado_en TEXT NOT NULL,
                FOREIGN KEY (grupo_id) REFERENCES grupos (id) ON DELETE CASCADE
            )
            """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS calificaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alumno_id INTEGER NOT NULL,
                tarea TEXT NOT NULL,
                valor REAL,
                fuente TEXT NOT NULL,        -- 'classroom' | 'excel' | 'manual'
                registrado_en TEXT NOT NULL,
                FOREIGN KEY (alumno_id) REFERENCES alumnos (id) ON DELETE CASCADE
            )
            """
        )


# ---------- Grupos ----------

def crear_grupo(nombre: str, ciclo: str | None = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO grupos (nombre, ciclo, creado_en) VALUES (?, ?, ?)",
            (nombre, ciclo, datetime.utcnow().isoformat()),
        )
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute("SELECT id FROM grupos WHERE nombre = ?", (nombre,)).fetchone()
        return row["id"]


def listar_grupos() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM grupos ORDER BY nombre").fetchall()
        return [dict(r) for r in rows]


def editar_grupo(grupo_id: int, nombre: str, ciclo: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE grupos SET nombre = ?, ciclo = ? WHERE id = ?",
            (nombre, ciclo, grupo_id),
        )


def eliminar_grupo(grupo_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM grupos WHERE id = ?", (grupo_id,))


# ---------- Alumnos ----------

def agregar_alumno(grupo_id: int, nombre: str, identificador: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO alumnos (grupo_id, nombre, identificador) VALUES (?, ?, ?)",
            (grupo_id, nombre, identificador),
        )


def agregar_alumnos_bulk(
    grupo_id: int,
    nombres: Iterable[str],
    numeros_lista: Iterable[int | None] | None = None,
) -> None:
    """Inserta alumnos en lote. Si se pasan numeros_lista, se asignan."""
    lista_nums = list(numeros_lista) if numeros_lista else None
    with get_conn() as conn:
        for i, n in enumerate(nombres):
            if not n or not str(n).strip():
                continue
            num = lista_nums[i] if lista_nums and i < len(lista_nums) else None
            conn.execute(
                "INSERT OR IGNORE INTO alumnos (grupo_id, nombre, numero_lista) VALUES (?, ?, ?)",
                (grupo_id, n, num),
            )
            # Si ya existía, actualizar numero_lista si viene uno nuevo
            if num is not None:
                conn.execute(
                    "UPDATE alumnos SET numero_lista = ? WHERE grupo_id = ? AND nombre = ? AND numero_lista IS NULL",
                    (num, grupo_id, n),
                )


def listar_alumnos(grupo_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM alumnos WHERE grupo_id = ? ORDER BY "
            "CASE WHEN numero_lista IS NOT NULL THEN 0 ELSE 1 END, numero_lista, nombre",
            (grupo_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def actualizar_alumno(alumno_id: int, nombre: str, identificador: str | None, numero_lista: int | None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE alumnos SET nombre = ?, identificador = ?, numero_lista = ? WHERE id = ?",
            (nombre, identificador, numero_lista, alumno_id),
        )


def eliminar_alumnos(alumno_ids: Iterable[int]) -> None:
    with get_conn() as conn:
        conn.executemany(
            "DELETE FROM alumnos WHERE id = ?",
            [(aid,) for aid in alumno_ids],
        )


# ---------- Plantilla de orden ----------

def guardar_plantilla(grupo_id: int, columnas: list[str]) -> None:
    """Upsert del orden canónico de columnas para un grupo."""
    payload = json.dumps(columnas, ensure_ascii=False)
    ahora = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO plantillas_orden (grupo_id, columnas, actualizado_en)
            VALUES (?, ?, ?)
            ON CONFLICT(grupo_id) DO UPDATE SET
                columnas = excluded.columnas,
                actualizado_en = excluded.actualizado_en
            """,
            (grupo_id, payload, ahora),
        )


def obtener_plantilla(grupo_id: int) -> list[str]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT columnas FROM plantillas_orden WHERE grupo_id = ?", (grupo_id,)
        ).fetchone()
        return json.loads(row["columnas"]) if row else []


# ---------- Historial de calificaciones ----------

def registrar_calificaciones(
    grupo_id: int, df_largo: list[dict], fuente: str = "manual"
) -> None:
    """
    Inserta lote de calificaciones en formato largo:
    [{"alumno": "...", "tarea": "...", "valor": 9.5}, ...]
    """
    ahora = datetime.utcnow().isoformat()
    with get_conn() as conn:
        # Map nombre -> id (evita N consultas)
        id_por_nombre = {
            r["nombre"]: r["id"]
            for r in conn.execute(
                "SELECT id, nombre FROM alumnos WHERE grupo_id = ?", (grupo_id,)
            ).fetchall()
        }
        filas = []
        for r in df_largo:
            alumno_id = id_por_nombre.get(r["alumno"])
            if alumno_id is None:
                continue
            filas.append((alumno_id, r["tarea"], r.get("valor"), fuente, ahora))
        if filas:
            conn.executemany(
                """
                INSERT INTO calificaciones (alumno_id, tarea, valor, fuente, registrado_en)
                VALUES (?, ?, ?, ?, ?)
                """,
                filas,
            )


def historial_grupo(grupo_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT a.nombre AS alumno, c.tarea, c.valor, c.fuente, c.registrado_en
            FROM calificaciones c
            JOIN alumnos a ON a.id = c.alumno_id
            WHERE a.grupo_id = ?
            ORDER BY c.registrado_en DESC
            """,
            (grupo_id,),
        ).fetchall()
        return [dict(r) for r in rows]
