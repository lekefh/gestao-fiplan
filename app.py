import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re
import io

# --- CONFIGURAÇÕES ---
DB_NAME = 'dados_gestao_integrada.db'
st.set_page_config(page_title="Gestão Integrada FIPLAN", layout="wide")
MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS receitas 
        (mes INTEGER, ano INTEGER, codigo_full TEXT, natureza TEXT, 
        orcado REAL, realizado REAL, previsao REAL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS despesas 
        (mes INTEGER, ano INTEGER, uo TEXT, funcao TEXT, subfuncao TEXT, 
        programa TEXT, projeto TEXT, natureza TEXT, fonte TEXT,
        dotacao REAL, empenhado REAL, liquidado REAL, pago REAL, saldo REAL)''')
    conn.close()

def limpar_f(v):
    if pd.isna(v) or v == "" or v == "-": return 0.0
    if isinstance(v, str): v = v.replace('.', '').replace(',', '.')
    try: return float(v)
    except: return 0.0

inicializar_banco()

# --- SIDEBAR: IMPORTAÇÃO ---
with st.sidebar:
    st.header("📥 Importar FIPLAN")
    tipo_dado = st.radio("Tipo de Arquivo:", ["Receita", "Despesa"])
    arquivo = st.file_uploader(f"Selecionar {tipo_dado}", type=["xlsx"])
    mes_ref = st.selectbox("Mês de Referência", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano", value=2026)
    
    if arquivo and st.button("🚀 Processar Dados"):
        conn = sqlite3.connect(DB_NAME)
        if tipo_dado == "Receita":
            df = pd.read_excel(arquivo, skiprows=7)
            dados = []
            for _, row in df.iterrows():
                cod = str(row.iloc[0]).strip()
                nat = str(row.iloc[1]).strip()
                if re.match(r'^\d', cod) and not cod.endswith('.0') and not cod.endswith('.00') and len(cod) > 10:
                    dados.append((mes_ref, ano_ref, cod, nat, limpar_f(row.iloc[3]), limpar_f(row.iloc[6]), limpar_f(row.iloc[5])))
            conn.execute("DELETE FROM receitas WHERE mes=? AND ano=?", (mes_ref, ano_ref))
            conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?)", dados)
        else:
            df = pd.read_excel(arquivo, skiprows=10)
            dados = []
            for _, row in df.iterrows():
                uo = str(row.iloc[0]).strip()
                if uo.isdigit():
                    dados.append((mes_ref, ano_ref, uo, str(row.iloc[2]), str(row.iloc[3]), str(row.iloc[4]), 
                                 str(row.iloc[5]), str(row.iloc[7]), str(row.iloc[8]),
                                 limpar_f(row.iloc[11]), limpar_f(row.iloc[21]), limpar_f(row.iloc[22]), 
                                 limpar_f(row.iloc[24]), limpar_f(row.iloc[20])))
            conn.execute("DELETE FROM despesas WHERE mes=? AND ano=?", (mes_ref, ano_ref))
            conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
        conn.commit(); conn.close(); st.rerun()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM receitas"); conn.execute("DELETE FROM despesas")
        conn.commit(); conn.close(); st.rerun()

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
        nat_r = c3.multiselect("Filtrar Naturezas:", sorted(df_rec_raw['natureza'].unique()), key="nr")
        
        df_periodo = df_rec_raw[df_rec_raw['ano'].isin(anos_r) & df_rec_raw['mes'].isin(meses_r)]
        total_geral_rec = df_periodo['realizado'].sum()
        df_rf = df_periodo.copy()
        if nat_r: df_rf = df_rf[df_rf['natureza'].isin(nat_r)]
        
        if not df_rf.empty:
            v_orc = df_rf.groupby(['ano', 'codigo_full'])['orcado'].last().sum()
            v_real = df_rf['realizado'].sum()
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Orçado (Período)", f"R$ {v_orc:,.2f}")
            k2.metric("Realizado (Período)", f"R$ {v_real:,.2f}")
            k3.metric("Atingimento", f"{(v_real/v_orc*100 if v_orc != 0 else 0):.1f}%")

            df_g = df_rf.groupby(['ano', 'mes'])[['realizado', 'previsao']].sum().reset_index()
            df_g['label'] = df_g.apply(lambda x: f"{MESES_NOMES[int(x['mes'])-1]}/{str(int(x['ano']))[2:]}", axis=1)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_g['label'], y=df_g['realizado'], name="Realizado", marker_color='#72A0C1'))
            fig.add_trace(go.Scatter(x=df_g['label'], y=df_g['previsao'], name="Previsão", line=dict(color='#FF9800', width=2, dash='dot')))
            fig.update_layout(height=350, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)

            df_rf['% s/ Total'] = (df_rf['realizado'] / total_geral_rec * 100).fillna(0)
            st.dataframe(df_rf[['codigo_full', 'natureza', 'realizado', '% s/ Total', 'orcado']].style.format({
                'realizado': '{:,.2f}', 'orcado': '{:,.2f}', '% s/ Total': '{:.2f}%'
            }), height=400, use_container_width=True)
    else: st.info("Suba um arquivo de Receita.")

# --- ABA 2: DESPESAS ---
with tab2:
    if not df_desp_raw.empty:
        # Filtros de Período e Categorias
        f_c1, f_c2, f_c3, f_c4, f_c5 = st.columns([1, 1, 1.5, 1.5, 1.5])
        anos_d = f_c1.multiselect("Anos:", sorted(df_desp_raw['ano'].unique()), default=df_desp_raw['ano'].unique(), key="ad")
        meses_d = f_c2.multiselect("Meses:", sorted(df_desp_raw['mes'].unique()), default=df_desp_raw['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="md")
        func_sel = f_c3.multiselect("Função:", sorted(df_desp_raw['funcao'].unique()))
        nat_desp_sel = f_c4.multiselect("Natureza:", sorted(df_desp_raw['natureza'].unique()))
        font_sel = f_c5.multiselect("Fonte:", sorted(df_desp_raw['fonte'].unique()))
        
        # Filtro de Período (para base do índice %)
        df_periodo_desp = df_desp_raw[df_desp_raw['ano'].isin(anos_d) & df_desp_raw['mes'].isin(meses_d)]
        total_geral_emp_periodo = df_periodo_desp['empenhado'].sum()
        
        # Filtro Final (Período + Categorias)
        df_df = df_periodo_desp.copy()
        if func_sel: df_df = df_df[df_df['funcao'].isin(func_sel)]
        if nat_desp_sel: df_df = df_df[df_df['natureza'].isin(nat_desp_sel)]
        if font_sel: df_df = df_df[df_df['fonte'].isin(font_sel)]

        if not df_df.empty:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Empenhado", f"R$ {df_df['empenhado'].sum():,.2f}")
            k2.metric("Liquidado", f"R$ {df_df['liquidado'].sum():,.2f}")
            k3.metric("Pago", f"R$ {df_df['pago'].sum():,.2f}")
            k4.metric("Saldo Dotação", f"R$ {df_df['saldo'].sum():,.2f}")
            
            st.markdown("##### Configurar Gráfico de Totais")
            c_g1, c_g2, c_g3 = st.columns(3)
            ver_emp = c_g1.checkbox("Ver Empenhado", value=True, key="ve")
            ver_liq = c_g2.checkbox("Ver Liquidado", value=True, key="vl")
            ver_pag = c_g3.checkbox("Ver Pago", value=False, key="vp")

            fig_d = go.Figure()
            if ver_emp: fig_d.add_trace(go.Bar(name='Empenhado', x=['Total Período'], y=[df_df['empenhado'].sum()], marker_color='#A9A9A9'))
            if ver_liq: fig_d.add_trace(go.Bar(name='Liquidado', x=['Total Período'], y=[df_df['liquidado'].sum()], marker_color='#72A0C1'))
            if ver_pag: fig_d.add_trace(go.Bar(name='Pago', x=['Total Período'], y=[df_df['pago'].sum()], marker_color='#2E7D32'))
            
            fig_d.update_layout(height=300, barmode='group', margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig_d, use_container_width=True)

            df_df['% s/ Emp. Total'] = (df_df['liquidado'] / total_geral_emp_periodo * 100).fillna(0)
            st.dataframe(df_df[['funcao', 'natureza', 'empenhado', 'liquidado', '% s/ Emp. Total', 'pago', 'saldo']].style.format({
                'empenhado': '{:,.2f}', 'liquidado': '{:,.2f}', 'pago': '{:,.2f}', 'saldo': '{:,.2f}', '% s/ Emp. Total': '{:.2f}%'
            }), height=400, use_container_width=True)
    else: st.info("Suba um arquivo de Despesa.")

# --- ABA 3: CONFRONTO ---
with tab3:
    if not df_rec_raw.empty and not df_desp_raw.empty:
        # Filtros de Período para o Confronto
        cf_1, cf_2 = st.columns(2)
        anos_c = cf_1.multiselect("Anos Confronto:", sorted(list(set(df_rec_raw['ano'].unique()) | set(df_desp_raw['ano'].unique()))), default=[2026], key="ac")
        meses_c = cf_2.multiselect("Meses Confronto:", range(1, 13), default=sorted(list(set(df_rec_raw['mes'].unique()) | set(df_desp_raw['mes'].unique()))), format_func=lambda x: MESES_NOMES[x-1], key="mc")

        tr = df_rec_raw[df_rec_raw['ano'].isin(anos_c) & df_rec_raw['mes'].isin(meses_c)]['realizado'].sum()
        te = df_desp_raw[df_desp_raw['ano'].isin(anos_c) & df_desp_raw['mes'].isin(meses_c)]['empenhado'].sum()
        tl = df_desp_raw[df_desp_raw['ano'].isin(anos_c) & df_desp_raw['mes'].isin(meses_c)]['liquidado'].sum()
        tp = df_desp_raw[df_desp_raw['ano'].isin(anos_c) & df_desp_raw['mes'].isin(meses_c)]['pago'].sum()
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Receita Realizada", f"R$ {tr:,.2f}")
        c2.metric("Desp. Empenhada", f"R$ {te:,.2f}")
        c3.metric("Desp. Liquidada", f"R$ {tl:,.2f}")
        c4.metric("Desp. Paga", f"R$ {tp:,.2f}")

        st.divider()
        m1, m2 = st.columns(2)
        m1.info(f"**Superávit Financeiro (Realizado - Pago):** \n R$ {tr - tp:,.2f}")
        m2.warning(f"**Superávit Orçamentário (Realizado - Empenhado):** \n R$ {tr - te:,.2f}")
        
        fig_c = go.Figure()
        fig_c.add_trace(go.Bar(name='Receita', x=['Confronto'], y=[tr], marker_color='green'))
        fig_c.add_trace(go.Bar(name='Empenhado', x=['Confronto'], y=[te], marker_color='orange'))
        fig_c.add_trace(go.Bar(name='Pago', x=['Confronto'], y=[tp], marker_color='red'))
        fig_c.update_layout(height=350)
        st.plotly_chart(fig_c, use_container_width=True)
    else: st.warning("Necessário dados de Receita e Despesa para confronto.")
