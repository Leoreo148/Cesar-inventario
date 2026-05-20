import streamlit as st
import pandas as pd
from datetime import datetime, date
import numpy as np
from supabase import create_client
import io
from st_aggrid import AgGrid, GridOptionsBuilder, ColumnsAutoSizeMode, GridUpdateMode, JsCode
from streamlit_extras.metric_cards import style_metric_cards
from streamlit_extras.stylable_container import stylable_container

# 🚨 CANDADO VIP: EXCLUSIVO PARA ALMACÉN
if "autenticado" not in st.session_state or not st.session_state["autenticado"]:
    st.warning("⚠️ Por favor, inicie sesión en la página principal.")
    st.stop()

# Aquí bloqueamos a José de Sanidad o a Edgar de Costos
if st.session_state["rol"] not in ["Admin", "Logistica","Programador"]:
    st.error("🚫 Acceso denegado. Este módulo es exclusivo para el área de Almacén y Mezclas (Miguel).")
    st.stop()

# --- 1. CONFIGURACIÓN E IDENTIDAD VISUAL ---
st.set_page_config(page_title="Kardex & Inventario Maestro", page_icon="📦", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

if 'editing_product_id' not in st.session_state:
    st.session_state.editing_product_id = None

# --- 2. CONEXIÓN ---
@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_supabase()

st.info("💡 **Guía de Unidades:** Usa **001** para productos líquidos (Lt) y **002** para sólidos/polvos (Kg).")

# --- 3. CARGA DE DATOS AUDITADA ---
@st.cache_data(ttl=60)
def cargar_todo():
    if not supabase: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    p = supabase.table('Productos').select("*").order('Producto').execute()
    # 💡 AÑADIDO: Traemos campos logísticos extra para auditoría
    i = supabase.table('Ingresos').select("id, Codigo_Producto, Codigo_Lote, Cantidad_Ingresada, Precio_Unitario_PEN, Fecha_Vencimiento, Proveedor, Factura, Observaciones, Estado_Registro, Guia_Remision, Responsable").execute()
    s = supabase.table('Salidas').select("Ingreso_ID, Cantidad_Usada").execute()
    
    return pd.DataFrame(p.data), pd.DataFrame(i.data), pd.DataFrame(s.data)

def generar_kardex(df_p, df_i, df_s):
    # 🛡️ FIX BÚNKER: Variables inicializadas
    df_balance = pd.DataFrame()
    
    if df_p.empty: return pd.DataFrame()
    
    # Limpieza básica y protección de columnas nuevas (Soft Delete)
    df_p['Stock_Minimo'] = df_p.get('Stock_Minimo', 0.0).fillna(0.0)
    if 'Activo' not in df_p.columns: df_p['Activo'] = True
    df_p['Activo'] = df_p['Activo'].fillna(True).astype(bool)
    
    if df_i.empty:
        df_final = df_p.copy()
        for col in ['Stock_Lote', 'Valorizado_PEN']: df_final[col] = 0.0
        df_final['Dias_para_Vencer'] = 999
        df_final['Estado_Registro'] = 'Sin Ingresos'
        return df_final

    # Protección si el Estado_Registro es nulo en datos viejos
    if 'Estado_Registro' not in df_i.columns: df_i['Estado_Registro'] = 'Completo 🟢'
    df_i['Estado_Registro'] = df_i['Estado_Registro'].fillna('Completo 🟢')

    # Cálculo de saldos
    if not df_s.empty:
        gastado = df_s.groupby('Ingreso_ID')['Cantidad_Usada'].sum().reset_index()
        df_balance = pd.merge(df_i, gastado, left_on='id', right_on='Ingreso_ID', how='left').fillna({'Cantidad_Usada': 0})
        df_balance['Stock_Lote'] = df_balance['Cantidad_Ingresada'] - df_balance['Cantidad_Usada']
    else:
        df_balance = df_i.copy()
        df_balance['Stock_Lote'] = df_balance['Cantidad_Ingresada']

    # Merge con catálogo
    df_final = pd.merge(df_balance, df_p, left_on='Codigo_Producto', right_on='Codigo', how='right')
    
    # 🛡️ FIX MATEMÁTICO: Forzar a número antes de multiplicar
    df_final['Stock_Lote'] = df_final['Stock_Lote'].fillna(0.0)
    df_final['Precio_Unitario_PEN'] = pd.to_numeric(df_final.get('Precio_Unitario_PEN', 0), errors='coerce').fillna(0.0)
    df_final['Valorizado_PEN'] = df_final['Stock_Lote'] * df_final['Precio_Unitario_PEN']
    
    # --- PROCESAMIENTO DE FECHAS SEGURO ---
    hoy = pd.Timestamp(date.today())
    df_final['Venc_Date'] = pd.to_datetime(df_final.get('Fecha_Vencimiento'), errors='coerce')
    df_final['Dias_para_Vencer'] = (df_final['Venc_Date'] - hoy).dt.days
    df_final.loc[df_final['Venc_Date'].isnull() | (df_final['Venc_Date'].dt.year < 2000), 'Dias_para_Vencer'] = 999
    
    return df_final

# --- 4. PROCESAMIENTO Y ANÁLISIS ABC ---
df_p, df_i, df_s = cargar_todo()
df_kardex_crudo = generar_kardex(df_p, df_i, df_s)
df_kardex = df_kardex_crudo.copy()

if not df_kardex.empty and df_kardex.get('Valorizado_PEN', pd.Series([0])).sum() > 0:
    df_kardex = df_kardex.sort_values(by='Valorizado_PEN', ascending=False).reset_index(drop=True)
    total_valor = df_kardex['Valorizado_PEN'].sum()
    df_kardex['Porcentaje_Acumulado'] = df_kardex['Valorizado_PEN'].cumsum() / total_valor
    
    condiciones = [
        (df_kardex['Porcentaje_Acumulado'] <= 0.80), 
        (df_kardex['Porcentaje_Acumulado'] > 0.80) & (df_kardex['Porcentaje_Acumulado'] <= 0.95), 
        (df_kardex['Porcentaje_Acumulado'] > 0.95)
    ]
    valores = ['A (Crítico)', 'B (Intermedio)', 'C (Rutina)']
    df_kardex['Clase_ABC'] = np.select(condiciones, valores, default='C (Rutina)')
    df_kardex.loc[df_kardex['Valorizado_PEN'] == 0, 'Clase_ABC'] = 'Sin Stock'
else:
    df_kardex['Clase_ABC'] = 'Sin Stock'

# --- 5. PANEL DE CONTROL ---
with stylable_container(key="green_panel", css_styles="{ background-color: #1e3d33; color: white; padding: 1.5rem; border-radius: 1rem; }"):
    st.subheader("📦 Gestión Maestra de Inventario")
    
    # Fila 1: Filtros principales
    c0, c1, c2, c3 = st.columns([1.5, 2, 2, 2])
    with c0:
        st.write("")
        ocultar_archivados = st.checkbox("Ocultar Archivados", value=True)
    with c1:
        busqueda = st.text_input("🔍 Buscador:", placeholder="Lote, Producto...")
    with c2:
        tipos_limpios = sorted([str(t) for t in df_kardex.get('Tipo_Accion', []).unique() if t and str(t) not in ['0', 'nan', 'None']])
        filtro_tipo = st.selectbox("Categoría:", ["Todos"] + tipos_limpios)
    with c3:
        filtro_abc = st.selectbox("Clase ABC:", ["Todos", "A (Crítico)", "B (Intermedio)", "C (Rutina)"])

    # Fila 2: Filtros Avanzados y KPIs
    with st.expander("🛠️ Filtros Avanzados y Auditoría Logística"):
        ca1, ca2, ca3, ca4 = st.columns(4)
        
        # Obtenemos listas limpias para los selectores si existen en el DF
        provs = ["Todos"] + sorted(df_kardex['Proveedor'].dropna().unique().tolist()) if 'Proveedor' in df_kardex.columns else ["Todos"]
        resps = ["Todos"] + sorted(df_kardex['Responsable'].dropna().unique().tolist()) if 'Responsable' in df_kardex.columns else ["Todos"]
        
        f_prov = ca1.selectbox("Proveedor", provs)
        f_resp = ca2.selectbox("Responsable Recepción", resps)
        f_fact = ca3.text_input("N° Factura", placeholder="Buscar factura...")
        f_guia = ca4.text_input("Guía Remisión", placeholder="Buscar guía...")
        
        st.markdown("**Filtros por KPIs (Alertas):**")
        kpi1, kpi2 = st.columns(2)
        filtro_kpi_stock = kpi1.checkbox("🚨 Mostrar SOLO Stock Crítico (< Mínimo)")
        filtro_kpi_venc = kpi2.checkbox("⏳ Mostrar SOLO Próximos a Vencer (< 15 días)")
        
    # Columnas Extra (Ahora incluye las de agronomía)
    cols_detalle = [
        'Estado_Registro', 'Proveedor', 'Factura', 'Guia_Remision', 'Responsable', 
        'Precio_Unitario_PEN', 'Observaciones', 
        'Ingrediente_Activo', 'Marca', 'Formulacion', 'Banda_Toxicologica', 'Ficha_Tecnica_URL'
    ]
    mostrar_extras = st.multiselect("⚙️ Mostrar columnas extra en la tabla:", options=cols_detalle, default=['Estado_Registro', 'Ingrediente_Activo'])

# Aplicar Filtros
if not df_kardex.empty:
    # 1. Filtros Básicos
    if ocultar_archivados and 'Activo' in df_kardex.columns:
        df_kardex = df_kardex[df_kardex['Activo'] == True]
    if busqueda:
        mask = df_kardex.apply(lambda row: row.astype(str).str.contains(busqueda, case=False).any(), axis=1)
        df_kardex = df_kardex[mask]
    if filtro_tipo != "Todos":
        df_kardex = df_kardex[df_kardex['Tipo_Accion'] == filtro_tipo]
    if filtro_abc != "Todos" and 'Clase_ABC' in df_kardex.columns:
        df_kardex = df_kardex[df_kardex['Clase_ABC'] == filtro_abc]

    # 2. Filtros Avanzados (Logística)
    if f_prov != "Todos" and 'Proveedor' in df_kardex.columns:
        df_kardex = df_kardex[df_kardex['Proveedor'] == f_prov]
    if f_resp != "Todos" and 'Responsable' in df_kardex.columns:
        df_kardex = df_kardex[df_kardex['Responsable'] == f_resp]
    if f_fact and 'Factura' in df_kardex.columns:
        df_kardex = df_kardex[df_kardex['Factura'].astype(str).str.contains(f_fact, case=False, na=False)]
    if f_guia and 'Guia_Remision' in df_kardex.columns:
        df_kardex = df_kardex[df_kardex['Guia_Remision'].astype(str).str.contains(f_guia, case=False, na=False)]

    # 3. Filtros KPIs
    if filtro_kpi_stock and 'Stock_Lote' in df_kardex.columns and 'Stock_Minimo' in df_kardex.columns:
        df_kardex = df_kardex[df_kardex['Stock_Lote'] < df_kardex['Stock_Minimo']]
    if filtro_kpi_venc and 'Dias_para_Vencer' in df_kardex.columns:
        df_kardex = df_kardex[df_kardex['Dias_para_Vencer'] < 15]

# --- 6. MÉTRICAS A PRUEBA DE BALAS ---
st.write("")

# 💡 NUEVO: Control de Tipo de Cambio en la misma fila de métricas
c_tc, m1, m2, m3, m4 = st.columns([1.5, 2, 1.5, 1.5, 1.5])
tc_usd = c_tc.number_input("💵 Tipo de Cambio (S/)", min_value=3.00, max_value=4.50, value=3.75, step=0.01)

style_metric_cards(background_color="#ffffff", border_left_color="#1e3d33")

val_total_pen = df_kardex['Valorizado_PEN'].sum() if 'Valorizado_PEN' in df_kardex.columns else 0.0
val_total_usd = val_total_pen / tc_usd if tc_usd > 0 else 0.0

m1.metric("Valorización (PEN / USD)", f"S/ {val_total_pen:,.2f}", f"${val_total_usd:,.2f}", delta_color="off")

# --- 7. AG-GRID ---
if not df_kardex.empty:
    cols_base = ['Codigo', 'Producto', 'Clase_ABC', 'Codigo_Lote', 'Stock_Lote', 'Unidad'] + mostrar_extras + ['Dias_para_Vencer']
    cols_visibles = [c for c in cols_base if c in df_kardex.columns]

    gb = GridOptionsBuilder.from_dataframe(df_kardex[cols_visibles])
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=15)
    gb.configure_selection('multiple', use_checkbox=True, header_checkbox=True)
    
    for col in cols_visibles: gb.configure_column(col, minWidth=120)

    cellsytle_jcode = JsCode("""
    function(params) {
        if (params.data.Stock_Lote <= 0) { return { 'color': 'white', 'backgroundColor': '#e74c3c' }; }
        if (params.data.Dias_para_Vencer < 15) { return { 'color': 'black', 'backgroundColor': '#f1c40f' }; }
        return null;
    }
    """)
    gb.configure_column("Stock_Lote", cellStyle=cellsytle_jcode)
    
    grid_response = AgGrid(df_kardex, gridOptions=gb.build(), update_mode=GridUpdateMode.SELECTION_CHANGED, allow_unsafe_jscode=True, theme='balham', height=500)

    # Exportación
    st.write("")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df_kardex[cols_visibles].to_excel(writer, index=False)
    st.download_button("📥 Descargar Reporte (Excel)", data=buffer.getvalue(), file_name=f"Kardex_{date.today()}.xlsx", mime="application/vnd.ms-excel")

    # --- 8. ACCIONES Y DETALLES ---
    selected = grid_response['selected_rows']
    
    # Verificamos que haya al menos un elemento seleccionado
    if selected is not None and len(selected) > 0:
        # Streamlit a veces devuelve un DataFrame y a veces una lista de diccionarios
        if isinstance(selected, pd.DataFrame):
            selected_records = selected.to_dict('records')
        else:
            selected_records = selected
            
        st.divider()
        c_acc1, c_acc2, c_acc3 = st.columns([2,2,4])
        
        # 1. BOTÓN DE EDITAR (Solo funciona si hay exactamente 1 seleccionado)
        if len(selected_records) == 1:
            if c_acc1.button("✏️ Editar Producto Master"):
                match = df_p[df_p['Codigo'] == selected_records[0]['Codigo']]
                if not match.empty:
                    st.session_state.editing_product_id = int(match.iloc[0]['id'])
                    st.rerun()
        else:
            c_acc1.write(f"Has seleccionado **{len(selected_records)}** productos.")
            
        # 2. BOTÓN DE ARCHIVAR MASIVO
        if c_acc2.button(f"📦 Archivar ({len(selected_records)}) Productos", type="secondary"):
            for row in selected_records:
                match = df_p[df_p['Codigo'] == row['Codigo']]
                if not match.empty:
                    real_id = int(match.iloc[0]['id'])
                    # Archivamos uno por uno en la base de datos
                    supabase.table('Productos').update({"Activo": False}).eq('id', real_id).execute()
            
            st.success(f"Se han archivado {len(selected_records)} productos correctamente.")
            st.cache_data.clear()
            st.rerun()
        
        # 3. PANEL DE OBSERVACIONES Y SEGURIDAD
        with c_acc3:
            with stylable_container("obs", css_styles="{ background-color: #e8f4fd; padding: 10px; border-radius: 8px; border: 1px solid #b3d7ff;}"):
                if len(selected_records) == 1:
                    row_data = selected_records[0]
                    # Filtro Anti-None
                    obs_raw = str(row_data.get('Observaciones', ''))
                    obs_clean = "Sin notas." if obs_raw.strip() == '' or obs_raw in ['None', 'nan'] else obs_raw
                    
                    st.write(f"**💡 Observaciones del Lote:** {obs_clean}")
                    
                    # --- NUEVO: Indicadores de Seguridad y Ficha Técnica ---
                    c_seg1, c_seg2 = st.columns(2)
                    banda = str(row_data.get('Banda_Toxicologica', 'N/A'))
                    ficha_url = str(row_data.get('Ficha_Tecnica_URL', ''))
                    
                    if banda and banda not in ['nan', 'None', 'N/A']:
                        c_seg1.markdown(f"**☣️ Toxicidad:** {banda}")
                        
                    if ficha_url.startswith('http'):
                        c_seg2.markdown(f"[📄 Abrir Ficha Técnica]({ficha_url})", help="Haz clic para ver la hoja de seguridad del fabricante.")
                else:
                    st.write("**💡 Detalles:** Selecciona solo 1 producto para ver sus notas específicas y ficha técnica.")

