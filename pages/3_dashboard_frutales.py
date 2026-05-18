import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Dashboard Costos Frutales", page_icon="🍇", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
<style>
    .metric-card {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    .stHeader {
        color: #2c3e50;
    }
</style>
""", unsafe_allow_html=True)

# --- FUNCIÓN INTELIGENTE PARA DETECTAR COLUMNAS ---
def detectar_indices_columnas(fila_valores):
    """
    Escanea una fila para encontrar las columnas de datos.
    Limita la búsqueda a las primeras 15 columnas para evitar leer
    las tablas de resumen que a veces están a la derecha.
    """
    idx_88 = -1
    idx_ha = -1
    idx_actividad = -1
    idx_semana = -1
    
    # Convertimos a string y normalizamos
    fila_str = [str(x).lower().strip() for x in fila_valores]
    
    # Limitamos el rango de búsqueda (importante para no leer la tabla resumen de la derecha)
    limite_busqueda = min(len(fila_str), 15) 
    
    for i in range(limite_busqueda):
        val = fila_str[i]
        
        # Buscar Semana
        if "semana" in val and ("lunes" in val or "viernes" in val):
            idx_semana = i
        
        # Buscar Actividad
        if ("actividad" in val or "insumo" in val or "detalle" in val) and idx_actividad == -1:
            idx_actividad = i
            
        # Buscar Costos
        # Prioridad: Costo Ha tiene "ha" y "total"
        if "total" in val and "ha" in val and ("dólar" in val or "dolar" in val or "usd" in val):
            idx_ha = i
        # Costo 88m2 suele ser "costo total (dólares)" sin la palabra Ha
        elif "total" in val and ("dólar" in val or "dolar" in val or "usd" in val) and "ha" not in val:
            idx_88 = i
            
    # Fallback si falla la detección (usamos los índices más comunes de tu archivo)
    if idx_semana == -1: idx_semana = 0
    if idx_actividad == -1: idx_actividad = 2
    if idx_ha == -1: idx_ha = 10 
    if idx_88 == -1: idx_88 = 9
    
    return idx_semana, idx_actividad, idx_88, idx_ha

# --- FUNCIÓN DE LIMPIEZA MAESTRA ---
def procesar_hoja_compleja(df_raw, nombre_hoja):
    data = []
    current_month = "General" 
    current_week = "Semana 1" # Valor inicial por defecto
    
    # Índices iniciales por defecto
    col_semana_idx = 0
    col_actividad_idx = 2
    col_costo88_idx = 9
    col_costoha_idx = 10
    
    # Lista de meses para detección robusta
    nombres_meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", 
                     "julio", "agosto", "septiembre", "setiembre", "octubre", "noviembre", "diciembre"]

    # Iterar filas
    for index, row in df_raw.iterrows():
        row_vals = row.values
        row_str_full = [str(x).lower().strip() for x in row_vals]
        row_text_start = " ".join(row_str_full[:5]) # Texto de las primeras 5 columnas

        # 1. DETECTAR CABECERAS (PRIORIDAD ALTA)
        is_header = False
        for cell in row_str_full[:15]: 
            if "costo total" in cell and "dólar" in cell:
                col_semana_idx, col_actividad_idx, col_costo88_idx, col_costoha_idx = detectar_indices_columnas(row_vals)
                is_header = True
                break
        if is_header:
            continue

        # 2. DETECTAR CAMBIO DE MES
        found_month = False
        if "mes" in row_text_start and "-" in row_text_start:
            for mes in nombres_meses:
                if mes in row_text_start:
                    current_month = mes.capitalize()
                    if current_month == "Setiembre": current_month = "Septiembre"
                    current_week = "S/N" 
                    found_month = True
                    break
        if found_month:
            continue

        # 3. FILTRO ANTI-BASURA (MÁS ESTRICTO AÚN)
        es_total = False
        for cell in row_str_full[:5]:
            cell_clean = cell.replace(":","").replace(".","").strip()
            # Palabras prohibidas que indican filas de resumen o metadatos
            if cell_clean in ["total", "subtotal", "suma", "total semana", "total mes", "gran total", 
                              "densidad de plantas", "nuestra area", "total de macetas", "promedio"]:
                es_total = True
                break
            # Si contiene "total" y es corto, fuera
            if "total" in cell_clean and len(cell_clean) < 20 and "costo" not in cell_clean: 
                 es_total = True
                 break
        
        if es_total:
            continue

        # 4. EXTRAER DATOS
        try:
            val_semana_raw = row_vals[col_semana_idx]
            val_actividad = row_vals[col_actividad_idx]
            
            # --- LÓGICA FILL FORWARD SEMANA ---
            if not pd.isna(val_semana_raw):
                s_str = str(val_semana_raw).strip()
                if s_str not in ["", "nan", "None"]:
                    if s_str.isdigit():
                        current_week = f"Semana {s_str}"
                    elif "sem" not in s_str.lower():
                        current_week = f"Semana {s_str}"
                    else:
                        current_week = s_str
            
            if current_week == "S/N":
                current_week = "Semana 1"

            # --- EXTRAER COSTOS ---
            costo88_val = 0.0
            try:
                raw_88 = row_vals[col_costo88_idx]
                if isinstance(raw_88, str):
                    raw_88 = raw_88.replace("$","").replace("S/","").replace(",","").strip()
                if raw_88 != "":
                    costo88_val = float(raw_88)
            except: pass
                
            costoha_val = 0.0
            try:
                raw_ha = row_vals[col_costoha_idx]
                if isinstance(raw_ha, str):
                    raw_ha = raw_ha.replace("$","").replace("S/","").replace(",","").strip()
                if raw_ha != "":
                    costoha_val = float(raw_ha)
            except: pass

            # Validaciones Finales
            act_str = str(val_actividad).strip().lower()
            if act_str in ["nan", "none", "", "total", "subtotal", "rubro"]: # 'rubro' a veces se repite en cabeceras
                continue
            
            # Si no hay costos, saltar
            if costo88_val == 0 and costoha_val == 0:
                continue

            data.append({
                "Mes": current_month,
                "Semana": current_week,
                "Actividad": str(val_actividad),
                "Costo_88m2": costo88_val,
                "Costo_Ha": costoha_val,
                "Categoria": nombre_hoja
            })
            
        except IndexError:
            continue

    return pd.DataFrame(data)

# --- INTERFAZ PRINCIPAL ---

st.title("🍓 Dashboard de Costos y Proyecciones")
st.markdown("### Análisis Financiero Agrícola")

# Carga de Archivo
uploaded_file = st.sidebar.file_uploader("📂 Sube 'FRUTALES COSTOS (1).xlsx'", type=["xlsx"])

if uploaded_file:
    xls = pd.ExcelFile(uploaded_file)
    all_sheets = xls.sheet_names
    
    # Mapeo de hojas
    sheet_mo = next((s for s in all_sheets if "mano" in s.lower() and "obra" in s.lower()), None)
    sheet_insumos = next((s for s in all_sheets if "insumo" in s.lower()), None)
    sheet_maq = next((s for s in all_sheets if "maquinaria" in s.lower()), None)
    sheet_proy = next((s for s in all_sheets if "proyecc" in s.lower()), None)
    # NUEVO: Intentar leer la hoja de Costeo General para el resumen
    sheet_gen = next((s for s in all_sheets if "costeo" in s.lower() and "general" in s.lower()), None)

    # --- BARRA LATERAL ---
    st.sidebar.header("⚙️ Configuración")
    
    # 1. SELECTOR DE UNIDAD
    tipo_analisis = st.sidebar.radio(
        "📐 Unidad de Análisis:",
        ["Proyecto Actual (88 m²)", "Proyección Hectárea (1 Ha)"],
        index=0
    )
    col_uso = "Costo_88m2" if "88" in tipo_analisis else "Costo_Ha"
    
    st.sidebar.divider()
    
    # 2. SELECTOR DE SECCIÓN
    seccion = st.sidebar.radio("📍 Sección:", 
        ["Resumen General", "Mano de Obra", "Insumos", "Maquinaria", "Proyecciones"]
    )
    
    st.sidebar.divider()
    
    # 3. FILTRO DE MES
    meses_orden = ["General", "Septiembre", "Octubre", "Noviembre", "Diciembre", "Enero", "Febrero"]
    mes_seleccionado = st.sidebar.selectbox("📅 Mes:", meses_orden)

    # --- PROCESAMIENTO DE DATOS ---
    with st.spinner("Procesando Excel..."):
        # Procesamos hojas individuales
        df_mo = procesar_hoja_compleja(pd.read_excel(uploaded_file, sheet_name=sheet_mo, header=None), "Mano de Obra") if sheet_mo else pd.DataFrame()
        df_ins = procesar_hoja_compleja(pd.read_excel(uploaded_file, sheet_name=sheet_insumos, header=None), "Insumos") if sheet_insumos else pd.DataFrame()
        df_maq = procesar_hoja_compleja(pd.read_excel(uploaded_file, sheet_name=sheet_maq, header=None), "Maquinaria") if sheet_maq else pd.DataFrame()
        df_proy = procesar_hoja_compleja(pd.read_excel(uploaded_file, sheet_name=sheet_proy, header=None), "Proyecciones") if sheet_proy else pd.DataFrame()
        
        # Procesamos Costeo General si existe (Para el resumen exacto)
        if sheet_gen:
            df_gen_excel = procesar_hoja_compleja(pd.read_excel(uploaded_file, sheet_name=sheet_gen, header=None), "General")
        else:
            df_gen_excel = pd.DataFrame()

    # --- LÓGICA DE VISUALIZACIÓN ---
    
    if seccion == "Resumen General":
        st.header(f"📊 Resumen General - {tipo_analisis}")
        
        # ESTRATEGIA: Si existe la hoja "Costeo General" y seleccionamos meses pasados, USAMOS ESA.
        # Si no, sumamos las partes como antes.
        
        usar_hoja_general = not df_gen_excel.empty
        
        if usar_hoja_general:
            df_viz = df_gen_excel.copy()
            # En la hoja general, la columna "Categoria" es siempre "General", así que recuperamos el rubro de la columna 'Actividad' o 'Rubro' si fuera posible, 
            # pero procesar_hoja_compleja solo extrae actividad.
            # Para gráficos de torta, necesitariamos el Rubro real.
            # Como la hoja general tiene columna 'Rubro' en indice 1, intentaremos recuperarla mejor si queremos detalle.
            # Pero para el TOTAL, esta hoja es la autoridad.
        else:
            # Fallback: Sumar todo + proyecciones
            df_operativo = pd.concat([df_mo, df_ins, df_maq])
            df_viz = pd.concat([df_operativo, df_proy])
        
        # Filtro Mes
        if mes_seleccionado != "General":
            df_viz = df_viz[df_viz['Mes'] == mes_seleccionado]

        if df_viz.empty or df_viz[col_uso].sum() == 0:
            st.warning(f"⚠️ No hay datos de costos para el mes **{mes_seleccionado}**.")
        else:
            total = df_viz[col_uso].sum()
            
            # KPI Cards
            k1, k2, k3 = st.columns(3)
            k1.metric("Costo Total", f"{total:,.2f}")
            
            # Para el desglose por categoría, si usamos la hoja general plana, no tenemos categorías claras.
            # Así que para los GRÁFICOS usamos la suma de las hojas detalladas (que sí tienen categoría),
            # pero ajustamos el mensaje.
            
            df_graficos = pd.concat([df_mo, df_ins, df_maq, df_proy])
            if mes_seleccionado != "General":
                df_graficos = df_graficos[df_graficos['Mes'] == mes_seleccionado]
            
            grouped_cat = df_graficos.groupby('Categoria')[col_uso].sum()
            if not grouped_cat.empty:
                k2.metric("Mayor Gasto (Detalle)", grouped_cat.idxmax())
                k3.metric("Monto (Detalle)", f"{grouped_cat.max():,.2f}")
            
            st.divider()
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Por Categoría (Basado en Hojas Detalle)")
                fig_pie = px.pie(df_graficos, values=col_uso, names='Categoria', hole=0.4, 
                                 color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig_pie, use_container_width=True)
            with c2:
                st.subheader("Evolución Mensual")
                # Usamos df_viz (la hoja general) para la evolución total si es posible
                df_mes = df_viz.groupby('Mes')[col_uso].sum().reset_index()
                # Ordenar
                df_mes['Sort'] = df_mes['Mes'].apply(lambda x: meses_orden.index(x) if x in meses_orden else 99)
                df_mes = df_mes.sort_values('Sort')
                
                fig_bar = px.bar(df_mes, x='Mes', y=col_uso, color='Mes', text_auto='.2s')
                st.plotly_chart(fig_bar, use_container_width=True)

    elif seccion in ["Mano de Obra", "Insumos", "Maquinaria", "Proyecciones"]:
        if seccion == "Mano de Obra": df_active = df_mo
        elif seccion == "Insumos": df_active = df_ins
        elif seccion == "Maquinaria": df_active = df_maq
        elif seccion == "Proyecciones": df_active = df_proy
        
        st.header(f"Análisis: {seccion}")
        st.caption(f"Unidad: {tipo_analisis}")
        
        if mes_seleccionado != "General":
            df_active = df_active[df_active['Mes'] == mes_seleccionado]
            
        if df_active.empty or df_active[col_uso].sum() == 0:
            st.warning("No hay datos para mostrar.")
        else:
            total_sec = df_active[col_uso].sum()
            st.metric(f"Total {seccion}", f"{total_sec:,.2f}")
            
            tab1, tab2 = st.tabs(["📈 Gráficos", "📋 Tabla Detallada"])
            
            with tab1:
                c1, c2 = st.columns(2)
                # Gráfico Semanal
                # Limpieza de etiqueta semana
                df_active['Semana_Clean'] = df_active['Semana'].apply(lambda x: str(x).replace('.0',''))
                df_active['Mes_Semana'] = df_active['Mes'] + " - " + df_active['Semana_Clean']
                
                # Ordenar cronológicamente
                df_active['Mes_Index'] = df_active['Mes'].apply(lambda x: meses_orden.index(x) if x in meses_orden else 99)
                df_active = df_active.sort_values(['Mes_Index', 'Semana_Clean'])
                
                df_sem = df_active.groupby('Mes_Semana', sort=False)[col_uso].sum().reset_index()
                
                fig_sem = px.bar(df_sem, x='Mes_Semana', y=col_uso, title="Costo por Semana",
                                 text_auto='.2s', color_discrete_sequence=['#3498db'])
                c1.plotly_chart(fig_sem, use_container_width=True)
                
                # Top Items
                df_top = df_active.groupby('Actividad')[col_uso].sum().reset_index().sort_values(col_uso, ascending=False).head(10)
                fig_top = px.bar(df_top, y='Actividad', x=col_uso, orientation='h', title="Top 10 Actividades/Insumos",
                                 color_discrete_sequence=['#e74c3c'])
                fig_top.update_layout(yaxis={'categoryorder':'total ascending'})
                c2.plotly_chart(fig_top, use_container_width=True)
                
            with tab2:
                st.dataframe(df_active[['Mes', 'Semana', 'Actividad', col_uso]], use_container_width=True)

else:
    st.info("Esperando archivo...")