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
    
    # Cabeçalho
    pdf.set_font("helvetica", "B", 18)
    pdf.cell(190, 10, "Relatorio de Gestao Orcamentaria", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(190, 10, "Valores Consolidados (Contas Analiticas)", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(5)
    
    # Tentar capturar gráfico
    try:
        img_bytes = fig_plotly.to_image(format="png", width=1000, height=500, engine="kaleido")
        pdf.image(io.BytesIO(img_bytes), x=10, y=40, w=190)
        pdf.ln(95) 
    except:
        pdf.ln(5)

    # Tabela
    pdf.set_font("helvetica", "B", 9)
    pdf.set_fill_color(46, 125, 50) 
    pdf.set_text_color(255, 255, 255)
    pdf.cell(35, 8, "Cod. Natureza", 1, 0, "C", True)
    pdf.cell(85, 8, "Descricao", 1, 0, "C", True)
    pdf.cell(35, 8, "Realizado (R$)", 1, 0, "C", True)
    pdf.cell(35, 8, "Orcado (R$)", 1, 1, "C", True)
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "", 7)
    
    # Calculando Totais para o PDF (Garantindo que não some sintéticas)
    t_real = df_filtrado['realizado_mes'].sum()
    # O orçado anual é o último valor reportado para cada código único
    t_orc = df_filtrado.groupby(['ano', 'codigo_full'])['orcado_anual'].last().sum()
    
    fill = False
    for _, row in df_filtrado.iterrows():
        # Tratamento de Nones aqui também
        cod = str(row['codigo_full']) if row['codigo_full'] and str(row['codigo_full']) != 'None' else ""
        nat = str(row['natureza']) if row['natureza'] and str(row['natureza']) != 'None' else ""
        
        pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.cell(35, 7, cod[:15], 1, 0, 'L', fill)
        pdf.cell(85, 7, nat[:55], 1, 0, 'L', fill)
        pdf.cell(35, 7, f"{row['realizado_mes']:,.2f}", 1, 0, 'R', fill)
        pdf.cell(35, 7, f"{row['orcado_anual']:,.2f}", 1, 1, 'R', fill)
        fill = not fill
        
    # Rodapé da Tabela
    pdf.set_font("helvetica", "B", 8)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(120, 8, "TOTAIS (SOMENTE ANALITICAS)", 1, 0, 'R', True)
    pdf.cell(35, 8, f"{t_real:,.2f}", 1, 0, 'R', True)
    pdf.cell(35, 8, f"{t_orc:,.2f}", 1, 1, 'R', True)
    
    return bytes(pdf.output())

inicializar_banco()

# --- SIDEBAR ---
with st.sidebar:
    st.header("📥 Gestão de Dados")
    arquivo = st.file_uploader("FIPLAN (.xlsx) ou Backup (.csv)", type=["xlsx", "csv"])
    
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
                # FILTRO RÍGIDO PARA EVITAR CONTA SINTÉTICA (Garante os 953M)
                if re.match(r'^\d', cod) and not cod.endswith('.0') and not cod.endswith('.00') and len(cod) > 10:
                    is_ded = cod.startswith('9')
                    dados.append((int(mes_ref), int(ano_ref), cod, row.iloc[1], 
                                 limpar_valor(row.iloc[3], is_ded), limpar_valor(row.iloc[5], is_ded),
                                 limpar_valor(row.iloc[6], is_ded), limpar_valor(row.iloc[9], is_ded),
                                 limpar_valor(row.iloc[10], is_ded)))
            if dados:
                conn.execute("DELETE FROM receitas WHERE mes = ? AND ano = ?", (int(mes_ref), int(ano_ref)))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?,?,?)", dados)
                conn.commit()
                st.success("✅ Dados processados com sucesso!")
        conn.close()
        st.rerun()

# --- CARGA E LIMPEZA DE NONES ---
conn = sqlite3.connect(DB_NAME)
df_raw = pd.read_sql("SELECT * FROM receitas", conn)
conn.close()
# Limpa qualquer "None" que venha do banco de dados para a página ficar limpa
df_raw = df_raw.fillna("")
df_raw = df_raw.replace("None", "")

# --- DASHBOARD ---
if not df_raw.empty:
    st.title("📊 Painel Orçamentário Profissional")
    
    # Filtros
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
        
        # VOLTA DOS VALORES NO DASHBOARD (KPIs)
        st.divider()
        k1, k2, k3 = st.columns(3)
        # Orçado: Soma o último valor orçado de cada conta por ano selecionado
        val_orc = df_f.groupby(['ano', 'codigo_full'])['orcado_anual'].last().sum()
        val_real = df_f['realizado_mes'].sum()
        
        k1.metric("Orçado (Período Selecionado)", f"R$ {val_orc:,.2f}")
        k2.metric("Realizado (Período Selecionado)", f"R$ {val_real:,.2f}")
        k3.metric("Atingimento Global", f"{(val_real/val_orc*100 if val_orc != 0 else 0):.1f}%")

        # Gráfico
        df_g = df_f.groupby(['ano', 'mes'])[['realizado_mes', 'previsao_mes']].sum().reset_index()
        df_g['label'] = df_g.apply(lambda x: f"{MESES_NOMES[int(x['mes'])-1]}/{str(int(x['ano']))[2:]}", axis=1)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_g['label'], y=df_g['realizado_mes'], name="Realizado", marker_color='#2E7D32'))
        fig.add_trace(go.Scatter(x=df_g['label'], y=df_g['previsao_mes'], name="Previsão", line=dict(color='#FF9800', width=3, dash='dot')))
        fig.update_layout(height=400, hovermode="x unified", legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, width="stretch")

        # Botão PDF
        st.divider()
        try:
            pdf_bytes = gerar_pdf_com_grafico(df_f, fig)
            st.download_button(label="📄 Baixar Relatório PDF (Cravado 953M)", data=pdf_bytes, file_name="relatorio_gestao.pdf", mime="application/pdf")
        except:
            st.warning("🔄 O sistema está gerando o arquivo...")

        with st.expander("📋 Tabela de Naturezas"):
            st.dataframe(df_f[['codigo_full', 'natureza', 'realizado_mes', 'orcado_anual']], width="stretch")
else:
    st.info("Aguardando importação de dados.")
