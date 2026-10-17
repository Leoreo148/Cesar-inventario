import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, date, timedelta

from utils_cesar import (
    init_supabase,
    apply_cesar_theme,
    cargar_tabla_segura,
    mostrar_aviso_sql_si_local,
)

# --- 1. CONFIGURACIÓN E IDENTIDAD VISUAL ---
st.set_page_config(page_title="Panel General - César Agro & Dron", page_icon="📊", layout="wide")
apply_cesar_theme()

# --- 2. CONEXIÓN A SUPABASE ---
supabase = init_supabase()

# --- 3. CARGA DE DATOS CENTRALIZADA ---
@st.cache_data(ttl=120)
def cargar_todo():
    if not supabase:
        return {}
    tablas = ["Productos", "Ingresos", "Salidas", "Ordenes_de_Trabajo"]
    dfs = {}
    for t in tablas:
        try:
            res = supabase.table(t).select("*").execute()
            dfs[t] = pd.DataFrame(res.data)
        except Exception:
            dfs[t] = pd.DataFrame()
    return dfs

data = cargar_todo()
df_servicios_dron, ok_srv = cargar_tabla_segura(supabase, "Servicios_Dron")
df_campos_propios, ok_cp = cargar_tabla_segura(supabase, "Campos_Propios")

# --- 4. CEREBRO MATEMÁTICO (STOCK Y COSTOS) ---
def procesar_kardex_dashboard(dfs):
    df_p = dfs.get("Productos", pd.DataFrame())
    df_i = dfs.get("Ingresos", pd.DataFrame())
    df_s = dfs.get("Salidas", pd.DataFrame())

    if df_i.empty:
        return pd.DataFrame()

    if not df_s.empty:
        gastado = df_s.groupby("Ingreso_ID")["Cantidad_Usada"].sum().reset_index()
        df_balance = pd.merge(df_i, gastado, left_on="id", right_on="Ingreso_ID", how="left").fillna({"Cantidad_Usada": 0})
        df_balance["Stock_Lote"] = df_balance["Cantidad_Ingresada"] - df_balance["Cantidad_Usada"]
    else:
        df_balance = df_i.copy()
        df_balance["Stock_Lote"] = df_balance["Cantidad_Ingresada"]

    df_final = pd.merge(df_balance, df_p, left_on="Codigo_Producto", right_on="Codigo", how="left")
    df_final["Valorizado_PEN"] = df_final["Stock_Lote"] * pd.to_numeric(df_final.get("Precio_Unitario_PEN", 0), errors="coerce").fillna(0)

    hoy = pd.Timestamp(date.today())
    df_final["Venc_Date"] = pd.to_datetime(df_final.get("Fecha_Vencimiento"), errors="coerce")
    df_final["Dias_para_Vencer"] = (df_final["Venc_Date"] - hoy).dt.days
    df_final.loc[df_final["Venc_Date"].isnull() | (df_final["Venc_Date"].dt.year < 2000), "Dias_para_Vencer"] = 999

    return df_final

df_kardex = procesar_kardex_dashboard(data)

# --- 5. CABECERA PRINCIPAL ---
st.markdown(f"""
<div class="cesar-header">
    <h1>📊 Centro de Mando — César Inventario, Servicio Dron & Campos</h1>
    <p>Resumen operativo y financiero actualizado al {datetime.now().strftime('%d/%m/%Y')} — Conectado a Supabase</p>
</div>
""", unsafe_allow_html=True)

mostrar_aviso_sql_si_local(ok_srv and ok_cp)

# --- 6. ACCESOS RÁPIDOS A LAS 4 SECCIONES ---
nav1, nav2, nav3, nav4 = st.columns(4)
with nav1:
    st.page_link("pages/2_Inventario.py", label="📦 1. Inventario & Kardex", use_container_width=True)
with nav2:
    st.page_link("pages/4_Servicio_Dron.py", label="🚁 2. Servicio Dron & PDF", use_container_width=True)
with nav3:
    st.page_link("pages/5_Campos_Propios.py", label="🌱 3. Campos Propios", use_container_width=True)
with nav4:
    st.page_link("pages/6_Monitoreo_Multiespectral.py", label="🛰️ 4. Monitoreo Multiespectral", use_container_width=True)

# --- 7. KPIs (MÉTRICAS CLAVE) ---
st.write("")
m1, m2, m3, m4 = st.columns(4)

val_almacen = float(df_kardex["Valorizado_PEN"].sum()) if not df_kardex.empty else 0.0
lotes_vencer = len(df_kardex[(df_kardex["Dias_para_Vencer"] < 30) & (df_kardex["Stock_Lote"] > 0)]) if not df_kardex.empty else 0
ha_dron_tot = float(df_servicios_dron["hectareas_aplicadas"].sum()) if not df_servicios_dron.empty else 0.0
fact_dron_tot = float(df_servicios_dron["total_cobrar_pen"].sum()) if not df_servicios_dron.empty else 0.0

m1.metric("💰 Valor en Almacén", f"S/ {val_almacen:,.2f}", f"{lotes_vencer} lotes por vencer")
m2.metric("🚁 Hectáreas Voladas (Dron)", f"{ha_dron_tot:,.2f} ha", f"{len(df_servicios_dron)} servicios")
m3.metric("💵 Facturación Servicio Dron", f"S/ {fact_dron_tot:,.2f}")
m4.metric("🌱 Campos Propios Activos", f"{len(df_campos_propios)} lotes", f"{float(df_campos_propios['area_ha'].sum()) if not df_campos_propios.empty else 0:.2f} ha totales")

# --- 8. GRÁFICOS ---
st.divider()
c1, c2 = st.columns(2)

with c1:
    with st.container(border=True):
        st.subheader("🚁 Ingresos de Servicio Dron por Cultivo (S/)")
        if not df_servicios_dron.empty:
            df_dron_cult = df_servicios_dron.groupby("cultivo", as_index=False)["total_cobrar_pen"].sum()
            fig_dron = px.bar(
                df_dron_cult,
                x="cultivo",
                y="total_cobrar_pen",
                text_auto=".2f",
                color="cultivo",
                color_discrete_sequence=["#15803D", "#22C55E", "#A16207", "#0369A1"]
            )
            fig_dron.update_layout(showlegend=False, xaxis_title="Cultivo", yaxis_title="Total Facturado (S/)")
            st.plotly_chart(fig_dron, use_container_width=True)
        else:
            st.info("Registra servicios en la sección 'Servicio Dron' para visualizar la facturación por cultivo.")

with c2:
    with st.container(border=True):
        st.subheader("📦 Valor de Inventario por Categoría")
        if not df_kardex.empty and "Tipo_Accion" in df_kardex.columns:
            df_pie = df_kardex.groupby("Tipo_Accion")["Valorizado_PEN"].sum().reset_index()
            fig_pie = px.pie(
                df_pie,
                values="Valorizado_PEN",
                names="Tipo_Accion",
                hole=0.45,
                color_discrete_sequence=["#14532D", "#15803D", "#22C55E", "#86EFAC", "#A16207"]
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Sin stock valorizado disponible.")
