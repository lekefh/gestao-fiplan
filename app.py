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
    if isinstance(v, str): v = str(v).replace('.', '').replace(',', '.')
    try: return float(v)
    except: return 0.0

def detectar_mes_fiplan(arquivo):
    try:
        # Lê as primeiras 10 linhas para procurar o texto do mês
        df_topo = pd.read_excel(arquivo, nrows=10, header=None)
        # O FIP 616 costuma ter o mês na linha 6 (índice 5)
        for celula in df_topo.iloc[5]: 
            texto = str(celula).upper()
            for nome_mes, num_mes in MESES_MAPA.items():
                if nome_mes in texto:
                    return num_mes
    except:
        return None
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
        # Lógica de detecção automática
        mes_auto = detectar_mes_fiplan(arquivo)
        mes_final = mes_auto if mes_auto else mes_manual
        
        conn = sqlite3.connect(DB_NAME)
        try:
            if tipo_dado == "Receita":
                df = pd.read_excel(arquivo, skiprows=7)
                dados = []
                for _, row in df.iterrows():
                    cod, nat = str(row.iloc[0]).strip(), str(row.iloc[1]).strip()
                    if re.match(r'^\d', cod) and not cod.endswith('.0') and len(cod) >= 13:
                        dados.append((mes_final, ano_ref, cod, nat, limpar_f(row.iloc[3]), limpar_f(row.iloc[6]), limpar_f(row.iloc[5])))
                conn.execute("DELETE FROM receitas WHERE mes=? AND ano=?", (mes_final, ano_ref))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?)", dados)
            else:
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
            st.success(f"✅ Sucesso! Mês Identificado: {MESES_NOMES[mes_final-1]}")
            st.rerun()
        except Exception as e: st.error(f"Erro: {e}")
        finally: conn.close()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DROP TABLE IF EXISTS receitas"); conn.execute("DROP TABLE IF EXISTS despesas")
        conn.commit(); conn.close(); inicializar_banco(); st.rerun()

# --- CÁLCULO INCREMENTAL ---
def calcular_incremental(df, colunas_acumuladas):
    if df.empty: return df
    df = df.sort_values(by=['mes'])
    chaves = ['uo', 'funcao', 'subfuncao', 'programa', 'projeto', 'natureza', 'fonte'] if 'uo' in df.columns else ['codigo_full']
    df_res = df.copy()
    for mes in sorted(df['mes'].unique()):
        if mes > df['mes'].min():
            for _, grupo in df.groupby(chaves):
                val_atual = grupo[grupo['mes'] == mes]
                val_anterior = grupo[grupo['mes'] < mes].sort_values('mes', ascending=False).head(1)
                if not val_atual.empty and not val_anterior.empty:
                    idx = val_atual.index[0]
                    for col in colunas_acumuladas:
                        df_res.at[idx, col] = max(0, val_atual[col].values[0] - val_anterior[col].values[0])
    return df_res

conn = sqlite3.connect(DB_NAME)
df_rec_raw = pd.read_sql("SELECT * FROM receitas", conn)
df_desp_raw = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

df_rec_inc = calcular_incremental(df_rec_raw, ['realizado'])
df_desp_inc = calcular_incremental(df_desp_raw, ['empenhado', 'liquidado', 'pago'])

# Inicializa variáveis para o confronto não dar NameError
v_real_rec, v_pag_d, v_emp_d = 0.0, 0.0, 0.0

tab1, tab2, tab3 = st.tabs(["📊 Receitas", "💸 Despesas", "⚖️ Confronto"])

with tab1:
    if not df_rec_inc.empty:
        c1, c2 = st.columns(2)
        anos_r = c1.multiselect("Anos:", sorted(df_rec_inc['ano'].unique()), default=df_rec_inc['ano'].unique())
        meses_r = c2.multiselect("Meses:", sorted(df_rec_inc['mes'].unique()), default=df_rec_inc['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1])
        df_rf = df_rec_inc[(df_rec_inc['ano'].isin(anos_r)) & (df_rec_inc['mes'].isin(meses_r))]
        if not df_rf.empty:
            v_real_rec = df_rf['realizado'].sum()
            st.metric("Realizado no Período", f"R$ {v_real_rec:,.2f}")
            st.dataframe(df_rf[['natureza', 'realizado', 'orcado']].style.format({
                'realizado': '{:,.2f}', 'orcado': '{:,.2f}'
            }), use_container_width=True)

with tab2:
    if not df_desp_inc.empty:
        f1, f2 = st.columns(2)
        anos_d = f1.multiselect("Anos:", sorted(df_desp_inc['ano'].unique()), default=df_desp_inc['ano'].unique(), key="ad")
        meses_d = f2.multiselect("Meses:", sorted(df_desp_inc['mes'].unique()), default=df_desp_inc['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="md")
        df_df = df_desp_inc[(df_desp_inc['ano'].isin(anos_d)) & (df_desp_inc['mes'].isin(meses_d))]
        if not df_df.empty:
            v_emp_d, v_pag_d = df_df['empenhado'].sum(), df_df['pago'].sum()
            st.metric("Pago no Período", f"R$ {v_pag_d:,.2f}")
            st.dataframe(df_df[['natureza', 'empenhado', 'pago']].style.format({
                'empenhado': '{:,.2f}', 'pago': '{:,.2f}'
            }), use_container_width=True)

with tab3:
    st.subheader("⚖️ Confronto")
    col1, col2 = st.columns(2)
    col1.metric("Receita Arrecadada", f"R$ {v_real_rec:,.2f}")
    col2.metric("Despesa Paga", f"R$ {v_pag_d:,.2f}")
    st.info(f"**Resultado Financeiro: R$ {v_real_rec - v_pag_d:,.2f}**")
