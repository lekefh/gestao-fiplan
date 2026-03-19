import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re

# --- CONFIGURAÇÃO DA UNIDADE (Altere aqui para cada painel) ---
NOME_UNIDADE = "UO 03601 - FUNAJURIS" 

DB_NAME = 'dados_gestao_integrada.db'
st.set_page_config(page_title=f"FIPLAN - {NOME_UNIDADE}", layout="wide")
MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# Título visual no topo para não confundir as UOs
st.title(f"📊 {NOME_UNIDADE}")

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
        dotacao REAL, empenhado REAL, liquidado REAL, pago REAL, saldo REAL, cred_autorizado REAL)''')
    conn.close()

def limpar_f(v):
    if pd.isna(v) or v == "" or v == "-": return 0.0
    if isinstance(v, str): v = v.replace('.', '').replace(',', '.')
    try: return float(v)
    except: return 0.0

inicializar_banco()

# --- SIDEBAR: IMPORTAÇÃO ---
with st.sidebar:
    st.subheader(f"📥 Importar: {NOME_UNIDADE}")
    tipo_dado = st.radio("Tipo:", ["Receita", "Despesa"])
    arquivo = st.file_uploader(f"Arquivo {tipo_dado}", type=["xlsx"])
    mes_ref = st.selectbox("Mês", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano", value=2026)
    
    if arquivo and st.button("🚀 Processar Dados"):
        conn = sqlite3.connect(DB_NAME)
        if tipo_dado == "Receita":
            df = pd.read_excel(arquivo, skiprows=7)
            dados = []
            for _, row in df.iterrows():
                cod, nat = str(row.iloc[0]).strip(), str(row.iloc[1]).strip()
                if re.match(r'^\d', cod) and not cod.endswith('.0') and not cod.endswith('.00') and len(cod) >= 13:
                    dados.append((mes_ref, ano_ref, cod, nat, limpar_f(row.iloc[3]), limpar_f(row.iloc[6]), limpar_f(row.iloc[5])))
            conn.execute("DELETE FROM receitas WHERE mes=? AND ano=?", (mes_ref, ano_ref))
            conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?)", dados)
        else:
            df = pd.read_excel(arquivo, skiprows=10)
            df.columns = df.columns.str.strip()
            dados = []
            for _, row in df.iterrows():
                uo = str(row.get('UO', '')).strip()
                if uo.isdigit():
                    dados.append((mes_ref, ano_ref, uo, str(row.get('Função', '')), str(row.get('Subfunção', '')), 
                                 str(row.get('Programa', '')), str(row.get('Projeto/Atividade', '')), 
                                 str(row.get('Natureza de Despesa', '')), str(row.get('Fonte de Recurso', '')),
                                 limpar_f(row.get('Dotação Inicial', 0)), limpar_f(row.get('Empenhado', 0)), 
                                 limpar_f(row.get('Liquidado', 0)), limpar_f(row.get('Valor Pago', 0)), 
                                 limpar_f(row.get('Saldo Dotação', 0)), limpar_f(row.get('Créd. Autorizado', 0))))
            conn.execute("DELETE FROM despesas WHERE mes=? AND ano=?", (mes_ref, ano_ref))
            conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
        conn.commit(); conn.close(); st.rerun()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DROP TABLE IF EXISTS receitas"); conn.execute("DROP TABLE IF EXISTS despesas")
        conn.commit(); conn.close(); inicializar_banco(); st.rerun()

# --- CARGA ---
conn = sqlite3.connect(DB_NAME)
df_rec_raw = pd.read_sql("SELECT * FROM receitas WHERE natureza != 'None'", conn)
df_desp_raw = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

tab1, tab2, tab3 = st.tabs(["📊 Receitas", "💸 Despesas", "⚖️ Confronto"])

# --- ABA 1: RECEITAS ---
with tab1:
    if not df_rec_raw.empty:
        c1, c2, c3 = st.columns([1, 1, 2])
        anos_r = c1.multiselect("Anos:", sorted(df_rec_raw['ano'].unique()), default=df_rec_raw['ano'].unique(), key="ar")
        meses_r = c2.multiselect("Meses:", sorted(df_rec_raw['mes'].unique()), default=df_rec_raw['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="mr")
        nat_r = c3.multiselect("Filtrar Naturezas:", sorted(df_rec_raw['natureza'].unique()), key="nr")
        
        df_rf = df_rec_raw[(df_rec_raw['ano'].isin(anos_r)) & (df_rec_raw['mes'].isin(meses_r))]
        total_rec_p = df_rf['realizado'].sum()
        if nat_r: df_rf = df_rf[df_rf['natureza'].isin(nat_r)]
        
        if not df_rf.empty:
            k1, k2, k3 = st.columns(3)
            v_orc = df_rf.groupby(['ano', 'codigo_full'])['orcado'].last().sum()
            v_real = df_rf['realizado'].sum()
            k1.metric("Orçado", f"R$ {v_orc:,.2f}"); k2.metric("Realizado", f"R$ {v_real:,.2f}"); k3.metric("Atingimento", f"{(v_real/v_orc*100 if v_orc != 0 else 0):.1f}%")

            df_g = df_rf.groupby(['ano', 'mes'])[['realizado', 'previsao']].sum().reset_index()
            df_g['label'] = df_g.apply(lambda x: f"{MESES_NOMES[int(x['mes'])-1]}/{str(int(x['ano']))[2:]}", axis=1)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_g['label'], y=df_g['realizado'], name="Realizado", marker_color='#2E7D32'))
            fig.add_trace(go.Scatter(x=df_g['label'], y=df_g['previsao'], name="Previsão", line=dict(color='#FF9800', width=2, dash='dot')))
            fig.update_layout(height=350, margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig, use_container_width=True)

            df_rf['% s/ Total'] = (df_rf['realizado'] / total_rec_p * 100).fillna(0)
            st.dataframe(df_rf[['codigo_full', 'natureza', 'realizado', '% s/ Total', 'orcado']].style.format({'realizado': '{:,.2f}', 'orcado': '{:,.2f}', '% s/ Total': '{:.2f}%'}), height=450, use_container_width=True)

# --- ABA 2: DESPESAS ---
with tab2:
    if not df_desp_raw.empty:
        f1, f2, f3, f4, f5, f6 = st.columns(6)
        anos_d = f1.multiselect("Anos:", sorted(df_desp_raw['ano'].unique()), default=df_desp_raw['ano'].unique(), key="ad")
        meses_d = f2.multiselect("Meses:", sorted(df_desp_raw['mes'].unique()), default=df_desp_raw['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="md")
        func_sel = f3.multiselect("Função:", sorted(df_desp_raw['funcao'].unique()))
        prog_sel = f4.multiselect("Programa:", sorted(df_desp_raw['programa'].unique()))
        proj_sel = f5.multiselect("Projeto:", sorted(df_desp_raw['projeto'].unique()))
        nat_sel = f6.multiselect("Natureza:", sorted(df_desp_raw['natureza'].unique()))
        
        df_df = df_desp_raw[(df_desp_raw['ano'].isin(anos_d)) & (df_desp_raw['mes'].isin(meses_d))]
        total_emp_p = df_df['empenhado'].sum()
        if func_sel: df_df = df_df[df_df['funcao'].isin(func_sel)]
        if prog_sel: df_df = df_df[df_df['programa'].isin(prog_sel)]
        if proj_sel: df_df = df_df[df_df['projeto'].isin(proj_sel)]
        if nat_sel: df_df = df_df[df_df['natureza'].isin(nat_sel)]

        if not df_df.empty:
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Créd. Autorizado", f"R$ {df_df['cred_autorizado'].sum():,.2f}")
            k2.metric("Empenhado", f"R$ {df_df['empenhado'].sum():,.2f}")
            k3.metric("Liquidado", f"R$ {df_df['liquidado'].sum():,.2f}")
            k4.metric("Pago", f"R$ {df_df['pago'].sum():,.2f}")
            k5.metric("Saldo", f"R$ {df_df['saldo'].sum():,.2f}")
            
            fig_d = go.Figure()
            fig_d.add_trace(go.Bar(name='Empenhado', x=['Total'], y=[df_df['empenhado'].sum()], marker_color='#A9A9A9'))
            fig_d.add_trace(go.Bar(name='Liquidado', x=['Total'], y=[df_df['liquidado'].sum()], marker_color='#72A0C1'))
            fig_d.add_trace(go.Bar(name='Pago', x=['Total'], y=[df_df['pago'].sum()], marker_color='#2E7D32'))
            fig_d.update_layout(height=300, barmode='group', margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig_d, use_container_width=True)

            df_df['% s/ Empenho'] = (df_df['liquidado'] / total_emp_p * 100).fillna(0)
            st.dataframe(df_df[['funcao', 'programa', 'projeto', 'natureza', 'cred_autorizado', 'empenhado', 'liquidado', '% s/ Empenho', 'pago', 'saldo']].style.format({'cred_autorizado': '{:,.2f}', 'empenhado': '{:,.2f}', 'liquidado': '{:,.2f}', 'pago': '{:,.2f}', 'saldo': '{:,.2f}', '% s/ Empenho': '{:.2f}%'}), height=450, use_container_width=True)

# --- ABA 3: CONFRONTO ---
with tab3:
    if not df_rec_raw.empty and not df_desp_raw.empty:
        tr, te, tp = df_rec_raw['realizado'].sum(), df_desp_raw['empenhado'].sum(), df_desp_raw['pago'].sum()
        st.subheader("⚖️ Confronto do Período")
        st.info(f"**Superávit Financeiro (Receita - Pago): R$ {tr - tp:,.2f}**")
        st.warning(f"**Superávit Orçamentário (Receita - Empenhado): R$ {tr - te:,.2f}**")
