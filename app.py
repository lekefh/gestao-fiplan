import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import plotly.graph_objects as go
import re

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Gestão Orçamentária Pro", layout="wide")
MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# --- CONEXÃO COM GOOGLE SHEETS ---
def conectar_google():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        # Pega as credenciais
        creds_dict = dict(st.secrets["gcp_service_account"])
        
        # O TRUQUE: Garante que as quebras de linha da chave sejam lidas corretamente
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(credentials)
        return client.open("dados-FIPLAN").sheet1
    except Exception as e:
        st.error(f"Erro de conexão com Google Sheets: {e}")
        return None

def carregar_dados():
    sheet = conectar_google()
    if sheet:
        try:
            dados = sheet.get_all_records()
            return pd.DataFrame(dados) if dados else pd.DataFrame()
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def limpar_valor(valor, eh_dedutora=False):
    if pd.isna(valor) or valor == "" or valor == "-": return 0.0
    if isinstance(valor, str): valor = valor.replace('.', '').replace(',', '.')
    try:
        num = float(valor)
        return num * -1 if eh_dedutora else num
    except: return 0.0

# --- INTERFACE ---
st.title("📊 Gestão Orçamentária Profissional")

# --- SIDEBAR: IMPORTAÇÃO ---
with st.sidebar:
    st.header("📥 Importar Dados")
    mes_ref = st.selectbox("Mês", range(1, 13), index=0, format_func=lambda x: MESES_NOMES[x-1])
    ano_ref = st.number_input("Ano", value=2026)
    arquivo = st.file_uploader("Excel FIP 729", type=["xlsx"])
    
    if arquivo and st.button("🚀 Salvar na Planilha"):
        try:
            df_import = pd.read_excel(arquivo, skiprows=7)
            novos_rows = []
            for _, row in df_import.iterrows():
                cod = str(row.iloc[0]).strip()
                if re.match(r'^\d', cod) and not cod.endswith('.0') and len(cod) > 12:
                    is_ded = cod.startswith('9')
                    novos_rows.append({
                        'mes': int(mes_ref), 'ano': int(ano_ref), 'codigo_full': cod, 'natureza': row.iloc[1],
                        'orcado_anual': limpar_valor(row.iloc[3], is_ded),
                        'previsao_mes': limpar_valor(row.iloc[5], is_ded),
                        'realizado_mes': limpar_valor(row.iloc[6], is_ded),
                        'previsao_acumulada': limpar_valor(row.iloc[9], is_ded),
                        'realizado_acumulado': limpar_valor(row.iloc[10], is_ded)
                    })
            
            if novos_rows:
                df_atual = carregar_dados()
                if not df_atual.empty:
                    df_atual = df_atual[~((df_atual['mes'] == mes_ref) & (df_atual['ano'] == ano_ref))]
                
                df_final = pd.concat([df_atual, pd.DataFrame(novos_rows)], ignore_index=True)
                
                sheet = conectar_google()
                if sheet:
                    sheet.clear()
                    sheet.update([df_final.columns.values.tolist()] + df_final.values.tolist())
                    st.success("Dados salvos com sucesso!")
                    st.rerun()
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

# --- DASHBOARD ---
df_raw = carregar_dados()

if not df_raw.empty:
    # Filtros Globais
    c1, c2 = st.columns([1, 2])
    anos_disp = sorted(df_raw['ano'].unique(), reverse=True)
    with c1: anos_sel = st.multiselect("Selecione os Anos:", anos_disp, default=anos_disp)
    with c2: 
        naturezas = sorted(df_raw['natureza'].unique())
        nat_sel = st.multiselect("Filtrar Naturezas:", naturezas)
    
    df_f = df_raw[df_raw['ano'].isin(anos_sel)].copy()
    if nat_sel: df_f = df_f[df_f['natureza'].isin(nat_sel)]

    if not df_f.empty:
        df_f = df_f.sort_values(['ano', 'mes'])
        
        # KPIs Consolidados
        st.divider()
        k1, k2, k3 = st.columns(3)
        # Orçado: Pega o último orçado de cada código por ano selecionado
        orc = df_f.groupby(['ano', 'codigo_full'])['orcado_anual'].last().sum()
        real = df_f['realizado_mes'].sum()
        k1.metric("Orçado Total", f"R$ {orc:,.2f}")
        k2.metric("Realizado Total", f"R$ {real:,.2f}")
        k3.metric("Atingimento", f"{(real/orc*100 if orc != 0 else 0):.1f}%")

        # Gráfico Multiano com Previsão
        st.subheader("📈 Evolução Temporal (Realizado vs Previsão)")
        df_g = df_f.groupby(['ano', 'mes'])[['realizado_mes', 'previsao_mes']].sum().reset_index()
        df_g['label'] = df_g.apply(lambda x: f"{MESES_NOMES[int(x['mes'])-1]}/{str(int(x['ano']))[2:]}", axis=1)

        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_g['label'], y=df_g['realizado_mes'], name="Realizado", marker_color='#2E7D32'))
        fig.add_trace(go.Scatter(x=df_g['label'], y=df_g['previsao_mes'], name="Previsão", 
                                 line=dict(color='#FF9800', width=3, dash='dot'), mode='lines+markers'))
        
        fig.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("📄 Ver Detalhamento"):
            st.dataframe(df_f, use_container_width=True)
else:
    st.info("Banco de dados vazio. Importe um arquivo na barra lateral.")
