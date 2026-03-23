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

st.markdown("<style>[data-testid='stMetricValue'] { font-size: 1.4rem !important; font-weight: 700; }</style>", unsafe_allow_html=True)

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

def detectar_mes(arquivo):
    try:
        df_scan = pd.read_excel(arquivo, nrows=10, header=None)
        for r in range(len(df_scan)):
            for celula in df_scan.iloc[r]:
                texto = str(celula).upper()
                for nome, num in MESES_MAPA.items():
                    if nome in texto: return num
    except: return None
    return None

inicializar_banco()

# --- IMPORTAÇÃO ---
with st.sidebar:
    st.subheader("📥 Importar Dados")
    tipo = st.radio("Tipo:", ["Receita", "Despesa"])
    arq = st.file_uploader("Selecionar Arquivo", type=["xlsx"])
    if arq and st.button("🚀 Processar Dados"):
        m_ref = detectar_mes(arq)
        if not m_ref: st.error("Mês não detectado."); st.stop()
        conn = sqlite3.connect(DB_NAME)
        if tipo == "Receita":
            df = pd.read_excel(arq, skiprows=7)
            dados = []
            for _, row in df.iterrows():
                cod, nat = str(row.iloc[0]).strip(), str(row.iloc[1]).strip()
                if re.match(r'^\d', cod) and len(cod) >= 11:
                    dados.append((m_ref, 2026, cod, nat, limpar_f(row.iloc[3]), limpar_f(row.iloc[6]), limpar_f(row.iloc[5])))
            conn.execute("DELETE FROM receitas WHERE mes=?", (m_ref,))
            conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?)", dados)
        else:
            df = pd.read_excel(arq, skiprows=6)
            df.columns = df.columns.str.strip().str.upper()
            # AGORA O SEGREDO: Pegamos o valor único por Natureza/Fonte para não somar as UGs repetidas
            df_limpo = df.groupby(['UO','FUNÇÃO','SUBFUNÇÃO','PROGRAMA','PAOE','NATUREZA DESPESA','FONTE']).agg({
                'ORÇADO INICIAL': 'max', 'CRÉDITO AUTORIZADO': 'max', 'EMPENHADO': 'max', 'LIQUIDADO': 'max', 'PAGO': 'max'
            }).reset_index()
            
            dados = []
            for _, row in df_limpo.iterrows():
                dados.append((m_ref, 2026, str(row['UO']), str(row['FUNÇÃO']), str(row['SUBFUNÇÃO']), str(row['PROGRAMA']), str(row['PAOE']), str(row['NATUREZA DESPESA']), str(row['FONTE']), limpar_f(row['ORÇADO INICIAL']), limpar_f(row['CRÉDITO AUTORIZADO']), limpar_f(row['EMPENHADO']), limpar_f(row['LIQUIDADO']), limpar_f(row['PAGO'])))
            conn.execute("DELETE FROM despesas WHERE mes=?", (m_ref,))
            conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
        conn.commit(); conn.close(); st.success(f"✅ {MESES_NOMES[m_ref-1]} Importado!"); st.rerun()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DROP TABLE IF EXISTS receitas"); conn.execute("DROP TABLE IF EXISTS despesas")
        conn.commit(); conn.close(); inicializar_banco(); st.rerun()

# --- CÁLCULO DEDUÇÃO ---
conn = sqlite3.connect(DB_NAME)
df_rec = pd.read_sql("SELECT * FROM receitas", conn)
df_desp_raw = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

def calcular_mensal(df):
    if df.empty: return df
    df = df.sort_values('mes')
    keys = ['funcao', 'subfuncao', 'programa', 'projeto', 'natureza', 'fonte']
    res = df.copy()
    for m in sorted(df['mes'].unique(), reverse=True):
        if m > df['mes'].min():
            for _, g in df.groupby(keys):
                at, ant = g[g['mes'] == m], g[g['mes'] < m].sort_values('mes', ascending=False).head(1)
                if not at.empty and not ant.empty:
                    for c in ['empenhado', 'liquidado', 'pago']:
                        res.loc[at.index[0], c] = max(0, at[c].values[0] - ant[c].values[0])
    return res

df_desp_mensal = calcular_mensal(df_desp_raw)

# --- VISUALIZAÇÃO ---
t1, t2 = st.tabs(["📊 Receitas", "💸 Despesas"])

with t1:
    if not df_rec.empty:
        ms_r = st.multiselect("Meses:", sorted(df_rec['mes'].unique()), default=df_rec['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1])
        df_rf = df_rec[df_rec['mes'].isin(ms_r)]
        st.metric("Total Realizado", f"R$ {df_rf['realizado'].sum():,.2f}")
        st.dataframe(df_rf[['natureza', 'realizado', 'orcado']].style.format('{:,.2f}'), use_container_width=True)

with t2:
    if not df_desp_mensal.empty:
        f1, f2, f3, f4 = st.columns(4)
        ms_d = f1.multiselect("Meses:", sorted(df_desp_mensal['mes'].unique()), default=df_desp_mensal['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1])
        ss = f2.multiselect("Subfunção:", sorted(df_desp_mensal['subfuncao'].unique()))
        ps = f3.multiselect("Programa:", sorted(df_desp_mensal['programa'].unique()))
        fts = f4.multiselect("Fonte:", sorted(df_desp_mensal['fonte'].unique()))
        
        df_f = df_desp_mensal[df_desp_mensal['mes'].isin(ms_d)]
        if ss: df_f = df_f[df_f['subfuncao'].isin(ss)]
        if ps: df_f = df_f[df_f['programa'].isin(ps)]
        if fts: df_f = df_f[df_f['fonte'].isin(fts)]
        
        if not df_f.empty:
            m_max = df_desp_raw['mes'].max()
            # Crédito: Soma o valor máximo único do último mês
            v_aut = df_desp_raw[df_desp_raw['mes'] == m_max].groupby(['funcao','subfuncao','programa','projeto','natureza','fonte'])['cred_autorizado'].max().sum()
            ve, vp = df_f['empenhado'].sum(), df_f['pago'].sum()
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Créd. Autorizado", f"R$ {v_aut:,.2f}")
            k2.metric("Empenhado", f"R$ {ve:,.2f}")
            k3.metric("Pago", f"R$ {vp:,.2f}")
            st.dataframe(df_f[['funcao', 'subfuncao', 'programa', 'projeto', 'fonte', 'natureza', 'cred_autorizado', 'empenhado', 'pago']].style.format('{:,.2f}'), use_container_width=True)
