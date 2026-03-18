import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import plotly.graph_objects as go
import re

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Gestão Orçamentária Pro", layout="wide")

MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# --- CONEXÃO COM GOOGLE SHEETS ---
# Certifique-se de que a planilha está como "Editor" para qualquer pessoa com o link
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados():
    try:
        # ttl=0 força o app a buscar os dados mais recentes na planilha sempre
        return conn.read(ttl=0)
    except:
        return pd.DataFrame(columns=[
            'mes', 'ano', 'codigo_full', 'natureza', 
            'orcado_anual', 'previsao_mes', 'realizado_mes', 
            'previsao_acumulada', 'realizado_acumulado'
        ])

def limpar_valor(valor, eh_dedutora=False):
    if pd.isna(valor) or valor == "" or valor == "-": return 0.0
    if isinstance(valor, str): valor = valor.replace('.', '').replace(',', '.')
    try:
        num = float(valor)
        return num * -1 if eh_dedutora else num
    except: return 0.0

# --- INTERFACE PRINCIPAL ---
st.title("📊 Gestão Financeira Profissional")

# --- SIDEBAR: IMPORTAÇÃO ---
with st.sidebar:
    st.header("📥 Importar Dados FIPLAN")
    mes_ref = st.selectbox("Mês de Referência", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano de Referência", value=2026)
    arquivo = st.file_uploader("Selecione o arquivo Excel (FIP 729)", type=["xlsx"])
    
    if arquivo and st.button("🚀 Salvar na Planilha Google"):
        try:
            df_import = pd.read_excel(arquivo, skiprows=7)
            novos_dados = []
            
            for _, row in df_import.iterrows():
                cod = str(row.iloc[0]).strip()
                # Filtro para pegar apenas linhas analíticas válidas
                if re.match(r'^\d', cod) and not cod.endswith('.0') and not cod.endswith('.00') and len(cod) > 12:
                    is_ded = cod.startswith('9')
                    novos_dados.append({
                        'mes': int(mes_ref),
                        'ano': int(ano_ref),
                        'codigo_full': cod,
                        'natureza': row.iloc[1],
                        'orcado_anual': limpar_valor(row.iloc[3], is_ded),
                        'previsao_mes': limpar_valor(row.iloc[5], is_ded),
                        'realizado_mes': limpar_valor(row.iloc[6], is_ded),
                        'previsao_acumulada': limpar_valor(row.iloc[9], is_ded),
                        'realizado_acumulado': limpar_valor(row.iloc[10], is_ded)
                    })
            
            if novos_dados:
                df_atual = carregar_dados()
                # Remove dados antigos do mesmo mês/ano para evitar duplicidade
                if not df_atual.empty:
                    df_atual = df_atual[~((df_atual['mes'] == mes_ref) & (df_atual['ano'] == ano_ref))]
                
                df_final = pd.concat([df_atual, pd.DataFrame(novos_dados)], ignore_index=True)
                
                # ENVIO PARA O GOOGLE SHEETS
                conn.update(data=df_final)
                st.success(f"Dados de {MESES_NOMES[mes_ref-1]}/{ano_ref} atualizados com sucesso!")
                st.rerun()
        except Exception as e:
            st.error(f"Erro ao processar: {e}")

# --- DASHBOARD DE VISUALIZAÇÃO ---
df_raw = carregar_dados()

if not df_raw.empty:
    st.markdown("### 🔍 Filtros de Análise")
    
    c_filt1, c_filt2 = st.columns([1, 2])
    with c_filt1:
        anos_disp = sorted(df_raw['ano'].unique(), reverse=True)
        anos_sel = st.multiselect("Anos em Análise:", options=anos_disp, default=anos_disp)
    
    with c_filt2:
        naturezas = sorted(df_raw['natureza'].unique())
        sel_naturezas = st.multiselect("Filtrar Naturezas:", options=naturezas)
    
    # Aplicação dos filtros
    df_f = df_raw[df_raw['ano'].isin(anos_sel)].copy()
    if sel_naturezas:
        df_f = df_f[df_f['natureza'].isin(sel_naturezas)]

    if not df_f.empty:
        # Ordenação cronológica para o gráfico
        df_f = df_f.sort_values(['ano', 'mes'])
        
        # KPIs Consolidados
        st.divider()
        k1, k2, k3 = st.columns(3)
        orc_total = df_f.groupby(['ano', 'codigo_full'])['orcado_anual'].last().sum()
        real_total = df_f['realizado_mes'].sum()
        
        k1.metric("Orçado Total (Período)", f"R$ {orc_total:,.2f}")
        k2.metric("Realizado Total", f"R$ {real_total:,.2f}")
        k3.metric("Atingimento", f"{(real_total/orc_total*100 if orc_total != 0 else 0):.1f}%")

        # --- GRÁFICO DE EVOLUÇÃO ---
        st.subheader("📈 Realizado vs Previsão Mensal")
        df_g = df_f.groupby(['ano', 'mes'])[['realizado_mes', 'previsao_mes']].sum().reset_index()
        df_g['label'] = df_g.apply(lambda x: f"{MESES_NOMES[int(x['mes'])-1]}/{str(int(x['ano']))[2:]}", axis=1)

        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_g['label'], y=df_g['realizado_mes'], name="Realizado", marker_color='#2E7D32'))
        fig.add_trace(go.Scatter(x=df_g['label'], y=df_g['previsao_mes'], name="Previsão (Meta)", 
                                 line=dict(color='#FF9800', width=3, dash='dot'), mode='lines+markers'))

        fig.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("📄 Ver Planilha de Dados"):
            st.dataframe(df_f, use_container_width=True)
else:
    st.info("O banco de dados está vazio. Importe um arquivo na barra lateral para começar.")
