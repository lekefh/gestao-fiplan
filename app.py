import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re

# --- CONFIGURAÇÃO ---
DB_NAME = 'dados_gestao_integrada.db'
st.set_page_config(page_title="Gestão Integrada FIPLAN", layout="wide")
MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
MESES_MAPA = {"JANEIRO": 1, "FEVEREIRO": 2, "MARÇO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}

st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; font-weight: 700; }
    [data-testid="stMetricLabel"] { font-size: 0.85rem !important; }
    </style>
    """, unsafe_allow_html=True)

def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS receitas (mes INTEGER, ano INTEGER, codigo_full TEXT, natureza TEXT, orcado REAL, realizado REAL, previsao REAL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS despesas (mes INTEGER, ano INTEGER, uo TEXT, funcao TEXT, subfuncao TEXT, programa TEXT, projeto TEXT, natureza TEXT, fonte TEXT, orcado_inicial REAL, cred_autorizado REAL, empenhado REAL, liquidado REAL, pago REAL)''')
    conn.close()

def limpar_f(v):
    if pd.isna(v) or v == "" or v == "-": return 0.0
    v = str(v).replace('.', '').replace(',', '.')
    try: return float(v)
    except: return 0.0

def detectar_mes_fiplan(arquivo):
    try:
        df_scan = pd.read_excel(arquivo, nrows=15, header=None)
        for r in range(len(df_scan)):
            for c in range(len(df_scan.columns)):
                celula = str(df_scan.iloc[r, c]).upper()
                if "MÊS DE REFERÊNCIA" in celula:
                    for nome_mes, num_mes in MESES_MAPA.items():
                        if nome_mes in celula: return num_mes
    except: return None
    return None

inicializar_banco()

# --- SIDEBAR: IMPORTAÇÃO ---
with st.sidebar:
    st.subheader("📥 Importar Dados")
    tipo_dado = st.radio("Tipo:", ["Receita", "Despesa"])
    arquivo = st.file_uploader(f"Arquivo {tipo_dado}", type=["xlsx"])
    mes_manual = st.selectbox("Mês (Backup)", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano", value=2026)
    
    if arquivo and st.button("🚀 Processar Dados"):
        mes_auto = detectar_mes_fiplan(arquivo)
        mes_final = mes_auto if mes_auto else mes_manual
        conn = sqlite3.connect(DB_NAME)
        try:
            if tipo_dado == "Receita":
                df = pd.read_excel(arquivo, skiprows=7)
                dados = []
                for _, row in df.iterrows():
                    cod, nat = str(row.iloc[0]).strip(), str(row.iloc[1]).strip()
                    if re.match(r'^\d', cod) and not cod.endswith('.0') and len(cod) >= 11:
                        dados.append((mes_final, ano_ref, cod, nat, limpar_f(row.iloc[3]), limpar_f(row.iloc[6]), limpar_f(row.iloc[5])))
                conn.execute("DELETE FROM receitas WHERE mes=? AND ano=?", (mes_final, ano_ref))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?)", dados)
            else:
                df = pd.read_excel(arquivo, skiprows=6)
                df.columns = df.columns.str.strip().str.upper()
                # Remove linhas de totais/vazias
                df = df[df['UO'].notna()]
                # Pega apenas valores únicos por combinação para evitar duplicidade de UGs/Subtotais
                df_clean = df.groupby(['UO','FUNÇÃO','SUBFUNÇÃO','PROGRAMA','PAOE','NATUREZA DESPESA','FONTE']).agg({
                    'ORÇADO INICIAL': 'max', 'CRÉDITO AUTORIZADO': 'max', 'EMPENHADO': 'max', 'LIQUIDADO': 'max', 'PAGO': 'max'
                }).reset_index()
                
                dados = []
                for _, row in df_clean.iterrows():
                    dados.append((mes_final, ano_ref, str(row['UO']), str(row['FUNÇÃO']), str(row['SUBFUNÇÃO']), str(row['PROGRAMA']), str(row['PAOE']), str(row['NATUREZA DESPESA']), str(row['FONTE']), row['ORÇADO INICIAL'], row['CRÉDITO AUTORIZADO'], row['EMPENHADO'], row['LIQUIDADO'], row['PAGO']))
                
                conn.execute("DELETE FROM despesas WHERE mes=? AND ano=?", (mes_final, ano_ref))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
            
            conn.commit()
            st.success(f"✅ Sucesso! Mês: {MESES_NOMES[mes_final-1]}")
            st.rerun()
        except Exception as e: st.error(f"Erro: {e}")
        finally: conn.close()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DROP TABLE IF EXISTS receitas"); conn.execute("DROP TABLE IF EXISTS despesas")
        conn.commit(); conn.close(); inicializar_banco(); st.rerun()

# --- CARGA ---
conn = sqlite3.connect(DB_NAME)
df_rec = pd.read_sql("SELECT * FROM receitas", conn)
df_desp = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

tab1, tab2 = st.tabs(["📊 Receitas", "💸 Despesas"])

with tab1:
    if not df_rec.empty:
        c1, c2, c3 = st.columns([1, 1, 2])
        ms_r = c2.multiselect("Meses:", sorted(df_rec['mes'].unique()), default=df_rec['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1])
        busca_r = c3.text_input("Natureza (Contém):", key="br")
        df_rf = df_rec[df_rec['mes'].isin(ms_r)]
        if busca_r: df_rf = df_rf[df_rf['natureza'].str.contains(busca_r, case=False, na=False)]
        
        st.metric("Total Realizado", f"R$ {df_rf['realizado'].sum():,.2f}")
        st.dataframe(df_rf[['natureza', 'realizado', 'orcado']].style.format({'realizado': '{:,.2f}', 'orcado': '{:,.2f}'}), use_container_width=True)

with tab2:
    if not df_desp.empty:
        f1, f2, f3 = st.columns(3)
        ms_d = f1.multiselect("Meses:", sorted(df_desp['mes'].unique()), default=df_desp['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="md_d")
        ps = f2.multiselect("Programa:", sorted(df_desp['programa'].unique()))
        busca_d = f3.text_input("Natureza (Contém):", key="bd")
        
        df_df = df_desp[df_desp['mes'].isin(ms_d)]
        if ps: df_df = df_df[df_df['programa'].isin(ps)]
        if busca_d: df_df = df_df[df_df['natureza'].str.contains(busca_d, case=False, na=False)]
        
        if not df_df.empty:
            ve, vp = df_df['empenhado'].sum(), df_df['pago'].sum()
            k1, k2 = st.columns(2)
            k1.metric("Total Empenhado", f"R$ {ve:,.2f}")
            k2.metric("Total Pago", f"R$ {vp:,.2f}")
            
            st.dataframe(df_df[['funcao', 'programa', 'projeto', 'fonte', 'natureza', 'cred_autorizado', 'empenhado', 'pago']].style.format({
                'cred_autorizado': '{:,.2f}', 'empenhado': '{:,.2f}', 'pago': '{:,.2f}'
            }), use_container_width=True)
