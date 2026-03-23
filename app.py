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
    arq = st.file_uploader("Arquivo XLSX", type=["xlsx"])
    if arq and st.button("🚀 Processar"):
        m_ref = detectar_mes(arq)
        if not m_ref: st.error("Mês não detectado na linha 6."); st.stop()
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
            dados = []
            for _, row in df.iterrows():
                ug = str(row.get('UG', '')).strip()
                # REGRA: Ignora UG=0 para evitar duplicar totais
                if ug != "0" and ug != "" and ug != "nan":
                    dados.append((m_ref, 2026, str(row.get('UO')), str(row.get('FUNÇÃO')), str(row.get('SUBFUNÇÃO')), str(row.get('PROGRAMA')), str(row.get('PAOE')), str(row.get('NATUREZA DESPESA')), str(row.get('FONTE')), limpar_f(row.get('ORÇADO INICIAL')), limpar_f(row.get('CRÉDITO AUTORIZADO')), limpar_f(row.get('EMPENHADO')), limpar_f(row.get('LIQUIDADO')), limpar_f(row.get('PAGO'))))
            conn.execute("DELETE FROM despesas WHERE mes=?", (m_ref,))
            conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
        conn.commit(); conn.close(); st.success(f"✅ {MESES_NOMES[m_ref-1]} Importado!"); st.rerun()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DROP TABLE IF EXISTS receitas"); conn.execute("DROP TABLE IF EXISTS despesas")
        conn.commit(); conn.close(); inicializar_banco(); st.rerun()

# --- PROCESSAMENTO ---
conn = sqlite3.connect(DB_NAME)
df_rec = pd.read_sql("SELECT * FROM receitas", conn)
df_desp_raw = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

def processar_desp(df):
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

df_desp_mensal = processar_desp(df_desp_raw)

# --- DASHBOARD ---
t1, t2 = st.tabs(["📊 Receitas", "💸 Despesas"])

with t1:
    if not df_rec.empty:
        ms_r = st.multiselect("Meses:", sorted(df_rec['mes'].unique()), default=df_rec['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1])
        df_rf = df_rec[df_rec['mes'].isin(ms_r)]
        st.metric("Receita Realizada", f"R$ {df_rf['realizado'].sum():,.2f}")
        st.plotly_chart(go.Figure(data=[go.Bar(x=df_rf['mes'].map(lambda x: MESES_NOMES[x-1]), y=df_rf['realizado'], marker_color='#2E7D32')]))

with t2:
    if not df_desp_mensal.empty:
        f1, f2, f3 = st.columns(3)
        ms_d = f1.multiselect("Meses:", sorted(df_desp_mensal['mes'].unique()), default=df_desp_mensal['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1])
        ps = f2.multiselect("Programa:", sorted(df_desp_mensal['programa'].unique()))
        fts = f3.multiselect("Fonte:", sorted(df_desp_mensal['fonte'].unique()))
        
        df_f = df_desp_mensal[df_desp_mensal['mes'].isin(ms_d)]
        if ps: df_f = df_f[df_f['programa'].isin(ps)]
        if fts: df_f = df_f[df_f['fonte'].isin(fts)]
        
        if not df_f.empty:
            m_max = df_desp_raw['mes'].max()
            # Lógica do Crédito: Soma o valor máximo de cada linha no último mês (evita duplicar por UG)
            v_aut = df_desp_raw[df_desp_raw['mes'] == m_max].groupby(['funcao','subfuncao','programa','projeto','natureza','fonte'])['cred_autorizado'].max().sum()
            ve, vp = df_f['empenhado'].sum(), df_f['pago'].sum()
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Créd. Autorizado (Atual)", f"R$ {v_aut:,.2f}")
            k2.metric("Empenhado (Filtro)", f"R$ {ve:,.2f}")
            k3.metric("Pago (Filtro)", f"R$ {vp:,.2f}")
            st.dataframe(df_f.style.format({'cred_autorizado': '{:,.2f}', 'empenhado': '{:,.2f}', 'pago': '{:,.2f}'}))
