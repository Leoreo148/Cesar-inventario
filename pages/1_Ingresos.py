import streamlit as st
import pandas as pd
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ValidationError, field_validator
from supabase import create_client
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
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
st.set_page_config(page_title="Gestión de Ingresos Pro", page_icon="📥", layout="wide")

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

# --- 2. ESQUEMA DE DATOS AUDITADO ---
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
    Responsable: Optional[str] = None 
    # --- NUEVOS CAMPOS DE CONTROL ---
    Estado_Registro: Optional[str] = "Completo 🟢" 
    Motivo_Anulacion: Optional[str] = None

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
    st.write("Auditoría de almacén, control de compras y recepciones provisionales.")
df_p = get_products()

# --- DIÁLOGO PARA CREAR PRODUCTO NUEVO ---
@st.dialog("📦 Registrar Nuevo Producto en el Catálogo")
def modal_crear_producto():
    st.write("Crea el 'molde' del producto antes de ingresarlo al almacén.")
    with st.form("form_crear_maestro"):
        st.markdown("**1. Datos Generales**")
        c_mod1, c_mod2, c_mod3 = st.columns([1.5, 2, 1.5])
        n_cod = c_mod1.text_input("Código (Ej: A260)*", help="Debe ser único")
        n_nom = c_mod2.text_input("Nombre Comercial*")
        n_marca = c_mod3.text_input("Marca / Laboratorio")
        
        # --- NUEVO: Ingrediente Activo Inteligente ---
        n_ingrediente = st.text_input("Ingrediente(s) Activo(s)", placeholder="Ej: cymoxanil, mancozeb", help="Si tiene más de uno, sepáralos con comas.")
        
        st.markdown("**2. Clasificación Técnica**")
        c_mod4, c_mod5, c_mod6 = st.columns(3)
        
        # Categorías exactas del Excel
        CATEGORIAS = ["Insecticida", "Acaricida", "Fungicida", "Herbicida", "Coadyuvante", "Regulador de pH", "Nematicida", "Foliar", "Fertilizante", "Otro"]
        n_tipo = c_mod4.selectbox("Categoría", CATEGORIAS)
        
        # Formulaciones comunes
        FORMULACIONES = ["Concentrado Soluble (SL)", "Concentrado Emulsionable (EC)", "Suspensión Concentrada (SC)", "Polvo Mojable (WP)", "Gránulos Dispersables (WG)", "Otro"]
        n_form = c_mod5.selectbox("Formulación", FORMULACIONES)
        
        n_uni = c_mod6.selectbox("Unidad Base", ["L", "Kg", "Gal", "Saco"])
        
        st.markdown("**3. Seguridad y Documentación**")
        c_mod7, c_mod8 = st.columns(2)
        n_banda = c_mod7.selectbox("Banda Toxicológica", ["Verde (Ligeramente Tóxico)", "Azul (Moderadamente Tóxico)", "Amarillo (Altamente Tóxico)", "Rojo (Extremadamente Tóxico)", "No Aplica"])
        n_ficha = c_mod8.text_input("URL Ficha Técnica", placeholder="https://link-al-pdf.com...")
        
        if st.form_submit_button("Guardar en Catálogo Maestro", use_container_width=True):
            if n_cod and n_nom:
                try:
                    # 💡 LÓGICA INTELIGENTE: Limpieza de texto para el Ingrediente Activo
                    # Convierte "agua , MANCOZEB" en "Agua, Mancozeb"
                    ingredientes_limpios = ", ".join([i.strip().capitalize() for i in n_ingrediente.split(",") if i.strip()]) if n_ingrediente else None
                    
                    nuevo_prod = {
                        "Codigo": n_cod.strip().upper(), 
                        "Producto": n_nom.strip().upper(), 
                        "Unidad": n_uni, 
                        "Tipo_Accion": n_tipo,
                        "Marca": n_marca.strip().upper() if n_marca else None,
                        "Ingrediente_Activo": ingredientes_limpios,
                        "Formulacion": n_form,
                        "Banda_Toxicologica": n_banda,
                        "Ficha_Tecnica_URL": n_ficha.strip() if n_ficha else None
                    }
                    supabase.table('Productos').insert(nuevo_prod).execute()
                    st.success(f"¡{n_nom} agregado al catálogo con éxito!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error (¿Código duplicado?): {e}")
            else:
                st.warning("⚠️ Código y Nombre son obligatorios.")
                
