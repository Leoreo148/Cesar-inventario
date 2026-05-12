import streamlit as st
import pandas as pd
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ValidationError, field_validator
from supabase import create_client, Client
from st_aggrid import AgGrid, GridOptionsBuilder, ColumnsAutoSizeMode
from streamlit_extras.stylable_container import stylable_container

# --- 1. CONFIGURACIÓN E IDENTIDAD VISUAL ---
st.set_page_config(page_title="Gestión de Ingresos Pro", page_icon="📥", layout="wide")

# Inyectamos CSS para suavizar el blanco y mejorar el contraste
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f6; }
    .stHeader { background-color: #1e3d33; }
    div[data-testid="stForm"] {
        background-color: #ffffff;
        border-radius: 15px;
        padding: 20px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. ESQUEMA DE DATOS AUDITADO (Basado en Excel) ---
class IngresoSchema(BaseModel):
    Codigo_Producto: str
    Codigo_Lote: str
    Fecha_Recepcion: date
    Fecha_Vencimiento: Optional[date] = None 
    Cantidad_Ingresada: float
    Precio_Unitario_PEN: float = 0.0
    Proveedor: Optional[str] = None
    Factura: Optional[str] = None
    Guia_Remision: Optional[str] = None      
    Observaciones: Optional[str] = None       
    Responsable: Optional[str] = None # <-- NUEVO CAMPO DE AUDITORÍA

    @field_validator('Cantidad_Ingresada', 'Precio_Unitario_PEN')
    def must_be_positive(cls, v):
        if v < 0: raise ValueError('Debe ser un valor positivo')
        return v

# --- 3. CONEXIÓN ---
@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_supabase()

# --- 4. FUNCIONES DE CARGA ---
@st.cache_data(ttl=60)
def get_products():
    res = supabase.table('Productos').select("Codigo, Producto").execute()
    df = pd.DataFrame(res.data)
    return df if not df.empty else pd.DataFrame(columns=['Codigo', 'Producto'])

def get_history():
    try:
        res_i = supabase.table('Ingresos').select("*").order('created_at', desc=True).limit(100).execute()
        res_p = supabase.table('Productos').select("Codigo, Producto").execute()
        df_i, df_p = pd.DataFrame(res_i.data), pd.DataFrame(res_p.data)
        if df_i.empty: return pd.DataFrame()
        if df_p.empty: 
            df_i['Producto'] = "N/A"
            return df_i
        return pd.merge(df_i, df_p, left_on='Codigo_Producto', right_on='Codigo', how='left')
    except Exception as e:
        return pd.DataFrame()

# --- 5. INTERFAZ DE USUARIO ---
with stylable_container(key="title_container", css_styles="""{ background-color: #1e3d33; color: white; padding: 1.5rem; border-radius: 1rem; margin-bottom: 2rem; }"""):
    st.title("📥 Registro Maestro de Ingresos")
    st.write("Auditoría de almacén y control de compras.")
df_p = get_products()

# --- DIÁLOGO PARA CREAR PRODUCTO NUEVO ---
@st.dialog("📦 Registrar Nuevo Producto en el Catálogo")
def modal_crear_producto():
    st.write("Crea el 'molde' del producto antes de ingresarlo al almacén.")
    with st.form("form_crear_maestro"):
        c_mod1, c_mod2 = st.columns(2)
        n_cod = c_mod1.text_input("Código (Ej: A260)", help="Debe ser único")
        n_nom = c_mod2.text_input("Nombre del Producto")
        
        c_mod3, c_mod4 = st.columns(2)
        n_uni = c_mod3.selectbox("Unidad de Medida", ["001", "002"], help="001=Lt | 002=Kg")
        n_tipo = c_mod4.selectbox("Categoría", ["Fungicida y Bactericida", "Insecticida y Acaricida", "Fertilizante", "Agroquímicos", "Herbicida", "Otro"])
        
        if st.form_submit_button("Guardar en Catálogo Maestro", use_container_width=True):
            if n_cod and n_nom:
                try:
                    nuevo_prod = {
                        "Codigo": n_cod.strip().upper(),
                        "Producto": n_nom.strip().upper(),
                        "Unidad": n_uni,
                        "Tipo_Accion": n_tipo
                    }
                    supabase.table('Productos').insert(nuevo_prod).execute()
                    st.success(f"¡{n_nom} agregado al catálogo!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error (¿Código duplicado?): {e}")
            else:
                st.warning("Código y Nombre son obligatorios.")

# FORMULARIO DE REGISTRO
with st.form("form_registro", clear_on_submit=True):
    st.markdown("##### 📝 Información del Producto")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        dict_productos = {}
        if not df_p.empty:
            for _, row in df_p.iterrows():
                nombre = str(row['Producto']).strip()
                codigo = str(row['Codigo']).strip()
                if nombre and nombre != 'nan':
                    etiqueta = f"{nombre} ({codigo})"
                    dict_productos[etiqueta] = codigo
        
        seleccion = st.selectbox(
            "Seleccionar Producto", 
            options=list(dict_productos.keys()), 
            index=None, 
            placeholder="🔍 Escribe para buscar..."
        )
        cod_prod = dict_productos[seleccion] if seleccion else None
        
        lote = st.text_input("Código de Lote / Batch")
    
    with c2:
        cant = st.number_input("Cantidad Ingresada", min_value=0.0, step=0.01)
        p_pen = st.number_input("Precio Unitario (S/)", min_value=0.0, step=0.01)
    
    with c3:
        fecha_rec = st.date_input("Fecha de Recepción", value=date.today())
        fecha_venc = st.date_input("Fecha de Vencimiento", value=date.today().replace(year=date.today().year + 2))

    st.divider()
    st.markdown("##### 🚛 Datos Logísticos y Auditoría")
    
    # 🛡️ Cambiamos a 4 columnas para incluir al Responsable
    c4, c5, c6, c7 = st.columns(4)
    
    with c4:
        prov = st.text_input("Proveedor")
    with c5:
        fact = st.text_input("N° de Factura")
    with c6:
        guia = st.text_input("Guía de Remisión")
    with c7:
        resp = st.text_input("Responsable (Recepción)", placeholder="Tu nombre")
    
    obs = st.text_area("Observaciones Adicionales", placeholder="Ej: Sacos con humedad, entrega parcial, etc.")

    if st.form_submit_button("💾 Confirmar Ingreso a Almacén", use_container_width=True):
        if cod_prod and lote and cant > 0:
            if not resp:
                st.warning("⚠️ Por favor, indica quién es el responsable de la recepción.")
            else:
                try:
                    nuevo = IngresoSchema(
                        Codigo_Producto=cod_prod, Codigo_Lote=lote, Fecha_Recepcion=fecha_rec,
                        Fecha_Vencimiento=fecha_venc, Cantidad_Ingresada=cant, Precio_Unitario_PEN=p_pen,
                        Proveedor=prov, Factura=fact, Guia_Remision=guia, Observaciones=obs,
                        Responsable=resp # <-- Se guarda el responsable
                    )
                    supabase.table('Ingresos').insert(nuevo.model_dump(mode='json')).execute()
                    st.success("✅ Ingreso registrado correctamente en la base de datos.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar: {e}")
        else:
            st.error("⚠️ Producto, Lote y Cantidad son campos obligatorios.")

# BOTÓN DE CREACIÓN RÁPIDA (Fuera del formulario principal)
st.write("")
col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
if col_btn2.button("💡 ¿El producto no existe? Crea uno nuevo aquí", use_container_width=True):
    modal_crear_producto()

# HISTORIAL DINÁMICO
st.divider()
st.subheader("📋 Historial de Movimientos")
df_hist = get_history()

if not df_hist.empty:
    # 🛡️ Añadimos 'Responsable' a las columnas visibles del historial
    cols_visibles = ['Fecha_Recepcion', 'Producto', 'Codigo_Lote', 'Cantidad_Ingresada', 'Precio_Unitario_PEN', 'Proveedor', 'Factura', 'Responsable']
    cols_reales = [c for c in cols_visibles if c in df_hist.columns]
    
    gb = GridOptionsBuilder.from_dataframe(df_hist[cols_reales])
    gb.configure_pagination(paginationPageSize=10)
    gb.configure_default_column(filterable=True, sortable=True)
    AgGrid(df_hist[cols_reales], gridOptions=gb.build(), theme='balham', height=400)
else:
    st.info("No se encontraron registros de ingresos previos.")
