import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px

# --- LIBRERÍAS PARA LA CONEXIÓN A SUPABASE ---
from supabase import create_client

# --- Configuración de la Página ---
st.set_page_config(page_title="Fenología del Arándano", page_icon="🌱", layout="wide")
st.title("🌱 Evaluación Fenológica del Arándano")
st.write("Registre las mediciones de crecimiento y estado para cada planta de la hilera seleccionada.")

# --- Archivo de Configuración ---
# MODIFICACIÓN 1: Se eliminó la Hilera 3
HILERAS = {
    'Hilera 1 (21 Emerald)': 21,
    'Hilera 2 (23 Biloxi/Emerald)': 23
}

ETAPAS_FENOLOGICAS = [
    'Yema Hinchada', 'Punta Verde', 'Salida de Hojas', 
    'Hojas Extendidas', 'Inicio de Floración', 'Plena Flor', 
    'Caída de Pétalos', 'Fruto Verde', 'Pinta', 'Cosecha'
]

# --- Conexión a Supabase ---
@st.cache_resource
def init_supabase_connection():
    """
    Inicializa y devuelve el cliente de Supabase.
    """
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Error al conectar con Supabase: {e}")
        return None

supabase = init_supabase_connection()

# --- Funciones de Datos ---
@st.cache_data(ttl=60)
def cargar_y_calcular_crecimiento():
    """
    Carga el historial de Supabase y calcula la Tasa de Crecimiento Diario (TCD).
    """
    if not supabase:
        st.error("Error al cargar datos: No hay conexión con Supabase.")
        return pd.DataFrame()
    
    try:
        response = supabase.table('Fenologia_Arandano').select("*").order('Fecha', desc=False).execute()
        df = pd.DataFrame(response.data)
        
        if df.empty:
            return pd.DataFrame()

        df['Fecha'] = pd.to_datetime(df['Fecha'])
        # Asegurar que los datos estén ordenados para el cálculo
        df = df.sort_values(by=['Hilera', 'Numero_de_Planta', 'Fecha'])

        # --- CÁLCULO DE TASA DE CRECIMIENTO ---
        # 1. Agrupar por cada planta individual
        grouped = df.groupby(['Hilera', 'Numero_de_Planta'])

        # 2. Calcular la diferencia (diff) con la fila anterior
        df['Altura_Anterior'] = grouped['Altura_Planta_cm'].shift(1)
        df['Fecha_Anterior'] = grouped['Fecha'].shift(1)

        # 3. Calcular los días pasados
        df['Dias_Pasados'] = (df['Fecha'] - df['Fecha_Anterior']).dt.days

        # 4. Calcular el crecimiento en cm
        df['Crecimiento_cm'] = df['Altura_Planta_cm'] - df['Altura_Anterior']

        # 5. Calcular la Tasa de Crecimiento Diario (TCD)
        df['Tasa_Crecimiento_cm_dia'] = 0.0
        mask = (df['Dias_Pasados'] > 0) & (df['Crecimiento_cm'] > 0)
        df.loc[mask, 'Tasa_Crecimiento_cm_dia'] = df['Crecimiento_cm'] / df['Dias_Pasados']
        
        # Limpiar valores infinitos si los hubiera
        df.replace([pd.NA, pd.NaT, float('inf'), float('-inf')], pd.NA, inplace=True)
        
        # Devolver ordenado por fecha (más reciente primero)
        return df.sort_values(by='Fecha', ascending=False) 

    except Exception as e:
        st.error(f"Error al cargar o calcular el crecimiento: {e}")
        return pd.DataFrame()

# --- Interfaz de Registro ---

with st.expander("➕ Registrar Nueva Evaluación por Planta", expanded=True):
    
    # Manejo del estado de la hilera seleccionada
    if 'hilera_para_registrar' not in st.session_state:
        st.session_state.hilera_para_registrar = list(HILERAS.keys())[0]

    def on_hilera_change():
        st.session_state.hilera_para_registrar = st.session_state.widget_selectbox_hilera

    st.subheader("1. Datos Generales de la Jornada")
    
    # MODIFICACIÓN 2: Etapa Fenológica ahora es un dato general (3 columnas)
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.selectbox(
            'Seleccione la Hilera:', 
            options=list(HILERAS.keys()),
            key='widget_selectbox_hilera',
            on_change=on_hilera_change
        )
    with col2:
        fecha_evaluacion = st.date_input("Fecha de Evaluación", datetime.now())
    with col3:
        # Aquí seleccionamos la etapa para TODAS las plantas de esta evaluación
        etapa_general = st.selectbox("Etapa Fenológica General", ETAPAS_FENOLOGICAS)
    
    hilera_actual = st.session_state.hilera_para_registrar
    num_plantas = HILERAS[hilera_actual]
    
    st.divider()
    
    with st.form("nueva_evaluacion_form"):
        st.subheader(f"2. Mediciones para las {num_plantas} plantas de '{hilera_actual}'")
        st.info(f"Todas las plantas se registrarán con la etapa: **{etapa_general}**")

        key_prefix = hilera_actual.replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")

        datos_plantas = []
        for i in range(num_plantas):
            st.markdown(f"**Planta {i+1}**")
            
            # MODIFICACIÓN 3: Solo 4 columnas numéricas (se quitó el selectbox de etapa)
            cols_planta = st.columns(4)
            with cols_planta[0]:
                altura = st.number_input("Altura (cm)", min_value=0.0, format="%.2f", key=f"{key_prefix}_altura_{i}")
            with cols_planta[1]:
                brotes = st.number_input("N° Brotes", min_value=0, step=1, key=f"{key_prefix}_brotes_{i}")
            with cols_planta[2]:
                yemas = st.number_input("N° Yemas", min_value=0, step=1, key=f"{key_prefix}_yemas_{i}")
            with cols_planta[3]:
                diametro = st.number_input("Diámetro Tallo (mm)", min_value=0.0, format="%.2f", key=f"{key_prefix}_diametro_{i}")
            
            datos_plantas.append({
                'Fecha': fecha_evaluacion.strftime("%Y-%m-%d"),
                'Hilera': hilera_actual,
                'Numero_de_Planta': i + 1,
                'Etapa_Fenologica': etapa_general, # Usamos la variable general seleccionada arriba
                'Altura_Planta_cm': altura,
                'Numero_Brotes': brotes,
                'Numero_Yemas': yemas,
                'diametro_tallo_mm': diametro,
            })
            st.divider() # Línea separadora entre plantas

        submitted = st.form_submit_button("✅ Guardar Evaluación Completa", type="primary")
        
        if submitted:
            if supabase:
                try:
                    # Filtramos registros vacíos para no llenar la BD de ceros si no se midió
                    registros_validos = [
                        reg for reg in datos_plantas 
                        if reg['Altura_Planta_cm'] > 0 or reg['Numero_Brotes'] > 0 or reg['Numero_Yemas'] > 0 or reg['diametro_tallo_mm'] > 0
                    ]
                    
                    if registros_validos:
                        response = supabase.table('Fenologia_Arandano').insert(registros_validos).execute()
                        st.toast(f"✅ ¡Se guardaron {len(registros_validos)} plantas exitosamente!", icon="🎉")
                        st.cache_data.clear() # Limpiar la caché para recargar los datos
                    else:
                        st.warning("⚠️ No se ingresaron datos numéricos (alturas, brotes, etc) en ninguna planta.")
                except Exception as e:
                    st.error(f"Error al guardar en Supabase: {e}")
            else:
                st.error("La conexión con Supabase no está disponible.")

