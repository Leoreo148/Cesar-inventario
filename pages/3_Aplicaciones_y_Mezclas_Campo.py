import streamlit as st
import pandas as pd
from datetime import datetime, date
from supabase import create_client

# --- 1. CONFIGURACIÓN E IDENTIDAD VISUAL ---
st.set_page_config(page_title="Gestión de Aplicaciones - Fundo", page_icon="🚁", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    .seccion-titulo { color: #1e3d33; font-weight: 600; margin-top: 15px; border-bottom: 2px solid #2ecc71; padding-bottom: 5px;}
    div[data-testid="stMetric"] { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e0e0e0; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONEXIÓN ---
@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_supabase()

# --- 3. CARGA DE DATOS RELACIONALES (Blindado contra errores de Esquema) ---
@st.cache_data(ttl=60)
def cargar_catalogos():
    # Inicializamos listas vacías por seguridad
    d_pers, d_maq, d_prod, d_ing, d_sal, d_ord = [], [], [], [], [], []
    
    # Probamos cada consulta de forma independiente para aislar el error
    try:
        d_pers = supabase.table('Personal').select("id, nombre_completo").eq('activo', True).execute().data
    except Exception as e:
        st.error(f"❌ Error en Tabla 'Personal': {e}. Revisa si la tabla o la columna 'activo' existen en Supabase.")
        
    try:
        d_maq = supabase.table('Maquinaria').select("id, nombre").execute().data
    except Exception as e:
        st.error(f"❌ Error en Tabla 'Maquinaria': {e}")
        
    try:
        d_prod = supabase.table('Productos').select("Codigo, Producto, Unidad").execute().data
    except Exception as e:
        st.error(f"❌ Error en Tabla 'Productos': {e}")
        
    try:
        d_ing = supabase.table('Ingresos').select("id, Codigo_Producto, Codigo_Lote, Cantidad_Ingresada, Precio_Unitario_PEN").execute().data
    except Exception as e:
        st.error(f"❌ Error en Tabla 'Ingresos': {e}")
        
    try:
        d_sal = supabase.table('Salidas').select("*").execute().data
    except Exception as e:
        st.error(f"❌ Error en Tabla 'Salidas': {e}")
        
    try:
        d_ord = supabase.table('Ordenes_de_Trabajo').select("*").order('created_at', desc=True).execute().data
    except Exception as e:
        st.error(f"❌ Error en Tabla 'Ordenes_de_Trabajo': {e}")

    return pd.DataFrame(d_pers), pd.DataFrame(d_maq), pd.DataFrame(d_prod), pd.DataFrame(d_ing), pd.DataFrame(d_sal), pd.DataFrame(d_ord)

df_pers, df_maq, df_prod, df_ing, df_sal, df_ord = cargar_catalogos()

# Motor FEFO
def obtener_fefo(df_p, df_i, df_s):
    if df_i.empty: return pd.DataFrame()
    gastado = df_s.groupby('Ingreso_ID')['Cantidad_Usada'].sum().reset_index() if not df_s.empty else pd.DataFrame(columns=['Ingreso_ID', 'Cantidad_Usada'])
    df_res = pd.merge(df_i, gastado, left_on='id', right_on='Ingreso_ID', how='left').fillna(0)
    df_res['Stock_Actual'] = df_res['Cantidad_Ingresada'] - df_res['Cantidad_Usada']
    return pd.merge(df_res[df_res['Stock_Actual'] > 0], df_p, left_on='Codigo_Producto', right_on='Codigo')

df_stock = obtener_fefo(df_prod, df_ing, df_sal)

# --- 4. INTERFAZ PRINCIPAL ---
st.title("🚁 Centro de Mezclas y Despacho")
tab1, tab2, tab3 = st.tabs(["📋 Programar Labor (Ingeniero)", "🚚 Almacén y Despacho", "💰 Historial de Costos"])

# ==========================================
# TAB 1: PROGRAMAR LABOR (El modelo de tu amigo)
# ==========================================
with tab1:
    if df_stock.empty:
        st.warning("⚠️ No hay stock disponible en el Kardex para programar mezclas.")
    else:
        # Adaptado a: FERTILIZACIÓN o FUMIGACIÓN
        tipo_labor = st.radio(
            "Seleccione la Categoría de Labor:", 
            ["🌱 FERTILIZACIÓN (Abonamiento)", "🚁 FUMIGACIÓN (Sanidad/Herbicida)"],
            horizontal=True
        )
        st.write("---")

        with st.form("nueva_ot_amigo"):
            st.markdown('<div class="seccion-titulo">1. Ubicación y Momento del Cultivo</div>', unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns(4)
            f_prog = c1.date_input("Fecha Programada", value=date.today())
            
            # Parcelas extraídas de sus apuntes
            PARCELAS = ['La Arenita', 'La Mariposa', 'Faclo', 'Lote Grande', 'Camaronera', 'Cebolla', 'Rio']
            parcela_dest = c2.selectbox("Parcela Destino", options=PARCELAS)
            ha_dest = c3.number_input("Hectáreas a tratar", min_value=0.1, value=1.0)
            
            # Conceptos de cultivo de ciclo corto
            corte_campana = c4.selectbox("Corte / Campaña", ["Corte 1", "Corte 2", "Corte 3", "Corte 4", "Único"])
            
            c1b, c2b, c3b, c4b = st.columns(4)
            fase_cultivo = c1b.selectbox("Fase del Cultivo", ["Almácigo", "Plante", "Desarrollo", "Maduración", "Secado"])
            nro_app = c2b.number_input("N° de Aplicación (Ej: 1, 2, 3...)", min_value=1, step=1, help="Para llevar la cuenta: 1ra Ferti, 2da Ferti...")
            obj_app = c3b.text_input("Objetivo (Ej: Deshierbo, Plaga)")
            
            st.markdown('<div class="seccion-titulo">2. Parámetros de Aplicación</div>', unsafe_allow_html=True)
            
            ca1, ca2, ca3 = st.columns(3)
            # Métodos adaptados
            metodos = ["Drone", "Mochila Manual", "Mochila a Motor", "Cilindro/Manguera", "Al Voleo (Manual)"]
            metodo_sel = ca1.selectbox("Método de Aplicación", metodos)
            vol_agua = ca2.number_input("Volumen de Agua Total (Lts)", value=200)
            obs_dosis = ca3.text_input("Nota de Dosis (Ej: 200/Cil, 1 sobre)", placeholder="Apunte de campo...")

            st.markdown('<div class="seccion-titulo">3. Receta de Insumos</div>', unsafe_allow_html=True)
            opciones_fefo = {f"{r['Producto']} - Lote: {r['Codigo_Lote']} (Sald: {r['Stock_Actual']} {r.get('Unidad','')} - S/{r['Precio_Unitario_PEN']:.2f})": r for _, r in df_stock.iterrows()}
            
            editor_receta = st.data_editor(
                pd.DataFrame([{"Insumo": list(opciones_fefo.keys())[0], "Cantidad_Total": 0.0}]),
                num_rows="dynamic",
                column_config={
                    "Insumo": st.column_config.SelectboxColumn("Lote en Almacén", options=list(opciones_fefo.keys()), required=True),
                    "Cantidad_Total": st.column_config.NumberColumn("Cantidad a retirar", min_value=0.0)
                }
            )

            if st.form_submit_button("📡 Enviar Orden a Almacén", type="primary"):
                if ha_dest <= 0:
                    st.error("⚠️ Las hectáreas deben ser mayores a 0 para calcular costos.")
                else:
                    costo_total_mezcla = 0
                    receta_final = []
                    
                    for _, row in editor_receta.iterrows():
                        info = opciones_fefo[row['Insumo']]
                        precio_unitario = float(info.get('Precio_Unitario_PEN', 0))
                        costo_insumo = row['Cantidad_Total'] * precio_unitario
                        costo_total_mezcla += costo_insumo
                        
                        receta_final.append({
                            "id": int(info['id']), 
                            "p": info['Producto'], 
                            "l": info['Codigo_Lote'], 
                            "c": row['Cantidad_Total'],
                            "precio_u": precio_unitario,
                            "costo_total": costo_insumo
                        })

                    # Empaquetamos toda la lógica nueva en el JSON de Datos Técnicos
                    categoria_limpia = "Fumigacion" if "FUMIGACIÓN" in tipo_labor else "Fertilizacion"
                    datos_extra_json = {
                        "Categoria": categoria_limpia,
                        "Corte": corte_campana,
                        "Fase": fase_cultivo,
                        "Nro_App": nro_app,
                        "Metodo": metodo_sel,
                        "Agua_Lts": vol_agua,
                        "Obs_Dosis": obs_dosis,
                        "Costo_Estimado_Total": costo_total_mezcla,
                        "Costo_Por_Ha": (costo_total_mezcla/ha_dest) if ha_dest>0 else 0
                    }

                    # Usamos Sector_Aplicacion para guardar la "Parcela" y no alterar la BD original de OTs
                    ot_data = {
                        "ID_Orden_Personalizado": f"OT-{datetime.now().strftime('%y%m%d-%H%M')}",
                        "Status": "En Preparación",
                        "Fecha_Programada": str(f_prog),
                        "Sector_Aplicacion": parcela_dest, 
                        "Objetivo": obj_app,
                        "Receta_Mezcla_Lotes": receta_final,
                        "Volumen_Hectarea": ha_dest,
                        "Datos_Tecnicos": datos_extra_json
                    }
                    
                    supabase.table('Ordenes_de_Trabajo').insert(ot_data).execute()
                    st.success(f"✅ Orden enviada a Almacén. Inversión calculada: S/ {costo_total_mezcla:,.2f}")
                    st.cache_data.clear()
                    st.rerun()

# ==========================================
# TAB 2: ALMACÉN Y DESPACHO
# ==========================================
with tab2:
    st.subheader("Órdenes por Despachar a Campo")
    pendientes = df_ord[df_ord['Status'] == 'En Preparación'] if not df_ord.empty else pd.DataFrame()
    
    if pendientes.empty:
        st.info("No hay órdenes pendientes.")
    else:
        for _, ot in pendientes.iterrows():
            dt = ot.get('Datos_Tecnicos', {}) if isinstance(ot.get('Datos_Tecnicos'), dict) else {}
            
            with st.expander(f"📦 {ot['ID_Orden_Personalizado']} | Parcela: {ot['Sector_Aplicacion']} | {dt.get('Categoria','')} N°{dt.get('Nro_App',1)}"):
                col_d1, col_d2 = st.columns([3, 1])
                
                df_receta = pd.DataFrame(ot['Receta_Mezcla_Lotes'])
                col_d1.dataframe(df_receta[['p', 'l', 'c']].rename(columns={'p':'Producto', 'l':'Lote', 'c':'Cantidad'}), hide_index=True)
                
                with col_d2:
                    st.markdown("**Firma de Salida Logística**")
                    resp_alm = st.text_input("Nombre Responsable*", key=f"resp_{ot['id']}", placeholder="Ej: Miguel")
                    
                    if st.button("✅ Confirmar Salida", key=f"btn_{ot['id']}", type="primary"):
                        if resp_alm.strip():
                            batch_salidas = []
                            for insumo in ot['Receta_Mezcla_Lotes']:
                                # Mapeo exacto al nuevo SQL diseñado para tu amigo
                                batch_salidas.append({
                                    "Fecha_Aplicacion": ot['Fecha_Programada'],
                                    "Ingreso_ID": insumo['id'],
                                    "Cantidad_Usada": insumo['c'],
                                    "Parcela_Destino": ot['Sector_Aplicacion'],
                                    "Corte_Campana": dt.get('Corte', ''),
                                    "Fase_Cultivo": dt.get('Fase', ''),
                                    "Categoria_Labor": dt.get('Categoria', ''),
                                    "Nro_Aplicacion": dt.get('Nro_App', 1),
                                    "Metodo_Aplicacion": dt.get('Metodo', ''),
                                    "Volumen_Agua_Lts": dt.get('Agua_Lts', 0.0),
                                    "Responsable": resp_alm,
                                    "Observacion_Dosis": dt.get('Obs_Dosis', '')
                                })
                            
                            supabase.table('Salidas').insert(batch_salidas).execute()
                            supabase.table('Ordenes_de_Trabajo').update({"Status": "Finalizada"}).eq('id', ot['id']).execute()
                            
                            st.success("Despacho exitoso. Kardex actualizado.")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("⚠️ La firma es obligatoria.")

# ==========================================
# TAB 3: HISTORIAL Y AUDITORÍA
# ==========================================
with tab3:
    st.subheader("Auditoría Financiera de Aplicaciones en Campo")
    finalizadas = df_ord[df_ord['Status'] == 'Finalizada'] if not df_ord.empty else pd.DataFrame()
    
    if finalizadas.empty:
        st.info("Aún no hay órdenes finalizadas.")
    else:
        costos_totales = []
        hectareas_totales = 0
        
        for _, ot in finalizadas.iterrows():
            dt = ot.get('Datos_Tecnicos', {}) if isinstance(ot.get('Datos_Tecnicos'), dict) else {}
            costos_totales.append(dt.get('Costo_Estimado_Total', 0))
            hectareas_totales += float(ot.get('Volumen_Hectarea', 0))
            
        inversion_global = sum(costos_totales)
        promedio_global_ha = inversion_global / hectareas_totales if hectareas_totales > 0 else 0

        k1, k2, k3 = st.columns(3)
        k1.metric("💰 Inversión Total Insumos", f"S/ {inversion_global:,.2f}")
        k2.metric("📉 Costo Promedio / Ha", f"S/ {promedio_global_ha:,.2f}")
        k3.metric("🚜 Hectáreas Totales", f"{hectareas_totales:,.1f} Ha")

        st.divider()
        st.write("### Desglose por Orden de Trabajo")
        
        for _, ot in finalizadas.iterrows():
            dt = ot.get('Datos_Tecnicos', {}) if isinstance(ot.get('Datos_Tecnicos'), dict) else {}
            c_ot = dt.get('Costo_Estimado_Total', 0)
            c_ha = dt.get('Costo_Por_Ha', 0)
            
            with st.expander(f"✅ OT: {ot.get('ID_Orden_Personalizado')} | Parcela: {ot.get('Sector_Aplicacion')} | {dt.get('Categoria','')} N°{dt.get('Nro_App',1)}"):
                st.markdown(f"**🎯 Fase / Objetivo:** {dt.get('Fase','')} - {ot.get('Objetivo', 'N/A')}")
                st.markdown(f"**Corte:** {dt.get('Corte','')} | **Inversión:** S/ {c_ot:,.2f} (S/ {c_ha:,.2f} por Ha)")
                st.markdown(f"**Método:** {dt.get('Metodo','')} | **Dosis Campo:** {dt.get('Obs_Dosis','N/A')}")
                
                if ot.get('Receta_Mezcla_Lotes'):
                    df_receta = pd.DataFrame(ot['Receta_Mezcla_Lotes'])
                    st.dataframe(df_receta[['p', 'l', 'c']].rename(columns={'p':'Producto', 'l':'Lote', 'c':'Cantidad'}), hide_index=True, use_container_width=True)

    # --- VISTA DE HORMIGA ADAPTADA ---
    st.divider()
    st.subheader("🔍 Trazabilidad Detallada de Salidas (Kardex Físico)")
    
    if not df_sal.empty and 'Fecha_Aplicacion' in df_sal.columns:
        df_sal_det = pd.merge(df_sal, df_ing[['id', 'Codigo_Lote', 'Codigo_Producto']], left_on='Ingreso_ID', right_on='id', how='left')
        df_sal_det = pd.merge(df_sal_det, df_prod[['Codigo', 'Producto', 'Unidad']], left_on='Codigo_Producto', right_on='Codigo', how='left')
        
        # Nuevas columnas de la tabla SQL adaptada
        cols_mostrar = ['Fecha_Aplicacion', 'Producto', 'Cantidad_Usada', 'Unidad', 'Parcela_Destino', 'Corte_Campana', 'Categoria_Labor', 'Nro_Aplicacion', 'Metodo_Aplicacion', 'Observacion_Dosis', 'Responsable']
        cols_existentes = [c for c in cols_mostrar if c in df_sal_det.columns]
        
        df_mostrar_salidas = df_sal_det[cols_existentes].sort_values(by='Fecha_Aplicacion', ascending=False)
        st.dataframe(df_mostrar_salidas, use_container_width=True, hide_index=True)
    else:
        st.info("No hay registros detallados de salidas en la base de datos.")