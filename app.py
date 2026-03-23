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
    conn.execute('''CREATE TABLE IF NOT EXISTS receitas (mes INTEGER, ano INTEGER, codigo_full TEXT, natureza TEXT, orcado REAL, realizado REAL, previsao REAL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS despesas (mes INTEGER, ano INTEGER, uo TEXT, funcao TEXT, subfuncao TEXT, programa TEXT, projeto TEXT, natureza TEXT, fonte TEXT, orcado_inicial REAL, cred_autorizado REAL, empenhado REAL, liquidado REAL, pago REAL)''')
    conn.close()

def limpar_f(v):
    if pd.isna(v) or v == "" or v == "-": return 0.0
    if isinstance(v, str): v = str(v).replace('.', '').replace(',', '.')
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
                dados = []
                for _, row in df.iterrows():
                    uo = str(row.get('UO', '')).strip()
                    ug = str(row.get('UG', '')).strip()
                    # Blindagem: Ignora subtotais (UG=0) para não duplicar valores na soma
                    if uo != "" and uo != "nan" and ug != "0" and ug != "":
                        dados.append((mes_final, ano_ref, uo, str(row.get('FUNÇÃO', '')), str(row.get('SUBFUNÇÃO', '')), 
                                     str(row.get('PROGRAMA', '')), str(row.get('PAOE', '')), 
                                     str(row.get('NATUREZA DESPESA', '')), str(row.get('FONTE', '')),
                                     limpar_f(row.get('ORÇADO INICIAL', 0)), limpar_f(row.get('CRÉDITO AUTORIZADO', 0)), 
                                     limpar_f(row.get('EMPENHADO', 0)), limpar_f(row.get('LIQUIDADO', 0)), limpar_f(row.get('PAGO', 0))))
                conn.execute("DELETE FROM despesas WHERE mes=? AND ano=?", (mes_final, ano_ref))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
            conn.commit()
            st.success(f"✅ Importado: {MESES_NOMES[mes_final-1]}")
            st.rerun()
        except Exception as e: st.error(f"Erro: {e}")
        finally: conn.close()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DROP TABLE IF EXISTS receitas"); conn.execute("DROP TABLE IF EXISTS despesas")
        conn.commit(); conn.close(); inicializar_banco(); st.rerun()

# --- CARGA E LÓGICA DE DEDUÇÃO ---
conn = sqlite3.connect(DB_NAME)
df_rec_raw = pd.read_sql("SELECT * FROM receitas", conn)
df_desp_raw = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

# Função para transformar acumulado em mensal (Dedução)
def calcular_mensal(df, colunas_valor):
    if df.empty: return df
    df = df.sort_values(by=['mes'])
    # Chave de identificação única da linha
    chaves = ['uo', 'funcao', 'subfuncao', 'programa', 'projeto', 'natureza', 'fonte'] if 'uo' in df.columns else ['codigo_full']
    df_mensal = df.copy()
    
    for mes in sorted(df['mes'].unique(), reverse=True):
        if mes > df['mes'].min():
            for _, grupo in df.groupby(chaves):
                idx_atual = grupo[grupo['mes'] == mes].index
                idx_anterior = grupo[grupo['mes'] < mes].sort_values('mes', ascending=False).head(1).index
                
                if not idx_atual.empty and not idx_anterior.empty:
                    for col in colunas_valor:
                        valor_mes = df.loc[idx_atual[0], col] - df.loc[idx_anterior[0], col]
                        df_mensal.loc[idx_atual[0], col] = max(0, valor_mes)
    return df_mensal

# Aplicando a dedução
df_rec = calcular_mensal(df_rec_raw, ['realizado'])
df_desp = calcular_mensal(df_desp_raw, ['empenhado', 'liquidado', 'pago'])

tab1, tab2, tab3 = st.tabs(["📊 Receitas", "💸 Despesas", "⚖️ Confronto"])

with tab2:
    if not df_desp.empty:
        f1, f2 = st.columns(2)
        meses_sel = f1.multiselect("Meses Selecionados:", sorted(df_desp['mes'].unique()), default=df_desp['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1])
        
        df_f = df_desp[df_desp['mes'].isin(meses_sel)]
        
        if not df_f.empty:
            # Lógica Cred. Autorizado: Pega sempre o valor do último mês disponível no banco para aquela linha
            mes_max = df_desp['mes'].max()
            v_autorizado = df_desp_raw[df_desp_raw['mes'] == mes_max]['cred_autorizado'].sum()
            
            v_emp = df_f['empenhado'].sum()
            v_liq = df_f['liquidado'].sum()
            v_pag = df_f['pago'].sum()

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Créd. Autorizado (Atual)", f"R$ {v_autorizado:,.2f}")
            k2.metric("Empenhado (No Filtro)", f"R$ {v_emp:,.2f}")
            k3.metric("Liquidado (No Filtro)", f"R$ {v_liq:,.2f}")
            k4.metric("Pago (No Filtro)", f"R$ {v_pag:,.2f}")

            st.dataframe(df_f[['natureza', 'cred_autorizado', 'empenhado', 'liquidado', 'pago']].style.format('{:,.2f}'), use_container_width=True)
