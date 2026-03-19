import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import io

# --- CONFIGURAÇÕES ---
DB_NAME = 'dados_gestao_total.db'
st.set_page_config(page_title="Gestão Integrada FIPLAN", layout="wide")
MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    # Tabela de Receitas
    conn.execute('''CREATE TABLE IF NOT EXISTS receitas 
        (mes INTEGER, ano INTEGER, codigo_full TEXT, natureza TEXT, 
        orcado REAL, realizado REAL)''')
    # Tabela de Despesas (Baseada no FIP 613)
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
    st.header("📥 Importar Dados")
    tipo_dado = st.radio("O que você vai subir?", ["Receita", "Despesa"])
    arquivo = st.file_uploader(f"Arquivo {tipo_dado} (FIPLAN)", type=["xlsx"])
    
    mes_ref = st.selectbox("Mês", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano", value=2026)
    
    if arquivo and st.button("🚀 Processar e Salvar"):
        conn = sqlite3.connect(DB_NAME)
        if tipo_dado == "Receita":
            df = pd.read_excel(arquivo, skiprows=7)
            dados = []
            for _, row in df.iterrows():
                cod = str(row.iloc[0]).strip()
                if re.match(r'^\d', cod) and not cod.endswith('.0') and len(cod) > 10:
                    dados.append((mes_ref, ano_ref, cod, str(row.iloc[1]), limpar_f(row.iloc[3]), limpar_f(row.iloc[6])))
            conn.execute("DELETE FROM receitas WHERE mes=? AND ano=?", (mes_ref, ano_ref))
            conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?)", dados)
        else:
            # Processamento de Despesa (FIP 613)
            df = pd.read_excel(arquivo, skiprows=10) # FIP 613 costuma ter mais cabeçalho
            dados = []
            for _, row in df.iterrows():
                uo = str(row.iloc[0]).strip()
                if uo.isdigit(): # Garante que é uma linha de dados (UO numérica)
                    dados.append((mes_ref, ano_ref, uo, str(row.iloc[2]), str(row.iloc[3]), 
                                 str(row.iloc[4]), str(row.iloc[5]), str(row.iloc[7]), str(row.iloc[8]),
                                 limpar_f(row.iloc[11]), limpar_f(row.iloc[21]), limpar_f(row.iloc[22]), 
                                 limpar_f(row.iloc[24]), limpar_f(row.iloc[20])))
            conn.execute("DELETE FROM despesas WHERE mes=? AND ano=?", (mes_ref, ano_ref))
            conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
        
        conn.commit()
        conn.close()
        st.success("Dados processados!")
        st.rerun()

    if st.button("🔴 Limpar Tudo"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM receitas"); conn.execute("DELETE FROM despesas")
        conn.commit(); conn.close(); st.rerun()

# --- CARGA DE DADOS ---
conn = sqlite3.connect(DB_NAME)
df_rec = pd.read_sql("SELECT * FROM receitas", conn)
df_desp = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

# --- INTERFACE POR ABAS ---
tab1, tab2, tab3 = st.tabs(["📊 Receitas", "💸 Despesas", "⚖️ Análise Receita x Despesa"])

# --- ABA 1: RECEITAS ---
with tab1:
    if not df_rec.empty:
        st.subheader("Painel de Receitas")
        # Filtros e Gráficos de Receita (mesma lógica que já tínhamos)
        c1, c2 = st.columns(2)
        v_orc = df_rec['orcado'].sum()
        v_real = df_rec['realizado'].sum()
        c1.metric("Orçado", f"R$ {v_orc:,.2f}")
        c2.metric("Realizado", f"R$ {v_real:,.2f}")
        
        fig_r = go.Figure(data=[go.Bar(x=df_rec['natureza'][:10], y=df_rec['realizado'][:10], marker_color='#2E7D32')])
        st.plotly_chart(fig_r, use_container_width=True)
    else:
        st.info("Aguardando dados de Receita.")

# --- ABA 2: DESPESAS ---
with tab2:
    if not df_desp.empty:
        st.subheader("Painel de Despesas (FIP 613)")
        
        # Filtros Dinâmicos de Despesa
        f1, f2, f3 = st.columns(3)
        funcao_sel = f1.multiselect("Função:", sorted(df_desp['funcao'].unique()))
        prog_sel = f2.multiselect("Programa:", sorted(df_desp['programa'].unique()))
        nat_sel = f3.multiselect("Natureza Despesa:", sorted(df_desp['natureza'].unique()))
        
        df_df = df_desp.copy()
        if funcao_sel: df_df = df_df[df_df['funcao'].isin(funcao_sel)]
        if prog_sel: df_df = df_df[df_df['programa'].isin(prog_sel)]
        if nat_sel: df_df = df_df[df_df['natureza'].isin(nat_sel)]
        
        # KPIs de Despesa
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Dotação Inicial", f"R$ {df_df['dotacao'].sum():,.2f}")
        k2.metric("Empenhado", f"R$ {df_df['empenhado'].sum():,.2f}")
        k3.metric("Liquidado", f"R$ {df_df['liquidado'].sum():,.2f}")
        k4.metric("Saldo Dotação", f"R$ {df_df['saldo'].sum():,.2f}")
        
        # Gráfico Despesa por Função
        df_graf = df_df.groupby('funcao')['liquidado'].sum().reset_index()
        fig_d = go.Figure(data=[go.Pie(labels=df_graf['funcao'], values=df_graf['liquidado'], hole=.3)])
        st.plotly_chart(fig_d, use_container_width=True)
        
        st.dataframe(df_df, use_container_width=True)
    else:
        st.info("Aguardando dados de Despesa.")

# --- ABA 3: CRUZAMENTO ---
with tab3:
    st.subheader("Equilíbrio Orçamentário")
    if not df_rec.empty and not df_desp.empty:
        tot_rec = df_rec['realizado'].sum()
        tot_desp = df_desp['liquidado'].sum()
        saldo = tot_rec - tot_desp
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Recebido", f"R$ {tot_rec:,.2f}")
        m2.metric("Total Liquidado", f"R$ {tot_desp:,.2f}")
        m3.metric("Saldo (Superávit/Déficit)", f"R$ {saldo:,.2f}", delta=f"{saldo:,.2f}")
        
        # Gráfico Comparativo
        fig_comp = go.Figure(data=[
            go.Bar(name='Receita (Realizada)', x=['Total'], y=[tot_rec], marker_color='green'),
            go.Bar(name='Despesa (Liquidada)', x=['Total'], y=[tot_desp], marker_color='red')
        ])
        st.plotly_chart(fig_comp, use_container_width=True)
    else:
        st.warning("É necessário carregar dados nas duas abas para ver o cruzamento.")
