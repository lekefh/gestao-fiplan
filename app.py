import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re

# --- CONFIGURAÇÃO ---
DB_NAME = 'dados_gestao_integrada.db'
st.set_page_config(page_title="Gestão Integrada FIPLAN", layout="wide")
MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
MESES_MAPA = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARÇO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6,
    "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12
}

# CSS: Letras menores nos KPIs
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; font-weight: 700; }
    [data-testid="stMetricLabel"] { font-size: 0.85rem !important; }
    </style>
    """, unsafe_allow_html=True)

def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS receitas 
        (mes INTEGER, ano INTEGER, codigo_full TEXT, natureza TEXT, 
        orcado REAL, realizado REAL, previsao REAL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS despesas 
        (mes INTEGER, ano INTEGER, uo TEXT, funcao TEXT, subfuncao TEXT, 
        programa TEXT, projeto TEXT, natureza TEXT, fonte TEXT,
        orcado_inicial REAL, cred_autorizado REAL, empenhado REAL, liquidado REAL, pago REAL)''')
    conn.close()

def limpar_f(v):
    if pd.isna(v) or v == "" or v == "-": return 0.0
    v = str(v).replace('.', '').replace(',', '.')
    try: return float(v)
    except: return 0.0

def detectar_mes_na_linha_6(arquivo):
    """Varre especificamente a linha 6 do Excel para achar o mês"""
    try:
        # Lê apenas as 10 primeiras linhas para busca
        df_topo = pd.read_excel(arquivo, nrows=10, header=None)
        # O FIP 616 tem o mês na linha 6 (índice 5 do pandas)
        linha_6 = df_topo.iloc[5].astype(str).str.upper()
        for conteudo in linha_6:
            for nome_mes, num_mes in MESES_MAPA.items():
                if nome_mes in conteudo:
                    return num_mes
    except Exception as e:
        st.sidebar.error(f"Erro na detecção: {e}")
    return None

inicializar_banco()

# --- SIDEBAR: IMPORTAÇÃO ---
with st.sidebar:
    st.header("📥 Importar Dados")
    tipo_dado = st.radio("Tipo de Arquivo:", ["Receita", "Despesa"])
    arquivo = st.file_uploader(f"Selecionar {tipo_dado}", type=["xlsx"])
    mes_manual = st.selectbox("Mês (Caso a detecção falhe)", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano", value=2026)
    
    if arquivo and st.button("🚀 Processar Arquivo"):
        # 1. Tenta detectar o mês automaticamente
        mes_detectado = detectar_mes_na_linha_6(arquivo)
        mes_final = mes_detectado if mes_detectado else mes_manual
        
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
                # FIP 616 - Despesa
                df = pd.read_excel(arquivo, skiprows=6)
                df.columns = df.columns.str.strip().str.upper()
                dados = []
                for _, row in df.iterrows():
                    uo = str(row.get('UO', '')).strip()
                    if uo != "" and uo != "nan":
                        dados.append((mes_final, ano_ref, uo, str(row.get('FUNÇÃO', '')), str(row.get('SUBFUNÇÃO', '')), 
                                     str(row.get('PROGRAMA', '')), str(row.get('PAOE', '')), 
                                     str(row.get('NATUREZA DESPESA', '')), str(row.get('FONTE', '')),
                                     limpar_f(row.get('ORÇADO INICIAL', 0)), limpar_f(row.get('CRÉDITO AUTORIZADO', 0)), 
                                     limpar_f(row.get('EMPENHADO', 0)), limpar_f(row.get('LIQUIDADO', 0)), limpar_f(row.get('PAGO', 0))))
                conn.execute("DELETE FROM despesas WHERE mes=? AND ano=?", (mes_final, ano_ref))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
            conn.commit()
            st.success(f"✅ Sucesso! Mês {MESES_NOMES[mes_final-1]} importado.")
            st.rerun()
        except Exception as e:
            st.error(f"Erro no processamento: {e}")
        finally:
            conn.close()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DROP TABLE IF EXISTS receitas"); conn.execute("DROP TABLE IF EXISTS despesas")
        conn.commit(); conn.close(); inicializar_banco(); st.rerun()

# --- CARGA SIMPLES (Sem deduções por enquanto) ---
conn = sqlite3.connect(DB_NAME)
df_rec = pd.read_sql("SELECT * FROM receitas", conn)
df_desp = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

tab1, tab2 = st.tabs(["📊 Receitas", "💸 Despesas"])

with tab1:
    if not df_rec.empty:
        mr = st.multiselect("Filtrar Meses:", sorted(df_rec['mes'].unique()), default=df_rec['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1])
        df_f = df_rec[df_rec['mes'].isin(mr)]
        st.metric("Total Realizado", f"R$ {df_f['realizado'].sum():,.2f}")
        st.dataframe(df_f, use_container_width=True)

with tab2:
    if not df_desp.empty:
        md = st.multiselect("Filtrar Meses:", sorted(df_desp['mes'].unique()), default=df_desp['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="md_desp")
        # Filtros básicos restaurados
        f3, f4, f5, f6 = st.columns(4)
        fs = f3.multiselect("Função:", sorted(df_desp['funcao'].unique()))
        ss = f4.multiselect("Subfunção:", sorted(df_desp['subfuncao'].unique()))
        ps = f5.multiselect("Programa:", sorted(df_desp['programa'].unique()))
        ns = f6.multiselect("Natureza:", sorted(df_desp['natureza'].unique()))
        
        df_d_f = df_desp[df_desp['mes'].isin(md)]
        if fs: df_d_f = df_d_f[df_d_f['funcao'].isin(fs)]
        if ss: df_d_f = df_d_f[df_d_f['subfuncao'].isin(ss)]
        if ps: df_d_f = df_d_f[df_d_f['programa'].isin(ps)]
        if ns: df_d_f = df_d_f[df_d_f['natureza'].isin(ns)]
        
        st.metric("Total Empenhado", f"R$ {df_d_f['empenhado'].sum():,.2f}")
        st.dataframe(df_d_f, use_container_width=True)
