import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re

# --- CONFIGURAÇÃO ---
DB_NAME = 'dados_gestao_integrada.db'
st.set_page_config(page_title="FIPLAN - GESTÃO INTEGRADA", layout="wide")
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
    conn.execute('''CREATE TABLE IF NOT EXISTS receitas 
        (mes INTEGER, ano INTEGER, codigo_full TEXT, natureza TEXT, orcado REAL, realizado REAL, previsao REAL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS despesas 
        (mes INTEGER, ano INTEGER, uo TEXT, funcao TEXT, subfuncao TEXT, programa TEXT, projeto TEXT, natureza TEXT, fonte TEXT, orcado_inicial REAL, cred_autorizado REAL, empenhado REAL, liquidado REAL, pago REAL)''')
    conn.close()

def limpar_f(v):
    if pd.isna(v) or v == "" or v == "-": return 0.0
    if isinstance(v, (int, float)): return float(v)
    v = str(v).replace('"', '').replace('.', '').replace(',', '.')
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
    
    # Backup caso o scanner falhe
    mes_manual = st.selectbox("Mês (Backup)", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano", value=2026)
    
    if arquivo and st.button("🚀 Processar Dados"):
        m_final = detectar_mes(arquivo) or mes_manual
        conn = sqlite3.connect(DB_NAME)
        try:
            if tipo_dado == "Receita":
                df = pd.read_excel(arquivo, skiprows=7)
                dados = []
                for _, row in df.iterrows():
                    cod = str(row.iloc[0]).strip().replace('"', '')
                    if re.match(r'^\d', cod) and len(cod) >= 11:
                        dados.append((m_final, ano_ref, cod, str(row.iloc[1]).replace('"', ''), limpar_f(row.iloc[3]), limpar_f(row.iloc[6]), limpar_f(row.iloc[5])))
                conn.execute("DELETE FROM receitas WHERE mes=? AND ano=?", (m_final, ano_ref))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?)", dados)
            else:
                # MOTOR DE DESPESA BLINDADO PARA FIP 616
                df = pd.read_excel(arquivo, skiprows=6)
                df.columns = df.columns.str.strip().str.upper()
                dados = []
                for _, row in df.iterrows():
                    uo, ug = str(row.get('UO', '')).strip(), str(row.get('UG', '')).strip()
                    if uo != "" and uo != "nan":
                        elem = limpar_f(row.get('ELEMENTO', 0))
                        # Só captura execução de linhas analíticas (UG != 0)
                        v_emp = limpar_f(row.get('EMPENHADO', 0)) if (ug != '0' and elem != 0) else 0.0
                        v_liq = limpar_f(row.get('LIQUIDADO', 0)) if (ug != '0' and elem != 0) else 0.0
                        v_pag = limpar_f(row.get('PAGO', 0)) if (ug != '0' and elem != 0) else 0.0
                        v_aut = limpar_f(row.get('CRÉDITO AUTORIZADO', 0))
                        v_ini = limpar_f(row.get('ORÇADO INICIAL', 0))
                        
                        if v_aut > 0 or v_emp > 0 or v_liq > 0 or v_pag > 0:
                            dados.append((m_final, ano_ref, uo, str(row.get('FUNÇÃO', '')), str(row.get('SUBFUNÇÃO', '')), str(row.get('PROGRAMA', '')), str(row.get('PAOE', '')), str(row.get('NATUREZA DESPESA', '')), str(row.get('FONTE', '')), v_ini, v_aut, v_emp, v_liq, v_pag))
                conn.execute("DELETE FROM despesas WHERE mes=? AND ano=?", (m_final, ano_ref))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
            
            conn.commit()
            st.success(f"✅ Importado: {MESES_NOMES[m_final-1]}")
            st.rerun()
        except Exception as e: st.error(f"Erro: {e}")
        finally: conn.close()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DROP TABLE IF EXISTS receitas"); conn.execute("DROP TABLE IF EXISTS despesas")
        conn.commit(); conn.close(); inicializar_banco(); st.rerun()

# --- CARGA ---
conn = sqlite3.connect(DB_NAME)
df_rec_raw = pd.read_sql("SELECT * FROM receitas", conn)
df_desp_raw = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

tab1, tab2, tab3 = st.tabs(["📊 Receitas", "💸 Despesas", "⚖️ Confronto"])

