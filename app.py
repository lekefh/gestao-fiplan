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
    if isinstance(v, str): v = str(v).replace('.', '').replace(',', '.')
    try: return float(v)
    except: return 0.0

def detectar_mes(arquivo):
    try:
        df_topo = pd.read_excel(arquivo, nrows=10, header=None)
        for celula in df_topo.iloc[5]:
            texto = str(celula).upper()
            for nome, num in MESES_MAPA.items():
                if nome in texto: return num
    except: return None
    return None

inicializar_banco()

with st.sidebar:
    st.subheader("📥 Importar Dados")
    tipo_dado = st.radio("Tipo:", ["Receita", "Despesa"])
    arquivo = st.file_uploader(f"Arquivo {tipo_dado}", type=["xlsx"])
    mes_backup = st.selectbox("Mês (Manual)", range(1, 13), format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano", value=2026)
    
    if arquivo and st.button("🚀 Processar Dados"):
        m_auto = detectar_mes(arquivo)
        m_final = m_auto if m_auto else mes_backup
        conn = sqlite3.connect(DB_NAME)
        try:
            if tipo_dado == "Receita":
                df = pd.read_excel(arquivo, skiprows=7)
                dados = []
                for _, row in df.iterrows():
                    cod, nat = str(row.iloc[0]).strip(), str(row.iloc[1]).strip()
                    if re.match(r'^\d', cod) and not cod.endswith('.0') and len(cod) >= 13:
                        dados.append((m_final, ano_ref, cod, nat, limpar_f(row.iloc[3]), limpar_f(row.iloc[6]), limpar_f(row.iloc[5])))
                conn.execute("DELETE FROM receitas WHERE mes=? AND ano=?", (m_final, ano_ref))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?)", dados)
            else:
                df = pd.read_excel(arquivo, skiprows=6)
                df.columns = df.columns.str.strip().str.upper()
                dados = []
                for _, row in df.iterrows():
                    uo = str(row.get('UO', '')).strip()
                    if uo != "" and uo != "nan":
                        dados.append((m_final, ano_ref, uo, str(row.get('FUNÇÃO', '')), str(row.get('SUBFUNÇÃO', '')), str(row.get('PROGRAMA', '')), str(row.get('PAOE', '')), str(row.get('NATUREZA DESPESA', '')), str(row.get('FONTE', '')), limpar_f(row.get('ORÇADO INICIAL', 0)), limpar_f(row.get('CRÉDITO AUTORIZADO', 0)), limpar_f(row.get('EMPENHADO', 0)), limpar_f(row.get('LIQUIDADO', 0)), limpar_f(row.get('PAGO', 0))))
                conn.execute("DELETE FROM despesas WHERE mes=? AND ano=?", (m_final, ano_ref))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
            conn.commit()
            st.success(f"✅ Sucesso! Mês: {MESES_NOMES[m_final-1]}")
            st.rerun()
        except Exception as e: st.error(f"Erro: {e}")
        finally: conn.close()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DROP TABLE IF EXISTS receitas"); conn.execute("DROP TABLE IF EXISTS despesas")
        conn.commit(); conn.close(); inicializar_banco(); st.rerun()

# --- LÓGICA INCREMENTAL ---
def calcular_incremental(df, cols_acum):
    if df.empty: return df
    df = df.sort_values(by=['mes'])
    keys = ['uo', 'funcao', 'subfuncao', 'programa', 'projeto', 'natureza', 'fonte'] if 'uo' in df.columns else ['codigo_full']
    res = df.copy()
    for m in sorted(df['mes'].unique()):
        if m > df['mes'].min():
            for _, g in df.groupby(keys):
                at, ant = g[g['mes'] == m], g[g['mes'] < m].sort_values('mes', ascending=False).head(1)
                if not at.empty and not ant.empty:
                    for c in cols_acum: res.at[at.index[0], c] = max(0, at[c].values[0] - ant[c].values[0])
    return res

conn = sqlite3.connect(DB_NAME)
dr_inc = calcular_incremental(pd.read_sql("SELECT * FROM receitas", conn), ['realizado'])
dd_inc = calcular_incremental(pd.read_sql("SELECT * FROM despesas", conn), ['empenhado', 'liquidado', 'pago'])
conn.close()

t1, t2, t3 = st.tabs(["📊 Receitas", "💸 Despesas", "⚖️ Confronto"])

