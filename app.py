import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re

# --- CONFIGURAÇÃO ---
DB_NAME = 'dados_gestao_integrada.db'
st.set_page_config(page_title="Gestão Integrada FIPLAN", layout="wide")
MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# CSS: Letras menores nos KPIs
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; font-weight: 700; }
    [data-testid="stMetricLabel"] { font-size: 0.8rem !important; }
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

inicializar_banco()

# --- SIDEBAR: IMPORTAÇÃO ---
with st.sidebar:
    st.subheader("📥 Importar Dados")
    tipo_dado = st.radio("Tipo:", ["Receita", "Despesa"])
    arquivo = st.file_uploader(f"Arquivo {tipo_dado}", type=["xlsx"])
    mes_ref = st.selectbox("Mês", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano", value=2026)
    
    if arquivo and st.button("🚀 Processar Dados"):
        conn = sqlite3.connect(DB_NAME)
        try:
            if tipo_dado == "Receita":
                df = pd.read_excel(arquivo, skiprows=7)
                dados = []
                for _, row in df.iterrows():
                    cod, nat = str(row.iloc[0]).strip(), str(row.iloc[1]).strip()
                    if re.match(r'^\d', cod) and not cod.endswith('.0') and len(cod) >= 13:
                        dados.append((mes_ref, ano_ref, cod, nat, limpar_f(row.iloc[3]), limpar_f(row.iloc[6]), limpar_f(row.iloc[5])))
                conn.execute("DELETE FROM receitas WHERE mes=? AND ano=?", (mes_ref, ano_ref))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?)", dados)
            else:
                df = pd.read_excel(arquivo, skiprows=6)
                df.columns = df.columns.str.strip().str.upper()
                dados = []
                for _, row in df.iterrows():
                    uo = str(row.get('UO', '')).strip()
                    if uo != "" and uo != "nan":
                        dados.append((mes_ref, ano_ref, uo, str(row.get('FUNÇÃO', '')), str(row.get('SUBFUNÇÃO', '')), 
                                     str(row.get('PROGRAMA', '')), str(row.get('PAOE', '')), 
                                     str(row.get('NATUREZA DESPESA', '')), str(row.get('FONTE', '')),
                                     limpar_f(row.get('ORÇADO INICIAL', 0)), limpar_f(row.get('CRÉDITO AUTORIZADO', 0)), 
                                     limpar_f(row.get('EMPENHADO', 0)), limpar_f(row.get('LIQUIDADO', 0)), limpar_f(row.get('PAGO', 0))))
                conn.execute("DELETE FROM despesas WHERE mes=? AND ano=?", (mes_ref, ano_ref))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
            conn.commit(); st.success("✅ Importado!"); st.rerun()
        except Exception as e: st.error(f"Erro: {e}")
        finally: conn.close()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DROP TABLE IF EXISTS receitas"); conn.execute("DROP TABLE IF EXISTS despesas")
        conn.commit(); conn.close(); inicializar_banco(); st.rerun()

# --- FUNÇÃO DE CÁLCULO INCREMENTAL ---
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
                        incremental = val_atual[col].values[0] - val_anterior[col].values[0]
                        df_res.at[idx, col] = max(0, incremental)
    return df_res

# --- CARGA E CÁLCULO ---
conn = sqlite3.connect(DB_NAME)
df_rec_raw = pd.read_sql("SELECT * FROM receitas", conn)
df_desp_raw = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

df_rec_inc = calcular_incremental(df_rec_raw, ['realizado'])
df_desp_inc = calcular_incremental(df_desp_raw, ['empenhado', 'liquidado', 'pago'])

# --- LÓGICA DE FILTRAGEM GLOBAL (Resolve o NameError) ---
st.write("") # Espaço para layout
tab1, tab2, tab3 = st.tabs(["📊 Receitas", "💸 Despesas", "⚖️ Confronto"])

