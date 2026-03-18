import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re
from fpdf import FPDF
import io
from PIL import Image

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

# FUNÇÃO PDF COM GRÁFICO E FILTROS
def gerar_pdf_com_grafico(df_filtrado, fig_plotly):
    pdf = FPDF()
    pdf.add_page()
    
    # Título
    pdf.set_font("helvetica", "B", 18)
    pdf.cell(190, 10, "Relatorio de Gestao Orcamentaria", ln=True, align="C")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(190, 10, "Filtros aplicados: Dados selecionados no Dashboard", ln=True, align="C")
    pdf.ln(5)
    
    # Exportar gráfico Plotly para imagem (Bytes)
    img_bytes = fig_plotly.to_image(format="png", width=800, height=400)
    img_io = io.BytesIO(img_bytes)
    
    # Adicionar Imagem do Gráfico ao PDF
    # Salvamos temporariamente para o FPDF carregar
    with open("temp_chart.png", "wb") as f:
        f.write(img_bytes)
    pdf.image("temp_chart.png", x=15, y=35, w=180)
    pdf.ln(85) # Pula o espaço do gráfico
    
    # Tabela de Dados
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(190, 10, "Detalhamento por Natureza", ln=True)
    pdf.ln(2)
    
    pdf.set_font("helvetica", "B", 9)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(35, 8, "Cod. Natureza", 1, 0, "C", True)
    pdf.cell(85, 8, "Descricao", 1, 0, "C", True)
    pdf.cell(35, 8, "Realizado (R$)", 1, 0, "C", True)
    pdf.cell(35, 8, "Orcado (R$)", 1, 1, "C", True)
    
    pdf.set_font("helvetica", "", 7)
    for _, row in df_filtrado.iterrows():
        desc = str(row['natureza'])[:55]
        pdf.cell(35, 7, str(row['codigo_full'])[:15], 1)
        pdf.cell(85, 7, desc, 1)
        pdf.cell(35, 7, f"{row['realizado_mes']:,.2f}", 1)
        pdf.cell(35, 7, f"{row['orcado_anual']:,.2f}", 1)
        pdf.ln()
    
    return bytes(pdf.output())

inicializar_banco()

# --- SIDEBAR ---
with st.sidebar:
    st.header("📥 Gestão de Dados")
    arquivo = st.file_uploader("Subir FIPLAN (.xlsx) ou Backup (.csv)", type=["xlsx", "csv"])
    
    if arquivo and arquivo.name.endswith('.xlsx'):
        mes_ref = st.selectbox("Mês", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
        ano_ref = st.number_input("Ano", value=2026)
    
    if arquivo and st.button("🚀 Processar"):
        conn = sqlite3.connect(DB_NAME)
        try:
            if arquivo.name.endswith('.csv'):
                pd.read_csv(arquivo).to_sql('receitas', conn, if_exists='replace', index=False)
                st.success("✅ Backup restaurado!")
            else:
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
                    st.success("✅ Dados salvos!")
        finally:
            conn.close()
            st.rerun()
    
    # Download de Backup
    conn = sqlite3.connect(DB_NAME)
    df_raw = pd.read_sql("SELECT * FROM receitas", conn)
    conn.close()
    if not df_raw.empty:
        csv_data = df_raw.to_csv(index=False).encode('utf-8')
        st.sidebar.divider()
        st.sidebar.download_button("📥 Baixar Backup CSV", csv_data, "gestao_backup.csv", "text/csv")

# --- DASHBOARD ---
if not df_raw.empty:
    st.title("📊 Gestão Orçamentária - Relatório")
    
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
        
        # KPIs
        st.divider()
        k1, k2, k3 = st.columns(3)
        orc_total = df_f.groupby(['ano', 'codigo_full'])['orcado_anual'].last().sum()
        real_total = df_f['realizado_mes'].sum()
        k1.metric("Orçado (Período)", f"R$ {orc_total:,.2f}")
        k2.metric("Realizado (Período)", f"R$ {real_total:,.2f}")
        k3.metric("Atingimento", f"{(real_total/orc_total*100 if orc_total != 0 else 0):.1f}%")

        # Gráfico
        df_g = df_f.groupby(['ano', 'mes'])[['realizado_mes', 'previsao_mes']].sum().reset_index()
        df_g['label'] = df_g.apply(lambda x: f"{MESES_NOMES[int(x['mes'])-1]}/{str(int(x['ano']))[2:]}", axis=1)
        
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_g['label'], y=df_g['realizado_mes'], name="Realizado", marker_color='#2E7D32'))
        fig.add_trace(go.Scatter(x=df_g['label'], y=df_g['previsao_mes'], name="Previsão", line=dict(color='#FF9800', width=3, dash='dot')))
        fig.update_layout(title="Evolução Mensal (Filtro Ativo)", hovermode="x unified", legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)

        # Botão PDF Dinâmico
        st.divider()
        try:
            pdf_data = gerar_pdf_com_grafico(df_f, fig)
            st.download_button(label="📄 Gerar Relatório PDF Selecionado", data=pdf_data, file_name="relatorio_personalizado.pdf", mime="application/pdf")
        except Exception as e:
            st.warning("O gráfico está sendo processado para o PDF... Aguarde um instante.")

        # Detalhamento
        with st.expander("📋 Ver Naturezas Filtradas"):
            st.dataframe(df_f[['codigo_full', 'natureza', 'realizado_mes', 'orcado_anual']], use_container_width=True)
else:
    st.info("Importe dados para começar.")
