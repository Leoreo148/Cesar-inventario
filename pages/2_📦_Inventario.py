import streamlit as st
import pandas as pd
from datetime import datetime, date
import numpy as np
from supabase import create_client
import io

# --- LIBRERÍAS PRO ---
from st_aggrid import AgGrid, GridOptionsBuilder, ColumnsAutoSizeMode, GridUpdateMode, JsCode
from streamlit_extras.metric_cards import style_metric_cards
from streamlit_extras.stylable_container import stylable_container

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
if 'deleting_product_id' not in st.session_state:
    st.session_state.deleting_product_id = None

# --- 2. CONEXIÓN ---
@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_supabase()

# Un aviso pequeño y profesional
st.info("💡 **Guía de Unidades:** Usa **001** para productos líquidos (Lt) y **002** para sólidos/polvos (Kg).")

# --- 3. CARGA DE DATOS AUDITADA ---
@st.cache_data(ttl=60)
def cargar_todo():
    if not supabase: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    p = supabase.table('Productos').select("*").order('Producto').execute()
    # AUDITORÍA: Columnas exactas del Excel
    i = supabase.table('Ingresos').select("id, Codigo_Producto, Codigo_Lote, Cantidad_Ingresada, Precio_Unitario_PEN, Precio_Unitario_USD, Fecha_Vencimiento, Proveedor, Factura, Guia_Remision, Observaciones, Fecha_Recepcion, Deposito").execute()
    s = supabase.table('Salidas').select("Ingreso_ID, Cantidad_Usada").execute()
    
    return pd.DataFrame(p.data), pd.DataFrame(i.data), pd.DataFrame(s.data)

def generar_kardex(df_p, df_i, df_s):
    if df_p.empty: return pd.DataFrame()
    
    # Limpieza básica
    df_p['Stock_Minimo'] = df_p.get('Stock_Minimo', 0.0).fillna(0.0)
    
    if df_i.empty:
        df_final = df_p.copy()
        df_final[['Stock_Lote', 'Valorizado_PEN']] = 0.0
        df_final['Dias_para_Vencer'] = 999
        return df_final

    # Cálculo de saldos
    if not df_s.empty:
        gastado = df_s.groupby('Ingreso_ID')['Cantidad_Usada'].sum().reset_index()
        df_balance = pd.merge(df_i, gastado, left_on='id', right_on='Ingreso_ID', how='left').fillna({'Cantidad_Usada': 0})
        df_balance['Stock_Lote'] = df_balance['Cantidad_Ingresada'] - df_balance['Cantidad_Usada']
    else:
        df_balance = df_i.copy()
        df_balance['Stock_Lote'] = df_balance['Cantidad_Ingresada']

    # Merge con catálogo
    df_final = pd.merge(df_balance, df_p, left_on='Codigo_Producto', right_on='Codigo', how='right').fillna(0)
    df_final['Valorizado_PEN'] = df_final['Stock_Lote'] * df_final['Precio_Unitario_PEN']
    
    # --- PROCESAMIENTO DE FECHAS SEGURO ---
    hoy = pd.Timestamp(date.today())
    
    # 1. Convertimos a fecha, los errores se vuelven NaT (Not a Time)
    df_final['Venc_Date'] = pd.to_datetime(df_final['Fecha_Vencimiento'], errors='coerce')
    
    # 2. Calculamos los días
    df_final['Dias_para_Vencer'] = (df_final['Venc_Date'] - hoy).dt.days
    
    # 3. FILTRO ANTI-BUG: 
    # Si la fecha es nula (NaT) O si es una fecha "fantasma" muy antigua (anterior al año 2000)
    # le asignamos 999 para que no arruine las métricas.
    df_final.loc[df_final['Venc_Date'].isnull(), 'Dias_para_Vencer'] = 999
    df_final.loc[df_final['Venc_Date'].dt.year < 2000, 'Dias_para_Vencer'] = 999
    
    return df_final

# --- 4. PROCESAMIENTO Y ANÁLISIS ABC ---
df_p, df_i, df_s = cargar_todo()
df_kardex_crudo = generar_kardex(df_p, df_i, df_s)
df_kardex = df_kardex_crudo.copy()

