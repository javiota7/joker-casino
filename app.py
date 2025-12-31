import streamlit as st
import pandas as pd
import numpy as np
import os
import math
from collections import Counter
from datetime import datetime
import io

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Sistema Joker Pro", page_icon="🃏", layout="wide")

# --- CONSTANTES Y RUTA ---
NOMBRE_ARCHIVO = "registro_ruleta_app.xlsx"
# Cilindro Europeo Estándar
CILINDRO = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23,
            10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

# --- FUNCIONES MATEMÁTICAS ---
def get_indice(n): 
    try: return CILINDRO.index(n)
    except: return 0

def get_num(i): 
    return CILINDRO[i % 37]

def calcular_distancia(ant, act):
    """Calcula el camino más corto en el cilindro."""
    idx_ant, idx_act = get_indice(ant), get_indice(act)
    distancia = idx_act - idx_ant
    if distancia > 18: distancia -= 37
    elif distancia < -18: distancia += 37
    return distancia

# --- GESTIÓN DE DATOS ---
def inicializar_dataframe():
    """Crea una estructura de DataFrame vacía pero con tipos correctos."""
    return pd.DataFrame(columns=["ID", "Fecha_Hora", "Numero_Actual", "Numero_Anterior", "Distancia_Calculada"])

# EXCEL CARGA
def cargar_y_reparar_excel(file_buffer):
    try:
        # INTENTO 1: Leer como Excel
        try:
            df = pd.read_excel(file_buffer, engine='openpyxl')
        except:
            # INTENTO 2: Si falla, leer como CSV
            file_buffer.seek(0)
            df = pd.read_csv(file_buffer, sep=None, engine='python')

        if df.empty: return inicializar_dataframe()
        
        # Limpieza básica de columnas
        df.columns = [str(c).strip() for c in df.columns]
        
        # Buscar columna de números
        col_num = next((c for c in df.columns if "actual" in c.lower() or "numero" in c.lower() or c.lower() == "n"), None)
        if not col_num: return pd.DataFrame()

        # Reconstrucción Joker
        if "ID" in df.columns: df = df.sort_values(by="ID", ascending=True)
        numeros = df[col_num].fillna(0).astype(int).tolist()
        
        nuevo_df = pd.DataFrame()
        nuevo_df["ID"] = range(1, len(numeros) + 1)
        nuevo_df["Fecha_Hora"] = df["Fecha_Hora"] if "Fecha_Hora" in df.columns else "HISTORICO"
        nuevo_df["Numero_Actual"] = numeros
        nuevo_df["Numero_Anterior"] = [0] + numeros[:-1]
        
        # Recalcular distancias
        nuevo_df["Distancia_Calculada"] = [
            calcular_distancia(ant, act) 
            for ant, act in zip(nuevo_df["Numero_Anterior"], nuevo_df["Numero_Actual"])
        ]
        return nuevo_df

    except Exception:
        return inicializar_dataframe()

def guardar_tirada(ant, act):
    # Usar el estado de sesión como fuente de verdad
    df = st.session_state.df_historico
    
    nuevo_id = (df["ID"].max() + 1) if not df.empty else 1
    nueva_fila = pd.DataFrame([{
        "ID": int(nuevo_id),
        "Fecha_Hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Numero_Actual": int(act),
        "Numero_Anterior": int(ant),
        "Distancia_Calculada": int(calcular_distancia(ant, act))
    }])
    
    # Concatenar y actualizar estado
    st.session_state.df_historico = pd.concat([df, nueva_fila], ignore_index=True)
    
    # Intentar guardar en disco (Solo funciona en local)
    try:
        st.session_state.df_historico.to_excel(NOMBRE_ARCHIVO, index=False)
    except Exception:
        pass # Ignoramos errores de escritura silenciosamente

