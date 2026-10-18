import json
from datetime import date
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import folium
from folium.plugins import Fullscreen
from streamlit_folium import st_folium

from utils_cesar import (
    init_supabase,
    apply_cesar_theme,
    construir_url_google_maps,
    cargar_tabla_segura,
    insertar_registro_seguro,
    mostrar_aviso_sql_si_local,
)

st.set_page_config(page_title="Monitoreo Multiespectral NDVI", page_icon="🛰️", layout="wide")
apply_cesar_theme()

supabase = init_supabase()

st.markdown("""
<div class="cesar-header">
    <h1>🛰️ Monitoreo Multiespectral (NDVI / NDWI / Vigor y Estrés Hídrico)</h1>
    <p>Análisis satelital y de dron para detectar zonas de bajo vigor, deficiencia de agua o plagas en Campos Propios y de Clientes.</p>
</div>
""", unsafe_allow_html=True)

df_propios, ok_p = cargar_tabla_segura(supabase, "Campos_Propios")
df_clientes_campos, ok_c = cargar_tabla_segura(supabase, "Campos_Clientes_Dron")
df_monitoreos, ok_m = cargar_tabla_segura(supabase, "Monitoreo_Multiespectral")

mostrar_aviso_sql_si_local(ok_p and ok_c and ok_m)

# --- BARRA DE SELECCIÓN DE LOTE Y MODO ESPECTRAL ---
c1, c2, c3 = st.columns([1, 1.4, 1.2])

tipo_origen = c1.radio("📂 Origen del Campo:", options=["🌱 Mis Campos Propios", "🚁 Campos de Clientes Dron"], horizontal=True)

catalogo_lotes = []
if tipo_origen == "🌱 Mis Campos Propios" and not df_propios.empty:
    for _, r in df_propios.iterrows():
        catalogo_lotes.append({
            "label": f"{r['nombre_lote']} ({r['cultivo_actual']} - {float(r['area_ha']):.2f} ha)",
            "propietario": "César (Propio)",
            "nombre_campo": r["nombre_lote"],
            "cultivo": r["cultivo_actual"],
            "area_ha": float(r["area_ha"]),
            "latitud": float(r.get("latitud") or -7.2190),
            "longitud": float(r.get("longitud") or -79.4350),
            "geojson": r.get("geojson", "")
        })
elif tipo_origen == "🚁 Campos de Clientes Dron" and not df_clientes_campos.empty:
    for _, r in df_clientes_campos.iterrows():
        catalogo_lotes.append({
            "label": f"{r['cliente_nombre']} — {r['nombre_campo']} ({r['cultivo']} - {float(r['area_ha']):.2f} ha)",
            "propietario": r["cliente_nombre"],
            "nombre_campo": r["nombre_campo"],
            "cultivo": r["cultivo"],
            "area_ha": float(r["area_ha"]),
            "latitud": float(r.get("latitud") or -7.2215),
            "longitud": float(r.get("longitud") or -79.4312),
            "geojson": r.get("geojson", "")
        })

if not catalogo_lotes:
    catalogo_lotes = [{
        "label": "Campo Propio 1 - El Molino (Arroz - 5.50 ha)",
        "propietario": "César",
        "nombre_campo": "Campo Propio 1 - El Molino",
        "cultivo": "Arroz",
        "area_ha": 5.50,
        "latitud": -7.2190,
        "longitud": -79.4350,
        "geojson": ""
    }]

lote_sel_label = c2.selectbox("🎯 Seleccionar Campo a Monitorear:", options=[x["label"] for x in catalogo_lotes])
lote_info = next(x for x in catalogo_lotes if x["label"] == lote_sel_label)

indice_sel = c3.selectbox(
    "🔬 Índice Multiespectral:",
    options=[
        "NDVI — Vigor Vegetativo y Biomasa",
        "NDWI — Estrés Hídrico y Humedad Foliar",
        "NDRE — Clorofila y Nitrógeno en Dosel",
        "GNDVI — Actividad Fotosintética"
    ]
)

# Buscar último monitoreo guardado para este campo o usar valores base realistas
df_mon_campo = df_monitoreos[df_monitoreos["nombre_campo"] == lote_info["nombre_campo"]] if not df_monitoreos.empty else pd.DataFrame()
if not df_mon_campo.empty:
    ult = df_mon_campo.iloc[-1]
    val_prom = float(ult.get("valor_promedio", 0.75))
    val_min = float(ult.get("valor_min", 0.44))
    val_max = float(ult.get("valor_max", 0.88))
    pct_opt = float(ult.get("pct_vigor_optimo", 76.0))
    pct_mod = float(ult.get("pct_vigor_moderado", 17.0))
    pct_est = float(ult.get("pct_estres_critico", 7.0))
    diag_txt = str(ult.get("diagnostico", "Vigor alto en el centro del lote; ligera caída en bordes."))
    rec_txt = str(ult.get("recomendacion_dron", "Aplicar bioestimulante focalizado con dron en zonas amarillas/rojas."))
