import streamlit as st
import pandas as pd
import numpy as np
import os
import math
from collections import Counter
from datetime import datetime
import io # Necesario para la descarga

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Sistema Joker", page_icon="🃏", layout="centered")

# --- RUTA DEL ARCHIVO TEMPORAL ---
NOMBRE_ARCHIVO = "registro_ruleta_app.xlsx"

CILINDRO = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23,
            10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]

# --- FUNCIONES MATEMÁTICAS ---
def get_indice(n): 
    try: return CILINDRO.index(n)
    except: return 0
def get_num(i): return CILINDRO[i % 37]

def calcular_distancia(ant, act):
    idx_ant, idx_act = get_indice(ant), get_indice(act)
    distancia = idx_act - idx_ant
    if distancia > 18: distancia -= 37
    elif distancia < -18: distancia += 37
    return distancia

def calcular_z_rayleigh(distancias_lista):
    if not distancias_lista: return 0
    angulos = [d * (2 * np.pi / 37) for d in distancias_lista]
    N = len(angulos)
    X, Y = np.sum(np.cos(angulos)), np.sum(np.sin(angulos))
    R_mean = np.sqrt(X**2 + Y**2) / N
    return N * (R_mean ** 2)

def cargar_y_reparar_excel(ruta_o_archivo):
    try:
        df = pd.read_excel(ruta_o_archivo)
        if df.empty: return pd.DataFrame(columns=["ID", "Fecha_Hora", "Numero_Actual", "Numero_Anterior", "Distancia_Calculada"])
        
        if "Distancia_Calculada" not in df.columns:
            # Intentar reparar calculando distancias
            col_num = next((c for c in df.columns if "numero" in str(c).lower() or "actual" in str(c).lower()), None)
            if col_num:
                distancias = [0] + [calcular_distancia(df[col_num].iloc[i-1], df[col_num].iloc[i]) for i in range(1, len(df))]
                df["Distancia_Calculada"] = distancias
                df["Numero_Actual"] = df[col_num]
            else:
                return pd.DataFrame(columns=["ID", "Fecha_Hora", "Numero_Actual", "Numero_Anterior", "Distancia_Calculada"])
        return df
    except:
        return pd.DataFrame(columns=["ID", "Fecha_Hora", "Numero_Actual", "Numero_Anterior", "Distancia_Calculada"])

def guardar_tirada_excel(ant, act):
    if 'df_historico' in st.session_state: df = st.session_state.df_historico
    elif os.path.exists(NOMBRE_ARCHIVO): df = cargar_y_reparar_excel(NOMBRE_ARCHIVO)
    else: df = pd.DataFrame(columns=["ID", "Fecha_Hora", "Numero_Actual", "Numero_Anterior", "Distancia_Calculada"])
    
    nueva_fila = pd.DataFrame([{
        "ID": (df["ID"].max() + 1 if not df.empty else 1),
        "Fecha_Hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Numero_Actual": act,
        "Numero_Anterior": ant,
        "Distancia_Calculada": calcular_distancia(ant, act)
    }])
    df_actualizado = pd.concat([df, nueva_fila], ignore_index=True)
    df_actualizado.to_excel(NOMBRE_ARCHIVO, index=False)
    st.session_state.df_historico = df_actualizado

def obtener_top_movimientos_dinamico(distancias_historicas, peso_reciente):
    distancias_historicas = [d for d in distancias_historicas if not pd.isna(d)]
    if not distancias_historicas: return []
    ventana = 30
    conteo = Counter()
    
    if len(distancias_historicas) <= ventana: conteo.update(distancias_historicas)
    else:
        conteo.update(distancias_historicas[:-ventana])
        for d in distancias_historicas[-ventana:]: conteo[d] += peso_reciente 

    lista = conteo.most_common()
    if not lista: return []
    m1 = lista[0][0]
    tops = [(m1, lista[0][1])]
    m2 = next(((m, f) for m, f in lista[1:] if abs(m - m1) >= 3), None)
    if m2: tops.append(m2)
    return tops

# --- ESTADO DE SESIÓN ---
if 'bank' not in st.session_state: st.session_state.bank = 0.0
if 'bank_inicial' not in st.session_state: st.session_state.bank_inicial = 0.0
if 'u_num' not in st.session_state: st.session_state.u_num = None
if 'jugando' not in st.session_state: st.session_state.jugando = False
if 'calibrado' not in st.session_state: st.session_state.calibrado = False
if 'historial_sesion' not in st.session_state: st.session_state.historial_sesion = []
if 'memoria_dists' not in st.session_state: st.session_state.memoria_dists = []
if 'apuesta_actual' not in st.session_state: st.session_state.apuesta_actual = []

# --- APP ---
st.title("🃏 SISTEMA JOKER")

