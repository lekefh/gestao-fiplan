import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import os
import re

# --- CONFIGURAÇÕES ---
DB_NAME = 'data_financeiro.db'
MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

def conectar_db():
    return sqlite3.connect(DB_NAME)

def inicializar_banco():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS receitas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes INTEGER,
            ano INTEGER,
            codigo_full TEXT,
            natureza TEXT,
            orcado_anual REAL,
            previsao_mes REAL,
            realizado_mes REAL,
            previsao_acumulada REAL,
            realizado_acumulado REAL
        )
    ''')
    conn.commit()
    conn.close()

def deletar_mes_existente(mes, ano):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM receitas WHERE mes = ? AND ano = ?", (mes, ano))
    conn.commit()
    conn.close()

def limpar_valor(valor, eh_dedutora=False):
    if pd.isna(valor) or valor == "" or valor == "-":
        return 0.0
    if isinstance(valor, str):
        valor = valor.replace('.', '').replace(',', '.')
    try:
        num = float(valor)
        return num * -1 if eh_dedutora else num
    except:
        return 0.0

# --- INTERFACE ---
st.set_page_config(page_title="Gestão Orçamentária Pro", layout="wide")
inicializar_banco()

st.title("📊 Gestão Financeira - Receitas FIPLAN")

# --- SIDEBAR: IMPORTAÇÃO ---
with st.sidebar:
    st.header("📥 Importar Novo Mês")
    mes_ref = st.selectbox("Mês do Arquivo", range(1, 13), index=1, format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano", value=2026)
    arquivo = st.file_uploader("Selecione o Excel", type=["xlsx"])
    
    if arquivo and st.button("🚀 Salvar e Substituir Dados"):
        try:
            df_import = pd.read_excel(arquivo, skiprows=7)
            dados_lista = []
            
            for _, row in df_import.iterrows():
                cod = str(row.iloc[0]).strip()
                # Filtro: Começa com número, Analítica (não termina em .0 ou .00), Tamanho mínimo
                if re.match(r'^\d', cod) and not cod.endswith('.0') and not cod.endswith('.00') and len(cod) > 12:
                    is_ded = cod.startswith('9')
                    dados_lista.append({
                        'mes': mes_ref, 'ano': ano_ref, 'codigo_full': cod, 'natureza': row.iloc[1],
                        'orcado_anual': limpar_valor(row.iloc[3], is_ded),
                        'previsao_mes': limpar_valor(row.iloc[5], is_ded),
                        'realizado_mes': limpar_valor(row.iloc[6], is_ded),
                        'previsao_acumulada': limpar_valor(row.iloc[9], is_ded),
                        'realizado_acumulado': limpar_valor(row.iloc[10], is_ded)
                    })
            
            if dados_lista:
                # 1. Limpa o mês antes de inserir para não duplicar
                deletar_mes_existente(mes_ref, ano_ref)
                # 2. Insere os novos dados
                conn = conectar_db()
                pd.DataFrame(dados_lista).to_sql('receitas', conn, if_exists='append', index=False)
                conn.close()
                st.success(f"Dados de {MESES_NOMES[mes_ref-1]} atualizados com sucesso!")
                st.rerun()
        except Exception as e:
            st.error(f"Erro: {e}")

# --- DASHBOARD: FILTROS DE TEMPO ---
if os.path.exists(DB_NAME):
    conn = conectar_db()
    df_raw = pd.read_sql("SELECT * FROM receitas", conn)
    conn.close()
else:
    df_raw = pd.DataFrame()

if not df_raw.empty:
    st.markdown("### 🔍 Filtros de Visualização")
    c1, c2 = st.columns([1, 3])
    with c1:
        ano_sel = st.selectbox("Selecione o Ano", sorted(df_raw['ano'].unique(), reverse=True))
    with c2:
        # Seletor de Intervalo de Meses
        meses_disponiveis = sorted(df_raw[df_raw['ano'] == ano_sel]['mes'].unique())
        if len(meses_disponiveis) >= 1:
            start_mes, end_mes = st.select_slider(
                "Selecione o intervalo de meses para somar:",
                options=meses_disponiveis,
                value=(min(meses_disponiveis), max(meses_disponiveis)),
                format_func=lambda x: MESES_NOMES[x-1]
            )
            df_f = df_raw[(df_raw['ano'] == ano_sel) & (df_raw['mes'] >= start_mes) & (df_raw['mes'] <= end_mes)]
        else:
            df_f = df_raw[df_raw['ano'] == ano_sel]

    # --- KPIs ---
    st.divider()
    k1, k2, k3 = st.columns(3)
    
    # Orçado Anual: Pegamos o valor da última importação dentro do range para cada conta
    # Isso evita somar o orçamento anual várias vezes ao selecionar múltiplos meses
    orc_anual_total = df_f.sort_values('mes').groupby('codigo_full')['orcado_anual'].last().sum()
    real_periodo = df_f['realizado_mes'].sum()
    prev_periodo = df_f['previsao_mes'].sum()

    k1.metric("Orçado Anual (Líq.)", f"R$ {orc_anual_total:,.2f}")
    k2.metric(f"Realizado no Período", f"R$ {real_periodo:,.2f}")
    k3.metric("Atingimento (vs Orçado)", f"{(real_periodo/orc_anual_total*100 if orc_anual_total != 0 else 0):.1f}%")

    # --- GRÁFICO DE EVOLUÇÃO ---
    st.subheader("📈 Evolução Mensal do Período")
    df_grafico = df_f.groupby('mes').agg({'realizado_mes': 'sum', 'previsao_mes': 'sum'}).reset_index()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[MESES_NOMES[m-1] for m in df_grafico['mes']], y=df_grafico['previsao_mes'], 
                             name="Previsto", line=dict(color='orange', dash='dot')))
    fig.add_trace(go.Bar(x=[MESES_NOMES[m-1] for m in df_grafico['mes']], y=df_grafico['realizado_mes'], 
                         name="Realizado", marker_color='green'))
    st.plotly_chart(fig, width='stretch')

    # --- TABELA ---
    with st.expander("📄 Ver Detalhamento por Natureza"):
        # Agrupamos por natureza para mostrar o consolidado do período selecionado
        df_tabela = df_f.groupby(['codigo_full', 'natureza']).agg({
            'orcado_anual': 'last',
            'previsao_mes': 'sum',
            'realizado_mes': 'sum'
        }).reset_index()
        st.dataframe(df_tabela, width='stretch')
else:
    st.info("O banco de dados está vazio. Importe o arquivo FIPLAN para começar.")