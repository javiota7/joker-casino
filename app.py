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
CILINDRO = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23,
            10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

# --- FUNCIONES MATEMÁTICAS ---
def get_indice(n): 
    try: return CILINDRO.index(n)
    except: return 0

def get_num(i): 
    return CILINDRO[i % 37]

def calcular_distancia(ant, act):
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
def cargar_y_reparar_excel(ruta_o_archivo):
    try:
        # Forzamos motor openpyxl para leer archivos modernos
        df = pd.read_excel(ruta_o_archivo, engine='openpyxl')
        
        # Si está vacío o no tiene datos, devolvemos estructura vacía
        if df.empty: 
            return pd.DataFrame(columns=["ID", "Fecha_Hora", "Numero_Actual", "Numero_Anterior", "Distancia_Calculada"])
        
        # Limpieza de nombres de columnas (quita espacios extra)
        df.columns = [str(c).strip() for c in df.columns]
        
        # Buscamos la columna de los números (acepta 'Numero_Actual', 'Numero', 'Rotación', etc.)
        col_num = next((c for c in df.columns if "actual" in c.lower() or "numero" in c.lower()), None)
        
        if not col_num:
            return pd.DataFrame() # Falló la búsqueda de columna

        # RECONSTRUCCIÓN INTELIGENTE (JOKER):
        # Ignoramos la columna 'Numero_Anterior' del Excel porque venía con ceros.
        # Creamos la secuencia real usando solo los números que salieron.
        numeros = df[col_num].astype(int).tolist()
        
        nuevo_df = pd.DataFrame()
        nuevo_df["ID"] = range(1, len(numeros) + 1)
        nuevo_df["Fecha_Hora"] = df["Fecha_Hora"] if "Fecha_Hora" in df.columns else "HISTORICO"
        nuevo_df["Numero_Actual"] = numeros
        # El anterior es el número de la fila previa (o 0 para el primero)
        nuevo_df["Numero_Anterior"] = [0] + numeros[:-1]
        
        # Recalculamos las distancias nosotros mismos para que sean perfectas
        nuevo_df["Distancia_Calculada"] = [
            calcular_distancia(ant, act) 
            for ant, act in zip(nuevo_df["Numero_Anterior"], nuevo_df["Numero_Actual"])
        ]
        
        return nuevo_df

    except Exception:
        return pd.DataFrame() # En caso de error grave, devolvemos vacío
                # Crear IDs si no existen
                if "ID" not in df.columns: df["ID"] = range(1, len(df) + 1)
            else:
                return inicializar_dataframe()
        
        return df
    except Exception as e:
        st.error(f"Error al cargar archivo: {e}")
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
    
    # Guardar en disco
    try:
        st.session_state.df_historico.to_excel(NOMBRE_ARCHIVO, index=False)
    except Exception as e:
        st.warning(f"No se pudo guardar en disco (pero sí en memoria): {e}")

def obtener_top_movimientos(distancias_series, peso_reciente):
    """Analiza las distancias usando el DataFrame completo."""
    if distancias_series.empty: return []
    
    # Convertir a lista limpia
    distancias = distancias_series.dropna().astype(int).tolist()
    # Filtramos la primera (que suele ser 0 o NaN al inicio de sesión) si es ruido
    if len(distancias) > 0 and distancias[0] == 0: distancias.pop(0) 
    
    if not distancias: return []

    ventana = 30
    conteo = Counter()
    
    # Pesado temporal
    if len(distancias) <= ventana:
        conteo.update(distancias)
    else:
        conteo.update(distancias[:-ventana])
        # Los últimos tienen más peso si peso_reciente > 1
        for d in distancias[-ventana:]:
            conteo[d] += peso_reciente

    lista = conteo.most_common()
    if not lista: return []
    
    # Seleccionar top 1 y top 2 (que no esté pegado al top 1)
    m1 = lista[0][0]
    tops = [(m1, lista[0][1])]
    
    # Buscar el segundo mejor que tenga una diferencia mínima de 3 posiciones en el cilindro
    m2 = next(((m, f) for m, f in lista[1:] if abs(m - m1) >= 3), None)
    if m2: tops.append(m2)
    
    return tops

