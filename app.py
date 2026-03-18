import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re

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

inicializar_banco()

# --- SIDEBAR: IMPORTAÇÃO ---
with st.sidebar:
    st.header("📥 Gestão de Dados")
    mes_ref = st.selectbox("Mês", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano", value=2026)
    arquivo = st.file_uploader("Upload Excel FIPLAN", type=["xlsx", "csv"])
    
    if arquivo and st.button("🚀 Salvar Dados"):
        if arquivo.name.endswith('.csv'):
            df_backup = pd.read_csv(arquivo)
            conn = sqlite3.connect(DB_NAME)
            df_backup.to_sql('receitas', conn, if_exists='replace', index=False)
            conn.close()
            st.success("Backup restaurado!")
        else:
            df_import = pd.read_excel(arquivo, skiprows=7)
            dados = []
            for _, row in df_import.iterrows():
                cod = str(row.iloc[0]).strip()
                
                # --- FILTRO REFORÇADO: REGRAS DO FIPLAN ---
                # 1. Deve começar com número
                # 2. NÃO pode terminar com .0 ou .00 (Subtotais)
                # 3. Deve ter mais de 10 caracteres (Contas analíticas são longas)
                if re.match(r'^\d', cod) and not cod.endswith('.0') and not cod.endswith('.00') and len(cod) > 10:
                    is_ded = cod.startswith('9')
                    dados.append((int(mes_ref), int(ano_ref), cod, row.iloc[1], 
                                 limpar_valor(row.iloc[3], is_ded), limpar_valor(row.iloc[5], is_ded),
                                 limpar_valor(row.iloc[6], is_ded), limpar_valor(row.iloc[9], is_ded),
                                 limpar_valor(row.iloc[10], is_ded)))
            
            if dados:
                conn = sqlite3.connect(DB_NAME)
                # Limpa o mês/ano atual para evitar duplicidade no "re-upload"
                conn.execute("DELETE FROM receitas WHERE mes = ? AND ano = ?", (int(mes_ref), int(ano_ref)))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?,?,?)", dados)
                conn.commit()
                conn.close()
                st.success(f"Foram importadas {len(dados)} linhas analíticas!")
            else:
                st.warning("Nenhuma conta analítica encontrada. Verifique o formato do arquivo.")
        st.rerun()

# --- DASHBOARD ---
conn = sqlite3.connect(DB_NAME)
df_raw = pd.read_sql("SELECT * FROM receitas", conn)
conn.close()

if not df_raw.empty:
    st.title("📊 Painel Orçamentário")
    
    # Filtros
    c1, c2 = st.columns([1, 2])
    anos_disp = sorted(df_raw['ano'].unique(), reverse=True)
    with c1: anos_sel = st.multiselect("Anos:", anos_disp, default=anos_disp)
    with c2: 
        naturezas = sorted(df_raw['natureza'].unique())
        nat_sel = st.multiselect("Filtrar Naturezas:", naturezas)
    
    df_f = df_raw[df_raw['ano'].isin(anos_sel)].copy()
    if nat_sel: df_f = df_f[df_f['natureza'].isin(nat_sel)]

    if not df_f.empty:
        df_f = df_f.sort_values(['ano', 'mes'])
        
        # KPIs (Soma apenas o último orçado de cada conta única para evitar duplicar orçamentos mensais)
        st.divider()
        k1, k2, k3 = st.columns(3)
        
        orc_total = df_f.groupby(['ano', 'codigo_full'])['orcado_anual'].last().sum()
        real_total = df_f['realizado_mes'].sum()
        
        k1.metric("Orçado Total (Período)", f"R$ {orc_total:,.2f}")
        k2.metric("Realizado Total", f"R$ {real_total:,.2f}")
        k3.metric("Atingimento Global", f"{(real_total/orc_total*100 if orc_total != 0 else 0):.1f}%")

        # Gráfico
        st.subheader("📈 Realizado vs Previsão")
        df_g = df_f.groupby(['ano', 'mes'])[['realizado_mes', 'previsao_mes']].sum().reset_index()
        df_g['label'] = df_g.apply(lambda x: f"{MESES_NOMES[int(x['mes'])-1]}/{str(int(x['ano']))[2:]}", axis=1)

        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_g['label'], y=df_g['realizado_mes'], name="Realizado", marker_color='#2E7D32'))
        fig.add_trace(go.Scatter(x=df_g['label'], y=df_g['previsao_mes'], name="Previsão", 
                                 line=dict(color='#FF9800', width=3, dash='dot')))
        st.plotly_chart(fig, use_container_width=True)
        
    # Botão de Backup na Sidebar
    csv = df_raw.to_csv(index=False).encode('utf-8')
    st.sidebar.download_button("📥 Baixar Backup CSV", csv, "backup.csv", "text/csv")
else:
    st.info("Importe um arquivo FIPLAN para começar.")