# --- ABA 1: RECEITAS ---
with tab1:
    if not df_rec_inc.empty:
        c1, c2, c3 = st.columns([1, 1, 2])
        anos_r = c1.multiselect("Anos:", sorted(df_rec_inc['ano'].unique()), default=df_rec_inc['ano'].unique(), key="ar")
        meses_r = c2.multiselect("Meses:", sorted(df_rec_inc['mes'].unique()), default=df_rec_inc['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="mr")
        nat_r = c3.multiselect("Filtrar Naturezas:", sorted(df_rec_inc['natureza'].unique()), key="nr")
        
        df_rf = df_rec_inc[(df_rec_inc['ano'].isin(anos_r)) & (df_rec_inc['mes'].isin(meses_r))]
        if nat_r: df_rf = df_rf[df_rf['natureza'].isin(nat_r)]
        
        if not df_rf.empty:
            v_real_rec = df_rf['realizado'].sum()
            v_orc_rec = df_rf[df_rf['mes'] == df_rf['mes'].max()].groupby(['ano', 'codigo_full'])['orcado'].last().sum()
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Orçado (Atual)", f"R$ {v_orc_rec:,.2f}")
            k2.metric("Realizado (Soma)", f"R$ {v_real_rec:,.2f}")
            k3.metric("Atingimento", f"{(v_real_rec/v_orc_rec*100 if v_orc_rec != 0 else 0):.1f}%")

            df_g_r = df_rf.groupby(['ano', 'mes'])[['realizado']].sum().reset_index()
            st.plotly_chart(go.Figure(data=[go.Bar(x=df_g_r['mes'].map(lambda x: MESES_NOMES[x-1]), y=df_g_r['realizado'], marker_color='#2E7D32')]), use_container_width=True)
            st.dataframe(df_rf[['natureza', 'realizado', 'orcado']].style.format({'realizado': '{:,.2f}', 'orcado': '{:,.2f}'}), use_container_width=True)

# --- ABA 2: DESPESAS ---
with tab2:
    if not df_desp_inc.empty:
        f1, f2, f3, f4, f5, f6 = st.columns(6)
        anos_d = f1.multiselect("Anos:", sorted(df_desp_inc['ano'].unique()), default=df_desp_inc['ano'].unique(), key="ad")
        meses_d = f2.multiselect("Meses:", sorted(df_desp_inc['mes'].unique()), default=df_desp_inc['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="md")
        func_sel = f3.multiselect("Função:", sorted(df_desp_inc['funcao'].unique()))
        sub_sel = f4.multiselect("Subfunção:", sorted(df_desp_inc['subfuncao'].unique()))
        font_sel = f5.multiselect("Fonte:", sorted(df_desp_inc['fonte'].unique()))
        nat_sel = f6.multiselect("Natureza:", sorted(df_desp_inc['natureza'].unique()))
        
        df_df = df_desp_inc[(df_desp_inc['ano'].isin(anos_d)) & (df_desp_inc['mes'].isin(meses_d))]
        if func_sel: df_df = df_df[df_df['funcao'].isin(func_sel)]
        if sub_sel: df_df = df_df[df_df['subfuncao'].isin(sub_sel)]
        if font_sel: df_df = df_df[df_df['fonte'].isin(font_sel)]
        if nat_sel: df_df = df_df[df_df['natureza'].isin(nat_sel)]

        if not df_df.empty:
            v_aut_d = df_df[df_df['mes'] == df_df['mes'].max()]['cred_autorizado'].sum()
            v_emp_d, v_liq_d, v_pag_d = df_df['empenhado'].sum(), df_df['liquidado'].sum(), df_df['pago'].sum()

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Créd. Autorizado", f"R$ {v_aut_d:,.2f}")
            k2.metric("Empenhado", f"R$ {v_emp_d:,.2f}")
            k3.metric("Liquidado", f"R$ {v_liq_d:,.2f}")
            k4.metric("Pago", f"R$ {v_pag_d:,.2f}")
            
            fig_d = go.Figure(data=[
                go.Bar(name='Empenhado', x=['Total'], y=[v_emp_d], marker_color='#A9A9A9'),
                go.Bar(name='Liquidado', x=['Total'], y=[v_liq_d], marker_color='#72A0C1'),
                go.Bar(name='Pago', x=['Total'], y=[v_pag_d], marker_color='#2E7D32')
            ])
            st.plotly_chart(fig_d, use_container_width=True)
            st.dataframe(df_df[['funcao', 'subfuncao', 'fonte', 'natureza', 'cred_autorizado', 'empenhado', 'liquidado', 'pago']].style.format({
                'cred_autorizado': '{:,.2f}', 'empenhado': '{:,.2f}', 'liquidado': '{:,.2f}', 'pago': '{:,.2f}'
            }), use_container_width=True)

# --- ABA 3: CONFRONTO (Corrigida) ---
with tab3:
    st.subheader("⚖️ Confronto do Período")
    # Busca os valores calculados nas outras abas se existirem, senão usa 0
    # Definindo variáveis locais para evitar o NameError
    try: tr = v_real_rec
    except: tr = 0
    try: tp = v_pag_d
    except: tp = 0
    try: te = v_emp_d
    except: te = 0
    try: tl = v_liq_d
    except: tl = 0

    if tr > 0 or te > 0:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Receita Arrecadada", f"R$ {tr:,.2f}")
        c2.metric("Despesa Empenhada", f"R$ {te:,.2f}")
        c3.metric("Despesa Liquidada", f"R$ {tl:,.2f}")
        c4.metric("Despesa Paga", f"R$ {tp:,.2f}")

        st.divider()
        m1, m2 = st.columns(2)
        m1.info(f"**Superávit Financeiro (Receita - Pago):** \n R$ {tr - tp:,.2f}")
        m2.warning(f"**Superávit Orçamentário (Receita - Empenhado):** \n R$ {tr - te:,.2f}")
        
        fig_c = go.Figure(data=[
            go.Bar(name='Receita', x=['Total'], y=[tr], marker_color='green'),
            go.Bar(name='Empenhado', x=['Total'], y=[te], marker_color='orange'),
            go.Bar(name='Pago', x=['Total'], y=[tp], marker_color='red')
        ])
        st.plotly_chart(fig_c, use_container_width=True)
    else:
        st.info("Navegue pelas abas de Receita e Despesa para carregar os dados do período.")
