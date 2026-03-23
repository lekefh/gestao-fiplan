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

def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS receitas (mes INTEGER, ano INTEGER, codigo_full TEXT, natureza TEXT, orcado REAL, realizado REAL, previsao REAL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS despesas (mes INTEGER, ano INTEGER, uo TEXT, funcao TEXT, subfuncao TEXT, programa TEXT, projeto TEXT, natureza TEXT, fonte TEXT, orcado_inicial REAL, cred_autorizado REAL, empenhado REAL, liquidado REAL, pago REAL)''')
    conn.close()

def limpar_f(v):
    if pd.isna(v) or v == "" or v == "-": return 0.0
    if isinstance(v, (int, float)): return float(v)
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

# --- SIDEBAR: IMPORTAÇÃO ---
with st.sidebar:
    st.subheader("📥 Importar Dados")
    tipo_dado = st.radio("Tipo:", ["Receita", "Despesa"])
    arquivo = st.file_uploader(f"Arquivo {tipo_dado}", type=["xlsx"])
    if arquivo and st.button("🚀 Processar Dados"):
        m_final = detectar_mes(arquivo)
        if not m_final:
            st.error("Mês não detectado. Verifique se o arquivo é o FIP 616 original.")
            st.stop()
        conn = sqlite3.connect(DB_NAME)
        try:
            if tipo_dado == "Receita":
                df = pd.read_excel(arquivo, skiprows=7)
                dados = []
                for _, row in df.iterrows():
                    cod = str(row.iloc[0]).strip()
                    if re.match(r'^\d', cod) and len(cod) >= 11:
                        dados.append((m_final, 2026, cod, str(row.iloc[1]), limpar_f(row.iloc[3]), limpar_f(row.iloc[6]), limpar_f(row.iloc[5])))
                conn.execute("DELETE FROM receitas WHERE mes=?", (m_final,))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?)", dados)
            else:
                df = pd.read_excel(arquivo, skiprows=6)
                df.columns = df.columns.str.strip().str.upper()
                # AGORA A MÁGICA: Agrupa para remover duplicidades de subtotais antes de salvar
                df_limpo = df.groupby(['UO','FUNÇÃO','SUBFUNÇÃO','PROGRAMA','PAOE','NATUREZA DESPESA','FONTE']).agg({
                    'ORÇADO INICIAL': 'max', 'CRÉDITO AUTORIZADO': 'max', 'EMPENHADO': 'max', 'LIQUIDADO': 'max', 'PAGO': 'max'
                }).reset_index()
                
                dados = []
                for _, row in df_limpo.iterrows():
                    dados.append((m_final, 2026, str(row['UO']), str(row['FUNÇÃO']), str(row['SUBFUNÇÃO']), str(row['PROGRAMA']), str(row['PAOE']), str(row['NATUREZA DESPESA']), str(row['FONTE']), row['ORÇADO INICIAL'], row['CRÉDITO AUTORIZADO'], row['EMPENHADO'], row['LIQUIDADO'], row['PAGO']))
                conn.execute("DELETE FROM despesas WHERE mes=?", (m_final,))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
            conn.commit()
            st.success(f"✅ Sucesso! Mês {MESES_NOMES[m_final-1]} Importado.")
            st.rerun()
        except Exception as e: st.error(f"Erro: {e}")
        finally: conn.close()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DROP TABLE IF EXISTS receitas"); conn.execute("DROP TABLE IF EXISTS despesas")
        conn.commit(); conn.close(); inicializar_banco(); st.rerun()

# --- CARGA E FILTROS ---
conn = sqlite3.connect(DB_NAME)
df_rec = pd.read_sql("SELECT * FROM receitas", conn)
df_desp = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

tab1, tab2 = st.tabs(["📊 Receitas", "💸 Despesas"])

with tab1:
    if not df_rec.empty:
        ms_r = st.multiselect("Meses:", sorted(df_rec['mes'].unique()), default=df_rec['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="msr")
        df_rf = df_rec[df_rec['mes'].isin(ms_r)]
        st.metric("Total Realizado", f"R$ {df_rf['realizado'].sum():,.2f}")
        st.dataframe(df_rf[['natureza', 'realizado', 'orcado']].style.format({'realizado': '{:,.2f}', 'orcado': '{:,.2f}'}), width="stretch")

with tab2:
    if not df_desp.empty:
        col1, col2 = st.columns(2)
        ms_d = col1.multiselect("Meses Selecionados:", sorted(df_desp['mes'].unique()), default=df_desp['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="msd")
        busca = col2.text_input("Natureza (Contém):", placeholder="Ex: 3390", key="bd")
        
        df_f = df_desp[df_desp['mes'].isin(ms_d)]
        if busca: df_f = df_f[df_f['natureza'].str.contains(busca, case=False, na=False)]
        
        if not df_f.empty:
            # Lógica correta para o Crédito: Pega o último mês e não soma linhas repetidas
            m_ultima = max(ms_d)
            # Agrupamos por chave única para garantir que o crédito de 953M não triplique
            v_aut = df_desp[df_desp['mes'] == m_ultima].groupby(['uo','funcao','subfuncao','programa','projeto','natureza','fonte'])['cred_autorizado'].max().sum()
            ve, vp = df_f['empenhado'].sum(), df_f['pago'].sum()
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Créd. Autorizado (Foto Atual)", f"R$ {v_aut:,.2f}")
            k2.metric("Empenhado (No Período)", f"R$ {ve:,.2f}")
            k3.metric("Pago (No Período)", f"R$ {vp:,.2f}")
            
            # Formatação segura que não quebra a tela
            st.dataframe(df_f[['programa', 'projeto', 'natureza', 'cred_autorizado', 'empenhado', 'pago']].style.format({
                'cred_autorizado': '{:,.2f}', 'empenhado': '{:,.2f}', 'pago': '{:,.2f}'
            }), width="stretch")