else:
    val_prom, val_min, val_max = 0.74, 0.42, 0.87
    pct_opt, pct_mod, pct_est = 75.0, 18.0, 7.0
    diag_txt = f"El cultivo de {lote_info['cultivo']} presenta buen desarrollo general ({val_prom:.2f}), con un {pct_est:.1f}% de superficie con alerta de estrés hídrico/nutricional."
    rec_txt = f"Programar vuelo de dron en {lote_info['nombre_campo']} priorizando los sectores de bajo índice."

ha_tot = lote_info["area_ha"]
ha_opt = round(ha_tot * (pct_opt / 100.0), 2)
ha_mod = round(ha_tot * (pct_mod / 100.0), 2)
ha_est = round(ha_tot * (pct_est / 100.0), 2)

# KPIs Espectrales
k1, k2, k3, k4 = st.columns(4)
k1.metric(f"📈 Índice Promedio ({indice_sel.split('—')[0].strip()})", f"{val_prom:.3f}", f"Rango: {val_min:.2f} a {val_max:.2f}")
k2.metric("🟢 Zona Vigor Óptimo", f"{ha_opt:.2f} ha", f"{pct_opt:.1f}% del campo")
k3.metric("🟡 Zona Vigor Moderado", f"{ha_mod:.2f} ha", f"{pct_mod:.1f}% del campo")
k4.metric("🔴 Zona Estrés / Alerta", f"{ha_est:.2f} ha", f"-{pct_est:.1f}% focalizado", delta_color="inverse")

col_mapa, col_graf = st.columns([1.35, 1], gap="large")

with col_mapa:
    st.subheader(f"🗺️ Mapa de Zonificación Multiespectral — {lote_info['nombre_campo']}")
    lat_c = lote_info["latitud"]
    lon_c = lote_info["longitud"]

    m_ndvi = folium.Map(location=[lat_c, lon_c], zoom_start=16, control_scale=True)
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google Satellite",
        name="Satélite Base",
        overlay=False
    ).add_to(m_ndvi)

    # Generar grilla multiespectral sobre el polígono o entorno del lote
    np.random.seed(abs(hash(lote_info["nombre_campo"] + indice_sel)) % 10000)
    n_grid = 6
    d_lat = 0.0014 / n_grid
    d_lon = 0.0018 / n_grid
    start_lat = lat_c - (d_lat * n_grid / 2)
    start_lon = lon_c - (d_lon * n_grid / 2)

    for i in range(n_grid):
        for j in range(n_grid):
            # Simulación espacial realista con gradiente hacia esquina noreste
            score = np.clip(val_prom + np.random.normal(0, 0.09) - (0.04 if (i == n_grid - 1 and j == n_grid - 1) else 0), 0.25, 0.92)
            if score >= 0.68:
                fill_col = "#16A34A"  # Verde vigor óptimo
                etiqueta = "Vigor Óptimo"
            elif score >= 0.50:
                fill_col = "#EAB308"  # Amarillo vigor moderado
                etiqueta = "Vigor Moderado"
            else:
                fill_col = "#DC2626"  # Rojo estrés hídrico / nutricional
                etiqueta = "Estrés / Deficiencia"

            cell_coords = [
                [start_lat + i * d_lat, start_lon + j * d_lon],
                [start_lat + (i + 1) * d_lat, start_lon + j * d_lon],
                [start_lat + (i + 1) * d_lat, start_lon + (j + 1) * d_lon],
                [start_lat + i * d_lat, start_lon + (j + 1) * d_lon],
            ]
            folium.Polygon(
                locations=cell_coords,
                color=fill_col,
                weight=0.6,
                fill=True,
                fill_color=fill_col,
                fill_opacity=0.55,
                tooltip=f"{indice_sel.split('—')[0].strip()}: {score:.2f} ({etiqueta})"
            ).add_to(m_ndvi)

    # Contorno del lote
    if lote_info.get("geojson"):
        try:
            g_obj = json.loads(lote_info["geojson"]) if isinstance(lote_info["geojson"], str) else lote_info["geojson"]
            folium.GeoJson(
                g_obj,
                name="Contorno Lote",
                style_function=lambda x: {"fillColor": "transparent", "color": "#FFFFFF", "weight": 3}
            ).add_to(m_ndvi)
        except Exception:
            pass

    Fullscreen(position="topright").add_to(m_ndvi)
    st_folium(m_ndvi, width=None, height=410, returned_objects=[])

    st.markdown("""
    <div class="legend-box">
        <b>Leyenda Espectral:</b>
        <span>🟢 <b>> 0.68:</b> Vigor Alto / Sanidad Óptima</span>
        <span>🟡 <b>0.50 – 0.68:</b> Vigor Moderado / Transición</span>
        <span>🔴 <b>< 0.50:</b> Estrés Hídrico / Suelo Desnudo / Plaga</span>
    </div>
    """, unsafe_allow_html=True)

