import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import io

# --- CONFIGURAÇÕES ---
DB_NAME = 'dados_gestao.db'
st.set_page_config(page_title="Gestão Orçamentária", layout="wide")
MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS receitas 
        (mes INTEGER, ano INTEGER, codigo_full TEXT, natureza TEXT, 
        orcado_anual REAL, previsao_mes REAL, realizado_mes REAL, 
        previsao_acumulada REAL, realizado_acumulado REAL)''')
    conn.close()

def limpar_valor(valor, eh_dedutora=False):
    if pd.isna(valor) or valor == "" or valor == "-": return 0.0
    if isinstance(valor, str): valor = valor.replace('.', '').replace(',', '.')
    try:
        num = float(valor)
        return num * -1 if eh_dedutora else num
    except: return 0.0

def gerar_pdf(df_filtrado, fig_plotly):
    pdf = FPDF()
    pdf.add_page()
    
    # Título
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(190, 10, "Relatorio de Gestao Orcamentaria", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    
    # Gráfico
    try:
        img_bytes = fig_plotly.to_image(format="png", width=800, height=400, engine="kaleido")
        pdf.image(io.BytesIO(img_bytes), x=15, y=30, w=180)
        pdf.ln(85)
    except: pdf.ln(10)
    
    # Tabela - Cabeçalho
    pdf.set_font("helvetica", "B", 10)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(40, 8, "Cod. Natureza", 1, 0, "C", True)
    pdf.cell(80, 8, "Natureza", 1, 0, "C", True)
    pdf.cell(35, 8, "Realizado", 1, 0, "C", True)
    pdf.cell(35, 8, "Orcado", 1, 1, "C", True)
    
    pdf.set_font("helvetica", "", 7)
    
    # LÓGICA DE TOTAIS CORRIGIDA (Igual ao Dashboard)
    total_realizado = df_filtrado['realizado_mes'].sum()
    # Soma o orçamento único por conta/ano para evitar duplicidade de sintéticas/mensais
    total_orcado = df_filtrado.groupby(['ano', 'codigo_full'])['orcado_anual'].last().sum()
    
    for _, row in df_filtrado.iterrows():
        pdf.cell(40, 7, str(row['codigo_full']), 1)
        pdf.cell(80, 7, str(row['natureza'])[:50], 1)
        pdf.cell(35, 7, f"{row['realizado_mes']:,.2f}", 1, 0, "R")
        pdf.cell(35, 7, f"{row['orcado_anual']:,.2f}", 1, 1, "R")
        
    # --- LINHA DE TOTAIS NO PDF (Cravada com o Dashboard) ---
    pdf.set_font("helvetica", "B", 9)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(120, 9, "TOTAIS CONSOLIDADOS (ANALITICOS)", 1, 0, "R", True)
    pdf.cell(35, 9, f"{total_realizado:,.2f}", 1, 0, "R", True)
    pdf.cell(35, 9, f"{total_orcado:,.2f}", 1, 1, "R", True)
    
    return bytes(pdf.output())

inicializar_banco()

# --- SIDEBAR ---
with st.sidebar:
    st.header("📥 Gestão de Dados")
    arquivo = st.file_uploader("Upload FIPLAN (.xlsx)", type=["xlsx", "csv"])
    
    mes_ref = st.selectbox("Mês de Referência", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano de Referência", value=2026)
    
    if arquivo and st.button("🚀 Processar Dados"):
        conn = sqlite3.connect(DB_NAME)
        if arquivo.name.endswith('.csv'):
            pd.read_csv(arquivo).to_sql('receitas', conn, if_exists='replace', index=False)
            st.success("Backup Restaurado")
        else:
            df_import = pd.read_excel(arquivo, skiprows=7)
            dados = []
            for _, row in df_import.iterrows():
                cod = str(row.iloc[0]).strip()
                nat = str(row.iloc[1]).strip()
                # REGRA DE OURO ORIGINAL (Analítica pura)
                if re.match(r'^\d', cod) and not cod.endswith('.0') and not cod.endswith('.00') and len(cod) > 10 and nat != "None":
                    is_ded = cod.startswith('9')
                    dados.append((int(mes_ref), int(ano_ref), cod, nat, 
                                 limpar_valor(row.iloc[3], is_ded), limpar_valor(row.iloc[5], is_ded),
                                 limpar_valor(row.iloc[6], is_ded), limpar_valor(row.iloc[9], is_ded),
                                 limpar_valor(row.iloc[10], is_ded)))
            if dados:
                conn.execute("DELETE FROM receitas WHERE mes = ? AND ano = ?", (int(mes_ref), int(ano_ref)))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?,?,?)", dados)
                conn.commit()
                st.success("Dados Salvos com Sucesso!")
        conn.close()
        st.rerun()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM receitas"); conn.commit(); conn.close()
        st.rerun()

# --- DASHBOARD ---
conn = sqlite3.connect(DB_NAME)
df_raw = pd.read_sql("SELECT * FROM receitas WHERE natureza != 'None' AND natureza != ''", conn)
conn.close()

if not df_raw.empty:
    st.title("📊 Painel Orçamentário Profissional")
    
    c1, c2, c3 = st.columns([1, 1, 2])
    anos_sel = c1.multiselect("Anos:", sorted(df_raw['ano'].unique()), default=df_raw['ano'].unique())
    meses_sel = c2.multiselect("Meses:", sorted(df_raw['mes'].unique()), default=df_raw['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1])
    naturezas = sorted(df_raw['natureza'].unique())
    nat_sel = c3.multiselect("Naturezas:", naturezas)
    
    df_f = df_raw[df_raw['ano'].isin(anos_sel) & df_raw['mes'].isin(meses_sel)].copy()
    if nat_sel: df_f = df_f[df_f['natureza'].isin(nat_sel)]

    if not df_f.empty:
        # KPIs
        k1, k2, k3 = st.columns(3)
        v_orc = df_f.groupby(['ano', 'codigo_full'])['orcado_anual'].last().sum()
        v_real = df_f['realizado_mes'].sum()
        k1.metric("Orçado Total", f"R$ {v_orc:,.2f}")
        k2.metric("Realizado Total", f"R$ {v_real:,.2f}")
        k3.metric("Atingimento", f"{(v_real/v_orc*100 if v_orc != 0 else 0):.1f}%")

        # Gráfico
        df_g = df_f.groupby(['ano', 'mes'])[['realizado_mes', 'previsao_mes']].sum().reset_index()
        df_g['label'] = df_g.apply(lambda x: f"{MESES_NOMES[int(x['mes'])-1]}/{str(int(x['ano']))[2:]}", axis=1)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_g['label'], y=df_g['realizado_mes'], name="Realizado", marker_color='#4F4F4F'))
        fig.add_trace(go.Scatter(x=df_g['label'], y=df_g['previsao_mes'], name="Previsão", line=dict(color='#FF9800', width=3, dash='dot')))
        st.plotly_chart(fig, use_container_width=True)
        
        st.download_button("📄 Baixar Relatório PDF", data=gerar_pdf(df_f, fig), file_name="relatorio_gestao.pdf")
    
    st.sidebar.divider()
    st.sidebar.download_button("📥 Backup CSV", df_raw.to_csv(index=False).encode('utf-8'), "backup.csv")
else:
    st.info("Aguardando importação de dados.")
