import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, date, timedelta
from supabase import create_client

# --- LIBRERÍAS PRO ---
from streamlit_extras.metric_cards import style_metric_cards
from streamlit_extras.stylable_container import stylable_container

# --- 1. CONFIGURACIÓN E IDENTIDAD VISUAL ---
st.set_page_config(page_title="Panel del Fundo - Dashboard", page_icon="📊", layout="wide")

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

# --- 2. CONEXIÓN A SUPABASE ---
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# --- 3. CARGA DE DATOS CENTRALIZADA ---
@st.cache_data(ttl=300)
def cargar_todo():
    if not supabase: return {}
    
    # Tablas necesarias para el resumen
    tablas = ["Productos", "Ingresos", "Salidas", "Registro_Horas_Tractor", "Maquinaria", "Ordenes_de_Trabajo"]
    dfs = {}
    for t in tablas:
        try:
            res = supabase.table(t).select("*").execute()
            dfs[t] = pd.DataFrame(res.data)
        except:
            dfs[t] = pd.DataFrame()
    return dfs

data = cargar_todo()

# --- 4. CEREBRO MATEMÁTICO (STOCK Y COSTOS) ---
def procesar_kardex_dashboard(dfs):
    df_p = dfs.get("Productos", pd.DataFrame())
    df_i = dfs.get("Ingresos", pd.DataFrame())
    df_s = dfs.get("Salidas", pd.DataFrame())
    
    if df_i.empty: return pd.DataFrame()

    if not df_s.empty:
        gastado = df_s.groupby('Ingreso_ID')['Cantidad_Usada'].sum().reset_index()
        df_balance = pd.merge(df_i, gastado, left_on='id', right_on='Ingreso_ID', how='left').fillna({'Cantidad_Usada': 0})
        df_balance['Stock_Lote'] = df_balance['Cantidad_Ingresada'] - df_balance['Cantidad_Usada']
    else:
        df_balance = df_i.copy()
        df_balance['Stock_Lote'] = df_balance['Cantidad_Ingresada']

    df_final = pd.merge(df_balance, df_p, left_on='Codigo_Producto', right_on='Codigo', how='left')
    df_final['Valorizado_PEN'] = df_final['Stock_Lote'] * df_final['Precio_Unitario_PEN'].fillna(0)
    
    # Limpieza de fechas para evitar el bug del número negativo
    hoy = pd.Timestamp(date.today())
    df_final['Venc_Date'] = pd.to_datetime(df_final['Fecha_Vencimiento'], errors='coerce')
    df_final['Dias_para_Vencer'] = (df_final['Venc_Date'] - hoy).dt.days
    df_final.loc[df_final['Venc_Date'].isnull() | (df_final['Venc_Date'].dt.year < 2000), 'Dias_para_Vencer'] = 999
    
    return df_final

df_kardex = procesar_kardex_dashboard(data)

# --- 5. CABECERA PRINCIPAL ---
with stylable_container(key="title_panel", css_styles="{ background-color: #1e3d33; color: white; padding: 1.5rem; border-radius: 1rem; }"):
    st.title("📊 Dashboard General del Fundo")
    st.write(f"Resumen operativo y financiero actualizado al {datetime.now().strftime('%d/%m/%Y')}")

# --- 6. KPIs (MÉTRICAS CLAVE) ---
st.write("")
m1, m2, m3, m4 = st.columns(4)
style_metric_cards(border_left_color="#1e3d33")

if not df_kardex.empty:
    m1.metric("💰 Valor Almacén", f"S/ {df_kardex['Valorizado_PEN'].sum():,.2f}")
    m2.metric("⚠️ Lotes por Vencer", len(df_kardex[(df_kardex['Dias_para_Vencer'] < 30) & (df_kardex['Stock_Lote'] > 0)]))

df_h = data.get("Registro_Horas_Tractor", pd.DataFrame())
if not df_h.empty:
    h7 = pd.to_datetime(df_h['Fecha']).dt.date >= (date.today() - timedelta(days=7))
    m3.metric("🚜 Horas Tractor (7d)", f"{df_h[h7]['Total_Horas'].sum():,.1f} h")

df_ot = data.get("Ordenes_de_Trabajo", pd.DataFrame())
if not df_ot.empty:
    pendientes = len(df_ot[df_ot['Status'] != 'Aplicada en Campo'])
    m4.metric("📝 Órdenes en Curso", pendientes)

# --- 7. GRÁFICOS ---
st.divider()
c1, c2 = st.columns(2)

with c1:
    with st.container(border=True):
        st.subheader("📦 Inversión por Categoría")
        if not df_kardex.empty:
            df_pie = df_kardex.groupby('Tipo_Accion')['Valorizado_PEN'].sum().reset_index()
            fig_pie = px.pie(df_pie, values='Valorizado_PEN', names='Tipo_Accion', hole=0.4,
                             color_discrete_sequence=px.colors.qualitative.Prism)
            st.plotly_chart(fig_pie, use_container_width=True)

with c2:
    with st.container(border=True):
        st.subheader("📉 Consumo de Insumos (Top 10)")
        df_s = data.get("Salidas", pd.DataFrame())
        df_i = data.get("Ingresos", pd.DataFrame())
        df_p = data.get("Productos", pd.DataFrame())
        if not df_s.empty and not df_i.empty:
            df_merge = pd.merge(df_s, df_i[['id', 'Codigo_Producto']], left_on='Ingreso_ID', right_on='id')
            df_merge = pd.merge(df_merge, df_p[['Codigo', 'Producto']], left_on='Codigo_Producto', right_on='Codigo')
            top_insumos = df_merge.groupby('Producto')['Cantidad_Usada'].sum().sort_values(ascending=False).head(10).reset_index()
            fig_bar = px.bar(top_insumos, x='Cantidad_Usada', y='Producto', orientation='h', 
                             color_discrete_sequence=['#2ecc71'])
            st.plotly_chart(fig_bar, use_container_width=True)

st.info("👈 Usa la barra lateral para navegar entre el Inventario, Mezclas y Gestión de Campo.")
