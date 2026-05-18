import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, time 
from supabase import create_client 
import pytz 
import os 
import re 

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Estación Meteorológica", page_icon="🌦️", layout="wide")

# --- CONEXIÓN A SUPABASE ---
@st.cache_resource
def init_supabase_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Error al conectar con Supabase: {e}")
        return None

supabase = init_supabase_connection()

# --- ZONA HORARIA DE PERÚ ---
try:
    TZ_PERU = pytz.timezone('America/Lima')
except ImportError:
    st.error("Se necesita la librería 'pytz'. Instálala con: pip install pytz")
    TZ_PERU = None

# ======================================================================
# SECCIÓN DE CARGA DE DATOS
# ======================================================================
st.title("🌦️ Dashboard de Estación Meteorológica")
st.write("Sube el archivo de datos (`.xlsx`) de la estación para ingestar y analizar los datos climáticos.")

uploaded_file = st.file_uploader(
    "Sube tu archivo de datos de la estación (.xlsx)", 
    type=["xlsx"],
    help="Sube el archivo .xlsx. El script se encargará de limpiarlo y subirlo a Supabase."
)

COLUMNAS_FINALES = [
    'fecha', 'hora', 'humedad_out', 'temperatura_out', 'velocidad_viento', 
    'direccion_viento', 'radiacion_solar', 'uv_index', 'lluvia_rate'
]

if uploaded_file is not None:
    try:
        with st.spinner(f"Procesando archivo '{uploaded_file.name}'... Esto puede tardar varios minutos."):
            
            st.info("Detectado archivo .xlsx. Leyendo la primera hoja...")
            # Leemos con header=1 porque la fila 1 real (indice 0) está vacía o tiene metadata
            df = pd.read_excel(uploaded_file, header=1)
            
            if df is None or df.empty:
                st.warning("El archivo está vacío o no se pudo leer.")
                st.stop()

            col_fecha_original = df.columns[0]
            col_hora_original = df.columns[1]
            df = df.dropna(subset=[col_fecha_original, col_hora_original])

            if df.empty:
                st.warning("El archivo se leyó, pero no se encontraron filas con datos de 'Date' y 'Time'.")
                st.stop()
                
            st.write(f"Encontrados {len(df)} registros con datos. Procesando...")

            current_cols = df.columns.tolist()
            
            if len(current_cols) < 9:
                st.error(f"Error: El archivo solo tiene {len(current_cols)} columnas, se esperaban al menos 9 (Date, Time, Temp, Hum, etc.).")
                st.stop()

            rename_map = {
                current_cols[0]: 'fecha',           # 'Date'
                current_cols[1]: 'hora',            # 'Time'
                current_cols[2]: 'temperatura_out', # 'Out Temp'
                current_cols[3]: 'humedad_out',     # 'Out Hum'
                current_cols[4]: 'velocidad_viento',# 'Wind Speed'
                current_cols[5]: 'direccion_viento',# 'Wind Dir'
                current_cols[6]: 'radiacion_solar', # 'Solar Rad.'
                current_cols[7]: 'uv_index',        # 'UV Index'
                current_cols[8]: 'lluvia_rate'      # 'Rain Rate'
            }

            df = df.rename(columns=rename_map)

            numeric_cols = [
                'temperatura_out', 'humedad_out', 'velocidad_viento', 
                'radiacion_solar', 'uv_index', 'lluvia_rate'
            ]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            st.write("Procesando timestamp para formato XLSX...")
            
            # --- [SOLUCIÓN DEL ERROR] ---
            # En lugar de usar datetime.combine (que falla con strings),
            # convertimos todo a texto, lo unimos y luego Pandas lo convierte inteligentemente.
            
            # 1. Aseguramos que sea texto
            df['fecha_str'] = df['fecha'].astype(str)
            df['hora_str'] = df['hora'].astype(str)

            # 2. Unimos fecha y hora en una sola columna de texto
            df['fecha_hora_completa'] = df['fecha_str'] + ' ' + df['hora_str']

            # 3. Convertimos a datetime real (dayfirst=True es vital para formato Perú dd/mm/yy)
            df['timestamp_naive'] = pd.to_datetime(df['fecha_hora_completa'], dayfirst=True, errors='coerce')
            
            # 4. Limpiamos si alguna fecha falló
            df = df.dropna(subset=['timestamp_naive'])
            # ----------------------------
            
            # Localizamos a hora de Perú
            df['timestamp'] = df['timestamp_naive'].apply(
                lambda ts_naive: TZ_PERU.localize(ts_naive)
            )

            columnas_para_subir = ['timestamp'] + [col for col in COLUMNAS_FINALES if col not in ['fecha', 'hora']]
            columnas_existentes = [col for col in columnas_para_subir if col in df.columns]
            df_final = df[columnas_existentes]
            
            # Convertir a ISO para Supabase
            df_final['timestamp'] = df_final['timestamp'].apply(lambda x: x.isoformat())
            df_final = df_final.astype(object).where(pd.notnull(df_final), None)
            records_to_insert = df_final.to_dict('records')
            
            if not records_to_insert:
                st.warning("El archivo no contenía datos válidos para procesar.")
            else:
                st.write(f"Se procesaron {len(records_to_insert)} registros. Subiendo a Supabase...")
                
                # Upsert en bloques (chunks) opcional si son muchos datos, pero directo funciona para <50k
                response = supabase.table('Datos_Estacion_Clima').upsert(
                    records_to_insert, 
                    on_conflict='timestamp'
                ).execute()
                
                st.success(f"¡Éxito! Se han subido y/o actualizado {len(records_to_insert)} registros en la base de datos.")
                st.balloons()
                st.cache_data.clear()

    except Exception as e:
        st.error(f"Ocurrió un error al procesar el archivo: {e}")
        st.warning("Verifica el formato del archivo. ¿La cabecera está en la fila 2 (header=1)?")
        st.info("Asegúrate que el orden de las columnas sea Date, Time, Out Temp, Out Hum, Wind Speed, etc.")

