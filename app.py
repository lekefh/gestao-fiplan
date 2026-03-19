import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re
from fpdf import FPDF
from fpdf.enums import XPos, YPos
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
                # Regra original blindada anti-sintética
                if re.match(r'^\d', cod) and not cod.endswith('.0') and not cod.endswith('.00') and len(cod) > 10 and nat != "None":
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
        conn.commit(); conn.close()
        st.success("Importado com sucesso!"); st.rerun()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM receitas"); conn.execute("DELETE FROM despesas")
        conn.commit(); conn.close(); st.rerun()

# --- CARGA ---
conn = sqlite3.connect(DB_NAME)
df_rec_raw = pd.read_sql("SELECT * FROM receitas", conn)
df_desp_raw = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

tab1, tab2, tab3 = st.tabs(["📊 Receitas", "💸 Despesas", "⚖️ Confronto"])

# --- ABA 1: RECEITAS (LAYOUT RESTAURADO) ---
with tab1:
    if not df_rec_raw.empty:
        st.title("Painel Orçamentário de Receitas")
        c1, c2, c3 = st.columns([1, 1, 2])
        anos_r = c1.multiselect("Anos:", sorted(df_rec_raw['ano'].unique()), default=df_rec_raw['ano'].unique())
        meses_r = c2.multiselect("Meses:", sorted(df_rec_raw['mes'].unique()), default=df_rec_raw['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1])
        nat_r = c3.multiselect("Naturezas:", sorted(df_rec_raw['natureza'].unique()))
        
        df_rf = df_rec_raw[df_rec_raw['ano'].isin(anos_r) & df_rec_raw['mes'].isin(meses_r)]
        if nat_r: df_rf = df_rf[df_rf['natureza'].isin(nat_r)]
        
        if not df_rf.empty:
            st.divider()
            k1, k2, k3 = st.columns(3)
            v_orc = df_rf.groupby(['ano', 'codigo_full'])['orcado'].last().sum()
            v_real = df_rf['realizado'].sum()
            k1.metric("Orçado Total", f"R$ {v_orc:,.2f}")
            k2.metric("Realizado Total", f"R$ {v_real:,.2f}")
            k3.metric("Atingimento", f"{(v_real/v_orc*100 if v_orc != 0 else 0):.1f}%")

            df_g = df_rf.groupby(['ano', 'mes'])[['realizado', 'previsao']].sum().reset_index()
            df_g['label'] = df_g.apply(lambda x: f"{MESES_NOMES[int(x['mes'])-1]}/{str(int(x['ano']))[2:]}", axis=1)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_g['label'], y=df_g['realizado'], name="Realizado", marker_color='#2E7D32'))
            fig.add_trace(go.Scatter(x=df_g['label'], y=df_g['previsao'], name="Previsão", line=dict(color='#FF9800', width=3, dash='dot')))
            st.plotly_chart(fig, use_container_width=True)
    else: st.info("Suba um arquivo de Receita.")

# --- ABA 2: DESPESAS (COM PAGAMENTO) ---
with tab2:
    if not df_desp_raw.empty:
        st.title("Painel de Despesas Orçamentárias")
        d1, d2, d3 = st.columns(3)
        func_sel = d1.multiselect("Função:", sorted(df_desp_raw['funcao'].unique()))
        prog_sel = d2.multiselect("Programa:", sorted(df_desp_raw['programa'].unique()))
        font_sel = d3.multiselect("Fonte de Recurso:", sorted(df_desp_raw['fonte'].unique()))
        
        df_df = df_desp_raw.copy()
        if func_sel: df_df = df_df[df_df['funcao'].isin(func_sel)]
        if prog_sel: df_df = df_df[df_df['programa'].isin(prog_sel)]
        if font_sel: df_df = df_df[df_df['fonte'].isin(font_sel)]

        st.divider()
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Dotação Autorizada", f"R$ {df_df['dotacao'].sum():,.2f}")
        k2.metric("Liquidado", f"R$ {df_df['liquidado'].sum():,.2f}")
        k3.metric("Valor Pago", f"R$ {df_df['pago'].sum():,.2f}", delta_color="normal")
        k4.metric("Saldo Dotação", f"R$ {df_df['saldo'].sum():,.2f}")
        
        st.subheader("Detalhamento das Despesas")
        st.dataframe(df_df[['uo', 'funcao', 'programa', 'projeto', 'natureza', 'dotacao', 'liquidado', 'pago', 'saldo']], use_container_width=True)
    else: st.info("Suba um arquivo de Despesa (FIP 613).")

# --- ABA 3: CONFRONTO ---
with tab3:
    if not df_rec_raw.empty and not df_desp_raw.empty:
        st.title("Equilíbrio Financeiro")
        tr = df_rec_raw['realizado'].sum()
        td = df_desp_raw['liquidado'].sum()
        tp = df_desp_raw['pago'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Receita Realizada", f"R$ {tr:,.2f}")
        c2.metric("Despesa Paga", f"R$ {tp:,.2f}")
        c3.metric("Resultado Financeiro (Caixa)", f"R$ {tr - tp:,.2f}")
    else: st.warning("Necessário dados de Receita e Despesa para análise.")
