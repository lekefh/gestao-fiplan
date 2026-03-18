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
st.set_page_config(page_title="Gestão Orçamentária Pro", layout="wide")
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

def gerar_pdf_com_grafico(df_filtrado, fig_plotly):
    pdf = FPDF()
    pdf.add_page()
    
    # Título
    pdf.set_font("helvetica", "B", 18)
    pdf.cell(190, 10, "Relatorio de Gestao Orcamentaria", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(190, 10, "Filtros aplicados: Selecao do Dashboard", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(5)
    
    # Exportar gráfico (Usando motor engine="kaleido" explícito)
    try:
        # Gerar imagem do gráfico em alta resolução
        img_bytes = fig_plotly.to_image(format="png", width=1000, height=500, engine="kaleido")
        pdf.image(io.BytesIO(img_bytes), x=10, y=40, w=190)
        pdf.ln(95) 
    except Exception as e:
        pdf.set_font("helvetica", "I", 10)
        pdf.cell(190, 10, f"(Gráfico indisponível no PDF - Erro técnico)", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        pdf.ln(5)

    # Tabela formatada
    pdf.set_font("helvetica", "B", 10)
    pdf.set_fill_color(46, 125, 50) # Verde do Realizado
    pdf.set_text_color(255, 255, 255)
    pdf.cell(35, 8, "Cod. Natureza", 1, 0, "C", True)
    pdf.cell(85, 8, "Descricao", 1, 0, "C", True)
    pdf.cell(35, 8, "Realizado (R$)", 1, 0, "C", True)
    pdf.cell(35, 8, "Orcado (R$)", 1, 1, "C", True)
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "", 7)
    fill = False
    for _, row in df_filtrado.iterrows():
        pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
        desc = str(row['natureza'])[:55]
        pdf.cell(35, 7, str(row['codigo_full'])[:15], 1, 0, 'L', fill)
        pdf.cell(85, 7, desc, 1, 0, 'L', fill)
        pdf.cell(35, 7, f"{row['realizado_mes']:,.2f}", 1, 0, 'R', fill)
        pdf.cell(35, 7, f"{row['orcado_anual']:,.2f}", 1, 1, 'R', fill)
        fill = not fill
    
    return bytes(pdf.output())

inicializar_banco()

# --- SIDEBAR ---
with st.sidebar:
    st.header("📥 Gestão de Dados")
    arquivo = st.file_uploader("Subir FIPLAN (.xlsx) ou Backup (.csv)", type=["xlsx", "csv"])
    
    if arquivo and st.button("🚀 Processar Arquivo"):
        conn = sqlite3.connect(DB_NAME)
        if arquivo.name.endswith('.csv'):
            pd.read_csv(arquivo).to_sql('receitas', conn, if_exists='replace', index=False)
            st.success("✅ Backup restaurado!")
        else:
            mes_ref = st.selectbox("Mês", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
            ano_ref = st.number_input("Ano", value=2026)
            df_import = pd.read_excel(arquivo, skiprows=7)
            dados = []
            for _, row in df_import.iterrows():
                cod = str(row.iloc[0]).strip()
                if re.match(r'^\d', cod) and not cod.endswith('.0') and len(cod) > 10:
                    is_ded = cod.startswith('9')
                    dados.append((int(mes_ref), int(ano_ref), cod, row.iloc[1], 
                                 limpar_valor(row.iloc[3], is_ded), limpar_valor(row.iloc[5], is_ded),
                                 limpar_valor(row.iloc[6], is_ded), limpar_valor(row.iloc[9], is_ded),
                                 limpar_valor(row.iloc[10], is_ded)))
            if dados:
                conn.execute("DELETE FROM receitas WHERE mes = ? AND ano = ?", (int(mes_ref), int(ano_ref)))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?,?,?)", dados)
                conn.commit()
                st.success("✅ Dados importados!")
        conn.close()
        st.rerun()

# --- DASHBOARD ---
conn = sqlite3.connect(DB_NAME)
df_raw = pd.read_sql("SELECT * FROM receitas", conn)
conn.close()

if not df_raw.empty:
    st.title("📊 Painel Orçamentário Profissional")
    
    c1, c2, c3 = st.columns([1, 1, 2])
    anos_disp = sorted(df_raw['ano'].unique(), reverse=True)
    with c1: anos_sel = st.multiselect("Anos:", anos_disp, default=anos_disp)
    with c2:
        meses_disp = sorted(df_raw['mes'].unique())
        meses_sel = st.multiselect("Meses:", meses_disp, default=meses_disp, format_func=lambda x: MESES_NOMES[x-1])
    with c3:
        naturezas = sorted(df_raw['natureza'].unique())
        nat_sel = st.multiselect("Filtrar Naturezas:", naturezas)
    
    df_f = df_raw[df_raw['ano'].isin(anos_sel) & df_raw['mes'].isin(meses_sel)].copy()
    if nat_sel: df_f = df_f[df_f['natureza'].isin(nat_sel)]

    if not df_f.empty:
        df_f = df_f.sort_values(['ano', 'mes'])
        
        # Gráfico
        df_g = df_f.groupby(['ano', 'mes'])[['realizado_mes', 'previsao_mes']].sum().reset_index()
        df_g['label'] = df_g.apply(lambda x: f"{MESES_NOMES[int(x['mes'])-1]}/{str(int(x['ano']))[2:]}", axis=1)
        
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_g['label'], y=df_g['realizado_mes'], name="Realizado", marker_color='#2E7D32'))
        fig.add_trace(go.Scatter(x=df_g['label'], y=df_g['previsao_mes'], name="Previsão", line=dict(color='#FF9800', width=3, dash='dot')))
        fig.update_layout(height=450, hovermode="x unified", legend=dict(orientation="h", y=1.1))
        
        st.plotly_chart(fig, width="stretch")

        # Botão PDF
        st.divider()
        try:
            pdf_bytes = gerar_pdf_com_grafico(df_f, fig)
            st.download_button(label="📄 Baixar Relatório PDF Completo", data=pdf_bytes, file_name="relatorio_orcamentario.pdf", mime="application/pdf")
        except:
            st.warning("🔄 Processando gráfico para o PDF... Clique novamente em instantes.")

        with st.expander("📋 Ver Detalhamento"):
            st.dataframe(df_f[['codigo_full', 'natureza', 'realizado_mes', 'orcado_anual']], width="stretch")
else:
    st.info("Nenhum dado encontrado. Faça a importação na barra lateral.")