# --- ABA 1: RECEITAS ---
with tab1:
    if not df_rec_raw.empty:
        c1, c2, c3 = st.columns([1, 1, 2])
        anos_r = c1.multiselect("Anos:", sorted(df_rec_raw['ano'].unique()), default=df_rec_raw['ano'].unique(), key="ar")
        meses_r = c2.multiselect("Meses:", sorted(df_rec_raw['mes'].unique()), default=df_rec_raw['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="mr")
        busca_nat_r = c3.text_input("Natureza (Contém):", key="br_r")
        
        df_rf = df_rec_raw[(df_rec_raw['ano'].isin(anos_r)) & (df_rec_raw['mes'].isin(meses_r))]
        if busca_nat_r:
            df_rf = df_rf[df_rf['natureza'].str.contains(busca_nat_r, case=False, na=False)]
        
        if not df_rf.empty:
            v_real = df_rf['realizado'].sum()
            v_orc = df_rec_raw[df_rec_raw['mes'] == max(meses_r)]['orcado'].sum()
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Orçado Atual", f"R$ {v_orc:,.2f}")
            k2.metric("Realizado", f"R$ {v_real:,.2f}")
            k3.metric("Atingimento", f"{(v_real/v_orc*100 if v_orc != 0 else 0):.1f}%")

            # Gráfico de Receitas
            df_g = df_rf.groupby(['ano', 'mes'])[['realizado', 'previsao']].sum().reset_index()
            df_g['label'] = df_g.apply(lambda x: f"{MESES_NOMES[int(x['mes'])-1]}/{str(int(x['ano']))[2:]}", axis=1)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_g['label'], y=df_g['realizado'], name="Realizado", marker_color='#2E7D32'))
            fig.add_trace(go.Scatter(x=df_g['label'], y=df_g['previsao'], name="Previsão", line=dict(color='#FF9800', width=2, dash='dot')))
            st.plotly_chart(fig, use_container_width=True)
            
            st.dataframe(df_rf[['codigo_full', 'natureza', 'realizado', 'orcado']].style.format({'realizado': '{:,.2f}', 'orcado': '{:,.2f}'}), width='stretch')

# --- ABA 2: DESPESAS ---
with tab2:
    if not df_desp_raw.empty:
        f1, f2, f3, f4, f5 = st.columns(5)
        ms_d = f1.multiselect("Meses:", sorted(df_desp_raw['mes'].unique()), default=df_desp_raw['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="msd")
        ss = f2.multiselect("Subfunção:", sorted(df_desp_raw['subfuncao'].unique()))
        ps = f3.multiselect("Programa:", sorted(df_desp_raw['programa'].unique()))
        fts = f4.multiselect("Fonte:", sorted(df_desp_raw['fonte'].unique()))
        bd = f5.text_input("Natureza (Contém):", key="bd_d")
        
        df_df = df_desp_raw[df_desp_raw['mes'].isin(ms_d)]
        if ss: df_df = df_df[df_df['subfuncao'].isin(ss)]
        if ps: df_df = df_df[df_df['programa'].isin(ps)]
        if fts: df_df = df_df[df_df['fonte'].isin(fts)]
        if bd: df_df = df_df[df_df['natureza'].str.contains(bd, case=False, na=False)]
        
        if not df_df.empty:
            m_max = max(ms_d)
            # Crédito: Agrupamento para evitar duplicidade
            v_aut = df_desp_raw[df_desp_raw['mes'] == m_max].groupby(['uo','funcao','subfuncao','programa','projeto','natureza','fonte'])['cred_autorizado'].max().sum()
            ve, vl, vp = df_df['empenhado'].sum(), df_df['liquidado'].sum(), df_df['pago'].sum()
            
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Créd. Autorizado", f"R$ {v_aut:,.2f}")
            k2.metric("Empenhado", f"R$ {ve:,.2f}")
            k3.metric("Liquidado", f"R$ {vl:,.2f}")
            k4.metric("Pago", f"R$ {vp:,.2f}")
            
            st.dataframe(df_df[['funcao', 'subfuncao', 'programa', 'projeto', 'fonte', 'natureza', 'cred_autorizado', 'empenhado', 'liquidado', 'pago']].style.format({
                'cred_autorizado': '{:,.2f}', 'empenhado': '{:,.2f}', 'liquidado': '{:,.2f}', 'pago': '{:,.2f}'
            }), width='stretch')

# --- ABA 3: CONFRONTO ---
with tab3:
    if not df_rec_raw.empty or not df_desp_raw.empty:
        st.subheader("⚖️ Confronto Geral Financeiro")
        ms_c = st.multiselect("Meses para Confronto:", range(1, 13), default=range(1, 13), format_func=lambda x: MESES_NOMES[x-1], key="msc")
        
        tr = df_rec_raw[df_rec_raw['mes'].isin(ms_c)]['realizado'].sum()
        tp = df_desp_raw[df_desp_raw['mes'].isin(ms_c)]['pago'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Receita Arrecadada", f"R$ {tr:,.2f}")
        c2.metric("Despesa Paga", f"R$ {tp:,.2f}")
        c3.metric("Superávit Financeiro", f"R$ {tr - tp:,.2f}")
        
        fig_c = go.Figure()
        fig_c.add_trace(go.Bar(name='Receita', x=['Total'], y=[tr], marker_color='green'))
        fig_c.add_trace(go.Bar(name='Despesa Paga', x=['Total'], y=[tp], marker_color='red'))
        st.plotly_chart(fig_c, use_container_width=True)