st.divider()

# ======================================================================
# SECCIÓN DE VISUALIZACIÓN DE DATOS
# ======================================================================
st.header("Visualización de Datos Climáticos")

@st.cache_data(ttl=600) 
def cargar_datos_climaticos(start_date, end_date):
    if not supabase:
        st.error("No hay conexión con Supabase.")
        return pd.DataFrame()
    try:
        start_iso = start_date.isoformat()
        end_iso = end_date.isoformat()
        
        response = supabase.table('Datos_Estacion_Clima') \
                           .select("*") \
                           .gte('timestamp', start_iso) \
                           .lte('timestamp', end_iso) \
                           .order('timestamp', desc=False) \
                           .execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            
            # --- [CORRECCIÓN DE ZONA HORARIA AL LEER] ---
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            # Convertir UTC (Supabase) a Perú
            df['timestamp'] = df['timestamp'].dt.tz_convert(TZ_PERU)
            
            # Convertir columnas a numérico
            cols_to_convert = ['velocidad_viento', 'humedad_out', 'radiacion_solar', 'temperatura_out', 'uv_index', 'lluvia_rate']
            for col in cols_to_convert:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
        else:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error al cargar datos del historial: {e}")
        return pd.DataFrame()

# --- Selectores de Fecha ---
today = datetime.now(TZ_PERU).date()
default_start = today - pd.Timedelta(days=7)

col_f1, col_f2 = st.columns(2)
with col_f1:
    start_date = st.date_input(
        "Fecha de Inicio", 
        default_start, 
        max_value=today
    )
with col_f2:
    end_date = st.date_input(
        "Fecha de Fin", 
        today, 
        min_value=start_date, 
        max_value=today
    )

start_datetime = TZ_PERU.localize(datetime.combine(start_date, datetime.min.time()))
end_datetime = TZ_PERU.localize(datetime.combine(end_date, datetime.max.time()))

df_datos = cargar_datos_climaticos(start_datetime, end_datetime)

if df_datos.empty:
    st.info("No se encontraron datos para el rango de fechas seleccionado. Sube un archivo o ajusta las fechas.")
