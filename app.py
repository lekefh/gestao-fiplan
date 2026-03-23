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

# --- SIDEBAR ---
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
                dados = []
                for _, row in df.iterrows():
                    uo, ug = str(row.get('UO', '')).strip(), str(row.get('UG', '')).strip()
                    if uo != "" and uo != "nan" and ug != "0" and ug != "":
                        dados.append((mes_final, ano_ref, uo, str(row.get('FUNÇÃO', '')), str(row.get('SUBFUNÇÃO', '')), str(row.get('PROGRAMA', '')), str(row.get('PAOE', '')), str(row.get('NATUREZA DESPESA', '')), str(row.get('FONTE', '')), limpar_f(row.get('ORÇADO INICIAL', 0)), limpar_f(row.get('CRÉDITO AUTORIZADO', 0)), limpar_f(row.get('EMPENHADO', 0)), limpar_f(row.get('LIQUIDADO', 0)), limpar_f(row.get('PAGO', 0))))
                conn.execute("DELETE FROM despesas WHERE mes=? AND ano=?", (mes_final, ano_ref))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
            conn.commit()
            st.success(f"✅ Importado: {MESES_NOMES[mes_final-1]}"); st.rerun()
        except Exception as e: st.error(f"Erro: {e}")
        finally: conn.close()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DROP TABLE IF EXISTS receitas"); conn.execute("DROP TABLE IF EXISTS despesas")
        conn.commit(); conn.close(); inicializar_banco(); st.rerun()

# --- LÓGICA DE DEDUÇÃO ---
conn = sqlite3.connect(DB_NAME)
df_rec_raw = pd.read_sql("SELECT * FROM receitas", conn)
df_desp_raw = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

def calcular_mensal(df, cols):
    if df.empty: return df
    df = df.sort_values(by=['mes'])
    keys = ['uo', 'funcao', 'subfuncao', 'programa', 'projeto', 'natureza', 'fonte'] if 'uo' in df.columns else ['codigo_full']
    res = df.copy()
    for m in sorted(df['mes'].unique(), reverse=True):
        if m > df['mes'].min():
            for _, g in df.groupby(keys):
                idx_at, idx_ant = g[g['mes'] == m].index, g[g['mes'] < m].sort_values('mes', ascending=False).head(1).index
                if not idx_at.empty and not idx_ant.empty:
                    for c in cols: res.loc[idx_at[0], c] = max(0, df.loc[idx_at[0], c] - df.loc[idx_ant[0], c])
    return res

df_rec = calcular_mensal(df_rec_raw, ['realizado'])
df_desp = calcular_mensal(df_desp_raw, ['empenhado', 'liquidado', 'pago'])

tab1, tab2, tab3 = st.tabs(["📊 Receitas", "💸 Despesas", "⚖️ Confronto"])

with tab2:
    if not df_desp.empty:
        # --- FILTROS RESTAURADOS ---
        f1, f2, f3 = st.columns(3)
        ms = f1.multiselect("Meses:", sorted(df_desp['mes'].unique()), default=df_desp['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1])
        fs = f2.multiselect("Função:", sorted(df_desp['funcao'].unique()))
        ss = f3.multiselect("Subfunção:", sorted(df_desp['subfuncao'].unique()))
        
        f4, f5, f6 = st.columns(3)
        ps = f4.multiselect("Programa:", sorted(df_desp['programa'].unique()))
        fts = f5.multiselect("Fonte:", sorted(df_desp['fonte'].unique()))
        ns = f6.multiselect("Natureza:", sorted(df_desp['natureza'].unique()))
        
        df_f = df_desp[df_desp['mes'].isin(ms)]
        if fs: df_f = df_f[df_f['funcao'].isin(fs)]
        if ss: df_f = df_f[df_f['subfuncao'].isin(ss)]
        if ps: df_f = df_f[df_f['programa'].isin(ps)]
        if fts: df_f = df_f[df_f['fonte'].isin(fts)]
        if ns: df_f = df_f[df_f['natureza'].isin(ns)]
        
        if not df_f.empty:
            m_max = df_desp_raw['mes'].max()
            v_aut = df_desp_raw[df_desp_raw['mes'] == m_max]['cred_autorizado'].sum()
            v_emp, v_liq, v_pag = df_f['empenhado'].sum(), df_f['liquidado'].sum(), df_f['pago'].sum()

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Créd. Autorizado (Atual)", f"R$ {v_aut:,.2f}")
            k2.metric("Empenhado (Filtro)", f"R$ {v_emp:,.2f}")
            k3.metric("Liquidado (Filtro)", f"R$ {v_liq:,.2f}")
            k4.metric("Pago (Filtro)", f"R$ {v_pag:,.2f}")

            # FORMATAÇÃO SEGURA: Apenas colunas numéricas
            st.dataframe(df_f[['funcao', 'subfuncao', 'programa', 'fonte', 'natureza', 'cred_autorizado', 'empenhado', 'liquidado', 'pago']].style.format({
                'cred_autorizado': '{:,.2f}', 'empenhado': '{:,.2f}', 'liquidado': '{:,.2f}', 'pago': '{:,.2f}'
            }), use_container_width=True)
