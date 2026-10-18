import json
from datetime import date
import streamlit as st
import pandas as pd
import folium
from folium.plugins import Draw, Fullscreen
from streamlit_folium import st_folium

from utils_cesar import (
    init_supabase,
    apply_cesar_theme,
    CULTIVOS_FRECUENTES,
    construir_url_google_maps,
    calcular_geometria_poligono,
    cargar_tabla_segura,
    insertar_registro_seguro,
    mostrar_aviso_sql_si_local,
)

st.set_page_config(page_title="Campos Propios & Historial", page_icon="🌱", layout="wide")
apply_cesar_theme()

supabase = init_supabase()

st.markdown("""
<div class="cesar-header">
    <h1>🌱 Campos Propios — Historial Agronómico por Lote</h1>
    <p>Control integral de tus propios cultivos dividido en: Fertilizantes, Aplicaciones (Dron/Agroquímicos) y Extras (Siembra, Semilla, Trasplante, Quema de Hierba y Alertas de Agua).</p>
</div>
""", unsafe_allow_html=True)

df_campos_propios, ok_cp = cargar_tabla_segura(supabase, "Campos_Propios")
df_historial, ok_his = cargar_tabla_segura(supabase, "Historial_Campos_Propios")

mostrar_aviso_sql_si_local(ok_cp and ok_his)

# --- SECCIÓN SUPERIOR: SELECTOR DE CAMPO PROPIO Y REGISTRO DE NUEVO LOTE ---
col_sel, col_add = st.columns([1.4, 1])

with col_add:
    with st.expander("➕ Registrar Nuevo Campo Propio", expanded=df_campos_propios.empty):
        with st.form("form_nuevo_campo_propio", clear_on_submit=True):
            cp_nom = st.text_input("Nombre del Campo / Lote *", placeholder="Ej: Campo Propio 2 - La Esperanza")
            c1, c2, c3 = st.columns(3)
            cp_cul = c1.selectbox("Cultivo Actual *", options=CULTIVOS_FRECUENTES)
            cp_var = c2.text_input("Variedad / Híbrido", placeholder="Ej: Hass / IR-43")
            cp_ha = c3.number_input("Área (ha) *", min_value=0.1, value=4.0, step=0.25, format="%.2f")

            d1, d2, d3 = st.columns(3)
            cp_siembra = d1.date_input("Fecha Siembra / Plantación", value=date.today())
            cp_trasp = d2.date_input("Fecha Trasplante (Opcional)", value=date.today())
            cp_est = d3.selectbox("Estado", options=["En Campaña 🟢", "Preparación de Terreno 🚜", "Cosecha / Descanso 🌾"])

            g1, g2 = st.columns(2)
            cp_lat = g1.number_input("Latitud GPS", value=-7.219000, format="%.6f")
            cp_lon = g2.number_input("Longitud GPS", value=-79.435000, format="%.6f")
            cp_obs = st.text_input("Notas del Lote", placeholder="Ej: Suelo franco, turno de riego cada 8 días")

            if st.form_submit_button("💾 Crear Campo Propio", type="primary", use_container_width=True):
                if not cp_nom.strip():
                    st.error("Ingresa el nombre del campo propio.")
                else:
                    ok, msg = insertar_registro_seguro(supabase, "Campos_Propios", {
                        "nombre_lote": cp_nom.strip(),
                        "cultivo_actual": cp_cul,
                        "variedad": cp_var.strip(),
                        "area_ha": float(cp_ha),
                        "perimetro_m": round((cp_ha * 10000) ** 0.5 * 4, 1),
                        "fecha_siembra": str(cp_siembra),
                        "fecha_trasplante": str(cp_trasp),
                        "latitud": float(cp_lat),
                        "longitud": float(cp_lon),
                        "google_maps_url": construir_url_google_maps(cp_lat, cp_lon),
                        "estado": cp_est,
                        "observaciones": cp_obs.strip()
                    })
                    if ok:
                        st.success(f"Campo '{cp_nom}' registrado exitosamente.")
                        st.cache_data.clear()
                        st.rerun()