# Lógica del Modelo ABC Financiero
if not df_kardex.empty and df_kardex['Valorizado_PEN'].sum() > 0:
    # 1. Filtramos para evaluar solo lo que tiene stock y lo ordenamos por valor
    df_kardex = df_kardex.sort_values(by='Valorizado_PEN', ascending=False).reset_index(drop=True)
    
    # 2. Calculamos el valor total del almacén y el peso acumulado de cada producto
    total_valor = df_kardex['Valorizado_PEN'].sum()
    df_kardex['Porcentaje_Acumulado'] = df_kardex['Valorizado_PEN'].cumsum() / total_valor
    
    # 3. Asignamos las categorías basándonos en el Principio de Pareto
    condiciones = [
        (df_kardex['Porcentaje_Acumulado'] <= 0.80), # 80% del valor del almacén
        (df_kardex['Porcentaje_Acumulado'] > 0.80) & (df_kardex['Porcentaje_Acumulado'] <= 0.95), # Siguiente 15%
        (df_kardex['Porcentaje_Acumulado'] > 0.95) # Último 5%
    ]
    valores = ['A (Crítico)', 'B (Intermedio)', 'C (Rutina)']
    df_kardex['Clase_ABC'] = np.select(condiciones, valores, default='C (Rutina)')
    
    # Limpiamos los que tienen stock cero para que no ensucien el análisis
    df_kardex.loc[df_kardex['Valorizado_PEN'] == 0, 'Clase_ABC'] = 'Sin Stock'
else:
    df_kardex['Clase_ABC'] = 'Sin Stock'

# --- 5. PANEL DE CONTROL ---
with stylable_container(key="green_panel", css_styles="{ background-color: #1e3d33; color: white; padding: 1.5rem; border-radius: 1rem; }"):
    st.subheader("📦 Gestión Maestra de Inventario")
    
    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        busqueda = st.text_input("🔍 Buscador:", placeholder="Lote, Factura, Producto...")
    with c2:
        # 🛡️ Shield: Verificamos si la columna existe antes de pedir los valores únicos
        if 'Tipo_Accion' in df_kardex.columns:
            tipos_raw = df_kardex['Tipo_Accion'].unique()
            tipos_limpios = sorted([str(t) for t in tipos_raw if t and str(t) not in ['0', 'nan', 'None']])
        else:
            tipos_limpios = []
            
        filtro_tipo = st.selectbox("Categoría:", ["Todos"] + tipos_limpios)
    with c3:
        cols_detalle = ['Proveedor', 'Factura', 'Guia_Remision', 'Deposito', 'Precio_Unitario_PEN', 'Precio_Unitario_USD', 'Ingrediente_Activo', 'Observaciones']
        mostrar_extras = st.multiselect("⚙️ Columnas adicionales:", options=cols_detalle, default=[])

# Filtros
if busqueda:
    mask = df_kardex.apply(lambda row: row.astype(str).str.contains(busqueda, case=False).any(), axis=1)
    df_kardex = df_kardex[mask]
if filtro_tipo != "Todos":
    df_kardex = df_kardex[df_kardex['Tipo_Accion'] == filtro_tipo]

# --- 6. MÉTRICAS ---
st.write("")
m1, m2, m3, m4 = st.columns(4)
style_metric_cards(background_color="#ffffff", border_left_color="#1e3d33")
m1.metric("Valorización (S/)", f"S/ {df_kardex['Valorizado_PEN'].sum():,.2f}")
m2.metric("Alertas Stock", len(df_kardex[df_kardex['Stock_Lote'] < df_kardex['Stock_Minimo']]))
m3.metric("Vencimientos <15d", len(df_kardex[df_kardex['Dias_para_Vencer'] < 15]))
m4.metric("Lotes en Vista", len(df_kardex))

