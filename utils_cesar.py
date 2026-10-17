import os
import io
import json
import math
from datetime import datetime, date
import streamlit as st
import pandas as pd
from supabase import create_client

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_FALLBACK_PATH = os.path.join(BASE_DIR, "data_local_cesar.json")
SQL_SCHEMA_PATH = os.path.join(BASE_DIR, "sql", "schema_completo_cesar.sql")

CULTIVOS_FRECUENTES = [
    "Palto",
    "Arroz",
    "Espárrago",
    "Tomate",
    "Maíz",
    "Arándano",
    "Uva",
    "Papa",
    "Cebolla",
    "Ají Páprika",
    "Sandía",
    "Maracuyá",
    "Otro"
]

# --- 1. CONEXIÓN SUPABASE ---
@st.cache_resource
def init_supabase():
    try:
        url = st.secrets.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
        if url and key:
            return create_client(url, key)
    except Exception:
        pass
    return None

# --- 2. SISTEMA DE DISEÑO (UI/UX PRO MAX + IMPECCABLE) ---
def apply_cesar_theme():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Fira Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            color: #14532D;
        }
        .stApp {
            background-color: #F8FAF9;
        }
        /* Tabular numerals for metrics and financial data */
        div[data-testid="stMetricValue"], table, .tabular-nums {
            font-family: 'Fira Code', monospace;
            font-variant-numeric: tabular-nums;
        }
        div[data-testid="stMetric"] {
            background-color: #FFFFFF;
            border: 1px solid #BBF7D0;
            padding: 16px 18px;
            border-radius: 14px;
            box-shadow: 0 2px 8px rgba(20, 83, 45, 0.05);
        }
        div[data-testid="stMetricLabel"] {
            color: #475569;
            font-weight: 600;
            font-size: 0.88rem;
        }
        div[data-testid="stMetricValue"] {
            color: #14532D;
            font-weight: 700;
        }
        div[data-testid="stForm"] {
            background-color: #FFFFFF;
            border-radius: 16px;
            padding: 22px;
            border: 1px solid #DCFCE7;
            box-shadow: 0 4px 12px rgba(20, 83, 45, 0.04);
        }
        .cesar-header {
            background: #14532D;
            color: #FFFFFF;
            padding: 1.5rem 1.8rem;
            border-radius: 16px;
            margin-bottom: 1.2rem;
            box-shadow: 0 6px 16px rgba(20, 83, 45, 0.12);
        }
        .cesar-header h1 {
            color: #FFFFFF !important;
            margin: 0 0 0.25rem 0;
            font-size: 1.75rem;
            font-weight: 700;
            letter-spacing: -0.02em;
        }
        .cesar-header p {
            color: #DCFCE7;
            margin: 0;
            font-size: 0.95rem;
        }
        .gps-btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background-color: #15803D;
            color: #FFFFFF !important;
            padding: 10px 16px;
            border-radius: 10px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.9rem;
            min-height: 44px;
            transition: background-color 0.2s ease, transform 0.15s ease;
            box-shadow: 0 2px 6px rgba(21, 128, 61, 0.2);
        }
        .gps-btn:hover {
            background-color: #166534;
            transform: translateY(-1px);
        }
        .field-card {
            background: #FFFFFF;
            border: 1px solid #DCFCE7;
            border-radius: 14px;
            padding: 16px;
            margin-bottom: 12px;
            box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
        }
        </style>
    """, unsafe_allow_html=True)

# --- 3. CÁLCULO GEODÉSICO DE POLÍGONOS (ÁREA HA, PERÍMETRO M, CENTROIDE Y GOOGLE MAPS) ---
def construir_url_google_maps(lat: float, lon: float) -> str:
    return f"https://www.google.com/maps/dir/?api=1&destination={lat:.6f},{lon:.6f}"

def calcular_geometria_poligono(geojson_obj):
    """
    Recibe un objeto GeoJSON (Feature o Geometry de st_folium Draw) y calcula:
    - area_ha (Hectáreas reales sobre proyección esférica local)
    - perimetro_m (Perímetro total en metros)
    - latitud, longitud (Centroide del lote)
    - google_maps_url (Enlace directo de navegación GPS)
    """
    default_res = {
        "area_ha": 0.0,
        "perimetro_m": 0.0,
        "latitud": -7.223500,
        "longitud": -79.429100,
        "google_maps_url": construir_url_google_maps(-7.223500, -79.429100),
    }
    if not geojson_obj:
        return default_res

    try:
        if isinstance(geojson_obj, str):
            geojson_obj = json.loads(geojson_obj)

        geom = geojson_obj.get("geometry", geojson_obj)
        geom_type = geom.get("type", "")
        coords_raw = geom.get("coordinates", [])

        if geom_type == "Point" and len(coords_raw) >= 2:
            lon, lat = float(coords_raw[0]), float(coords_raw[1])
            return {
                "area_ha": 0.0,
                "perimetro_m": 0.0,
                "latitud": round(lat, 6),
                "longitud": round(lon, 6),
                "google_maps_url": construir_url_google_maps(lat, lon),
            }

        if geom_type == "Polygon" and coords_raw:
            ring = coords_raw[0]
        elif geom_type == "MultiPolygon" and coords_raw:
            ring = coords_raw[0][0]
        else:
            return default_res

        if len(ring) < 3:
            return default_res

        lats = [float(pt[1]) for pt in ring]
        lons = [float(pt[0]) for pt in ring]
        lat_mean = sum(lats) / len(lats)
        lon_mean = sum(lons) / len(lons)

        # Conversión geodésica local a metros planos (WGS84)
        R = 6378137.0
        cos_lat = math.cos(math.radians(lat_mean))
        xs = [math.radians(lon - lon_mean) * R * cos_lat for lon in lons]
        ys = [math.radians(lat - lat_mean) * R for lat in lats]

        # Fórmula de Gauss (Shoelace) para área y suma euclidiana para perímetro
        area_m2 = 0.0
        perimetro_m = 0.0
        n = len(ring)
        for i in range(n - 1):
            area_m2 += (xs[i] * ys[i + 1]) - (xs[i + 1] * ys[i])
            dx = xs[i + 1] - xs[i]
            dy = ys[i + 1] - ys[i]
            perimetro_m += math.hypot(dx, dy)

        area_m2 = abs(area_m2) * 0.5
        area_ha = round(area_m2 / 10000.0, 2)
        perimetro_m = round(perimetro_m, 1)

        # Centroide sin duplicar el vértice de cierre
        pts_unicos = ring[:-1] if len(ring) > 3 and ring[0] == ring[-1] else ring
        c_lat = round(sum(float(p[1]) for p in pts_unicos) / len(pts_unicos), 6)
        c_lon = round(sum(float(p[0]) for p in pts_unicos) / len(pts_unicos), 6)

        return {
            "area_ha": max(area_ha, 0.01),
            "perimetro_m": perimetro_m,
            "latitud": c_lat,
            "longitud": c_lon,
            "google_maps_url": construir_url_google_maps(c_lat, c_lon),
        }
    except Exception:
        return default_res

# --- 4. MOTOR DE PERSISTENCIA HÍBRIDO (SUPABASE + RESPALDO LOCAL AUTOMÁTICO) ---
def _default_local_store():
    hoy = str(date.today())
    return {
        "Clientes_Dron": [
            {
                "id": 1,
                "nombre": "Leonardo",
                "ruc_dni": "10458923141",
                "telefono": "948112233",
                "zona_sector": "Valle Jequetepeque / Chepén",
                "notas": "Cliente frecuente - Cultivos de Palto, Arroz y Espárrago",
                "activo": True,
                "created_at": hoy
            }
        ],
        "Campos_Clientes_Dron": [
            {
                "id": 1,
                "cliente_id": 1,
                "cliente_nombre": "Leonardo",
                "nombre_campo": "Lote Palto Norte",
                "cultivo": "Palto",
                "area_ha": 6.50,
                "perimetro_m": 1040.0,
                "latitud": -7.221500,
                "longitud": -79.431200,
                "google_maps_url": construir_url_google_maps(-7.221500, -79.431200),
                "geojson": json.dumps({
                    "type": "Feature",
                    "properties": {"nombre": "Lote Palto Norte", "cultivo": "Palto"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [-79.4325, -7.2205],
                            [-79.4298, -7.2205],
                            [-79.4298, -7.2226],
                            [-79.4325, -7.2226],
                            [-79.4325, -7.2205]
                        ]]
                    }
                }),
                "observaciones": "Entrada por acequia principal, sin cables eléctricos.",
                "created_at": hoy
            },
            {
                "id": 2,
                "cliente_id": 1,
                "cliente_nombre": "Leonardo",
                "nombre_campo": "Pozas Arroz Sector B",
                "cultivo": "Arroz",
                "area_ha": 12.00,
                "perimetro_m": 1420.0,
                "latitud": -7.225200,
                "longitud": -79.427800,
                "google_maps_url": construir_url_google_maps(-7.225200, -79.427800),
                "geojson": json.dumps({
                    "type": "Feature",
                    "properties": {"nombre": "Pozas Arroz Sector B", "cultivo": "Arroz"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [-79.4295, -7.2240],
                            [-79.4260, -7.2240],
                            [-79.4260, -7.2265],
                            [-79.4295, -7.2265],
                            [-79.4295, -7.2240]
                        ]]
                    }
                }),
                "observaciones": "Vuelo a 3.5m de altura, borde con árboles en lindero sur.",
                "created_at": hoy
            }
        ],
        "Servicios_Dron": [
            {
                "id": 1,
                "cliente_id": 1,
                "cliente_nombre": "Leonardo",
                "campo_id": 1,
                "nombre_campo": "Lote Palto Norte",
                "cultivo": "Palto",
                "fecha_servicio": hoy,
                "hectareas_aplicadas": 6.50,
                "precio_por_ha_pen": 65.00,
                "total_cobrar_pen": 422.50,
                "tipo_aplicacion": "Foliar + Fungicida Preventivo",
                "productos_aplicados": "Foliar Potasio + Cupravit",
                "volumen_caldo_l_ha": 30.0,
                "piloto_operador": "César",
                "dron_equipo": "DJI Agras T40",
                "estado_pago": "Pagado",
                "monto_pagado_pen": 422.50,
                "observaciones": "Aplicación uniforme con boquilla centrífuga.",
                "created_at": hoy
            },
            {
                "id": 2,
                "cliente_id": 1,
                "cliente_nombre": "Leonardo",
                "campo_id": 2,
                "nombre_campo": "Pozas Arroz Sector B",
                "cultivo": "Arroz",
                "fecha_servicio": hoy,
                "hectareas_aplicadas": 12.00,
                "precio_por_ha_pen": 55.00,
                "total_cobrar_pen": 660.00,
                "tipo_aplicacion": "Control Fitosanitario Insecticida",
                "productos_aplicados": "Insecticida Sistémico + Adherente",
                "volumen_caldo_l_ha": 25.0,
                "piloto_operador": "César",
                "dron_equipo": "DJI Agras T40",
                "estado_pago": "Pendiente",
                "monto_pagado_pen": 0.00,
                "observaciones": "Realizado en turno mañana sin viento.",
                "created_at": hoy
            }
        ],
        "Campos_Propios": [
            {
                "id": 1,
                "nombre_lote": "Campo Propio 1 - El Molino",
                "cultivo_actual": "Arroz",
                "variedad": "IR-43 / NIR",
                "area_ha": 5.50,
                "perimetro_m": 940.0,
                "fecha_siembra": "2026-08-15",
                "fecha_trasplante": "2026-09-10",
                "latitud": -7.219000,
                "longitud": -79.435000,
                "google_maps_url": construir_url_google_maps(-7.219000, -79.435000),
                "geojson": json.dumps({
                    "type": "Feature",
                    "properties": {"nombre": "Campo Propio 1 - El Molino", "cultivo": "Arroz"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [-79.4362, -7.2180],
                            [-79.4338, -7.2180],
                            [-79.4338, -7.2200],
                            [-79.4362, -7.2200],
                            [-79.4362, -7.2180]
                        ]]
                    }
                }),
                "estado": "En Campaña 🟢",
                "observaciones": "Suelo franco arcilloso, buen drenaje.",
                "created_at": hoy
            }
        ],
        "Historial_Campos_Propios": [
            {
                "id": 1,
                "campo_id": 1,
                "nombre_lote": "Campo Propio 1 - El Molino",
                "cultivo": "Arroz",
                "categoria": "Fertilizantes",
                "fecha": "2026-09-18",
                "etapa_labor": "1ra Fertilizada (Macollamiento)",
                "productos_detalle": "Urea Agrícola (4 sacos/ha) + Fosfato Diamónico (2 sacos/ha)",
                "dosis_por_ha": "300 Kg/ha",
                "cantidad_total": 1650.0,
                "unidad": "Kg",
                "costo_total_pen": 3450.0,
                "metodo_equipo": "Voleo Manual / Dron Esparcidor",
                "alerta_campo": "Normal 🟢",
                "observaciones": "Lámina de agua controlada antes de incorporar.",
                "created_at": hoy
            },
            {
                "id": 2,
                "campo_id": 1,
                "nombre_lote": "Campo Propio 1 - El Molino",
                "cultivo": "Arroz",
                "categoria": "Aplicaciones",
                "fecha": "2026-10-02",
                "etapa_labor": "1ra Aplicación Dron (Control Sogata / Gusano Rojo)",
                "productos_detalle": "Tiametoxam + Cipermetrina + Bioestimulante Aminoácidos",
                "dosis_por_ha": "25 L caldo/ha (0.4 L/ha prod)",
                "cantidad_total": 2.2,
                "unidad": "Lt",
                "costo_total_pen": 490.0,
                "metodo_equipo": "Dron DJI Agras",
                "alerta_campo": "Normal 🟢",
                "observaciones": "Excelente cobertura foliar en bordes.",
                "created_at": hoy
            },
            {
                "id": 3,
                "campo_id": 1,
                "nombre_lote": "Campo Propio 1 - El Molino",
                "cultivo": "Arroz",
                "categoria": "Extras",
                "fecha": "2026-09-10",
                "etapa_labor": "Trasplante y Quema de Bordes",
                "productos_detalle": "Semilla Certificada NIR (80 Kg/ha en almácigo) + Glifosato en bordos",
                "dosis_por_ha": "80 Kg semilla/ha",
                "cantidad_total": 440.0,
                "unidad": "Kg",
                "costo_total_pen": 1980.0,
                "metodo_equipo": "Cuadrilla / Mochila",
                "alerta_campo": "Deficiencia de Agua 💧",
                "observaciones": "Sector noreste presenta ligera deficiencia de agua por desnivel; reforzar riego.",
                "created_at": hoy
            }
        ],
        "Monitoreo_Multiespectral": [
            {
                "id": 1,
                "tipo_propiedad": "Campo Propio",
                "propietario": "César",
                "nombre_campo": "Campo Propio 1 - El Molino",
                "cultivo": "Arroz",
                "fecha_monitoreo": hoy,
                "indice": "NDVI (Vigor Vegetativo)",
                "valor_promedio": 0.760,
                "valor_min": 0.450,
                "valor_max": 0.890,
                "pct_vigor_optimo": 78.0,
                "pct_vigor_moderado": 16.0,
                "pct_estres_critico": 6.0,
                "diagnostico": "Cobertura uniforme en el 78% del lote. Manchas focalizadas de menor vigor en la esquina noreste por falta de lámina de agua.",
                "recomendacion_dron": "Aplicar bioestimulante + foliares nitrogenados focalizados con dron en el 6% de área con estrés hídrico.",
                "latitud": -7.219000,
                "longitud": -79.435000,
                "geojson": "",
                "created_at": hoy
            }
        ]
    }

def _read_local_store():
    if not os.path.exists(LOCAL_FALLBACK_PATH):
        store = _default_local_store()
        with open(LOCAL_FALLBACK_PATH, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
        return store
    try:
        with open(LOCAL_FALLBACK_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _default_local_store()

def _write_local_store(store):
    with open(LOCAL_FALLBACK_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)

def cargar_tabla_segura(supabase, nombre_tabla: str):
    """
    Intenta leer la tabla desde Supabase.
    Si la tabla aún no fue creada en Supabase (error PGRST205), devuelve los datos del respaldo local
    e informa que el SQL está disponible para sincronizar con Supabase.
    """
    if supabase:
        try:
            res = supabase.table(nombre_tabla).select("*").order("id", desc=False).execute()
            return pd.DataFrame(res.data), True
        except Exception:
            pass
    store = _read_local_store()
    rows = store.get(nombre_tabla, [])
    return pd.DataFrame(rows), False

def insertar_registro_seguro(supabase, nombre_tabla: str, payload: dict):
    if supabase:
        try:
            res = supabase.table(nombre_tabla).insert(payload).execute()
            return True, "Guardado en Supabase"
        except Exception:
            pass
    store = _read_local_store()
    lista = store.get(nombre_tabla, [])
    nuevo_id = max([int(r.get("id", 0)) for r in lista], default=0) + 1
    registro = {"id": nuevo_id, **payload, "created_at": str(date.today())}
    lista.append(registro)
    store[nombre_tabla] = lista
    _write_local_store(store)
    return True, "Guardado localmente (ejecuta el SQL en Supabase para sincronizar en la nube)"

def actualizar_registro_seguro(supabase, nombre_tabla: str, reg_id: int, payload: dict):
    if supabase:
        try:
            supabase.table(nombre_tabla).update(payload).eq("id", reg_id).execute()
            return True
        except Exception:
            pass
    store = _read_local_store()
    lista = store.get(nombre_tabla, [])
    for idx, item in enumerate(lista):
        if int(item.get("id", -1)) == int(reg_id):
            lista[idx] = {**item, **payload}
            break
    store[nombre_tabla] = lista
    _write_local_store(store)
    return True

def eliminar_registro_seguro(supabase, nombre_tabla: str, reg_id: int):
    if supabase:
        try:
            supabase.table(nombre_tabla).delete().eq("id", reg_id).execute()
            return True
        except Exception:
            pass
    store = _read_local_store()
    lista = store.get(nombre_tabla, [])
    store[nombre_tabla] = [r for r in lista if int(r.get("id", -1)) != int(reg_id)]
    _write_local_store(store)
    return True

def mostrar_aviso_sql_si_local(en_nube: bool):
    if not en_nube:
        with st.expander("⚡ Sincronización con Supabase pendiente — Clic aquí para copiar el script SQL de creación de tablas", expanded=False):
            st.info("Actualmente estás trabajando con almacenamiento local instantáneo. Para que estos registros se sincronicen en tiempo real con el Supabase de César (`wvbcfwhbilutuhpepeme`), copia y ejecuta este bloque en el **SQL Editor** de Supabase:")
            if os.path.exists(SQL_SCHEMA_PATH):
                with open(SQL_SCHEMA_PATH, "r", encoding="utf-8") as f:
                    st.code(f.read(), language="sql")

# --- 5. GENERADOR DE REPORTES PDF EJECUTIVOS (REPORTLAB + PREVIEW FITZ) ---
def generar_pdf_reporte_dron(cliente_filtro: str, cultivo_filtro: str, df_rep: pd.DataFrame) -> bytes:
    """
    Genera el PDF profesional para enviar al cliente con el resumen de hectáreas aplicadas,
    fecha, cultivo, precio por hectárea y total en Soles (S/).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=28,
        leftMargin=28,
        topMargin=28,
        bottomMargin=28
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleDron",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=colors.HexColor("#14532D"),
    )
    sub_style = ParagraphStyle(
        "SubDron",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#334155"),
    )
    cell_style = ParagraphStyle(
        "CellDron",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#0F172A"),
    )
    cell_bold = ParagraphStyle(
        "CellBoldDron",
        parent=cell_style,
        fontName="Helvetica-Bold",
    )

    elements = []

    # Cabecera
    fecha_emision = datetime.now().strftime("%d/%m/%Y %H:%M")
    header_data = [
        [
            Paragraph("<b>SERVICIOS AGRÍCOLAS & DRON — CÉSAR</b><br/><font size='9' color='#475569'>Liquidación y Reporte Técnico de Aplicaciones con Dron</font>", title_style),
            Paragraph(f"<b>FECHA EMISIÓN:</b> {fecha_emision}<br/><b>CLIENTE:</b> {cliente_filtro}<br/><b>CULTIVO(S):</b> {cultivo_filtro}", sub_style)
        ]
    ]
    t_head = Table(header_data, colWidths=[310, 225])
    t_head.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor("#15803D")),
    ]))
    elements.append(t_head)
    elements.append(Spacer(1, 14))

    # Resumen KPI
    total_ha = float(df_rep["hectareas_aplicadas"].sum()) if not df_rep.empty else 0.0
    total_pen = float(df_rep["total_cobrar_pen"].sum()) if not df_rep.empty else 0.0
    pagado_pen = float(df_rep["monto_pagado_pen"].sum()) if "monto_pagado_pen" in df_rep.columns and not df_rep.empty else 0.0
    saldo_pen = max(total_pen - pagado_pen, 0.0)

    kpi_data = [
        ["TOTAL HECTÁREAS APLICADAS", "TOTAL SERVICIOS (S/)", "MONTO ABONADO (S/)", "SALDO POR PAGAR (S/)"],
        [f"{total_ha:,.2f} ha", f"S/ {total_pen:,.2f}", f"S/ {pagado_pen:,.2f}", f"S/ {saldo_pen:,.2f}"]
    ]
    t_kpi = Table(kpi_data, colWidths=[133.75] * 4)
    t_kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14532D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F0FDF4")),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#14532D")),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BBF7D0")),
    ]))
    elements.append(t_kpi)
    elements.append(Spacer(1, 16))

    # Tabla Detallada
    rows = [[
        Paragraph("<b>Fecha</b>", cell_bold),
        Paragraph("<b>Cliente</b>", cell_bold),
        Paragraph("<b>Cultivo / Campo</b>", cell_bold),
        Paragraph("<b>Labor / Productos</b>", cell_bold),
        Paragraph("<b>Área (ha)</b>", cell_bold),
        Paragraph("<b>Precio/ha</b>", cell_bold),
        Paragraph("<b>Subtotal (S/)</b>", cell_bold),
        Paragraph("<b>Estado</b>", cell_bold),
    ]]

    for _, r in df_rep.iterrows():
        f_srv = str(r.get("fecha_servicio", ""))[:10]
        cli = str(r.get("cliente_nombre", ""))
        cul_cam = f"<b>{r.get('cultivo', '')}</b><br/>{r.get('nombre_campo', '')}"
        lab = f"{r.get('tipo_aplicacion', '')}"
        if r.get("productos_aplicados"):
            lab += f"<br/><font size='7.5' color='#475569'>{r.get('productos_aplicados')}</font>"
        ha = float(r.get("hectareas_aplicadas", 0))
        p_ha = float(r.get("precio_por_ha_pen", 0))
        tot = float(r.get("total_cobrar_pen", ha * p_ha))
        est = str(r.get("estado_pago", "Pendiente"))

        rows.append([
            Paragraph(f_srv, cell_style),
            Paragraph(cli, cell_style),
            Paragraph(cul_cam, cell_style),
            Paragraph(lab, cell_style),
            Paragraph(f"{ha:,.2f} ha", cell_style),
            Paragraph(f"S/ {p_ha:,.2f}", cell_style),
            Paragraph(f"<b>S/ {tot:,.2f}</b>", cell_style),
            Paragraph(est, cell_style),
        ])

    # Fila Total
    rows.append([
        Paragraph("<b>TOTAL GENERAL</b>", cell_bold),
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph(f"<b>{total_ha:,.2f} ha</b>", cell_bold),
        Paragraph("—", cell_style),
        Paragraph(f"<b>S/ {total_pen:,.2f}</b>", cell_bold),
        Paragraph("", cell_style),
    ])

    t_det = Table(rows, colWidths=[52, 62, 88, 123, 48, 52, 62, 48], repeatRows=1)
    t_det.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCFCE7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#14532D")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F0FDF4")),
        ("SPAN", (0, -1), (3, -1)),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(t_det)
    elements.append(Spacer(1, 24))

    # Pie de firma
    footer_data = [
        [
            Paragraph("____________________________________<br/><b>César — Operador & Servicios Dron</b>", sub_style),
            Paragraph("____________________________________<br/><b>Conformidad del Cliente</b>", sub_style),
        ]
    ]
    t_foot = Table(footer_data, colWidths=[267, 267])
    t_foot.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 20),
    ]))
    elements.append(t_foot)

    doc.build(elements)
    return buffer.getvalue()

def renderizar_preview_pdf(pdf_bytes: bytes):
    """Convierte la primera página del PDF en imagen PNG para vista previa en Streamlit."""
    if not fitz or not pdf_bytes:
        return None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(doc) > 0:
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=150)
            return pix.tobytes("png")
    except Exception:
        pass
    return None
