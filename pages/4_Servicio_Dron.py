import json
from datetime import date, datetime
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
    actualizar_registro_seguro,
    eliminar_registro_seguro,
    mostrar_aviso_sql_si_local,
    generar_pdf_reporte_dron,
    renderizar_preview_pdf,
)

st.set_page_config(page_title="Servicio Dron & Clientes", page_icon="🚁", layout="wide")
apply_cesar_theme()

supabase = init_supabase()

st.markdown("""
<div class="cesar-header">
    <h1>🚁 Servicio Dron — Clientes, Mapas GPS y Liquidación PDF</h1>
    <p>Gestión de clientes, delimitación satelital de cultivos (área, perímetro y ruta Google Maps) y reportes de cobro por hectárea.</p>
</div>
""", unsafe_allow_html=True)

# Carga de datos
df_clientes, ok_cli = cargar_tabla_segura(supabase, "Clientes_Dron")
df_campos, ok_cam = cargar_tabla_segura(supabase, "Campos_Clientes_Dron")
df_servicios, ok_srv = cargar_tabla_segura(supabase, "Servicios_Dron")

mostrar_aviso_sql_si_local(ok_cli and ok_cam and ok_srv)

tab_clientes_mapa, tab_registrar_vuelo, tab_reportes_pdf = st.tabs([
    "🗺️ 1. Clientes, Cultivos y Delimitación GPS",
    "🚁 2. Registrar Aplicación / Vuelo de Dron",
    "📊 3. Cuadros Resúmenes y Reporte PDF"
])

