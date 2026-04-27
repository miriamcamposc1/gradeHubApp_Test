# 📘 Hub de Calificaciones

Aplicación web (Streamlit) que sincroniza calificaciones entre **Google Classroom** y un **Excel Oficial**, evitando captura duplicada y reordenamiento manual de columnas.

## ✨ Funcionalidades

- **Gestión de grupos y alumnos** con persistencia en SQLite.
- **Plantilla de orden** por grupo: define una vez el orden de columnas que quieres ver.
- **Fuzzy matching** con `thefuzz` para emparejar tareas con nombres parecidos (`Tarea 1: Suma` ≈ `Tarea1 - sumas`).
- **Reordenamiento automático** del archivo de Classroom al formato del Excel Oficial.
- **Conciliación** lado a lado con `st.data_editor`, resaltando discrepancias.
- **Exportación** a Excel y PDF (formato listo para imprimir, A4 horizontal).
- **Historial** de calificaciones en SQLite.

## 🗂️ Estructura

```
.
├── app.py                    # Interfaz Streamlit
├── database.py               # Capa SQLite
├── processor.py              # Pandas + fuzzy matching + PDF
├── requirements.txt
├── Dockerfile
├── docker-compose.yml        # Base compartida
├── docker-compose.qa.yml     # Override QA
├── docker-compose.prod.yml   # Override Producción
├── .env.dev                  # Variables DEV
├── .env.qa                   # Variables QA
├── .env.prod                 # Variables PROD
├── scripts/
│   ├── dev.ps1               # Lanzar DEV local
│   ├── qa.ps1                # Lanzar QA con Docker
│   └── prod.ps1              # Lanzar PROD con Docker
├── data/                     # BD local (DEV, gitignored)
├── work/                     # Archivos de trabajo PROD
└── work-qa/                  # Archivos de trabajo QA
```

---

## 🚀 Ambientes

El proyecto usa **Docker Compose override files** para separar 3 ambientes en el mismo repositorio.

| Ambiente | Ejecución | Puerto | BD | Uso |
|----------|-----------|--------|------|-----|
| **DEV** | Local (Python) | `8501` | `./data/grades.db` | Desarrollo y pruebas rápidas |
| **QA** | Docker | `8502` | Volumen Docker aislado | Validar antes de prod |
| **PROD** | Docker | `8501` | Volumen Docker persistente | Usado por las maestras |

### 🟢 DEV — Ejecución local (sin Docker)

```powershell
# Opción 1: Script automático
.\scripts\dev.ps1

# Opción 2: Manual
$env:GRADES_DB_PATH = ".\data\grades.db"
$env:STREAMLIT_ENV  = "dev"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Acceder en: **http://localhost:8501**

### 🟡 QA — Docker en puerto 8502

```powershell
# Levantar
.\scripts\qa.ps1 up

# Ver logs
.\scripts\qa.ps1 logs

# Apagar
.\scripts\qa.ps1 down

# Reconstruir desde cero
.\scripts\qa.ps1 rebuild
```

Acceder en: **http://localhost:8502**

> QA y PROD pueden correr **al mismo tiempo** porque usan puertos y volúmenes distintos.

### 🔵 PROD — Docker en puerto 8501

```powershell
# Levantar (background)
.\scripts\prod.ps1 up

# Ver logs
.\scripts\prod.ps1 logs

# Apagar
.\scripts\prod.ps1 down
```

Acceder en: **http://localhost:8501**

### Persistencia

- **DEV**: BD en `./data/grades.db` (carpeta local, ignorada por git).
- **QA**: Volumen Docker `grades-qa_grades_data` (aislado de prod).
- **PROD**: Volumen Docker `grades-prod_grades_data` (persistente).

### Reset total de datos (por ambiente)

```powershell
# Solo QA
docker compose --env-file .env.qa -f docker-compose.yml -f docker-compose.qa.yml down -v

# Solo PROD (⚠️ cuidado, borra datos reales)
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml down -v
```

## 📝 Flujo recomendado

1. **Crea un grupo** en la barra lateral.
2. **Define la plantilla de orden** (sube tu Excel Oficial actual o escribe los nombres de columnas).
3. En la pestaña **Sincronizar**:
   - Sube el archivo exportado de Classroom.
   - (Opcional) Sube el Excel Oficial actual para conciliar valores.
   - Revisa el mapeo difuso de tareas y ajusta el umbral si hace falta.
   - Edita en el `data_editor` las celdas necesarias.
   - Descarga Excel o PDF, y/o guarda al historial.

## 🔧 Desarrollo local sin Docker

```bash
python -m venv .venv
source .venv/bin/activate     # o .venv\Scripts\activate en Windows
pip install -r requirements.txt
GRADES_DB_PATH=./grades.db streamlit run app.py
```
