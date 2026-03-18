import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import os
import re

# --- CONFIGURAÇÕES ---
DB_NAME = 'banco_dados_fiplan.db'
st.set_page_config(page_title="Gestão Orçamentária Pro", layout="wide")
MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

def conectar_db():
    return sqlite3.connect(DB_NAME)

def inicializar_banco():
    conn = conectar_db()
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

inicializar_banco()

# --- SIDEBAR: IMPORTAÇÃO ---
with st.sidebar:
    st.header("📥 Importar Dados")
    mes_ref = st.selectbox("Mês do Arquivo", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano", value=2026)
    arquivo = st.file_uploader("Selecione o Excel FIP 729", type=["xlsx"])
    
    if arquivo and st.button("🚀 Salvar e Atualizar"):
        try:
            df_import = pd.read_excel(arquivo, skiprows=7)
            dados = []
            for _, row in df_import.iterrows():
                cod = str(row.iloc[0]).strip()
                if re.match(r'^\d', cod) and not cod.endswith('.0') and not cod.endswith('.00') and len(cod) > 12:
                    is_ded = cod.startswith('9')
                    dados.append((int(mes_ref), int(ano_ref), cod, row.iloc[1], 
                                 limpar_valor(row.iloc[3], is_ded), limpar_valor(row.iloc[5], is_ded),
                                 limpar_valor(row.iloc[6], is_ded), limpar_valor(row.iloc[9], is_ded),
                                 limpar_valor(row.iloc[10], is_ded)))
            
            if dados:
                conn = conectar_db()
                conn.execute("DELETE FROM receitas WHERE mes = ? AND ano = ?", (int(mes_ref), int(ano_ref)))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?,?,?)", dados)
                conn.commit()
                conn.close()
                st.success("Dados salvos com sucesso!")
                st.rerun()
        except Exception as e:
            st.error(f"Erro ao processar: {e}")

# --- DASHBOARD ---
conn = conectar_db()
df_raw = pd.read_sql("SELECT * FROM receitas", conn)
conn.close()

if not df_raw.empty:
    st.title("📊 Painel de Controle Orçamentário")
    
    # FILTRO DE NATUREZA
    naturezas = sorted(df_raw['natureza'].unique())
    sel_naturezas = st.multiselect("Filtrar por Natureza de Receita:", options=naturezas)
    
    df_f_base = df_raw.copy()
    if sel_naturezas:
        df_f_base = df_f_base[df_f_base['natureza'].isin(sel_naturezas)]

    # LOOP POR ANOS
    anos_disp = sorted(df_f_base['ano'].unique(), reverse=True)
    for ano in anos_disp:
        with st.expander(f"📅 Relatório do Ano {ano}", expanded=True):
            df_ano = df_f_base[df_f_base['ano'] == ano]
            meses_disp = sorted(df_ano['mes'].unique())
            
            if len(meses_disp) > 1:
                start_m, end_m = st.select_slider(f"Intervalo de {ano}", options=meses_disp, 
                                                 value=(min(meses_disp), max(meses_disp)),
                                                 format_func=lambda x: MESES_NOMES[x-1], key=f"s_{ano}")
                df_f = df_ano[(df_ano['mes'] >= start_m) & (df_ano['mes'] <= end_m)]
            else:
                df_f = df_ano
                st.info(f"Dados disponíveis apenas para {MESES_NOMES[meses_disp[0]-1]}")

            # KPIs
            c1, c2, c3 = st.columns(3)
            orc = df_f.sort_values('mes').groupby('codigo_full')['orcado_anual'].last().sum()
            real = df_f['realizado_mes'].sum()
            c1.metric(f"Orçado Anual {ano}", f"R$ {orc:,.2f}")
            c2.metric("Realizado no Período", f"R$ {real:,.2f}")
            c3.metric("Atingimento", f"{(real/orc*100 if orc != 0 else 0):.1f}%")

            # Gráfico
            df_g = df_f.groupby('mes')[['realizado_mes']].sum().reset_index()
            fig = go.Figure(go.Bar(x=[MESES_NOMES[m-1] for m in df_g['mes']], y=df_g['realizado_mes'], marker_color='green'))
            fig.update_layout(title=f"Evolução Mensal {ano}", height=300)
            st.plotly_chart(fig, use_container_width=True)
            
            st.dataframe(df_f.drop(columns=['ano']), use_container_width=True)
            
    # Botão de Download de Backup
    csv = df_raw.to_csv(index=False).encode('utf-8')
    st.sidebar.download_button("📥 Baixar Backup CSV", csv, "backup_fiplan.csv", "text/csv")
else:
    st.info("Importe um arquivo FIPLAN para começar.")