with col_graf:
    st.subheader("📊 Distribución y Diagnóstico Dron")

    df_zonas = pd.DataFrame({
        "Zona Espectral": ["🟢 Vigor Óptimo", "🟡 Vigor Moderado", "🔴 Estrés / Alerta"],
        "Hectáreas (ha)": [ha_opt, ha_mod, ha_est],
        "Porcentaje (%)": [pct_opt, pct_mod, pct_est]
    })
    fig_bar = px.bar(
        df_zonas,
        x="Hectáreas (ha)",
        y="Zona Espectral",
        orientation="h",
        text="Porcentaje (%)",
        color="Zona Espectral",
        color_discrete_map={
            "🟢 Vigor Óptimo": "#16A34A",
            "🟡 Vigor Moderado": "#EAB308",
            "🔴 Estrés / Alerta": "#DC2626"
        },
        height=230
    )
    fig_bar.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_bar.update_layout(showlegend=False, margin=dict(l=10, r=35, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown(f"""
    <div class="field-card">
        <h4 style="margin:0 0 6px 0; color:#22C55E !important;">🩺 Diagnóstico Agronómico Actual</h4>
        <p style="margin:0 0 10px 0; font-size:0.9rem;">{diag_txt}</p>
        <h4 style="margin:0 0 6px 0; color:#EAB308 !important;">🚁 Prescripción para Vuelo de Dron</h4>
        <p style="margin:0; font-size:0.9rem;">{rec_txt}</p>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("➕ Registrar Nuevo Monitoreo Multiespectral / Actualizar Lectura"):
        with st.form("form_nuevo_monitoreo_ndvi", clear_on_submit=True):
            m_fecha = st.date_input("Fecha de Captura / Vuelo", value=date.today())
            mc1, mc2, mc3 = st.columns(3)
            m_prom = mc1.number_input("Índice Promedio", min_value=0.0, max_value=1.0, value=val_prom, step=0.02, format="%.3f")
            m_opt = mc2.number_input("% Vigor Óptimo", min_value=0.0, max_value=100.0, value=pct_opt, step=1.0)
            m_est = mc3.number_input("% Estrés Crítico", min_value=0.0, max_value=100.0, value=pct_est, step=1.0)
            m_diag = st.text_area("Diagnóstico Observado", value=diag_txt, height=65)
            m_rec = st.text_input("Acción Recomendada con Dron", value=rec_txt)

            if st.form_submit_button("💾 Guardar Evaluación Multiespectral", type="primary", use_container_width=True):
                m_mod = max(round(100.0 - m_opt - m_est, 1), 0.0)
                ok, _ = insertar_registro_seguro(supabase, "Monitoreo_Multiespectral", {
                    "tipo_propiedad": "Campo Propio" if "Propios" in tipo_origen else "Cliente Dron",
                    "propietario": lote_info["propietario"],
                    "nombre_campo": lote_info["nombre_campo"],
                    "cultivo": lote_info["cultivo"],
                    "fecha_monitoreo": str(m_fecha),
                    "indice": indice_sel.split("—")[0].strip(),
                    "valor_promedio": float(m_prom),
                    "valor_min": round(max(m_prom - 0.28, 0.15), 3),
                    "valor_max": round(min(m_prom + 0.14, 0.95), 3),
                    "pct_vigor_optimo": float(m_opt),
                    "pct_vigor_moderado": float(m_mod),
                    "pct_estres_critico": float(m_est),
                    "diagnostico": m_diag.strip(),
                    "recomendacion_dron": m_rec.strip(),
                    "latitud": lote_info["latitud"],
                    "longitud": lote_info["longitud"]
                })
                if ok:
                    st.success("Lectura multiespectral guardada exitosamente.")
                    st.cache_data.clear()
                    st.rerun()