def obtener_top_movimientos(distancias_series, peso_reciente):
    """Analiza las distancias usando el DataFrame completo."""
    if distancias_series.empty: return []
    
    # Convertir a lista limpia
    distancias = distancias_series.dropna().astype(int).tolist()
    # Filtramos la primera (que suele ser 0 o NaN al inicio de sesión)
    if len(distancias) > 0 and distancias[0] == 0: distancias.pop(0) 
    
    if not distancias: return []

    ventana = 30
    conteo = Counter()
    
    # Pesado temporal
    datos_a_analizar = distancias
    if len(distancias) > ventana:
        datos_a_analizar = distancias[-ventana:] # Solo los últimos X
    
    for i, d in enumerate(datos_a_analizar):
        peso = 1
        # Si estamos en los últimos 5, aplicamos el peso extra
        if i >= len(datos_a_analizar) - 5: 
            peso = peso_reciente
        conteo[d] += peso

    lista = conteo.most_common()
    if not lista: return []
    
    # Seleccionar top 1 y top 2 (que no esté pegado al top 1)
    m1 = lista[0][0]
    tops = [(m1, lista[0][1])]
    
    # Buscar el segundo mejor que tenga una diferencia mínima de 3 posiciones
    m2 = next(((m, f) for m, f in lista[1:] if abs(m - m1) >= 3), None)
    if m2: tops.append(m2)
    
    return tops

# --- ESTADO DE SESIÓN ---
if 'inicializado' not in st.session_state:
    st.session_state.df_historico = inicializar_dataframe()
    # Intentar cargar si existe archivo local
    if os.path.exists(NOMBRE_ARCHIVO):
        try:
            st.session_state.df_historico = cargar_y_reparar_excel(NOMBRE_ARCHIVO)
        except:
            pass
    
    st.session_state.bank = 0.0
    st.session_state.bank_inicial = 0.0
    st.session_state.historial_bank = [] # Para gráfica
    st.session_state.u_num = None
    st.session_state.jugando = False
    st.session_state.calibrado = False
    st.session_state.apuesta_actual = [] # Lista de números
    st.session_state.modo_rescate_activo = False
    st.session_state.inicializado = True

# --- INTERFAZ ---
st.title("🃏 SISTEMA JOKER: ANÁLISIS DE DESPLAZAMIENTO")

# PESTAÑAS PRINCIPALES
tab_juego, tab_stats, tab_config = st.tabs(["🎲 Sala de Juego", "📊 Estadísticas Avanzadas", "⚙️ Configuración"])