# --- Historial y Análisis ---
st.divider()
st.header("📊 Historial y Análisis Fenológico")
# Usar la nueva función que carga Y calcula
df_historial = cargar_y_calcular_crecimiento()

if df_historial is None or df_historial.empty:
    st.info("Aún no hay datos históricos para mostrar.")
else:
    ultima_fecha_evaluacion = df_historial['Fecha'].max().date()
    st.subheader(f"Análisis de la Última Evaluación ({ultima_fecha_evaluacion.strftime('%d/%m/%Y')})")
    df_ultima_eval = df_historial[df_historial['Fecha'].dt.date == ultima_fecha_evaluacion]

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        # Gráfico de Etapas Fenológicas
        df_etapas = df_ultima_eval['Etapa_Fenologica'].value_counts().reset_index()
        df_etapas.columns = ['Etapa_Fenologica', 'Numero_de_Plantas']
        fig_etapas = px.pie(df_etapas, values='Numero_de_Plantas', names='Etapa_Fenologica', 
                            title='Distribución de Etapas Fenológicas', hole=0.3)
        st.plotly_chart(fig_etapas, use_container_width=True)
    
    with col_g2:
        # Gráfico de Diámetro Promedio por Hilera
        if 'diametro_tallo_mm' in df_ultima_eval.columns:
            df_diametro = df_ultima_eval.groupby('Hilera')['diametro_tallo_mm'].mean().reset_index()
            fig_diam = px.bar(df_diametro, x='Hilera', y='diametro_tallo_mm', 
                              title='Diámetro Promedio de Tallo por Hilera', text_auto='.2f',
                              labels={'Hilera': 'Hilera', 'diametro_tallo_mm': 'Diámetro Promedio (mm)'})
            st.plotly_chart(fig_diam, use_container_width=True)
        else:
            st.warning("La columna 'diametro_tallo_mm' no se encuentra para el análisis.")

    st.divider()
    st.subheader("📈 Análisis de Crecimiento a lo Largo del Tiempo")
    
    # Gráfico 1: Evolución de Altura
    df_tendencia_altura = df_historial.groupby(['Fecha', 'Hilera'])['Altura_Planta_cm'].mean().reset_index()
    if not df_tendencia_altura.empty:
        fig_altura = px.line(df_tendencia_altura, x='Fecha', y='Altura_Planta_cm', color='Hilera',
                             title='Evolución de Altura Promedio por Hilera', markers=True,
                             labels={'Fecha': 'Fecha de Medición', 'Altura_Planta_cm': 'Altura Promedio (cm)', 'Hilera': 'Hilera'})
        st.plotly_chart(fig_altura, use_container_width=True)
    
    # Gráfico 2: Tasa de Crecimiento Diario
    df_tasa_crecimiento = df_historial.groupby(['Fecha', 'Hilera'])['Tasa_Crecimiento_cm_dia'].mean().reset_index()
    df_tasa_crecimiento = df_tasa_crecimiento[df_tasa_crecimiento['Tasa_Crecimiento_cm_dia'] > 0]
    
    if not df_tasa_crecimiento.empty:
        fig_tasa = px.bar(df_tasa_crecimiento, x='Fecha', y='Tasa_Crecimiento_cm_dia', color='Hilera',
                             title='Tasa de Crecimiento Diario (TCD) Promedio', 
                             barmode='group',
                             labels={'Fecha': 'Fecha de Medición', 'Tasa_Crecimiento_cm_dia': 'Tasa de Crecimiento (cm/día)', 'Hilera': 'Hilera'})
        st.plotly_chart(fig_tasa, use_container_width=True)
    else:
        st.info("No hay suficientes datos (mínimo 2 mediciones por planta) para calcular la tasa de crecimiento.")

    # Historial Detallado
    with st.expander("Ver historial de datos detallado (con cálculos de crecimiento)"):
        st.dataframe(df_historial, use_container_width=True)