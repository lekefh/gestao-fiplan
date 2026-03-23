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
    # Remove aspas, pontos de milhar e troca vírgula por ponto
    v = str(v).replace('"', '').replace('.', '').replace(',', '.')
    try: return float(v)
    except: return 0.0

def detectar_mes(arquivo):
    try:
        df_scan = pd.read_excel(arquivo, nrows=10, header=None)
        # O FIP 729 e 616 costumam ter o mês na linha 6 (índice 5)
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
            st.error("Mês não detectado na linha 6 do arquivo.")
            st.stop()
        conn = sqlite3.connect(DB_NAME)
        try:
            if tipo_dado == "Receita":
                # FIP 729: Pula 7 linhas de cabeçalho
                df = pd.read_excel(arquivo, skiprows=7)
                dados = []
                for _, row in df.iterrows():
                    cod = str(row.iloc[0]).strip().replace('"', '')
                    # Filtra apenas linhas que começam com número (códigos de receita)
                    if re.match(r'^\d', cod):
                        dados.append((
                            m_final, 2026, cod, 
                            str(row.iloc[1]).replace('"', ''), # Natureza/Descrição
                            limpar_f(row.iloc[3]),            # Orçado Atualizado
                            limpar_f(row.iloc[6]),            # Realização NO MÊS
                            limpar_f(row.iloc[5])             # Previsão Atualizada
                        ))
                conn.execute("DELETE FROM receitas WHERE mes=?", (m_final,))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?)", dados)
            else:
                # FIP 616: Despesa
                df = pd.read_excel(arquivo, skiprows=6)
                df.columns = df.columns.str.strip().str.upper()
                df_limpo = df.groupby(['UO','FUNÇÃO','SUBFUNÇÃO','PROGRAMA','PAOE','NATUREZA DESPESA','FONTE']).agg({
                    'ORÇADO INICIAL': 'max', 'CRÉDITO AUTORIZADO': 'max', 'EMPENHADO': 'max', 'LIQUIDADO': 'max', 'PAGO': 'max'
                }).reset_index()
                dados = []
                for _, row in df_limpo.iterrows():
                    dados.append((m_final, 2026, str(row['UO']), str(row['FUNÇÃO']), str(row['SUBFUNÇÃO']), str(row['PROGRAMA']), str(row['PAOE']), str(row['NATUREZA DESPESA']), str(row['FONTE']), row['ORÇADO INICIAL'], row['CRÉDITO AUTORIZADO'], row['EMPENHADO'], row['LIQUIDADO'], row['PAGO']))
                conn.execute("DELETE FROM despesas WHERE mes=?", (m_final,))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
            
            conn.commit()
            st.success(f"✅ Sucesso! {tipo_dado} de {MESES_NOMES[m_final-1]} importada.")
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
        c1, c2 = st.columns([1, 2])
        ms_r = c1.multiselect("Meses:", sorted(df_rec['mes'].unique()), default=df_rec['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="msr")
        br = c2.text_input("Natureza (Contém):", key="br", placeholder="Ex: 1.1.1.3")
        
        df_rf = df_rec[df_rec['mes'].isin(ms_r)]
        if br: df_rf = df_rf[df_rf['natureza'].str.contains(br, case=False, na=False)]
        
        if not df_rf.empty:
            v_real = df_rf['realizado'].sum()
            # Orçado: Pega o último valor orçado para não somar orçamentos de meses diferentes
            v_orc = df_rec[df_rec['mes'] == max(ms_r)]['orcado'].sum()
            
            k1, k2 = st.columns(2)
            k1.metric("Orçado Atualizado", f"R$ {v_orc:,.2f}")
            k2.metric("Realizado (Soma Seleção)", f"R$ {v_real:,.2f}")
            
            st.dataframe(df_rf[['codigo_full', 'natureza', 'realizado', 'orcado']].style.format({
                'realizado': '{:,.2f}', 'orcado': '{:,.2f}'
            }), width='stretch')

with tab2:
    if not df_desp.empty:
        # (Código da despesa mantido conforme última versão estável)
        f1, f2, f3 = st.columns(3)
        ms_d = f1.multiselect("Meses Selecionados:", sorted(df_desp['mes'].unique()), default=df_desp['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="msd")
        ps = f2.multiselect("Programa:", sorted(df_desp['programa'].unique()))
        bd = f3.text_input("Natureza (Contém):", placeholder="Ex: 3390", key="bd")
        
        df_f = df_desp[df_desp['mes'].isin(ms_d)]
        if ps: df_f = df_f[df_f['programa'].isin(ps)]
        if bd: df_f = df_f[df_f['natureza'].str.contains(bd, case=False, na=False)]
        
        if not df_f.empty:
            m_ultima = max(ms_d)
            v_aut = df_desp[df_desp['mes'] == m_ultima].groupby(['uo','funcao','subfuncao','programa','projeto','natureza','fonte'])['cred_autorizado'].max().sum()
            ve, vl, vp = df_f['empenhado'].sum(), df_f['liquidado'].sum(), df_f['pago'].sum()
            
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Créd. Autorizado", f"R$ {v_aut:,.2f}")
            k2.metric("Empenhado", f"R$ {ve:,.2f}")
            k3.metric("Liquidado", f"R$ {vl:,.2f}")
            k4.metric("Pago", f"R$ {vp:,.2f}")
            
            st.dataframe(df_f[['programa', 'natureza', 'cred_autorizado', 'empenhado', 'liquidado', 'pago']].style.format({
                'cred_autorizado': '{:,.2f}', 'empenhado': '{:,.2f}', 'liquidado': '{:,.2f}', 'pago': '{:,.2f}'
            }), width='stretch')
