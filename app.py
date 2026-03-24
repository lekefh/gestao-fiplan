import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re
import io

# --- CONFIGURAÇÃO ---
DB_NAME = 'dados_gestao_integrada.db'
st.set_page_config(page_title="FIPLAN - GESTÃO INTEGRADA", layout="wide")

MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
MESES_MAPA = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARÇO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6,
    "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12
}
BIMESTRES = {
    "1º Bimestre (Jan-Fev)": [1, 2],
    "2º Bimestre (Mar-Abr)": [3, 4],
    "3º Bimestre (Mai-Jun)": [5, 6],
    "4º Bimestre (Jul-Ago)": [7, 8],
    "5º Bimestre (Set-Out)": [9, 10],
    "6º Bimestre (Nov-Dez)": [11, 12]
}
CATEGORIAS_REC = ["Receita Tributária", "Receita Patrimonial", "Receita de Serviços", "Repasses Correntes", "Demais Receitas"]

st.markdown("<style>[data-testid='stMetricValue'] { font-size: 1.4rem !important; font-weight: 700; }</style>", unsafe_allow_html=True)

# --- FUNÇÕES DE BANCO E LIMPEZA ---
def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS receitas (mes INTEGER, ano INTEGER, codigo_full TEXT, natureza TEXT, orcado REAL, realizado REAL, previsao REAL, categoria TEXT DEFAULT 'Não Classificada')''')
    try: conn.execute("ALTER TABLE receitas ADD COLUMN categoria TEXT DEFAULT 'Não Classificada'")
    except: pass
    conn.execute('''CREATE TABLE IF NOT EXISTS despesas (mes INTEGER, ano INTEGER, uo TEXT, funcao TEXT, subfuncao TEXT, programa TEXT, projeto TEXT, natureza TEXT, fonte TEXT, orcado_inicial REAL, cred_autorizado REAL, empenhado REAL, liquidado REAL, pago REAL)''')
    conn.close()

def limpar_f(v):
    if pd.isna(v) or v == "" or v == "-": return 0.0
    if isinstance(v, (int, float)): return float(v)
    v = str(v).replace('"', '').replace('.', '').replace(',', '.')
    try: return float(v)
    except: return 0.0

def normalizar_chave(v):
    if pd.isna(v): return ""
    s = str(v).strip().replace('"', '')
    try:
        f = float(s)
        if f.is_integer(): return str(int(f))
    except: pass
    return s

def gerar_excel_lrf(df_final):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Relatorio_LRF')
    return output.getvalue()

inicializar_banco()

# --- SIDEBAR (IMPORTAÇÃO E BACKUP) ---
with st.sidebar:
    st.subheader("📥 Importar Dados")
    tipo_dado = st.radio("Tipo:", ["Receita", "Despesa"])
    arquivo = st.file_uploader(f"Arquivo {tipo_dado}", type=["xlsx"])
    
    if arquivo and st.button("🚀 Processar Dados"):
        m_final = 1
        df_scan = pd.read_excel(arquivo, nrows=10, header=None)
        for r in range(len(df_scan)):
            for celula in df_scan.iloc[r]:
                for nome, num in MESES_MAPA.items():
                    if nome in str(celula).upper(): m_final = num
        
        conn = sqlite3.connect(DB_NAME)
        if tipo_dado == "Receita":
            df = pd.read_excel(arquivo, skiprows=7)
            dados = []
            for _, row in df.iterrows():
                cod = str(row.iloc[0]).strip().replace('"', '')
                if re.match(r'^\d', cod) and cod[-1] != '0':
                    real = limpar_f(row.iloc[6])
                    if cod.startswith('9'): real = -abs(real)
                    cur = conn.execute("SELECT categoria FROM receitas WHERE codigo_full = ?", (cod,))
                    r_cat = cur.fetchone()
                    cat_atual = r_cat[0] if r_cat else "Não Classificada"
                    dados.append((m_final, 2026, cod, str(row.iloc[1]).replace('"', ''), limpar_f(row.iloc[3]), real, limpar_f(row.iloc[5]), cat_atual))
            conn.execute("DELETE FROM receitas WHERE ano=2026 AND mes=?", (m_final,))
            conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?,?)", dados)
        else:
            df = pd.read_excel(arquivo, skiprows=6); df.columns = df.columns.str.strip().str.upper()
            linhas = []
            for _, row in df.iterrows():
                uo, ug = normalizar_chave(row.get('UO', '')), normalizar_chave(row.get('UG', ''))
                if uo != "":
                    elem = limpar_f(row.get('ELEMENTO', 0))
                    tem_execucao = (ug != '0' and elem != 0)
                    linhas.append({'uo': uo, 'funcao': normalizar_chave(row.get('FUNÇÃO', '')), 'subfuncao': normalizar_chave(row.get('SUBFUNÇÃO', '')), 'programa': normalizar_chave(row.get('PROGRAMA', '')), 'projeto': normalizar_chave(row.get('PAOE', '')), 'natureza': normalizar_chave(row.get('NATUREZA DESPESA', '')), 'fonte': normalizar_chave(row.get('FONTE', '')), 'orcado_inicial': limpar_f(row.get('ORÇADO INICIAL', 0)), 'cred_autorizado': limpar_f(row.get('CRÉDITO AUTORIZADO', 0)), 'empenhado_cum': limpar_f(row.get('EMPENHADO', 0)) if tem_execucao else 0.0, 'liquidado_cum': limpar_f(row.get('LIQUIDADO', 0)) if tem_execucao else 0.0, 'pago_cum': limpar_f(row.get('PAGO', 0)) if tem_execucao else 0.0})
            
            if linhas:
                df_mes = pd.DataFrame(linhas); chaves = ['uo', 'funcao', 'subfuncao', 'programa', 'projeto', 'natureza', 'fonte']
                df_mes = df_mes.groupby(chaves, as_index=False).agg({'orcado_inicial': 'sum', 'cred_autorizado': 'sum', 'empenhado_cum': 'sum', 'liquidado_cum': 'sum', 'pago_cum': 'sum'})
                if m_final > 1:
                    df_ant = pd.read_sql("SELECT uo, funcao, subfuncao, programa, projeto, natureza, fonte, SUM(empenhado) as empenhado_ant, SUM(liquidado) as liquidado_ant, SUM(pago) as pago_ant FROM despesas WHERE ano=2026 AND mes < ? GROUP BY uo, funcao, subfuncao, programa, projeto, natureza, fonte", conn, params=(m_final,))
                    df_mes = df_mes.merge(df_ant, on=chaves, how='left').fillna(0)
                else:
                    df_mes['empenhado_ant'] = 0; df_mes['liquidado_ant'] = 0; df_mes['pago_ant'] = 0
                
                df_mes['empenhado'] = df_mes['empenhado_cum'] - df_mes['empenhado_ant']
                df_mes['liquidado'] = df_mes['liquidado_cum'] - df_mes['liquidado_ant']
                df_mes['pago'] = df_mes['pago_cum'] - df_mes['pago_ant']
                
                dados = [(m_final, 2026, r['uo'], r['funcao'], r['subfuncao'], r['programa'], r['projeto'], r['natureza'], r['fonte'], r['orcado_inicial'], r['cred_autorizado'], r['empenhado'], r['liquidado'], r['pago']) for _, r in df_mes.iterrows()]
                conn.execute("DELETE FROM despesas WHERE ano=2026 AND mes=?", (m_final,))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
        conn.commit(); conn.close(); st.rerun()

# --- CARGA E ABAS ---
conn = sqlite3.connect(DB_NAME)
df_rec = pd.read_sql("SELECT * FROM receitas", conn)
df_desp = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

t1, t2, t3, t4 = st.tabs(["📊 Receitas", "💸 Despesas", "⚖️ Comparativo", "📄 Relatórios LRF"])

with t1:
    if not df_rec.empty:
        with st.expander("🏷️ Classificar Categorias"):
            c1, c2, c3 = st.columns([2, 2, 1])
            sel_n = c1.selectbox("Natureza:", sorted(df_rec['natureza'].unique()))
            sel_c = c2.selectbox("Categoria:", CATEGORIAS_REC)
            if c3.button("Salvar"):
                conn = sqlite3.connect(DB_NAME); conn.execute("UPDATE receitas SET categoria=? WHERE natureza=?", (sel_c, sel_n)); conn.commit(); conn.close(); st.rerun()
        
        # Filtros e Gráficos da Receita (Lógica Verde/Pontilhada Restaurada)
        ms_r = st.multiselect("Meses:", sorted(df_rec['mes'].unique()), default=df_rec['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="ms_r")
        df_rf = df_rec[df_rec['mes'].isin(ms_r)]
        if not df_rf.empty:
            v_real = df_rf['realizado'].sum()
            v_orc = df_rec[df_rec['mes'] == max(ms_r)].groupby('codigo_full')['orcado'].max().sum()
            k1, k2, k3 = st.columns(3); k1.metric("Orçado", f"R$ {v_orc:,.2f}"); k2.metric("Realizado", f"R$ {v_real:,.2f}"); k3.metric("Atingimento", f"{(v_real/v_orc*100):.1f}%")
            
            df_g = df_rf.groupby('mes').agg({'realizado':'sum'}).reset_index()
            df_g['previsao'] = [df_rf[df_rf['mes']==m].groupby('codigo_full')['previsao'].max().sum() for m in df_g['mes']]
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_g['mes'].map(lambda x: MESES_NOMES[x-1]), y=df_g['realizado'], name="Realizado", marker_color='#2E7D32'))
            fig.add_trace(go.Scatter(x=df_g['mes'].map(lambda x: MESES_NOMES[x-1]), y=df_g['previsao'], name="Previsão", line=dict(color='#FF9800', dash='dot')))
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_rf[['categoria', 'natureza', 'realizado', 'orcado']].style.format({'realizado': '{:,.2f}', 'orcado': '{:,.2f}'}), width='stretch')

with t2:
    if not df_desp.empty:
        ms_d = st.multiselect("Meses:", sorted(df_desp['mes'].unique()), default=df_desp['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="ms_d")
        df_df = df_desp[df_desp['mes'].isin(ms_d)]
        if not df_df.empty:
            m_max = max(ms_d); col_ch = ['funcao', 'subfuncao', 'programa', 'projeto', 'fonte', 'natureza']
            df_ex = df_df.groupby(col_ch, as_index=False)[['empenhado', 'liquidado', 'pago']].sum()
            df_at = df_df[df_df['mes']==m_max].groupby(col_ch, as_index=False)[['cred_autorizado']].sum()
            df_v = df_ex.merge(df_at, on=col_ch, how='left').fillna(0)
            k1, k2, k3, k4 = st.columns(4); k1.metric("Crédito", f"R$ {df_v['cred_autorizado'].sum():,.2f}"); k2.metric("Empenhado", f"R$ {df_v['empenhado'].sum():,.2f}"); k3.metric("Liquidado", f"R$ {df_v['liquidado'].sum():,.2f}"); k4.metric("Pago", f"R$ {df_v['pago'].sum():,.2f}")
            st.dataframe(df_v.style.format({'cred_autorizado': '{:,.2f}', 'empenhado': '{:,.2f}', 'liquidado': '{:,.2f}', 'pago': '{:,.2f}'}), width='stretch')

with t3:
    st.subheader("⚖️ Confronto Financeiro")
    if not df_rec.empty and not df_desp.empty:
        ms_c = st.multiselect("Meses:", range(1,13), default=df_rec['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="ms_c")
        tr = df_rec[df_rec['mes'].isin(ms_c)]['realizado'].sum()
        tp = df_desp[df_desp['mes'].isin(ms_c)]['pago'].sum()
        st.info(f"**Superávit Financeiro:** R$ {tr - tp:,.2f}")
        fig_comp = go.Figure([go.Bar(name='Receita', x=['Total'], y=[tr], marker_color='green'), go.Bar(name='Despesa Paga', x=['Total'], y=[tp], marker_color='red')])
        st.plotly_chart(fig_comp, use_container_width=True)

with t4:
    st.subheader("📄 Relatórios Bimestrais LRF")
    bim_sel = st.selectbox("Escolha o Bimestre:", list(BIMESTRES.keys()))
    m_bim = BIMESTRES[bim_sel]; m_acum = list(range(1, max(m_bim)+1))
    
    if st.button("📊 Gerar Anexos LRF"):
        # Exemplo Anexo II: Função/Subfunção
        df_a2 = df_desp[df_desp['mes'].isin(m_acum)].groupby(['funcao', 'subfuncao']).agg({'cred_autorizado':'max', 'empenhado':'sum', 'liquidado':'sum'}).reset_index()
        st.download_button("📥 Baixar Anexo II (Excel)", data=gerar_excel_lrf(df_a2), file_name=f"LRF_Anexo2_{bim_sel}.xlsx")
        st.dataframe(df_a2)