# --- SIDEBAR (CONFIGURACIÓN) ---
with st.sidebar:
    st.header("Control de Banca")
    input_bank = st.number_input("Capital Inicial (€)", value=200.0, step=10.0, min_value=1.0)
    
    st.divider()
    st.write("📂 **Gestión de Archivos**")
    
 uploaded_file = st.file_uploader("Cargar Excel Histórico", type=["xlsx", "csv"])
    if uploaded_file:
        try:
            df_subido = cargar_y_reparar_excel(uploaded_file)
            if not df_subido.empty:
                # 1. Cargar Histórico
                st.session_state.df_historico = df_subido
                
                # 2. Sincronizar Último Número
                ultimo_numero = df_subido.iloc[-1]["Numero_Actual"]
                st.session_state.u_num = int(ultimo_numero)
                
                # 3. ACTIVACIÓN AUTOMÁTICA (El truco del Joker)
                st.session_state.bank = input_bank
                st.session_state.bank_inicial = input_bank
                st.session_state.historial_bank = [input_bank]
                st.session_state.calibrado = True
                st.session_state.jugando = True  # <--- ESTO ES LO QUE TE FALTABA
                
                # 4. Guardar Backup
                try: df_subido.to_excel(NOMBRE_ARCHIVO, index=False)
                except: pass
                
                st.success(f"✅ ¡SISTEMA INICIADO! Último: {ultimo_numero}")
                st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

    if st.button("🗑️ RESETEAR TODO"):
        if os.path.exists(NOMBRE_ARCHIVO):
            try: os.remove(NOMBRE_ARCHIVO)
            except: pass
        st.session_state.clear()
        st.rerun()

    st.divider()
    
    # --- BOTÓN DE GUARDADO (Corregido y Unificado) ---
    if not st.session_state.df_historico.empty:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            st.session_state.df_historico.to_excel(writer, index=False)
            
        st.download_button(
            label="💾 GUARDAR SESIÓN (Descargar Excel)",
            data=buffer.getvalue(),
            file_name=f"joker_registro_{datetime.now().strftime('%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# --- LÓGICA DE INICIO ---
if not st.session_state.jugando:
    with tab_juego:
        st.info("Configura tu banca en el menú lateral y pulsa comenzar.")
        if st.button("▶️ INICIAR SESIÓN", use_container_width=True):
            st.session_state.bank = input_bank
            st.session_state.bank_inicial = input_bank
            st.session_state.historial_bank = [input_bank]
            st.session_state.jugando = True
            st.rerun()

elif not st.session_state.calibrado:
    with tab_juego:
        st.warning("⚠️ El sistema necesita sincronizarse con la ruleta.")
        st.write("Introduce los últimos números (separados por espacio) para calibrar:")
        txt_calib = st.text_input("Ej: 32 15 19 4", key="input_calib")
        
        if st.button("Sincronizar", use_container_width=True):
            # Limpieza de input más robusta
            lista = [int(x) for x in txt_calib.replace(',', ' ').split() if x.isdigit()]
            
            if lista:
                # Guardamos historial de calibración
                if len(lista) > 1:
                    for i in range(1, len(lista)):
                        guardar_tirada(lista[i-1], lista[i])
                
                st.session_state.u_num = lista[-1]
                st.session_state.calibrado = True
                st.rerun()
else:
            
  # --- BUCLE PRINCIPAL DE JUEGO ---
    with tab_juego:
        # 1. Cálculos de Economía
        # Validación de ficha segura (Bank / 120 = muy conservador, perfecto para aguantar rachas)
        base_ficha = st.session_state.bank_inicial / 10 / 12 
        ficha = math.floor(base_ficha * 100) / 100
        if ficha < 0.10: ficha = 0.10 # Mínimo de mesa común
        
        # Estado de la sesión
        perdida_actual = st.session_state.bank_inicial - st.session_state.bank
        porcentaje_perdida = (perdida_actual / st.session_state.bank_inicial) * 100 if st.session_state.bank_inicial > 0 else 0
        spins_sesion = len(st.session_state.historial_bank) - 1

        # Lógica de Modo Rescate (Trigger al perder 35% tras 15 tiradas)
        MIN_SPINS = 15
        RIESGO_TRIGGER = 35.0 # %
        
        if st.session_state.modo_rescate_activo:
            peso = 5 # Modo agresivo: Mira más el corto plazo
            st.error("🚨 MODO RESCATE ACTIVO: Buscando patrones calientes agresivos")
            # Si recuperamos la banca inicial, salimos del modo rescate
            if st.session_state.bank >= st.session_state.bank_inicial:
                st.session_state.modo_rescate_activo = False
                st.success("✅ BANCA RECUPERADA: Volviendo a modo normal")
        else:
            peso = 1 # Modo normal: Análisis equilibrado
            # Entrar en pánico si llevamos tiempo jugando y perdemos mucho
            if spins_sesion > MIN_SPINS and porcentaje_perdida >= RIESGO_TRIGGER:
                st.session_state.modo_rescate_activo = True
                st.toast("⚠️ ALERTA: Activando Protocolo de Rescate", icon="🚨")
                        
  # 2. Interfaz de Juego (Tab Juego)
    with tab_juego:
        # Métricas superiores
        col1, col2, col3 = st.columns(3)
        col1.metric("Bankroll", f"{st.session_state.bank:.2f}€", delta=f"{st.session_state.bank - st.session_state.bank_inicial:.2f}€")
        col2.metric("Valor Ficha", f"{ficha:.2f}€")
        estado_sys = "🔥 RESCATE" if st.session_state.modo_rescate_activo else "🟢 CRUCERO"
        col3.metric("Estado Sistema", estado_sys)

        # Entrada de datos
        st.divider()
        with st.form("form_jugada", clear_on_submit=True):
            c_in, c_btn = st.columns([3, 1])
            with c_in:
                label_input = f"Último número ({st.session_state.u_num})" if st.session_state.u_num is not None else "Introduce primer número"
                nuevo_num = st.number_input(f"{label_input} -> Nuevo:", min_value=0, max_value=36, step=1)
            with c_btn:
                st.write("") # Espaciador
                jugada_hecha = st.form_submit_button("GIRA LA BOLA 🎱", use_container_width=True)

        if jugada_hecha:
            # A. Procesar Resultado Anterior
            nums_apostados = st.session_state.apuesta_actual
            coste_apuesta = len(nums_apostados) * ficha
            
            ganancia = 0
            # Solo descontamos dinero si había apuesta activa
            if nums_apostados:
                st.session_state.bank -= coste_apuesta
                if nuevo_num in nums_apostados:
                    ganancia = ficha * 36
                    st.session_state.bank += ganancia
                    st.toast(f"¡GANASTE {ganancia:.2f}€!", icon="🤑")
                else:
                    st.toast("Fallo", icon="❌")
            
            # B. Guardar Datos
            if st.session_state.u_num is not None:
                guardar_tirada(st.session_state.u_num, nuevo_num)
                st.session_state.historial_bank.append(st.session_state.bank)
            
            st.session_state.u_num = nuevo_num
            
            # C. Recargar para actualizar predicción
            st.rerun()

        # 3. Lógica de Predicción (Se ejecuta siempre tras el rerun)
        if st.session_state.u_num is not None:
            # Usar el DataFrame limpio para buscar tendencias
            tops = obtener_top_movimientos(st.session_state.df_historico["Distancia_Calculada"], peso)
            
            if tops:
                st.write("---")
                st.markdown("### 🎯 ESTRATEGIA AMBOS LADOS")
                
                apuesta_nums_final = []
                idx_base = get_indice(st.session_state.u_num)
                
                col_info, col_resumen = st.columns([2, 1])
                
                with col_info:
                    for i, (mov, freq) in enumerate(tops):
                        # Tomamos el movimiento (ej: 4) y sus vecinos (3, 4, 5)
                        vecinos_mov = [mov-1, mov, mov+1]
                        
                        st.markdown(f"**Tendencia {i+1}:** Desplazamiento de {mov} espacios")
                        st.caption(f"Cubriendo rango: {vecinos_mov} hacia IZQUIERDA y DERECHA")
                        
                        numeros_visuales = []
                        for v in vecinos_mov:
                            if v == 0: continue
                            # LADO POSITIVO (+v)
                            n_pos = get_num(idx_base + v)
                            # LADO NEGATIVO (-v)
                            n_neg = get_num(idx_base - v)
                            
                            numeros_visuales.extend([n_pos, n_neg])
                            apuesta_nums_final.extend([n_pos, n_neg])
                        
                        st.text(f"Números cubiertos: {sorted(list(set(numeros_visuales)))}")

                # Limpiamos duplicados y guardamos
                apuesta_nums_final = sorted(list(set(apuesta_nums_final)))
                st.session_state.apuesta_actual = apuesta_nums_final

                # Panel Resumen de Apuesta
                with col_resumen:
                    if apuesta_nums_final:
                        st.error("⚠️ EJECUTAR APUESTA")
                        st.metric("Total Números", len(apuesta_nums_final))
                        st.metric("Coste Fichas", f"{(len(apuesta_nums_final)*ficha):.2f}€")
                        st.caption(f"Apostar a: {str(apuesta_nums_final)}")
                    else:
                        st.info("Sin números para apostar.")

            else:
                st.info("Recopilando datos para detectar tendencias claras...")
                st.session_state.apuesta_actual = []

    # --- PESTAÑA ESTADÍSTICAS ---
    with tab_stats:
        if not st.session_state.df_historico.empty:
            st.subheader("📈 Evolución del Bankroll")
            st.line_chart(st.session_state.historial_bank)
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("📊 Frecuencia de Números")
                conteo_nums = st.session_state.df_historico["Numero_Actual"].value_counts().sort_index()
                st.bar_chart(conteo_nums)
            
            with c2:
                st.subheader("📏 Frecuencia de Distancias")
                if "Distancia_Calculada" in st.session_state.df_historico.columns:
                    # Filtramos ceros
                    data_dist = st.session_state.df_historico["Distancia_Calculada"]
                    data_dist = data_dist[data_dist != 0] 
                    conteo_dist = data_dist.value_counts().sort_index()
                    st.bar_chart(conteo_dist)
            
            st.subheader("📋 Historial Detallado")
            st.dataframe(st.session_state.df_historico.sort_values(by="ID", ascending=False).head(50), use_container_width=True)
        else:
            st.info("Juega bolas o carga un Excel para ver estadísticas.")