with st.sidebar:
    st.header("⚙️ Menú")
    input_bank = st.number_input("Capital (€)", value=200.0, step=10.0)
    
    st.write("---")
    st.write("📂 **Cargar Historial (Inicio)**")
    uploaded_file = st.file_uploader("Sube tu Excel aquí", type=["xlsx"])
    if uploaded_file:
        try:
            df_subido = cargar_y_reparar_excel(uploaded_file)
            st.session_state.df_historico = df_subido
            df_subido.to_excel(NOMBRE_ARCHIVO, index=False)
            st.success(f"✅ Cargados {len(df_subido)} datos.")
        except: pass

    st.write("---")
    st.write("💾 **Guardar Progreso (Final)**")
    
    # LÓGICA DEL BOTÓN DE DESCARGA
    # Preparamos el archivo para descargar
    df_descarga = pd.DataFrame()
    if 'df_historico' in st.session_state:
        df_descarga = st.session_state.df_historico
    elif os.path.exists(NOMBRE_ARCHIVO):
        df_descarga = cargar_y_reparar_excel(NOMBRE_ARCHIVO)
    
    if not df_descarga.empty:
        # Convertir a bytes para descargar
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_descarga.to_excel(writer, index=False)
        
        st.download_button(
            label="📥 DESCARGAR DATOS ACTUALIZADOS",
            data=buffer.getvalue(),
            file_name="historial_joker_actualizado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
    else:
        st.info("Juega para generar datos descargables.")

    st.write("---")
    # BOTÓN DE BORRADO
    if st.button("🗑️ BORRAR BASE DE DATOS"):
        if os.path.exists(NOMBRE_ARCHIVO):
            os.remove(NOMBRE_ARCHIVO)
        st.session_state.clear()
        st.rerun()

if not st.session_state.jugando:
    if st.button("▶️ COMENZAR SESIÓN", use_container_width=True):
        st.session_state.bank = input_bank
        st.session_state.bank_inicial = input_bank
        st.session_state.jugando = True
        st.rerun()

elif not st.session_state.calibrado:
    st.info("Introduce los últimos números para sincronizar.")
    txt_calib = st.text_input("Ej: 32 15 19 4 21", key="input_calib")
    if st.button("⚙️ CALIBRAR", use_container_width=True):
        lista = [int(x) for x in txt_calib.replace(',', ' ').split() if x.isdigit()]
        if lista:
            if len(lista) > 1:
                st.session_state.memoria_dists = [calcular_distancia(lista[i-1], lista[i]) for i in range(1, len(lista))]
            st.session_state.u_num = lista[-1]
            st.session_state.calibrado = True
            st.rerun()

else:
    # LÓGICA DE JUEGO
    if 'df_historico' in st.session_state: dists_excel = st.session_state.df_historico["Distancia_Calculada"].dropna().astype(int).tolist()
    elif os.path.exists(NOMBRE_ARCHIVO): 
        df = cargar_y_reparar_excel(NOMBRE_ARCHIVO)
        dists_excel = df["Distancia_Calculada"].dropna().astype(int).tolist() if "Distancia_Calculada" in df.columns else []
    else: dists_excel = []

    todas_dists = dists_excel + st.session_state.memoria_dists
    ficha = math.floor((st.session_state.bank_inicial / 10 / 12) * 100) / 100
    
    # Métricas
    c1, c2 = st.columns(2)
    c1.metric("Saldo", f"{st.session_state.bank:.2f}€", delta=f"{st.session_state.bank - st.session_state.bank_inicial:.2f}€")
    c2.metric("Ficha", f"{ficha:.2f}€")
    
    # Modos
    if len(todas_dists) < 15:
        peso = 1
        st.caption(f"❄️ Calentando ({len(todas_dists)} datos)")
    elif st.session_state.bank < st.session_state.bank_inicial:
        peso = 5
        st.error("🔥 MODO RESCATE (x5)")
    else:
        peso = 1
        st.success("🛳️ MODO CRUCERO")

    # Input
    st.write("---")
    with st.form("tirada_form", clear_on_submit=True):
        col_in, col_btn = st.columns([2, 1])
        with col_in:
            nuevo = st.number_input(f"Tras el {st.session_state.u_num} salió:", min_value=0, max_value=36)
        with col_btn:
            st.write("")
            enviado = st.form_submit_button("🎲 JUGAR")
    
    if enviado:
        st.session_state.bank -= (ficha * 12)
        if nuevo in st.session_state.apuesta_actual:
            st.session_state.bank += (ficha * 36)
            st.toast("🤑 ¡ACIERTO!", icon="💰")
        else:
            st.toast("❌ Fallo", icon="📉")
        
        guardar_tirada_excel(st.session_state.u_num, nuevo)
        st.session_state.memoria_dists.append(calcular_distancia(st.session_state.u_num, nuevo))
        st.session_state.historial_sesion.append(nuevo)
        st.session_state.u_num = nuevo
        st.rerun()

    # Predicción
    if st.session_state.u_num is not None:
        tops = obtener_top_movimientos_dinamico(todas_dists, peso)
        idx = get_indice(st.session_state.u_num)
        apuesta = []
        for t, f in tops:
            for m in [t-1, t, t+1]:
                if m > 0: apuesta.extend([get_num(idx + m), get_num(idx - m)])
        
        final = sorted(list(set(apuesta)))
        off = 2
        while len(final) < 12:
            base = tops[0][0] if tops else 0
            final.extend([get_num(idx + base + off), get_num(idx - base - off)])
            final = list(set(final))
            off += 1
            
        st.session_state.apuesta_actual = sorted(final)[:12]
        
        st.subheader("🔮 JUGAR:")
        st.code(str(sorted(final)[:12]))
        
        if tops:
            st.caption(f"Tendencia: Salto de {tops[0][0]} huecos")
            
    if st.session_state.historial_sesion:
        with st.expander("Historial"): st.write(st.session_state.historial_sesion[::-1])