# --- 9. DIÁLOGOS DE GESTIÓN ---
if st.session_state.editing_product_id:
    # 🛡️ Blindaje extra: asegurarnos de que el DataFrame no esté vacío al buscar
    match_prod = df_p[df_p['id'] == st.session_state.editing_product_id]
    
    if not match_prod.empty:
        prod_to_edit = match_prod.iloc[0]
        
        @st.dialog("✏️ Editar Maestro")
        def show_edit_dialog(p):
            with st.form("form_ed"):
                st.write(f"Editando: **{p['Producto']}**")
                
                # Fila 1
                col_a, col_b = st.columns(2)
                n_nombre = col_a.text_input("Nombre Comercial", value=str(p.get('Producto', '')))
                n_marca = col_b.text_input("Marca / Laboratorio", value=str(p.get('Marca', '')) if pd.notna(p.get('Marca')) else '')
                
                # Fila 2
                n_ing = st.text_input("Ingrediente Activo", value=str(p.get('Ingrediente_Activo', '')) if pd.notna(p.get('Ingrediente_Activo')) else '')
                
                # Fila 3
                c1, c2, c3 = st.columns(3)
                n_min = c1.number_input("Stock Mínimo", value=float(p.get('Stock_Minimo', 0)))
                n_car = c2.number_input("Carencia (Días)", value=int(p.get('Periodo_Carencia_Dias', 0)))
                
                CATEGORIAS = ["Insecticida", "Acaricida", "Fungicida", "Herbicida", "Coadyuvante", "Regulador de pH", "Nematicida", "Foliar", "Fertilizante", "Otro", "N/A"]
                tipo_actual = str(p.get('Tipo_Accion', 'N/A'))
                idx_tipo = CATEGORIAS.index(tipo_actual) if tipo_actual in CATEGORIAS else 10
                n_tipo = c3.selectbox("Categoría", CATEGORIAS, index=idx_tipo)
                
                # Fila 4
                c4, c5 = st.columns(2)
                FORMULACIONES = ["Concentrado Soluble (SL)", "Concentrado Emulsionable (EC)", "Suspensión Concentrada (SC)", "Polvo Mojable (WP)", "Gránulos Dispersables (WG)", "Otro"]
                form_actual = str(p.get('Formulacion', 'Otro'))
                idx_form = FORMULACIONES.index(form_actual) if form_actual in FORMULACIONES else 5
                n_form = c4.selectbox("Formulación", FORMULACIONES, index=idx_form)
                
                BANDAS = ["Verde (Ligeramente Tóxico)", "Azul (Moderadamente Tóxico)", "Amarillo (Altamente Tóxico)", "Rojo (Extremadamente Tóxico)", "No Aplica"]
                banda_actual = str(p.get('Banda_Toxicologica', 'No Aplica'))
                idx_banda = BANDAS.index(banda_actual) if banda_actual in BANDAS else 4
                n_banda = c5.selectbox("Banda Toxicológica", BANDAS, index=idx_banda)
                
                # Fila 5
                n_ficha = st.text_input("URL Ficha Técnica", value=str(p.get('Ficha_Tecnica_URL', '')) if pd.notna(p.get('Ficha_Tecnica_URL')) else '')
                n_inc = st.text_area("Incompatibilidades", value=str(p.get('Incompatible_Con', '')) if pd.notna(p.get('Incompatible_Con')) else '')
                
                submit = st.form_submit_button("Guardar Cambios")
                
                if submit:
                    # Aplicamos el filtro .capitalize() también al editar
                    ing_limpios = ", ".join([i.strip().capitalize() for i in n_ing.split(",") if i.strip()]) if n_ing else None
                    
                    data_upd = {
                        "Producto": n_nombre.strip().upper(),
                        "Marca": n_marca.strip().upper() if n_marca else None,
                        "Ingrediente_Activo": ing_limpios,
                        "Stock_Minimo": n_min, 
                        "Periodo_Carencia_Dias": n_car, 
                        "Tipo_Accion": n_tipo,
                        "Formulacion": n_form,
                        "Banda_Toxicologica": n_banda,
                        "Ficha_Tecnica_URL": n_ficha.strip() if n_ficha else None,
                        "Incompatible_Con": n_inc.strip() if n_inc else None
                    }
                    supabase.table('Productos').update(data_upd).eq('id', p['id']).execute()
                    st.session_state.editing_product_id = None
                    st.cache_data.clear()
                    st.rerun()
            
            # Botón de cancelar fuera del form
            if st.button("❌ Cancelar Edición"):
                st.session_state.editing_product_id = None
                st.rerun()
                
        show_edit_dialog(prod_to_edit)