with col_sel:
    lista_lotes_propios = df_campos_propios["nombre_lote"].tolist() if not df_campos_propios.empty else ["Campo Propio 1 - El Molino"]
    lote_activo = st.selectbox("🎯 Selecciona tu Campo Propio para ver y registrar su Historial:", options=lista_lotes_propios)

    row_lote = df_campos_propios[df_campos_propios["nombre_lote"] == lote_activo].iloc[0] if not df_campos_propios.empty else {
        "id": 1, "nombre_lote": lote_activo, "cultivo_actual": "Arroz", "variedad": "NIR", "area_ha": 5.5,
        "fecha_siembra": str(date.today()), "fecha_trasplante": str(date.today()),
        "latitud": -7.219, "longitud": -79.435, "estado": "En Campaña 🟢", "observaciones": ""
    }
    area_lote_ha = float(row_lote.get("area_ha", 1.0))
    cultivo_lote = str(row_lote.get("cultivo_actual", "Arroz"))
    campo_id_activo = int(row_lote.get("id", 1))
    gmaps_lote = row_lote.get("google_maps_url") or construir_url_google_maps(float(row_lote.get("latitud") or -7.219), float(row_lote.get("longitud") or -79.435))

    st.markdown(f"""
    <div class="field-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
                <span style="background:#DCFCE7; color:#14532D; padding:4px 12px; border-radius:99px; font-weight:700; font-size:0.82rem;">
                    🌱 Cultivo: {cultivo_lote} ({row_lote.get('variedad') or 'Estándar'}) — {row_lote.get('estado', 'En Campaña')}
                </span>
                <h3 style="margin:6px 0 4px 0;">{lote_activo}</h3>
                <p style="margin:0; font-size:0.88rem;" class="tabular-nums">
                    📐 <b>Área:</b> {area_lote_ha:.2f} ha &nbsp;|&nbsp;
                    🗓️ <b>Siembra:</b> {row_lote.get('fecha_siembra', '—')} &nbsp;|&nbsp;
                    🌿 <b>Trasplante:</b> {row_lote.get('fecha_trasplante', '—')}
                </p>
            </div>
            <div>
                <a href="{gmaps_lote}" target="_blank" class="gps-btn">📍 Ruta GPS al Campo</a>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Filtrar historial del campo seleccionado
df_hist_lote = df_historial[df_historial["nombre_lote"] == lote_activo].copy() if not df_historial.empty else pd.DataFrame()

# KPIs Rápidos del Campo Propio
df_fert = df_hist_lote[df_hist_lote["categoria"] == "Fertilizantes"] if not df_hist_lote.empty else pd.DataFrame()
df_apli = df_hist_lote[df_hist_lote["categoria"] == "Aplicaciones"] if not df_hist_lote.empty else pd.DataFrame()
df_extr = df_hist_lote[df_hist_lote["categoria"] == "Extras"] if not df_hist_lote.empty else pd.DataFrame()
costo_acumulado = float(df_hist_lote["costo_total_pen"].sum()) if not df_hist_lote.empty else 0.0

k1, k2, k3, k4 = st.columns(4)
k1.metric("🧪 Fertilizadas Registradas", f"{len(df_fert)} eventos")
k2.metric("🚁 Aplicaciones Dron / Fito", f"{len(df_apli)} vuelos")
k3.metric("📝 Labores & Notas Extras", f"{len(df_extr)} registros")
k4.metric("💰 Inversión Acumulada Lote", f"S/ {costo_acumulado:,.2f}", f"S/ {costo_acumulado / max(area_lote_ha, 0.1):,.2f} / ha")

# ==============================================================================
# LAS 3 SECCIONES DEL HISTORIAL QUE PIDIÓ CÉSAR EN EL AUDIO
# ==============================================================================
tab_fertilizantes, tab_aplicaciones, tab_extras = st.tabs([
    "🧪 1. Fertilizantes (1ra, 2da, 3ra Fertilizada...)",
    "🚁 2. Aplicaciones Dron (Insecticidas / Agroquímicos)",
    "📝 3. Extras (Siembra, Semilla, Trasplante, Quema de Hierba, Agua)"
])

# ------------------------------------------------------------------------------
# SECCIÓN 1: FERTILIZANTES
# ------------------------------------------------------------------------------
with tab_fertilizantes:
    c_form_f, c_hist_f = st.columns([1, 1.45], gap="large")

    with c_form_f:
        st.markdown(f"#### ➕ Registrar Fertilizada en **{lote_activo}**")
        with st.form("form_fert_propio", clear_on_submit=True):
            f_fecha = st.date_input("Fecha de Fertilización *", value=date.today())
            f_etapa = st.selectbox(
                "Etapa de Fertilización *",
                options=[
                    "Abonamiento de Fondo / Base",
                    "1ra Fertilizada",
                    "2da Fertilizada",
                    "3ra Fertilizada",
                    "4ta Fertilizada / Cierre",
                    "Fertirriego / Enmienda Húmica"
                ]
            )
            f_prods = st.text_area(
                "Fertilizantes Utilizados por Hectárea *",
                placeholder="Ej: Urea (4 sacos/ha) + Fosfato Diamónico (2 sacos/ha) + Sulfato de Potasio (1 saco/ha)",
                height=80
            )
            fc1, fc2 = st.columns(2)
            f_dosis_ha = fc1.text_input("Dosis Total por Hectárea *", placeholder="Ej: 300 Kg/ha (6 sacos/ha)")
            f_metodo = fc2.selectbox("Método de Aplicación", options=["Voleo Manual", "Dron Esparcidor", "Fertirriego", "Incorporado / Abonadora"])

            fc3, fc4, fc5 = st.columns(3)
            f_cant_tot = fc3.number_input("Cantidad Total Lote", min_value=0.0, value=float(area_lote_ha * 250), step=25.0)
            f_unid = fc4.selectbox("Unidad", options=["Kg", "Sacos (50kg)", "Litros", "Toneladas"])
            f_costo = fc5.number_input("Costo Total (S/)", min_value=0.0, value=0.0, step=50.0)

            f_obs = st.text_input("Observaciones de la Fertilizada", placeholder="Ej: Terreno húmedo, buena incorporación.")

            if st.form_submit_button("💾 Guardar Fertilizada en Historial", type="primary", use_container_width=True):
                if not f_prods.strip():
                    st.error("Especifica qué fertilizantes se utilizaron.")
                else:
                    ok, _ = insertar_registro_seguro(supabase, "Historial_Campos_Propios", {
                        "campo_id": campo_id_activo,
                        "nombre_lote": lote_activo,
                        "cultivo": cultivo_lote,
                        "categoria": "Fertilizantes",
                        "fecha": str(f_fecha),
                        "etapa_labor": f_etapa,
                        "productos_detalle": f_prods.strip(),
                        "dosis_por_ha": f_dosis_ha.strip(),
                        "cantidad_total": float(f_cant_tot),
                        "unidad": f_unid,
                        "costo_total_pen": float(f_costo),
                        "metodo_equipo": f_metodo,
                        "alerta_campo": "Normal 🟢",
                        "observaciones": f_obs.strip()
                    })
                    if ok:
                        st.success(f"{f_etapa} registrada en {lote_activo}.")
                        st.cache_data.clear()
                        st.rerun()

    with c_hist_f:
        st.markdown(f"#### 📜 Historial de Fertilizaciones — **{lote_activo}** ({area_lote_ha:.2f} ha)")
        if df_fert.empty:
            st.info("Aún no hay fertilizadas registradas en este campo.")
        else:
            df_fert_sorted = df_fert.sort_values(by="fecha", ascending=False)
            for _, rf in df_fert_sorted.iterrows():
                st.markdown(f"""
                <div class="field-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="background:#DCFCE7; color:#14532D; padding:3px 10px; border-radius:99px; font-weight:700; font-size:0.8rem;">
                            🧪 {rf.get('etapa_labor')}
                        </span>
                        <span class="tabular-nums" style="font-size:0.85rem; font-weight:600;">
                            📅 {rf.get('fecha')} &nbsp;|&nbsp; 💰 S/ {float(rf.get('costo_total_pen', 0)):,.2f}
                        </span>
                    </div>
                    <p style="margin:8px 0 4px 0; font-weight:600;">
                        Fertilizantes: {rf.get('productos_detalle')}
                    </p>
                    <p style="margin:0; font-size:0.86rem;" class="tabular-nums">
                        ⚖️ <b>Dosis/ha:</b> {rf.get('dosis_por_ha') or '—'} &nbsp;|&nbsp;
                        📦 <b>Total Lote:</b> {float(rf.get('cantidad_total', 0)):,.1f} {rf.get('unidad', '')} &nbsp;|&nbsp;
                        🚜 <b>Método:</b> {rf.get('metodo_equipo', '')}
                    </p>
                    <p class="muted-text" style="margin:4px 0 0 0;">
                        {rf.get('observaciones') or ''}
                    </p>
                </div>
                """, unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# SECCIÓN 2: APLICACIONES (DRON / INSECTICIDAS / AGROQUÍMICOS)
# ------------------------------------------------------------------------------
with tab_aplicaciones:
    c_form_a, c_hist_a = st.columns([1, 1.45], gap="large")

    with c_form_a:
        st.markdown(f"#### ➕ Registrar Aplicación Fitosanitaria / Dron en **{lote_activo}**")
        with st.form("form_apli_propio", clear_on_submit=True):
            a_fecha = st.date_input("Fecha de Aplicación *", value=date.today())
            a_etapa = st.text_input("Nombre / Objetivo de Aplicación *", placeholder="Ej: 1ra Aplicación Dron - Control Insecticida / Mosca / Hongos")
            a_prods = st.text_area(
                "Agroquímicos / Productos en Mezcla *",
                placeholder="Ej: Engeo (200 ml/ha) + Mancozeb (1 Kg/ha) + Foliar Aminoácidos (500 ml/ha)",
                height=80
            )
            ac1, ac2 = st.columns(2)
            a_dosis_ha = ac1.text_input("Dosis / Volumen Caldo por Ha *", value="25 L caldo/ha")
            a_equipo = ac2.selectbox("Equipo Utilizado", options=["Dron DJI Agras", "Mochila Motorizada", " Pulverizadora Tractor", "Drench"])

            ac3, ac4, ac5 = st.columns(3)
            a_cant = ac3.number_input("Litros/Kg Producto Total", min_value=0.0, value=2.5, step=0.5)
            a_unid = ac4.selectbox("Unidad", options=["Lt", "Kg", "Cilindros", "Tanques Dron"])
            a_costo = ac5.number_input("Costo Estimado (S/)", min_value=0.0, value=0.0, step=20.0)

            a_obs = st.text_input("Observaciones de la Aplicación", placeholder="Ej: Plaga controlada al 95%, repetir en 12 días.")

            if st.form_submit_button("💾 Guardar Aplicación en Historial", type="primary", use_container_width=True):
                if not a_prods.strip() or not a_etapa.strip():
                    st.error("Completa el objetivo y los agroquímicos aplicados.")
                else:
                    ok, _ = insertar_registro_seguro(supabase, "Historial_Campos_Propios", {
                        "campo_id": campo_id_activo,
                        "nombre_lote": lote_activo,
                        "cultivo": cultivo_lote,
                        "categoria": "Aplicaciones",
                        "fecha": str(a_fecha),
                        "etapa_labor": a_etapa.strip(),
                        "productos_detalle": a_prods.strip(),
                        "dosis_por_ha": a_dosis_ha.strip(),
                        "cantidad_total": float(a_cant),
                        "unidad": a_unid,
                        "costo_total_pen": float(a_costo),
                        "metodo_equipo": a_equipo,
                        "alerta_campo": "Normal 🟢",
                        "observaciones": a_obs.strip()
                    })
                    if ok:
                        st.success(f"Aplicación '{a_etapa}' guardada en {lote_activo}.")
                        st.cache_data.clear()
                        st.rerun()

    with c_hist_a:
        st.markdown(f"#### 🚁 Historial de Aplicaciones (Dron & Agroquímicos) — **{lote_activo}**")
        if df_apli.empty:
            st.info("Aún no hay aplicaciones fitosanitarias registradas en este campo.")
        else:
            df_apli_sorted = df_apli.sort_values(by="fecha", ascending=False)
            for _, ra in df_apli_sorted.iterrows():
                st.markdown(f"""
                <div class="field-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="background:#E0F2FE; color:#0369A1; padding:3px 10px; border-radius:99px; font-weight:700; font-size:0.8rem;">
                            🚁 {ra.get('etapa_labor')}
                        </span>
                        <span class="tabular-nums" style="font-size:0.85rem; font-weight:600;">
                            📅 {ra.get('fecha')} &nbsp;|&nbsp; 💰 S/ {float(ra.get('costo_total_pen', 0)):,.2f}
                        </span>
                    </div>
                    <p style="margin:8px 0 4px 0; font-weight:600;">
                        Agroquímicos: {ra.get('productos_detalle')}
                    </p>
                    <p style="margin:0; font-size:0.86rem;" class="tabular-nums">
                        💧 <b>Dosis / Caldo:</b> {ra.get('dosis_por_ha') or '—'} &nbsp;|&nbsp;
                        🚁 <b>Equipo:</b> {ra.get('metodo_equipo', '')}
                    </p>
                    <p class="muted-text" style="margin:4px 0 0 0;">
                        {ra.get('observaciones') or ''}
                    </p>
                </div>
                """, unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# SECCIÓN 3: EXTRAS (SIEMBRA, SEMILLA, TRASPLANTE, QUEMA DE HIERBA, DEFICIENCIA DE AGUA)
# ------------------------------------------------------------------------------
with tab_extras:
    c_form_e, c_hist_e = st.columns([1, 1.45], gap="large")

    with c_form_e:
        st.markdown(f"#### ➕ Registrar Evento Extra / Bitácora en **{lote_activo}**")
        with st.form("form_extra_propio", clear_on_submit=True):
            e_fecha = st.date_input("Fecha del Evento *", value=date.today())
            e_tipo = st.selectbox(
                "Tipo de Labor / Registro Extra *",
                options=[
                    "🌱 Siembra / Plantación y Cantidad de Semilla",
                    "🌿 Fecha de Trasplante",
                    "🔥 Quema de Hierba / Control de Maleza",
                    "💧 Alerta de Riego / Deficiencia de Agua",
                    "✂️ Deshierbe / Poda / Aporque",
                    "📌 Otra Observación de Campo"
                ]
            )
            e_detalle = st.text_area(
                "Detalle (Semilla usada, herbicida de quema, estado hídrico, etc.) *",
                placeholder="Ej: Se utilizó 80 Kg/ha de semilla certificada. Se quemó hierba en bordos el día martes. Sector sur con deficiencia de agua.",
                height=85
            )
            ec1, ec2, ec3 = st.columns(3)
            e_dosis = ec1.text_input("Cantidad / Indicador x Ha", placeholder="Ej: 80 Kg semilla/ha")
            e_alerta = ec2.selectbox(
                "Condición del Cultivo",
                options=[
                    "Normal 🟢",
                    "Deficiencia de Agua 💧",
                    "Exceso de Humedad 🌊",
                    "Maleza Alta 🌿",
                    "Presencia de Plaga 🐛",
                    "Deficiencia Nutricional 🍂"
                ]
            )
            e_costo = ec3.number_input("Gasto Asociado (S/)", min_value=0.0, value=0.0, step=20.0)

            e_obs = st.text_input("Nota Adicional / Recordatorio", placeholder="Ej: Programar riego pesado este viernes.")

            if st.form_submit_button("💾 Guardar en Bitácora de Extras", type="primary", use_container_width=True):
                if not e_detalle.strip():
                    st.error("Ingresa el detalle del evento o nota de campo.")
                else:
                    ok, _ = insertar_registro_seguro(supabase, "Historial_Campos_Propios", {
                        "campo_id": campo_id_activo,
                        "nombre_lote": lote_activo,
                        "cultivo": cultivo_lote,
                        "categoria": "Extras",
                        "fecha": str(e_fecha),
                        "etapa_labor": e_tipo,
                        "productos_detalle": e_detalle.strip(),
                        "dosis_por_ha": e_dosis.strip(),
                        "cantidad_total": 0.0,
                        "unidad": "Global",
                        "costo_total_pen": float(e_costo),
                        "metodo_equipo": "Campo",
                        "alerta_campo": e_alerta,
                        "observaciones": e_obs.strip()
                    })
                    if ok:
                        st.success("Evento extra guardado en el historial del campo.")
                        st.cache_data.clear()
                        st.rerun()

    with c_hist_e:
        st.markdown(f"#### 📝 Bitácora de Extras (Siembra, Semilla, Quema, Agua) — **{lote_activo}**")
        if df_extr.empty:
            st.info("Aún no hay registros extras en este campo.")
        else:
            df_extr_sorted = df_extr.sort_values(by="fecha", ascending=False)
            for _, re_row in df_extr_sorted.iterrows():
                alerta_str = str(re_row.get("alerta_campo", "Normal 🟢"))
                bg_badge = "#FEF2F2" if "Deficiencia" in alerta_str or "Plaga" in alerta_str else "#FEF9C3"
                col_badge = "#991B1B" if "Deficiencia" in alerta_str or "Plaga" in alerta_str else "#854D0E"
                st.markdown(f"""
                <div class="field-card">
                    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
                        <span style="background:#DCFCE7; color:#14532D; padding:3px 10px; border-radius:99px; font-weight:700; font-size:0.8rem;">
                            {re_row.get('etapa_labor')}
                        </span>
                        <span style="background:{bg_badge}; color:{col_badge}; padding:3px 10px; border-radius:99px; font-weight:700; font-size:0.78rem;">
                            Estado: {alerta_str}
                        </span>
                        <span class="tabular-nums" style="font-size:0.85rem; font-weight:600;">
                            📅 {re_row.get('fecha')} &nbsp;|&nbsp; 💰 S/ {float(re_row.get('costo_total_pen', 0)):,.2f}
                        </span>
                    </div>
                    <p style="margin:8px 0 4px 0; font-weight:600;">
                        {re_row.get('productos_detalle')}
                    </p>
                    <p style="margin:0; font-size:0.84rem;">
                        📌 <b>Indicador/Semilla:</b> {re_row.get('dosis_por_ha') or '—'} &nbsp;|&nbsp;
                        <b>Nota:</b> {re_row.get('observaciones') or '—'}
                    </p>
                </div>
                """, unsafe_allow_html=True)