# --- 7. AG-GRID ---
# Creamos una lista de columnas que REALMENTE existen en el DataFrame para evitar el KeyError
cols_base = ['Codigo', 'Producto', 'Clase_ABC', 'Codigo_Lote', 'Stock_Lote', 'Unidad', 'Dias_para_Vencer']
cols_visibles = [c for c in cols_base if c in df_kardex.columns] + mostrar_extras

if not df_kardex.empty:
    gb = GridOptionsBuilder.from_dataframe(df_kardex[cols_visibles])
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=15)
    gb.configure_selection('single', use_checkbox=True)
    
    for col in cols_visibles:
        gb.configure_column(col, minWidth=120, flex=1 if col in ['Producto', 'Proveedor'] else 0)

    cellsytle_jcode = JsCode("""
    function(params) {
        if (params.data.Stock_Lote <= 0) { return { 'color': 'white', 'backgroundColor': '#e74c3c' }; }
        if (params.data.Dias_para_Vencer < 15) { return { 'color': 'black', 'backgroundColor': '#f1c40f' }; }
        return null;
    }
    """)
    gb.configure_column("Stock_Lote", cellStyle=cellsytle_jcode)
    
    grid_response = AgGrid(
        df_kardex,
        gridOptions=gb.build(),
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        allow_unsafe_jscode=True, 
        theme='balham', 
        height=500
    )

    # Exportación
    st.write("")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df_kardex[cols_visibles].to_excel(writer, index=False)
    st.download_button("📥 Descargar Reporte (Excel)", data=buffer.getvalue(), file_name=f"Kardex_{date.today()}.xlsx", mime="application/vnd.ms-excel")

    # --- 8. ACCIONES Y DETALLES ---
    selected = grid_response['selected_rows']
    if selected is not None and not (isinstance(selected, pd.DataFrame) and selected.empty):
        sel_row = selected.iloc[0] if isinstance(selected, pd.DataFrame) else selected[0]
        
        st.divider()
        c_acc1, c_acc2, c_acc3 = st.columns([2,2,4])
        
        if c_acc1.button("✏️ Editar Producto Master"):
            match = df_p[df_p['Codigo'] == sel_row['Codigo']]
            if not match.empty:
                st.session_state.editing_product_id = int(match.iloc[0]['id'])
                st.rerun()
        
        with c_acc3:
            with stylable_container("obs", css_styles="{ background-color: #e8f4fd; padding: 10px; border-radius: 8px; border: 1px solid #b3d7ff;}"):
                st.write(f"**💡 Observaciones:** {sel_row.get('Observaciones','Sin notas.')}")

# --- 9. DIÁLOGOS DE GESTIÓN ---
if st.session_state.editing_product_id:
    prod_to_edit = df_p[df_p['id'] == st.session_state.editing_product_id].iloc[0]
    @st.dialog("✏️ Editar Maestro")
    def show_edit_dialog(p):
        with st.form("form_ed"):
            st.write(f"Editando: **{p['Producto']}**")
            col_a, col_b = st.columns(2)
            n_nombre = col_a.text_input("Nombre", value=p['Producto'])
            n_min = col_b.number_input("Mínimo", value=float(p.get('Stock_Minimo', 0)))
            n_car = col_a.number_input("Carencia", value=int(p.get('Periodo_Carencia_Dias', 0)))
            n_tipo = col_b.selectbox("Tipo", ["Insecticida", "Fungicida", "Herbicida", "Fertilizante", "Regulador", "Agroquímicos", "N/A"])
            n_inc = st.text_area("Incompatibilidades", value=p.get('Incompatible_Con', ''))
            
            if st.form_submit_button("Guardar"):
                data_upd = {
                    "Producto": n_nombre, 
                    "Stock_Minimo": n_min, 
                    "Periodo_Carencia_Dias": n_car, 
                    "Tipo_Accion": n_tipo, 
                    "Incompatible_Con": n_inc
                }
                supabase.table('Productos').update(data_upd).eq('id', p['id']).execute()
                st.session_state.editing_product_id = None
                st.cache_data.clear()
                st.rerun()
            if st.button("Cerrar"):
                st.session_state.editing_product_id = None
                st.rerun()
    show_edit_dialog(prod_to_edit)