# ==============================================================================
# TAB 1: CLIENTES, CULTIVOS Y DELIMITACIÓN EN MAPA SATELITAL + RUTA GOOGLE MAPS
# ==============================================================================
with tab_clientes_mapa:
    col_izq, col_der = st.columns([1.05, 1.45], gap="large")

    with col_izq:
        st.subheader("👥 1. Gestión de Clientes")
        with st.expander("➕ Añadir Nuevo Cliente", expanded=df_clientes.empty):
            with st.form("form_nuevo_cliente", clear_on_submit=True):
                c_nom = st.text_input("Nombre del Cliente / Fundo *", placeholder="Ej: Leonardo")
                c1, c2 = st.columns(2)
                c_tel = c1.text_input("Teléfono / WhatsApp", placeholder="Ej: 948112233")
                c_doc = c2.text_input("DNI / RUC (Opcional)", placeholder="Ej: 10458923141")
                c_zona = st.text_input("Zona / Valle / Referencia", placeholder="Ej: Chepén / San José / Guadalupe")
                c_not = st.text_area("Notas del Cliente", placeholder="Cultivos principales, acuerdos de tarifa, etc.", height=68)

                if st.form_submit_button("💾 Guardar Cliente", type="primary", use_container_width=True):
                    if not c_nom.strip():
                        st.error("El nombre del cliente es obligatorio.")
                    else:
                        ok, msg = insertar_registro_seguro(supabase, "Clientes_Dron", {
                            "nombre": c_nom.strip(),
                            "telefono": c_tel.strip(),
                            "ruc_dni": c_doc.strip(),
                            "zona_sector": c_zona.strip(),
                            "notas": c_not.strip(),
                            "activo": True
                        })
                        if ok:
                            st.success(f"Cliente '{c_nom}' registrado ({msg}).")
                            st.cache_data.clear()
                            st.rerun()

        # Selector de Cliente activo
        lista_clientes = df_clientes["nombre"].tolist() if not df_clientes.empty else ["Leonardo"]
        cliente_sel = st.selectbox("🎯 Seleccionar Cliente para ver sus Cultivos y Campos:", options=lista_clientes)

        # Editar o Eliminar el Cliente seleccionado
        if not df_clientes.empty and cliente_sel in df_clientes["nombre"].values:
            row_cli_act = df_clientes[df_clientes["nombre"] == cliente_sel].iloc[0]
            cli_act_id = int(row_cli_act["id"])
            with st.expander(f"✏️ Editar o 🗑️ Eliminar Cliente: {cliente_sel}", expanded=False):
                with st.form(f"form_edit_cli_{cli_act_id}"):
                    ec_nom = st.text_input("Nombre del Cliente", value=str(row_cli_act.get("nombre") or ""))
                    ec1, ec2 = st.columns(2)
                    ec_tel = ec1.text_input("Teléfono", value=str(row_cli_act.get("telefono") or ""))
                    ec_doc = ec2.text_input("DNI / RUC", value=str(row_cli_act.get("ruc_dni") or ""))
                    ec_zon = st.text_input("Zona / Sector", value=str(row_cli_act.get("zona_sector") or ""))
                    ec_not = st.text_area("Notas", value=str(row_cli_act.get("notas") or ""), height=60)
                    b_save_cli, b_del_cli = st.columns(2)
                    if b_save_cli.form_submit_button("💾 Actualizar Cliente", type="primary", use_container_width=True):
                        nuevo_nom = ec_nom.strip()
                        actualizar_registro_seguro(supabase, "Clientes_Dron", cli_act_id, {
                            "nombre": nuevo_nom,
                            "telefono": ec_tel.strip(),
                            "ruc_dni": ec_doc.strip(),
                            "zona_sector": ec_zon.strip(),
                            "notas": ec_not.strip(),
                        })
                        st.success("Cliente actualizado correctamente.")
                        st.cache_data.clear()
                        st.rerun()
                    if b_del_cli.form_submit_button("🗑️ Borrar Cliente", use_container_width=True):
                        eliminar_registro_seguro(supabase, "Clientes_Dron", cli_act_id)
                        st.warning(f"Cliente '{cliente_sel}' eliminado.")
                        st.cache_data.clear()
                        st.rerun()

        # Filtro de cultivos del cliente seleccionado
        df_campos_cli = df_campos[df_campos["cliente_nombre"] == cliente_sel].copy() if not df_campos.empty else pd.DataFrame()

        if not df_campos_cli.empty:
            cultivos_del_cliente = ["Todos"] + sorted(df_campos_cli["cultivo"].unique().tolist())
            filtro_cult_mapa = st.radio(
                f"🌱 Cultivos de {cliente_sel}:",
                options=cultivos_del_cliente,
                horizontal=True
            )
            if filtro_cult_mapa != "Todos":
                df_campos_cli = df_campos_cli[df_campos_cli["cultivo"] == filtro_cult_mapa]

            st.markdown(f"#### 📍 Campos delimitados de **{cliente_sel}** ({len(df_campos_cli)})")
            for _, row_c in df_campos_cli.iterrows():
                campo_id_card = int(row_c["id"])
                lat_c = float(row_c.get("latitud") or -7.2215)
                lon_c = float(row_c.get("longitud") or -79.4312)
                gmaps_link = row_c.get("google_maps_url") or construir_url_google_maps(lat_c, lon_c)

                with st.container():
                    st.markdown(f"""
                    <div class="field-card">
                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                            <div>
                                <span style="background:#DCFCE7; color:#14532D; padding:3px 10px; border-radius:99px; font-weight:700; font-size:0.8rem;">
                                    🌱 {row_c.get('cultivo', 'Cultivo')}
                                </span>
                                <h4 style="margin:6px 0 2px 0;">{row_c.get('nombre_campo', 'Campo')}</h4>
                                <p style="margin:0; font-size:0.86rem;" class="tabular-nums">
                                    📐 <b>Área:</b> {float(row_c.get('area_ha', 0)):.2f} ha &nbsp;|&nbsp;
                                    📏 <b>Perímetro:</b> {float(row_c.get('perimetro_m', 0)):,.0f} m &nbsp;|&nbsp;
                                    🧭 <b>GPS:</b> {lat_c:.5f}, {lon_c:.5f}
                                </p>
                                <p class="muted-text" style="margin:4px 0 0 0;">
                                    {row_c.get('observaciones') or 'Sin observaciones de vuelo.'}
                                </p>
                            </div>
                            <div>
                                <a href="{gmaps_link}" target="_blank" class="gps-btn">
                                    📍 Abrir Ruta en Google Maps
                                </a>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    with st.expander(f"✏️ Editar o 🗑️ Borrar «{row_c.get('nombre_campo', 'Campo')}»", expanded=False):
                        with st.form(f"form_edit_campo_{campo_id_card}"):
                            ed1, ed2, ed3 = st.columns([1.3, 1, 0.9])
                            ed_nom = ed1.text_input("Nombre del Campo", value=str(row_c.get("nombre_campo") or ""))
                            cult_actual = str(row_c.get("cultivo") or "Palto")
                            ed_cul = ed2.selectbox(
                                "Cultivo",
                                options=CULTIVOS_FRECUENTES,
                                index=CULTIVOS_FRECUENTES.index(cult_actual) if cult_actual in CULTIVOS_FRECUENTES else 0
                            )
                            ed_ha = ed3.number_input("Área (ha)", min_value=0.05, value=float(row_c.get("area_ha") or 1.0), step=0.25, format="%.2f")

                            ed4, ed5, ed6 = st.columns(3)
                            ed_per = ed4.number_input("Perímetro (m)", min_value=0.0, value=float(row_c.get("perimetro_m") or 0.0), step=10.0, format="%.1f")
                            ed_lat = ed5.number_input("Latitud GPS", value=lat_c, format="%.6f")
                            ed_lon = ed6.number_input("Longitud GPS", value=lon_c, format="%.6f")

                            ed_obs = st.text_input("Observaciones", value=str(row_c.get("observaciones") or ""))

                            btn_col1, btn_col2 = st.columns(2)
                            if btn_col1.form_submit_button("💾 Guardar Cambios", type="primary", use_container_width=True):
                                actualizar_registro_seguro(supabase, "Campos_Clientes_Dron", campo_id_card, {
                                    "nombre_campo": ed_nom.strip(),
                                    "cultivo": ed_cul,
                                    "area_ha": float(ed_ha),
                                    "perimetro_m": float(ed_per),
                                    "latitud": float(ed_lat),
                                    "longitud": float(ed_lon),
                                    "google_maps_url": construir_url_google_maps(float(ed_lat), float(ed_lon)),
                                    "observaciones": ed_obs.strip()
                                })
                                st.success(f"Campo '{ed_nom}' actualizado.")
                                st.cache_data.clear()
                                st.rerun()

                            if btn_col2.form_submit_button("🗑️ Borrar Campo", use_container_width=True):
                                eliminar_registro_seguro(supabase, "Campos_Clientes_Dron", campo_id_card)
                                st.warning(f"Campo '{row_c.get('nombre_campo')}' eliminado.")
                                st.cache_data.clear()
                                st.rerun()
        else:
            st.info(f"El cliente **{cliente_sel}** aún no tiene campos delimitados. Dibuja su polígono en el mapa de la derecha para agregarlo.")

    with col_der:
        st.subheader(f"🛰️ 2. Delimitar Área y Ubicación para: {cliente_sel}")
        st.caption("Usa el botón de polígono (pentágono en la esquina superior izquierda del mapa) para contornear el campo. El sistema calcula automáticamente las hectáreas, el perímetro y la ruta GPS.")

        # Centro inicial del mapa
        center_lat, center_lon = -7.2235, -79.4291
        if not df_campos_cli.empty:
            center_lat = float(df_campos_cli.iloc[0].get("latitud") or -7.2235)
            center_lon = float(df_campos_cli.iloc[0].get("longitud") or -79.4291)

        m = folium.Map(location=[center_lat, center_lon], zoom_start=15, control_scale=True)

        # Capa Satelital Google Hybrid (con nombres de caminos y acequias)
        folium.TileLayer(
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google Satellite Hybrid",
            name="🛰️ Satélite + Caminos (Google)",
            overlay=False,
            control=True
        ).add_to(m)

        # Pintar polígonos existentes del cliente
        if not df_campos_cli.empty:
            for _, rc in df_campos_cli.iterrows():
                g_str = rc.get("geojson")
                lat_m = float(rc.get("latitud") or center_lat)
                lon_m = float(rc.get("longitud") or center_lon)
                url_m = rc.get("google_maps_url") or construir_url_google_maps(lat_m, lon_m)
                if g_str:
                    try:
                        g_obj = json.loads(g_str) if isinstance(g_str, str) else g_str
                        folium.GeoJson(
                            g_obj,
                            name=f"{rc['cultivo']} - {rc['nombre_campo']}",
                            style_function=lambda x: {
                                "fillColor": "#22C55E",
                                "color": "#15803D",
                                "weight": 3,
                                "fillOpacity": 0.35
                            },
                            tooltip=f"{rc['cliente_nombre']} | {rc['cultivo']}: {rc['nombre_campo']} ({float(rc['area_ha']):.2f} ha)"
                        ).add_to(m)
                    except Exception:
                        pass

                folium.Marker(
                    location=[lat_m, lon_m],
                    tooltip=f"📍 {rc['nombre_campo']} ({rc['cultivo']}) - {float(rc['area_ha']):.2f} ha",
                    popup=folium.Popup(
                        f"<b>Cliente:</b> {rc['cliente_nombre']}<br>"
                        f"<b>Cultivo:</b> {rc['cultivo']}<br>"
                        f"<b>Campo:</b> {rc['nombre_campo']}<br>"
                        f"<b>Área:</b> {float(rc['area_ha']):.2f} ha<br>"
                        f"<b>Perímetro:</b> {float(rc['perimetro_m']):.0f} m<br>"
                        f"<a href='{url_m}' target='_blank'><b>👉 Ir con Google Maps</b></a>",
                        max_width=240
                    ),
                    icon=folium.Icon(color="green", icon="leaf", prefix="fa")
                ).add_to(m)

        draw = Draw(
            export=False,
            position="topleft",
            draw_options={
                "polyline": False,
                "polygon": {"allowIntersection": False, "showArea": True},
                "rectangle": True,
                "circle": False,
                "marker": True,
                "circlemarker": False,
            },
            edit_options={"edit": True, "remove": True}
        )
        draw.add_to(m)
        Fullscreen(position="topright").add_to(m)

        st_map_data = st_folium(m, width=None, height=440, returned_objects=["last_active_drawing"])

        # Detectar dibujo en el mapa
        dibujo = st_map_data.get("last_active_drawing") if st_map_data else None
        geom_calc = calcular_geometria_poligono(dibujo) if dibujo else None

        if geom_calc and geom_calc["area_ha"] > 0:
            st.success(
                f"✨ **Polígono detectado en el mapa:** Área calculada = **{geom_calc['area_ha']:.2f} ha** | "
                f"Perímetro = **{geom_calc['perimetro_m']:,.1f} m** | "
                f"Centro GPS = `{geom_calc['latitud']:.5f}, {geom_calc['longitud']:.5f}`"
            )

        with st.form("form_guardar_campo_cliente"):
            st.markdown(f"#### 💾 Registrar Cultivo / Lote para **{cliente_sel}**")
            f1, f2, f3 = st.columns([1.2, 1, 0.9])
            cultivo_campo = f1.selectbox("Cultivo *", options=CULTIVOS_FRECUENTES)
            nombre_campo = f2.text_input("Nombre del Campo / Lote *", placeholder="Ej: Lote San Pedro / Parcela 2")
            area_default = float(geom_calc["area_ha"]) if (geom_calc and geom_calc["area_ha"] > 0) else 5.0
            area_input = f3.number_input("Área Delimitada (ha) *", min_value=0.1, value=area_default, step=0.25, format="%.2f")

            g1, g2, g3 = st.columns(3)
            perim_default = float(geom_calc["perimetro_m"]) if geom_calc else round(math.sqrt(area_input * 10000) * 4, 1) if 'math' in globals() else 900.0
            perimetro_input = g1.number_input("Perímetro (m)", min_value=0.0, value=perim_default, step=10.0, format="%.1f")
            lat_default = float(geom_calc["latitud"]) if geom_calc else center_lat
            lon_default = float(geom_calc["longitud"]) if geom_calc else center_lon
            lat_input = g2.number_input("Latitud GPS", value=lat_default, format="%.6f")
            lon_input = g3.number_input("Longitud GPS", value=lon_default, format="%.6f")

            obs_campo = st.text_input("Observaciones de Ubicación / Obstáculos (Cables, árboles, entrada)", placeholder="Ej: Entrar por el canal lateral derecho, cables altos al sur.")

            if st.form_submit_button("💾 Guardar Campo y Generar Ruta Google Maps", type="primary", use_container_width=True):
                if not nombre_campo.strip():
                    st.error("Ingresa un nombre para identificar el campo o lote.")
                else:
                    cli_rows = df_clientes[df_clientes["nombre"] == cliente_sel] if not df_clientes.empty else pd.DataFrame()
                    cli_id = int(cli_rows.iloc[0]["id"]) if not cli_rows.empty else 1
                    url_gmaps = construir_url_google_maps(lat_input, lon_input)
                    geojson_str = json.dumps(dibujo) if dibujo else ""

                    ok, msg = insertar_registro_seguro(supabase, "Campos_Clientes_Dron", {
                        "cliente_id": cli_id,
                        "cliente_nombre": cliente_sel,
                        "nombre_campo": nombre_campo.strip(),
                        "cultivo": cultivo_campo,
                        "area_ha": float(area_input),
                        "perimetro_m": float(perimetro_input),
                        "latitud": float(lat_input),
                        "longitud": float(lon_input),
                        "google_maps_url": url_gmaps,
                        "geojson": geojson_str,
                        "observaciones": obs_campo.strip(),
                    })
                    if ok:
                        st.success(f"Campo '{nombre_campo}' ({cultivo_campo} - {area_input:.2f} ha) guardado con ruta Google Maps.")
                        st.cache_data.clear()
                        st.rerun()

# ==============================================================================
# TAB 2: REGISTRAR SERVICIO / APLICACIÓN DE DRON A CLIENTE
# ==============================================================================
with tab_registrar_vuelo:
    st.subheader("🚁 Registrar Trabajo de Dron Realizado")

    c_sel1, c_sel2 = st.columns(2)
    cli_vuelo = c_sel1.selectbox("Cliente *", options=lista_clientes, key="vuelo_cli_sel")

    campos_del_cli = df_campos[df_campos["cliente_nombre"] == cli_vuelo] if not df_campos.empty else pd.DataFrame()
    if not campos_del_cli.empty:
        opciones_campo = [f"{r['nombre_campo']} ({r['cultivo']} - {float(r['area_ha']):.2f} ha)" for _, r in campos_del_cli.iterrows()]
    else:
        opciones_campo = ["➕ Ingresar cultivo/campo manualmente"]

    campo_vuelo_str = c_sel2.selectbox("Campo / Cultivo del Cliente *", options=opciones_campo)

    if not campos_del_cli.empty and campo_vuelo_str != "➕ Ingresar cultivo/campo manualmente":
        idx_c = opciones_campo.index(campo_vuelo_str)
        row_campo_sel = campos_del_cli.iloc[idx_c]
        cultivo_def = row_campo_sel["cultivo"]
        nombre_campo_def = row_campo_sel["nombre_campo"]
        ha_def = float(row_campo_sel["area_ha"])
        campo_id_def = int(row_campo_sel["id"])
    else:
        cultivo_def = "Palto"
        nombre_campo_def = "Lote General"
        ha_def = 5.0
        campo_id_def = None

    with st.form("form_registro_servicio_dron"):
        r1, r2, r3, r4 = st.columns(4)
        fecha_srv = r1.date_input("Fecha de Aplicación *", value=date.today())
        cultivo_srv = r2.selectbox(
            "Cultivo Aplicado *",
            options=CULTIVOS_FRECUENTES,
            index=CULTIVOS_FRECUENTES.index(cultivo_def) if cultivo_def in CULTIVOS_FRECUENTES else 0
        )
        nombre_lote_srv = r3.text_input("Nombre del Lote / Parcela *", value=nombre_campo_def)
        tipo_ap_srv = r4.selectbox(
            "Tipo de Servicio Dron *",
            options=[
                "Aplicación Insecticida / Plagas",
                "Aplicación Fungicida",
                "Aplicación Foliar / Bioestimulante",
                "Aplicación Herbicida / Quema",
                "Esparcido de Fertilizante Granulado",
                "Vuelo Multiespectral NDVI"
            ]
        )

        m1, m2, m3, m4 = st.columns(4)
        ha_aplicadas = m1.number_input("Hectáreas Aplicadas (ha) *", min_value=0.1, value=ha_def, step=0.5, format="%.2f")
        precio_ha = m2.number_input("Precio por Hectárea (S/ / ha) *", min_value=1.0, value=60.0, step=5.0, format="%.2f")
        vol_caldo = m3.number_input("Volumen Caldo (L/ha)", min_value=5.0, value=25.0, step=5.0)
        estado_pago = m4.selectbox("Estado del Cobro", options=["Pendiente", "Pagado", "Parcial"])

        total_calculado = round(ha_aplicadas * precio_ha, 2)
        st.info(f"💰 **Cálculo Automático:** `{ha_aplicadas:.2f} ha` × `S/ {precio_ha:.2f}` = **Total a Cobrar: S/ {total_calculado:,.2f}**")

        p1, p2 = st.columns([2, 1])
        prod_aplicados = p1.text_input("Productos / Mezcla Utilizada (Opcional)", placeholder="Ej: Insecticida Sistémico + Foliar Potasio + Adherente")
        monto_abonado = p2.number_input("Monto Abonado / Adelanto (S/)", min_value=0.0, value=total_calculado if estado_pago == "Pagado" else 0.0, step=10.0, format="%.2f")

        obs_srv = st.text_input("Observaciones del Servicio", placeholder="Ej: Vuelo completado en 4 baterías, clima despejado.")

        if st.form_submit_button("✅ Registrar Servicio y Agregar al Estado de Cuenta", type="primary", use_container_width=True):
            total_final = round(ha_aplicadas * precio_ha, 2)
            abonado_final = total_final if estado_pago == "Pagado" else float(monto_abonado)
            cli_rows = df_clientes[df_clientes["nombre"] == cli_vuelo] if not df_clientes.empty else pd.DataFrame()
            cli_id = int(cli_rows.iloc[0]["id"]) if not cli_rows.empty else 1

            ok, msg = insertar_registro_seguro(supabase, "Servicios_Dron", {
                "cliente_id": cli_id,
                "cliente_nombre": cli_vuelo,
                "campo_id": campo_id_def,
                "nombre_campo": nombre_lote_srv.strip(),
                "cultivo": cultivo_srv,
                "fecha_servicio": str(fecha_srv),
                "hectareas_aplicadas": float(ha_aplicadas),
                "precio_por_ha_pen": float(precio_ha),
                "total_cobrar_pen": total_final,
                "tipo_aplicacion": tipo_ap_srv,
                "productos_aplicados": prod_aplicados.strip(),
                "volumen_caldo_l_ha": float(vol_caldo),
                "piloto_operador": "César",
                "dron_equipo": "DJI Agras",
                "estado_pago": estado_pago,
                "monto_pagado_pen": abonado_final,
                "observaciones": obs_srv.strip()
            })
            if ok:
                st.success(f"Servicio registrado: {cli_vuelo} | {cultivo_srv} ({ha_aplicadas:.2f} ha) — Total S/ {total_final:,.2f}")
                st.cache_data.clear()
                st.rerun()

# ==============================================================================
# TAB 3: CUADROS RESÚMENES Y REPORTE DESCARGABLE EN PDF
# ==============================================================================
with tab_reportes_pdf:
    st.subheader("📊 Cuadros Resúmenes y Liquidación por Cliente / Cultivo")
    st.caption("Selecciona el cliente y filtra ya sea por un cultivo específico (ej. solo Palto) o todos sus cultivos para generar su cuadro resumen y descargar el PDF.")

    if df_servicios.empty:
        st.warning("Aún no hay servicios de dron registrados.")
    else:
        f_col1, f_col2, f_col3, f_col4 = st.columns([1.2, 1.2, 1, 1])

        clientes_disp = ["Todos los Clientes"] + sorted(df_servicios["cliente_nombre"].dropna().unique().tolist())
        rep_cliente = f_col1.selectbox("👤 Filtrar Cliente:", options=clientes_disp, index=1 if len(clientes_disp) > 1 else 0)

        df_rep = df_servicios.copy()
        if rep_cliente != "Todos los Clientes":
            df_rep = df_rep[df_rep["cliente_nombre"] == rep_cliente]

        cultivos_disp = sorted(df_rep["cultivo"].dropna().unique().tolist())
        rep_cultivos = f_col2.multiselect(
            "🌱 Cultivos a incluir en el reporte:",
            options=cultivos_disp,
            default=cultivos_disp,
            help="Puedes dejar todos los cultivos del cliente o elegir solo uno (ej. Palto)."
        )
        if rep_cultivos:
            df_rep = df_rep[df_rep["cultivo"].isin(rep_cultivos)]

        rep_estado = f_col3.selectbox("💳 Estado de Pago:", options=["Todos", "Pendiente", "Pagado", "Parcial"])
        if rep_estado != "Todos":
            df_rep = df_rep[df_rep["estado_pago"] == rep_estado]

        orden_fecha = f_col4.selectbox("📅 Orden:", options=["Más recientes primero", "Más antiguos primero"])
        df_rep = df_rep.sort_values(by="fecha_servicio", ascending=(orden_fecha == "Más antiguos primero"))

        # Métricas del Cuadro Resumen
        tot_ha = float(df_rep["hectareas_aplicadas"].sum()) if not df_rep.empty else 0.0
        tot_facturado = float(df_rep["total_cobrar_pen"].sum()) if not df_rep.empty else 0.0
        tot_pagado = float(df_rep["monto_pagado_pen"].sum()) if "monto_pagado_pen" in df_rep.columns and not df_rep.empty else 0.0
        tot_pendiente = max(tot_facturado - tot_pagado, 0.0)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("📐 Total Hectáreas Aplicadas", f"{tot_ha:,.2f} ha")
        k2.metric("💰 Total General", f"S/ {tot_facturado:,.2f}")
        k3.metric("✅ Total Cobrado", f"S/ {tot_pagado:,.2f}")
        k4.metric("⏳ Saldo por Cobrar", f"S/ {tot_pendiente:,.2f}")

        st.markdown("#### 📋 Cuadro Resumen Detallado")
        if not df_rep.empty:
            # Cruzar con URL de Google Maps si existe el campo
            mapa_urls = {}
            if not df_campos.empty:
                for _, rc in df_campos.iterrows():
                    mapa_urls[(rc.get("cliente_nombre"), rc.get("nombre_campo"))] = rc.get("google_maps_url") or construir_url_google_maps(
                        float(rc.get("latitud") or -7.2215), float(rc.get("longitud") or -79.4312)
                    )

            df_vista = pd.DataFrame({
                "ID": df_rep["id"],
                "Fecha": df_rep["fecha_servicio"],
                "Cliente": df_rep["cliente_nombre"],
                "Cultivo": df_rep["cultivo"],
                "Campo / Lote": df_rep["nombre_campo"],
                "Labor / Aplicación": df_rep["tipo_aplicacion"],
                "Hectáreas (ha)": df_rep["hectareas_aplicadas"].map(lambda x: round(float(x), 2)),
                "Precio x Ha (S/)": df_rep["precio_por_ha_pen"].map(lambda x: round(float(x), 2)),
                "Total (S/)": df_rep["total_cobrar_pen"].map(lambda x: round(float(x), 2)),
                "Estado": df_rep["estado_pago"],
                "Ruta GPS": [
                    mapa_urls.get((r["cliente_nombre"], r["nombre_campo"]), "https://www.google.com/maps")
                    for _, r in df_rep.iterrows()
                ]
            })

            st.dataframe(
                df_vista,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Hectáreas (ha)": st.column_config.NumberColumn("Área Aplicada (ha)", format="%.2f ha"),
                    "Precio x Ha (S/)": st.column_config.NumberColumn("Precio / ha", format="S/ %.2f"),
                    "Total (S/)": st.column_config.NumberColumn("Total a Cobrar", format="S/ %.2f"),
                    "Ruta GPS": st.column_config.LinkColumn("Ubicación GPS", display_text="📍 Abrir en Google Maps"),
                }
            )

            # Resumen agrupado por Cultivo
            st.markdown("##### 🌱 Resumen Agrupado por Cultivo")
            df_agrupado = (
                df_rep.groupby(["cliente_nombre", "cultivo"], as_index=False)
                .agg(
                    Servicios=("id", "count"),
                    Hectareas_Totales=("hectareas_aplicadas", "sum"),
                    Precio_Promedio_Ha=("precio_por_ha_pen", "mean"),
                    Total_Soles=("total_cobrar_pen", "sum")
                )
            )
            st.dataframe(
                df_agrupado,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "cliente_nombre": "Cliente",
                    "cultivo": "Cultivo",
                    "Servicios": "N° Aplicaciones",
                    "Hectareas_Totales": st.column_config.NumberColumn("Total Hectáreas", format="%.2f ha"),
                    "Precio_Promedio_Ha": st.column_config.NumberColumn("Precio Prom. / ha", format="S/ %.2f"),
                    "Total_Soles": st.column_config.NumberColumn("Subtotal (S/)", format="S/ %.2f"),
                }
            )

            st.divider()
            col_pdf_btn, col_status_upd = st.columns([1.2, 1])

            cultivo_label = ", ".join(rep_cultivos) if rep_cultivos else "Todos"
            pdf_bytes = generar_pdf_reporte_dron(
                cliente_filtro=rep_cliente,
                cultivo_filtro=cultivo_label,
                df_rep=df_rep
            )
            nombre_archivo_pdf = f"Reporte_Dron_{rep_cliente.replace(' ', '_')}_{date.today()}.pdf"

            with col_pdf_btn:
                st.markdown("#### 📄 Exportar Reporte PDF para el Cliente")
                st.download_button(
                    label=f"📥 Descargar PDF ({rep_cliente} — S/ {tot_facturado:,.2f})",
                    data=pdf_bytes,
                    file_name=nombre_archivo_pdf,
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
                with st.expander("👁️ Ver Vista Previa del Documento PDF", expanded=False):
                    preview_png = renderizar_preview_pdf(pdf_bytes)
                    if preview_png:
                        st.image(preview_png, caption="Vista previa oficial del reporte PDF", use_container_width=True)
                    else:
                        st.info("El PDF está listo para descargarse con el botón superior.")

            with col_status_upd:
                st.markdown("#### ✏️ Editar / Cobrar / Borrar Servicio")
                id_actualizar = st.selectbox(
                    "Seleccionar Servicio (ID):",
                    options=df_rep["id"].tolist(),
                    format_func=lambda x: f"ID #{x} - {df_rep[df_rep['id']==x].iloc[0]['cliente_nombre']} ({df_rep[df_rep['id']==x].iloc[0]['cultivo']} - S/ {float(df_rep[df_rep['id']==x].iloc[0]['total_cobrar_pen']):.2f})"
                )
                fila_s = df_rep[df_rep["id"] == id_actualizar].iloc[0]

                b_quick1, b_quick2 = st.columns(2)
                if b_quick1.button("✅ Marcar PAGADO 100%", use_container_width=True):
                    actualizar_registro_seguro(supabase, "Servicios_Dron", int(id_actualizar), {
                        "estado_pago": "Pagado",
                        "monto_pagado_pen": float(fila_s["total_cobrar_pen"])
                    })
                    st.success(f"Servicio #{id_actualizar} actualizado a Pagado.")
                    st.cache_data.clear()
                    st.rerun()

                if b_quick2.button("🗑️ Borrar Servicio", use_container_width=True):
                    eliminar_registro_seguro(supabase, "Servicios_Dron", int(id_actualizar))
                    st.warning(f"Servicio #{id_actualizar} eliminado.")
                    st.cache_data.clear()
                    st.rerun()

                with st.expander(f"✏️ Editar datos del Servicio #{id_actualizar}", expanded=False):
                    with st.form(f"form_edit_srv_{id_actualizar}"):
                        es1, es2 = st.columns(2)
                        es_ha = es1.number_input("Hectáreas (ha)", min_value=0.1, value=float(fila_s.get("hectareas_aplicadas") or 1.0), step=0.25)
                        es_pr = es2.number_input("Precio / ha (S/)", min_value=1.0, value=float(fila_s.get("precio_por_ha_pen") or 60.0), step=5.0)
                        es3, es4 = st.columns(2)
                        est_act = str(fila_s.get("estado_pago") or "Pendiente")
                        es_est = es3.selectbox("Estado", options=["Pendiente", "Pagado", "Parcial"], index=["Pendiente", "Pagado", "Parcial"].index(est_act) if est_act in ["Pendiente", "Pagado", "Parcial"] else 0)
                        es_pag = es4.number_input("Monto Abonado (S/)", min_value=0.0, value=float(fila_s.get("monto_pagado_pen") or 0.0), step=10.0)
                        es_obs = st.text_input("Observaciones", value=str(fila_s.get("observaciones") or ""))
                        if st.form_submit_button("💾 Guardar Cambios del Servicio", type="primary", use_container_width=True):
                            nuevo_tot = round(float(es_ha) * float(es_pr), 2)
                            actualizar_registro_seguro(supabase, "Servicios_Dron", int(id_actualizar), {
                                "hectareas_aplicadas": float(es_ha),
                                "precio_por_ha_pen": float(es_pr),
                                "total_cobrar_pen": nuevo_tot,
                                "estado_pago": es_est,
                                "monto_pagado_pen": nuevo_tot if es_est == "Pagado" else float(es_pag),
                                "observaciones": es_obs.strip()
                            })
                            st.success(f"Servicio #{id_actualizar} actualizado.")
                            st.cache_data.clear()
                            st.rerun()
