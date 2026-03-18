import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import plotly.graph_objects as go
import re

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Gestão Orçamentária Pro", layout="wide")

MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# --- CONEXÃO COM GOOGLE SHEETS ---
# Lembrar de configurar o link nos Secrets do Streamlit Cloud
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados():
    try:
        # Tenta ler a planilha. ttl="0" força a atualização imediata dos dados
        return conn.read(ttl="0")
    except:
        # Se a planilha estiver vazia, cria um esqueleto
        return pd.DataFrame(columns=[
            'mes', 'ano', 'codigo_full', 'natureza', 
            'orcado_anual', 'previsao_mes', 'realizado_mes', 
            'previsao_acumulada', 'realizado_acumulado'
        ])

def limpar_valor(valor, eh_dedutora=False):
    if pd.isna(valor) or valor == "" or valor == "-":
        return 0.0
    if isinstance(valor, str):
        valor = valor.replace('.', '').replace(',', '.')
    try:
        num = float(valor)
        # Se for dedutora (começa com 9), o valor deve ser negativo para abater do total
        return num * -1 if eh_dedutora else num
    except:
        return 0.0

# --- INTERFACE PRINCIPAL ---
st.title("📊 Gestão Financeira - FIPLAN & Google Sheets")

# --- SIDEBAR: IMPORTAÇÃO DE DADOS ---
with st.sidebar:
    st.header("📥 Importar Dados")
    mes_ref = st.selectbox("Mês do Arquivo", range(1, 13), index=1, format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano", value=2026)
    arquivo = st.file_uploader("Selecione o Excel FIP 729", type=["xlsx"])
    
    if arquivo and st.button("🚀 Salvar e Atualizar Planilha"):
        try:
            df_import = pd.read_excel(arquivo, skiprows=7)
            novos_dados = []
            
            for _, row in df_import.iterrows():
                cod = str(row.iloc[0]).strip()
                
                # FILTRO ANALÍTICO: Deve começar com número, ter tamanho real e não ser subtotal (.0)
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
                # UPSERT: Remove dados antigos do mesmo mês/ano antes de inserir os novos
                if not df_atual.empty:
                    df_atual = df_atual[~((df_atual['mes'] == mes_ref) & (df_atual['ano'] == ano_ref))]
                
                df_final = pd.concat([df_atual, pd.DataFrame(novos_dados)], ignore_index=True)
                
                # Envia para o Google Sheets
                conn.update(data=df_final)
                st.success(f"Dados de {MESES_NOMES[mes_ref-1]}/{ano_ref} salvos com sucesso!")
                st.rerun()
            else:
                st.warning("Nenhuma linha analítica válida encontrada no arquivo.")
        except Exception as e:
            st.error(f"Erro no processamento: {e}")

# --- DASHBOARD DE VISUALIZAÇÃO ---
df_raw = carregar_dados()

if not df_raw.empty:
    st.markdown("### 🔍 Filtros Globais")
    
    # 1. Filtro de Natureza (Multiselect)
    todas_naturezas = sorted(df_raw['natureza'].unique())
    naturezas_sel = st.multiselect("Filtrar por Natureza:", options=todas_naturezas)
    
    df_filtrado_base = df_raw.copy()
    if naturezas_sel:
        df_filtrado_base = df_filtrado_base[df_filtrado_base['natureza'].isin(naturezas_sel)]

    # 2. Lógica Multiano com Sliders independentes
    anos_disp = sorted(df_filtrado_base['ano'].unique(), reverse=True)
    
    for ano in anos_disp:
        with st.expander(f"📅 Relatório Anual - {ano}", expanded=True):
            df_ano = df_filtrado_base[df_filtrado_base['ano'] == ano]
            meses_disp = sorted(df_ano['mes'].unique())
            
            if len(meses_disp) > 1:
                start_m, end_m = st.select_slider(
                    f"Selecione o intervalo de {ano}:",
                    options=meses_disp,
                    value=(min(meses_disp), max(meses_disp)),
                    format_func=lambda x: MESES_NOMES[x-1],
                    key=f"slider_{ano}"
                )
                df_f = df_ano[(df_ano['mes'] >= start_m) & (df_ano['mes'] <= end_m)]
            else:
                df_f = df_ano
                st.info(f"Dados apenas para {MESES_NOMES[meses_disp[0]-1]} em {ano}")

            # KPIs do Ano/Período
            k1, k2, k3 = st.columns(3)
            # Orçado Anual (Líquido): Pega o último valor orçado registrado no período
            orc_total = df_f.sort_values('mes').groupby('codigo_full')['orcado_anual'].last().sum()
            real_total = df_f['realizado_mes'].sum()
            
            k1.metric(f"Orçado Anual {ano}", f"R$ {orc_total:,.2f}")
            k2.metric(f"Realizado no Período", f"R$ {real_total:,.2f}")
            k3.metric("Atingimento", f"{(real_total/orc_total*100 if orc_total != 0 else 0):.1f}%")

            # Gráfico de Evolução
            df_g = df_f.groupby('mes')[['realizado_mes', 'previsao_mes']].sum().reset_index()
            fig = go.Figure()
            fig.add_trace(go.Bar(x=[MESES_NOMES[m-1] for m in df_g['mes']], y=df_g['realizado_mes'], name="Realizado", marker_color='green'))
            fig.add_trace(go.Scatter(x=[MESES_NOMES[m-1] for m in df_g['mes']], y=df_g['previsao_mes'], name="Previsto", line=dict(color='orange', dash='dot')))
            st.plotly_chart(fig, width='stretch')
            
            # Tabela de Conferência
            st.dataframe(df_f.drop(columns=['ano']), width='stretch')
else:
    st.info("Nenhum dado encontrado no Google Sheets. Faça a primeira importação.")
