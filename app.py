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
    pdf.set_font("helvetica", "B", 18)
    pdf.cell(190, 10, "Relatorio de Gestao Orcamentaria", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(5)
    try:
        img_bytes = fig_plotly.to_image(format="png", width=1000, height=500, engine="kaleido")
        pdf.image(io.BytesIO(img_bytes), x=10, y=35, w=180)
        pdf.ln(95) 
    except: pdf.ln(5)

    pdf.set_font("helvetica", "B", 9)
    pdf.set_fill_color(46, 125, 50); pdf.set_text_color(255, 255, 255)
    pdf.cell(35, 8, "Cod. Natureza", 1, 0, "C", True)
    pdf.cell(85, 8, "Descricao", 1, 0, "C", True)
    pdf.cell(35, 8, "Realizado", 1, 0, "C", True)
    pdf.cell(35, 8, "Orcado", 1, 1, "C", True)
    
    pdf.set_text_color(0, 0, 0); pdf.set_font("helvetica", "", 7)
    t_real = df_filtrado['realizado_mes'].sum()
    t_orc = df_filtrado.groupby(['ano', 'codigo_full'])['orcado_anual'].last().sum()
    
    fill = False
    for _, row in df_filtrado.iterrows():
        pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.cell(35, 7, str(row['codigo_full'])[:15], 1, 0, 'L', fill)
        pdf.cell(85, 7, str(row['natureza'])[:55], 1, 0, 'L', fill)
        pdf.cell(35, 7, f"{row['realizado_mes']:,.2f}", 1, 0, 'R', fill)
        pdf.cell(35, 7, f"{row['orcado_anual']:,.2f}", 1, 1, 'R', fill)
        fill = not fill
        
    pdf.set_font("helvetica", "B", 8); pdf.set_fill_color(200, 200, 200)
    pdf.cell(120, 8, "TOTAIS CONSOLIDADOS", 1, 0, 'R', True)
    pdf.cell(35, 8, f"{t_real:,.2f}", 1, 0, 'R', True)
    pdf.cell(35, 8, f"{t_orc:,.2f}", 1, 1, 'R', True)
    return bytes(pdf.output())

inicializar_banco()

# --- SIDEBAR ---
with st.sidebar:
    st.header("📥 Gestão de Dados")
    arquivo = st.file_uploader("Subir FIPLAN (.xlsx) ou Backup (.csv)", type=["xlsx", "csv"])
    
    # SELETOR SEMPRE VISÍVEL PARA EXCEL
    mes_ref, ano_ref = 1, 2026
    if arquivo and arquivo.name.endswith('.xlsx'):
        mes_ref = st.selectbox("Selecione o Mês", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
        ano_ref = st.number_input("Selecione o Ano", value=2026)
    
    if arquivo and st.button("🚀 Processar Arquivo"):
        conn = sqlite3.connect(DB_NAME)
        if arquivo.name.endswith('.csv'):
            df_bkp = pd.read_csv(arquivo)
            # Limpa lixo do backup antes de restaurar
            df_bkp = df_bkp.dropna(subset=['natureza'])
            df_bkp = df_bkp[df_bkp['natureza'].str.contains("None") == False]
            df_bkp.to_sql('receitas', conn, if_exists='replace', index=False)
            st.success("✅ Backup Limpo Restaurado!")
        else:
            df_import = pd.read_excel(arquivo, skiprows=7)
            dados = []
            for _, row in df_import.iterrows():
                cod = str(row.iloc[0]).strip()
                nat = str(row.iloc[1]).strip()
                if re.match(r'^\d', cod) and not cod.endswith('.0') and len(cod) > 10 and nat != "None":
                    is_ded = cod.startswith('9')
                    dados.append((int(mes_ref), int(ano_ref), cod, nat, 
                                 limpar_valor(row.iloc[3], is_ded), limpar_valor(row.iloc[5], is_ded),
                                 limpar_valor(row.iloc[6], is_ded), limpar_valor(row.iloc[9], is_ded),
                                 limpar_valor(row.iloc[10], is_ded)))
            if dados:
                conn.execute("DELETE FROM receitas WHERE mes = ? AND ano = ?", (int(mes_ref), int(ano_ref)))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?,?,?)", dados)
                conn.commit()
                st.success(f"✅ {len(dados)} linhas de {MESES_NOMES[mes_ref-1]} salvas!")
        conn.close()
        st.rerun()

    if st.sidebar.button("🔴 Limpar Tudo"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM receitas"); conn.commit(); conn.close()
        st.cache_data.clear()
        st.rerun()

# --- CARGA E FILTRO ---
conn = sqlite3.connect(DB_NAME)
df_raw = pd.read_sql("SELECT * FROM receitas WHERE natureza NOT LIKE '%None%' AND natureza != ''", conn)
conn.close()

if not df_raw.empty:
    st.title("📊 Gestão Orçamentária")
    c1, c2, c3 = st.columns([1, 1, 2])
    anos_disp = sorted(df_raw['ano'].unique(), reverse=True)
    with c1: anos_sel = st.multiselect("Anos:", anos_disp, default=anos_disp)
    with c2:
        meses_disp = sorted(df_raw['mes'].unique())
        meses_sel = st.multiselect("Meses:", meses_disp, default=meses_disp, format_func=lambda x: MESES_NOMES[x-1])
    with c3:
        naturezas = sorted([n for n in df_raw['natureza'].unique() if n and n != "None"])
        nat_sel = st.multiselect("Naturezas:", naturezas)
    
    df_f = df_raw[df_raw['ano'].isin(anos_sel) & df_raw['mes'].isin(meses_sel)].copy()
    if nat_sel: df_f = df_f[df_f['natureza'].isin(nat_sel)]

    if not df_f.empty:
        df_f = df_f.sort_values(['ano', 'mes'])
        k1, k2, k3 = st.columns(3)
        v_orc = df_f.groupby(['ano', 'codigo_full'])['orcado_anual'].last().sum()
        v_real = df_f['realizado_mes'].sum()
        k1.metric("Orçado", f"R$ {v_orc:,.2f}")
        k2.metric("Realizado", f"R$ {v_real:,.2f}")
        k3.metric("Atingimento", f"{(v_real/v_orc*100 if v_orc != 0 else 0):.1f}%")

        df_g = df_f.groupby(['ano', 'mes'])[['realizado_mes', 'previsao_mes']].sum().reset_index()
        df_g['label'] = df_g.apply(lambda x: f"{MESES_NOMES[int(x['mes'])-1]}/{str(int(x['ano']))[2:]}", axis=1)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_g['label'], y=df_g['realizado_mes'], name="Realizado", marker_color='#2E7D32'))
        fig.add_trace(go.Scatter(x=df_g['label'], y=df_g['previsao_mes'], name="Previsão", line=dict(color='#FF9800', width=3, dash='dot')))
        st.plotly_chart(fig, width="stretch")

        st.download_button("📄 Baixar PDF", data=gerar_pdf_com_grafico(df_f, fig), file_name="relatorio.pdf")
    
    st.sidebar.divider()
    st.sidebar.download_button("📥 Baixar Backup", df_raw.to_csv(index=False).encode('utf-8'), "backup.csv")
else:
    st.info("Importe dados para começar.")