# FORMULARIO DE REGISTRO ORIGINAL (Intacto)
with st.form("form_registro", clear_on_submit=True):
    st.markdown("##### 📝 Información del Producto")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        dict_productos = {}
        if not df_p.empty:
            for _, row in df_p.iterrows():
                nombre, codigo = str(row['Producto']).strip(), str(row['Codigo']).strip()
                if nombre and nombre != 'nan':
                    dict_productos[f"{nombre} ({codigo})"] = codigo
        
        seleccion = st.selectbox("Seleccionar Producto", options=list(dict_productos.keys()), index=None, placeholder="🔍 Escribe para buscar...")
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
    c4, c5, c6, c7 = st.columns(4)
    
    with c4: prov = st.text_input("Proveedor")
    with c5: fact = st.text_input("N° de Factura", help="Si lo dejas vacío, el ingreso será Provisional")
    with c6: guia = st.text_input("Guía de Remisión")
    with c7: resp = st.text_input("Responsable (Recepción)*", placeholder="Tu nombre")
    
    obs = st.text_area("Observaciones Adicionales", placeholder="Ej: Sacos con humedad, entrega parcial, etc.")

    if st.form_submit_button("💾 Confirmar Ingreso a Almacén", use_container_width=True):
        if cod_prod and lote and cant > 0:
            if not resp:
                st.warning("⚠️ Por favor, indica quién es el responsable de la recepción.")
            else:
                try:
                    # 💡 LÓGICA INTELIGENTE: Si no hay factura, es provisional
                    estado_actual = "Provisional 🔴" if not fact else "Completo 🟢"
                    
                    nuevo = IngresoSchema(
                        Codigo_Producto=cod_prod, Codigo_Lote=lote, Fecha_Recepcion=fecha_rec,
                        Fecha_Vencimiento=fecha_venc, Cantidad_Ingresada=cant, Precio_Unitario_PEN=p_pen,
                        Proveedor=prov, Factura=fact, Guia_Remision=guia, Observaciones=obs,
                        Responsable=resp, Estado_Registro=estado_actual
                    )
                    supabase.table('Ingresos').insert(nuevo.model_dump(mode='json')).execute()
                    st.success(f"✅ Ingreso registrado como {estado_actual}.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar: {e}")
        else:
            st.error("⚠️ Producto, Lote y Cantidad son campos obligatorios.")

st.write("")
col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
if col_btn2.button("💡 ¿El producto no existe? Crea uno nuevo aquí", use_container_width=True): modal_crear_producto()

# --- 6. HISTORIAL Y AUDITORÍA DE MOVIMIENTOS ---
st.divider()
st.subheader("📋 Historial de Movimientos y Auditoría")
df_hist = get_history()

if not df_hist.empty:
    cols_visibles = ['Estado_Registro', 'Fecha_Recepcion', 'Proveedor', 'Producto', 'Codigo_Lote', 'Cantidad_Ingresada', 'Precio_Unitario_PEN', 'Factura', 'Responsable', 'Motivo_Anulacion']
    cols_reales = [c for c in cols_visibles if c in df_hist.columns]
    
    gb = GridOptionsBuilder.from_dataframe(df_hist[cols_reales])
    gb.configure_pagination(paginationPageSize=10)
    gb.configure_default_column(filterable=True, sortable=True)
    # 💡 HACEMOS LA TABLA SELECCIONABLE
    gb.configure_selection('single', use_checkbox=True)
    
    grid_res = AgGrid(df_hist[cols_reales], gridOptions=gb.build(), update_mode=GridUpdateMode.SELECTION_CHANGED, theme='balham', height=350)
    
    # --- 7. ACCIONES POST-RECEPCIÓN ---
    selected = grid_res['selected_rows']
    if selected is not None and not (isinstance(selected, pd.DataFrame) and selected.empty):
        sel_row = selected.iloc[0] if isinstance(selected, pd.DataFrame) else selected[0]
        
        st.write("---")
        st.markdown(f"**Gestión del Lote seleccionado:** `{sel_row.get('Codigo_Lote', '')}` - {sel_row.get('Producto', '')}")
        
        c_acc1, c_acc2 = st.columns(2)
        
        # BOTÓN 1: COMPLETAR DATOS (Si es provisional)
        if sel_row.get('Estado_Registro') == 'Provisional 🔴':
            with c_acc1.expander("📝 Completar Factura / Precio"):
                with st.form(f"form_completar_{sel_row.get('id', '')}"):
                    n_fact = st.text_input("Nueva Factura")
                    n_precio = st.number_input("Precio Final (S/)", min_value=0.0, value=float(sel_row.get('Precio_Unitario_PEN', 0)))
                    if st.form_submit_button("Actualizar y Cerrar Registro"):
                        # Extraemos el ID original cruzando con el dataframe completo
                        real_id = df_hist[df_hist['Codigo_Lote'] == sel_row['Codigo_Lote']].iloc[0]['id']
                        supabase.table('Ingresos').update({"Factura": n_fact, "Precio_Unitario_PEN": n_precio, "Estado_Registro": "Completo 🟢"}).eq('id', int(real_id)).execute()
                        st.success("Registro actualizado.")
                        st.cache_data.clear()
                        st.rerun()

        # BOTÓN 2: ANULAR INGRESO (Cero borrados)
        if sel_row.get('Estado_Registro') != 'ANULADO ❌':
            with c_acc2.expander("⚠️ Anular Movimiento"):
                with st.form(f"form_anular_{sel_row.get('id', '')}"):
                    st.warning("Esto pondrá el stock de este ingreso en cero.")
                    motivo = st.text_input("Motivo de la anulación (Obligatorio)*")
                    if st.form_submit_button("Confirmar Anulación"):
                        if motivo:
                            real_id = df_hist[df_hist['Codigo_Lote'] == sel_row['Codigo_Lote']].iloc[0]['id']
                            supabase.table('Ingresos').update({"Cantidad_Ingresada": 0, "Estado_Registro": "ANULADO ❌", "Motivo_Anulacion": motivo}).eq('id', int(real_id)).execute()
                            st.success("Movimiento anulado por trazabilidad.")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("Debes escribir un motivo para la auditoría.")
else:
    st.info("No se encontraron registros de ingresos previos.")