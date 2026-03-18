import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
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
            st.error(f"Erro: {e}")

# --- DASHBOARD ---
conn = conectar_db()
df_raw = pd.read_sql("SELECT * FROM receitas", conn)
conn.close()

if not df_raw.empty:
    st.title("📊 Análise Orçamentária de Longo Prazo")
    
    # --- FILTROS TOTAIS ---
    c_filt1, c_filt2 = st.columns([1, 2])
    with c_filt1:
        anos_disponiveis = sorted(df_raw['ano'].unique(), reverse=True)
        anos_sel = st.multiselect("Selecione os Anos:", options=anos_disponiveis, default=anos_disponiveis[0])
    
    with c_filt2:
        naturezas = sorted(df_raw['natureza'].unique())
        sel_naturezas = st.multiselect("Filtrar por Natureza de Receita:", options=naturezas)
    
    # Aplicação dos Filtros
    df_f = df_raw[df_raw['ano'].isin(anos_sel)].copy()
    if sel_naturezas:
        df_f = df_f[df_f['natureza'].isin(sel_naturezas)]

    if not df_f.empty:
        # Criar coluna de data para ordenação correta no gráfico
        df_f['data_ref'] = df_f.apply(lambda x: f"{int(x['ano'])}-{int(x['mes']):02d}", axis=1)
        df_f = df_f.sort_values(['ano', 'mes'])

        # KPIs GERAIS (Soma de todos os anos selecionados)
        st.divider()
        k1, k2, k3 = st.columns(3)
        # Orçado: Soma do último orçado de cada conta por ano selecionado
        orc_total = df_f.groupby(['ano', 'codigo_full'])['orcado_anual'].last().sum()
        real_total = df_f['realizado_mes'].sum()
        
        k1.metric("Orçado Total (Anos Sel.)", f"R$ {orc_total:,.2f}")
        k2.metric("Realizado Total", f"R$ {real_total:,.2f}")
        k3.metric("Atingimento Global", f"{(real_total/orc_total*100 if orc_total != 0 else 0):.1f}%")

        # --- GRÁFICO DE EVOLUÇÃO (LINHA DE PREVISÃO REATIVADA) ---
        st.subheader("📈 Evolução Temporal: Realizado vs Previsto")
        df_g = df_f.groupby(['ano', 'mes', 'data_ref'])[['realizado_mes', 'previsao_mes']].sum().reset_index()
        df_g['rotulo'] = df_g.apply(lambda x: f"{MESES_NOMES[int(x['mes'])-1]}/{str(int(x['ano']))[2:]}", axis=1)

        fig = go.Figure()
        # Barras do Realizado
        fig.add_trace(go.Bar(
            x=df_g['rotulo'], 
            y=df_g['realizado_mes'], 
            name="Realizado", 
            marker_color='#2E7D32'
        ))
        # Linha da Previsão (A que tinha sumido)
        fig.add_trace(go.Scatter(
            x=df_g['rotulo'], 
            y=df_g['previsao_mes'], 
            name="Previsão Mensal", 
            line=dict(color='#FF9800', width=3, dash='dot'),
            mode='lines+markers'
        ))

        fig.update_layout(
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=0, r=0, t=30, b=0)
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Tabela Detalhada
        with st.expander("📄 Ver Dados Detalhados"):
            st.dataframe(df_f.drop(columns=['data_ref']), use_container_width=True)
            
    # Botão de Download
    csv = df_raw.to_csv(index=False).encode('utf-8')
    st.sidebar.download_button("📥 Baixar Backup CSV", csv, "backup_fiplan.csv", "text/csv")
else:
    st.info("Importe um arquivo FIPLAN para começar.")