# --- ESTADO DE SESIÓN ---
if 'inicializado' not in st.session_state:
    st.session_state.df_historico = inicializar_dataframe()
    # Intentar cargar si existe archivo local
    if os.path.exists(NOMBRE_ARCHIVO):
        st.session_state.df_historico = cargar_y_reparar_excel(NOMBRE_ARCHIVO)
    
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

# --- TAB CONFIGURACIÓN (SIDEBAR MOVIDO AQUÍ O LATERAL) ---
with st.sidebar:
    st.header("Control de Banca")
    input_bank = st.number_input("Capital Inicial (€)", value=200.0, step=10.0, min_value=1.0)
    
    st.divider()
    st.write("📂 **Gestión de Archivos**")
    
    uploaded_file = st.file_uploader("Cargar Excel Histórico", type=["xlsx"])
    if uploaded_file:
        try:
            df_subido = cargar_y_reparar_excel(uploaded_file)
            st.session_state.df_historico = df_subido
            df_subido.to_excel(NOMBRE_ARCHIVO, index=False)
            st.success(f"✅ Historial importado: {len(df_subido)} registros")
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

    if st.button("🗑️ RESETEAR TODO"):
        if os.path.exists(NOMBRE_ARCHIVO): os.remove(NOMBRE_ARCHIVO)
        st.session_state.clear()
        st.rerun()
        
    # Botón de descarga siempre disponible
    if not st.session_state.df_historico.empty:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            st.session_state.df_historico.to_excel(writer, index=False)
        st.download_button("📥 Descargar Excel", buffer.getvalue(), "joker_data.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

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
        st.write("Introduce los últimos números (separados por espacio):")
        txt_calib = st.text_input("Ej: 32 15 19 4", key="input_calib")
        
        if st.button("Sincronizar", use_container_width=True):
            lista = [int(x) for x in txt_calib.replace(',', ' ').split() if x.isdigit()]
            if lista:
                # Si hay más de 1 número, guardamos el historial para tener datos base
                if len(lista) > 1:
                    # Limpiamos df actual para empezar sesión limpia o añadimos?
                    # Mejor añadimos para tener contexto
                    for i in range(1, len(lista)):
                        guardar_tirada(lista[i-1], lista[i])
                
                st.session_state.u_num = lista[-1]
                st.session_state.calibrado = True
                st.rerun()

else:
    # --- BUCLE PRINCIPAL DE JUEGO ---
    
    # 1. Cálculos de Economía
    # Validación de ficha segura
    base_ficha = st.session_state.bank_inicial / 10 / 12 # Estrategia original
    ficha = math.floor(base_ficha * 100) / 100
    if ficha < 0.10: ficha = 0.10 # Mínimo de mesa común
    
    # Estado de la sesión
    perdida_actual = st.session_state.bank_inicial - st.session_state.bank
    porcentaje_perdida = (perdida_actual / st.session_state.bank_inicial) * 100 if st.session_state.bank_inicial > 0 else 0
    spins_sesion = len(st.session_state.historial_bank) - 1

    # Lógica de Modo Rescate (Hysteresis)
    MIN_SPINS = 15
    RIESGO_TRIGGER = 35.0 # %
    
    if st.session_state.modo_rescate_activo:
        peso = 5 # Modo agresivo en detección de tendencias
        if st.session_state.bank >= st.session_state.bank_inicial:
            st.session_state.modo_rescate_activo = False
    else:
        peso = 1
        if spins_sesion > MIN_SPINS and porcentaje_perdida >= RIESGO_TRIGGER:
            st.session_state.modo_rescate_activo = True

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
                nuevo_num = st.number_input(f"Último número ({st.session_state.u_num}) -> Nuevo:", min_value=0, max_value=36, step=1)
            with c_btn:
                st.write("") # Espaciador
                jugada_hecha = st.form_submit_button("GIRA LA BOLA 🎱", use_container_width=True)

        if jugada_hecha:
            # A. Procesar Resultado Anterior
            nums_apostados = st.session_state.apuesta_actual
            coste_apuesta = len(nums_apostados) * ficha
            
            ganancia = 0
            if nums_apostados:
                st.session_state.bank -= coste_apuesta
                if nuevo_num in nums_apostados:
                    ganancia = ficha * 36
                    st.session_state.bank += ganancia
                    st.toast(f"¡GANASTE {ganancia:.2f}€!", icon="🤑")
                else:
                    st.toast("Fallo", icon="❌")
            
            # B. Guardar Datos
            guardar_tirada(st.session_state.u_num, nuevo_num)
            st.session_state.historial_bank.append(st.session_state.bank)
            st.session_state.u_num = nuevo_num
            
            # C. Limpiar predicción anterior para forzar recálculo visual
            st.rerun()

        # 3. Lógica de Predicción (Se ejecuta siempre tras el rerun)
        if st.session_state.u_num is not None:
            # Usar el DataFrame limpio para buscar tendencias
            tops = obtener_top_movimientos(st.session_state.df_historico["Distancia_Calculada"], peso)
            
            # --- AQUÍ INTEGRAMOS TU LÓGICA DE VISUALIZACIÓN ---
            if tops:
                st.write("---")
                st.markdown("### 🎯 DESPLAZAMIENTOS A APOSTAR")
                
                desplazamientos_a_apostar = []
                
                col_info, col_resumen = st.columns([2, 1])
                
                with col_info:
                    for i, (mov, freq) in enumerate(tops):
                        vecinos = [mov-1, mov, mov+1]
                        desplazamientos_a_apostar.extend(vecinos)
                        tag = "🔥 (Tendencia Fuerte)" if i == 0 and peso > 1 else ""
                        
                        st.markdown(f"**Tendencia {i+1}** (Salto de {mov}) {tag}")
                        st.caption(f"Apostar desplazamientos: {vecinos[0]}, {vecinos[1]}, {vecinos[2]}")
                        
                        # Mostrar números para referencia
                        idx = get_indice(st.session_state.u_num)
                        numeros_tendencia = []
                        for v in vecinos:
                            if v != 0: # Evitamos el propio número si el desplazamiento es 0
                                # Normalizamos v para visualizar
                                n_pos = get_num(idx + v)
                                n_neg = get_num(idx - v)
                                numeros_tendencia.extend([n_pos, n_neg])
                        
                        st.text(f"Números cubiertos: {sorted(list(set(numeros_tendencia)))}")
                
                # Calcular números finales únicos para la apuesta interna
                apuesta_nums_final = []
                idx_base = get_indice(st.session_state.u_num)
                
                # Desplazamientos únicos positivos (para la lógica interna del sistema)
                desp_unicos = sorted(list(set([d for d in desplazamientos_a_apostar])))
                
                for d in desp_unicos:
                    if d == 0: continue # Ignorar desplazamiento 0 puro en apuesta salvo que sea estrategia
                    apuesta_nums_final.append(get_num(idx_base + d))
                    apuesta_nums_final.append(get_num(idx_base - d))
                
                # Guardar en estado para la siguiente validación
                apuesta_nums_final = sorted(list(set(apuesta_nums_final)))
                st.session_state.apuesta_actual = apuesta_nums_final

                with col_resumen:
                    st.success(f"**APUESTA ACTIVA**")
                    st.write(f"Números: **{len(apuesta_nums_final)}**")
                    st.write(f"Coste: **{(len(apuesta_nums_final)*ficha):.2f}€**")
                    st.info(f"""
                    **Instrucción Rápida:**
                    Último: **{st.session_state.u_num}**
                    Aplica desplazamientos:
                    {desp_unicos}
                    """)

            else:
                st.warning("Recopilando datos para detectar tendencias...")
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
                    # Filtramos ceros o nulos visualmente
                    data_dist = st.session_state.df_historico["Distancia_Calculada"]
                    data_dist = data_dist[data_dist != 0] 
                    conteo_dist = data_dist.value_counts().sort_index()
                    st.bar_chart(conteo_dist)
            
            st.subheader("📋 Raw Data")
            st.dataframe(st.session_state.df_historico.sort_values(by="ID", ascending=False).head(50), use_container_width=True)
        else:
            st.info("Juega bolas para ver estadísticas.")