with t1:
    if not dr_inc.empty:
        c1, c2, c3 = st.columns([1,1,2])
        ar, mr = c1.multiselect("Anos:", sorted(dr_inc['ano'].unique()), default=dr_inc['ano'].unique()), c2.multiselect("Meses:", sorted(dr_inc['mes'].unique()), default=dr_inc['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1])
        nr = c3.multiselect("Filtrar Naturezas:", sorted(dr_inc['natureza'].unique()))
        df_rf = dr_inc[(dr_inc['ano'].isin(ar)) & (dr_inc['mes'].isin(mr))]
        if nr: df_rf = df_rf[df_rf['natureza'].isin(nr)]
        if not df_rf.empty:
            vr = df_rf['realizado'].sum()
            vo = df_rf[df_rf['mes'] == df_rf['mes'].max()].groupby(['ano','codigo_full'])['orcado'].last().sum()
            k1, k2, k3 = st.columns(3)
            k1.metric("Orçado", f"R$ {vo:,.2f}"); k2.metric("Realizado", f"R$ {vr:,.2f}"); k3.metric("Atingimento", f"{(vr/vo*100 if vo != 0 else 0):.1f}%")
            st.plotly_chart(go.Figure(data=[go.Bar(x=df_rf['mes'].map(lambda x: MESES_NOMES[x-1]), y=df_rf['realizado'], marker_color='#2E7D32')]), use_container_width=True)
            st.dataframe(df_rf[['natureza', 'realizado', 'orcado']].style.format({'realizado': '{:,.2f}', 'orcado': '{:,.2f}'}), use_container_width=True)

with t2:
    if not dd_inc.empty:
        f1, f2 = st.columns(2)
        ad, md = f1.multiselect("Anos:", sorted(dd_inc['ano'].unique()), default=dd_inc['ano'].unique(), key="ad"), f2.multiselect("Meses:", sorted(dd_inc['mes'].unique()), default=dd_inc['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="md")
        # FILTROS RESTAURADOS
        f3, f4, f5 = st.columns(3)
        fs = f3.multiselect("Função:", sorted(dd_inc['funcao'].unique()))
        ss = f4.multiselect("Subfunção:", sorted(dd_inc['subfuncao'].unique()))
        ps = f5.multiselect("Programa:", sorted(dd_inc['programa'].unique()))
        
        f7, f8, f9 = st.columns(3)
        pjs = f7.multiselect("Projeto/PAOE:", sorted(dd_inc['projeto'].unique()))
        fts = f8.multiselect("Fonte:", sorted(dd_inc['fonte'].unique()))
        ns = f9.multiselect("Natureza:", sorted(dd_inc['natureza'].unique()))
        
        df_df = dd_inc[(dd_inc['ano'].isin(ad)) & (dd_inc['mes'].isin(md))]
        if fs: df_df = df_df[df_df['funcao'].isin(fs)]
        if ss: df_df = df_df[df_df['subfuncao'].isin(ss)]
        if ps: df_df = df_df[df_df['programa'].isin(ps)]
        if pjs: df_df = df_df[df_df['projeto'].isin(pjs)]
        if fts: df_df = df_df[df_df['fonte'].isin(fts)]
        if ns: df_df = df_df[df_df['natureza'].isin(ns)]
        
        if not df_df.empty:
            mm = df_df['mes'].max()
            va = df_df[df_df['mes'] == mm]['cred_autorizado'].sum()
            ve, vl, vp = df_df['empenhado'].sum(), df_df['liquidado'].sum(), df_df['pago'].sum()
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Créd. Autorizado", f"R$ {va:,.2f}"); k2.metric("Empenhado", f"R$ {ve:,.2f}"); k3.metric("Liquidado", f"R$ {vl:,.2f}"); k4.metric("Pago", f"R$ {vp:,.2f}")
            fig = go.Figure(data=[go.Bar(name='Empenhado', x=['Total'], y=[ve], marker_color='#A9A9A9'), go.Bar(name='Liquidado', x=['Total'], y=[vl], marker_color='#72A0C1'), go.Bar(name='Pago', x=['Total'], y=[vp], marker_color='#2E7D32')])
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_df[['funcao', 'subfuncao', 'programa', 'projeto', 'fonte', 'natureza', 'cred_autorizado', 'empenhado', 'liquidado', 'pago']].style.format({'cred_autorizado': '{:,.2f}', 'empenhado': '{:,.2f}', 'liquidado': '{:,.2f}', 'pago': '{:,.2f}'}), use_container_width=True)

with t3:
    st.subheader("⚖️ Confronto do Período")
    try: tr, tp, te = df_rf['realizado'].sum(), df_df['pago'].sum(), df_df['empenhado'].sum()
    except: tr, tp, te = 0, 0, 0
    c1, c2 = st.columns(2)
    c1.metric("Receita Arrecadada", f"R$ {tr:,.2f}"); c2.metric("Despesa Paga", f"R$ {tp:,.2f}")
    st.info(f"**Superávit Financeiro: R$ {tr - tp:,.2f}**")
    st.warning(f"**Superávit Orçamentário: R$ {tr - te:,.2f}**")