else:
    st.success(f"Mostrando {len(df_datos)} registros por minuto entre {start_date.strftime('%d/%m')} y {end_date.strftime('%d/%m')}.")
    
    # --- 1. MÉTRICAS CLAVE (KPIs) ---
    st.subheader("Métricas Clave del Periodo Seleccionado")
    
    avg_temp = df_datos['temperatura_out'].mean()
    max_temp = df_datos['temperatura_out'].max()
    avg_hum = df_datos['humedad_out'].mean()
    max_hum = df_datos['humedad_out'].max()
    avg_rad = df_datos['radiacion_solar'].mean()
    max_rad = df_datos['radiacion_solar'].max()
    avg_wind = df_datos['velocidad_viento'].mean()
    max_wind = df_datos['velocidad_viento'].max()
    
    if df_datos['temperatura_out'].notna().any():
        hora_max_temp = df_datos.loc[df_datos['temperatura_out'].idxmax()]['timestamp'].strftime('%d/%m a las %H:%M')
    else:
        hora_max_temp = "N/A"
    
    kpi_cols = st.columns(4)
    kpi_cols[0].metric("Temp. Promedio", f"{avg_temp:.1f} °C", help=f"Máxima: {max_temp:.1f} °C (el {hora_max_temp})")
    kpi_cols[1].metric("Humedad Promedio", f"{avg_hum:.1f} %", help=f"Máxima: {max_hum:.1f} %")
    kpi_cols[2].metric("Radiación Promedio", f"{avg_rad:.1f} W/m²", help=f"Máxima: {max_rad:.1f} W/m²")
    kpi_cols[3].metric("Viento Promedio", f"{avg_wind:.1f}", help=f"Máxima: {max_wind:.1f}")

    st.divider()

    # --- 2. GRÁFICOS DE CICLO DIARIO ---
    st.subheader("Promedio de las 24 Horas (Ciclo Diario)")
    st.write("Junta todos los días seleccionados para mostrar el comportamiento promedio a lo largo de un día.")
    
    df_by_hour = df_datos.copy()
    df_by_hour['hora_del_dia'] = df_by_hour['timestamp'].dt.hour
    df_cycle = df_by_hour.groupby('hora_del_dia').mean(numeric_only=True).reset_index()
    df_cycle['Hora (Formato 24h)'] = df_cycle['hora_del_dia'].apply(lambda h: f"{h:02d}:00")

    cycle_cols = st.columns(2)
    with cycle_cols[0]:
        fig_cycle_temp = px.line(df_cycle, x='Hora (Formato 24h)', y='temperatura_out',
                                 title='Ciclo Diario de Temperatura',
                                 labels={'Hora (Formato 24h)': 'Hora del Día (Promedio)', 'temperatura_out': 'Temp Promedio (°C)'},
                                 markers=True)
        st.plotly_chart(fig_cycle_temp, use_container_width=True)
        
    with cycle_cols[1]:
        fig_cycle_hum = px.line(df_cycle, x='Hora (Formato 24h)', y='humedad_out',
                                 title='Ciclo Diario de Humedad',
                                 labels={'Hora (Formato 24h)': 'Hora del Día (Promedio)', 'humedad_out': 'Humedad Promedio (%)'},
                                 markers=True)
        st.plotly_chart(fig_cycle_hum, use_container_width=True)
        
    st.divider()
    
    # --- 3. GRÁFICOS CRONOLÓGICOS ---
    st.subheader("Evolución Cronológica (Promedio Móvil)")
    st.write("Línea de tiempo 'suavizada' de los datos.")

    df_plot = df_datos.set_index('timestamp')
    
    # Promedio Móvil de 1 Hora para suavizar picos
    df_smooth = df_plot.rolling(window='1H', min_periods=1).mean(numeric_only=True)
    df_smooth = df_smooth.reset_index() 

    gcol1, gcol2 = st.columns(2)
    with gcol1:
        fig_temp = px.line(df_smooth, x='timestamp', y='temperatura_out',
                             title='Evolución de Temperatura (Suavizada)',
                             labels={'temperatura_out': 'Temp (°C)', 'timestamp': 'Fecha y Hora'})
        fig_temp.update_traces(line=dict(color='red'))
        st.plotly_chart(fig_temp, use_container_width=True)

    with gcol2:
        fig_humedad = px.line(df_smooth, x='timestamp', y='humedad_out',
                               title='Evolución de Humedad (Suavizada)',
                               labels={'humedad_out': 'Humedad (%)', 'timestamp': 'Fecha y Hora'})
        fig_humedad.update_traces(line=dict(color='green'))
        st.plotly_chart(fig_humedad, use_container_width=True)

    # --- 4. OTRAS MÉTRICAS ---
    st.subheader("Otras Métricas Cronológicas (Suavizadas)")

    gcol3, gcol4 = st.columns(2)
    with gcol3:
        fig_radiacion = px.line(df_smooth, x='timestamp', y='radiacion_solar',
                                 title='Evolución de Radiación Solar (Suavizada)',
                                 labels={'radiacion_solar': 'Radiación (W/m²)', 'timestamp': 'Fecha y Hora'})
        fig_radiacion.update_traces(line=dict(color='orange'))
        st.plotly_chart(fig_radiacion, use_container_width=True)

    with gcol4:
        fig_viento = px.line(df_smooth, x='timestamp', y='velocidad_viento',
                             title='Evolución de Velocidad del Viento (Suavizada)',
                             labels={'velocidad_viento': 'Velocidad', 'timestamp': 'Fecha y Hora'})
        fig_viento.update_traces(line=dict(color='blue'))
        st.plotly_chart(fig_viento, use_container_width=True)
    
    st.info("Nota: La 'Dirección del Viento' (ej: 92) se registra en grados (0°=Norte, 90°=Este, 180°=Sur, 270°=Oeste).")
    
    st.divider()
    
    # --- 5. DATOS CRUDOS ---
    with st.expander("Ver Datos Crudos (Tabla)"):
        st.dataframe(df_datos, use_container_width=True)