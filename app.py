import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re
import io
import unicodedata

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

# --- FUNÇÕES AUXILIARES ---
def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS receitas (mes INTEGER, ano INTEGER, codigo_full TEXT, natureza TEXT, orcado REAL, realizado REAL, previsao REAL, categoria TEXT DEFAULT 'Não Classificada')''')
    conn.execute('''CREATE TABLE IF NOT EXISTS despesas (mes INTEGER, ano INTEGER, uo TEXT, ug TEXT, funcao TEXT, subfuncao TEXT, programa TEXT, projeto TEXT, natureza TEXT, fonte TEXT, orcado_inicial REAL, cred_autorizado REAL, empenhado REAL, liquidado REAL, pago REAL)''')
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
        return str(int(f)) if f.is_integer() else s
    except: return s

def gerar_excel_lrf(df_final):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Anexo_LRF')
    return output.getvalue()

inicializar_banco()

# --- SIDEBAR ---
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
                uo = normalizar_chave(row.get('UO', ''))
                ug = normalizar_chave(row.get('UG', ''))
                if uo != "":
                    elem = limpar_f(row.get('ELEMENTO', 0)); tem_ex = (ug != '0' and elem != 0)
                    linhas.append({'uo':uo, 'ug':ug, 'funcao':normalizar_chave(row.get('FUNÇÃO', '')), 'subfuncao':normalizar_chave(row.get('SUBFUNÇÃO', '')), 'programa':normalizar_chave(row.get('PROGRAMA', '')), 'projeto':normalizar_chave(row.get('PAOE', '')), 'natureza':normalizar_chave(row.get('NATUREZA DESPESA', '')), 'fonte':normalizar_chave(row.get('FONTE', '')), 'orc_ini':limpar_f(row.get('ORÇADO INICIAL', 0)), 'cred_aut':limpar_f(row.get('CRÉDITO AUTORIZADO', 0)), 'emp_cum':limpar_f(row.get('EMPENHADO', 0)) if tem_ex else 0.0, 'liq_cum':limpar_f(row.get('LIQUIDADO', 0)) if tem_ex else 0.0, 'pag_cum':limpar_f(row.get('PAGO', 0)) if tem_ex else 0.0})
            
            if linhas:
                df_mes = pd.DataFrame(linhas); chaves = ['uo', 'ug', 'funcao', 'subfuncao', 'programa', 'projeto', 'natureza', 'fonte']
                df_mes = df_mes.groupby(chaves, as_index=False).agg({'orc_ini':'sum', 'cred_aut':'sum', 'emp_cum':'sum', 'liq_cum':'sum', 'pag_cum':'sum'})
                if m_final > 1:
                    df_ant = pd.read_sql("SELECT uo, ug, funcao, subfuncao, programa, projeto, natureza, fonte, SUM(empenhado) as e_ant, SUM(liquidado) as l_ant, SUM(pago) as p_ant FROM despesas WHERE ano=2026 AND mes < ? GROUP BY uo, ug, funcao, subfuncao, programa, projeto, natureza, fonte", conn, params=(m_final,))
                    df_mes = df_mes.merge(df_ant, on=chaves, how='left').fillna(0)
                else:
                    df_mes['e_ant'] = 0; df_mes['l_ant'] = 0; df_mes['p_ant'] = 0
                dados = [(m_final, 2026, r['uo'], r['ug'], r['funcao'], r['subfuncao'], r['programa'], r['projeto'], r['natureza'], r['fonte'], r['orc_ini'], r['cred_aut'], r['emp_cum']-r['e_ant'], r['liq_cum']-r['l_ant'], r['pag_cum']-r['p_ant']) for _, r in df_mes.iterrows()]
                conn.execute("DELETE FROM despesas WHERE ano=2026 AND mes=?", (m_final,))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
        conn.commit(); conn.close(); st.rerun()

    st.divider()
    st.subheader("💾 Backup")
    conn = sqlite3.connect(DB_NAME); df_bkp = pd.read_sql("SELECT * FROM receitas", conn); conn.close()
    if not df_bkp.empty:
        st.download_button("📥 Baixar Backup", data=df_bkp.to_csv(index=False).encode('utf-8'), file_name="backup.csv", mime="text/csv")
    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DELETE FROM receitas"); conn.execute("DELETE FROM despesas"); conn.commit(); conn.close(); st.rerun()

# --- CARGA ---
conn = sqlite3.connect(DB_NAME)
df_rec = pd.read_sql("SELECT * FROM receitas", conn)
df_desp = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

tab1, tab2, tab3, tab4 = st.tabs(["📊 Receitas", "💸 Despesas", "⚖️ Comparativo", "📄 Relatórios LRF"])

with tab1:
    if not df_rec.empty:
        with st.expander("🏷️ Classificar Categorias"):
            c1, c2, c3 = st.columns([2, 2, 1])
            sel_n = c1.selectbox("Natureza:", sorted(df_rec['natureza'].unique()))
            sel_c = c2.selectbox("Categoria:", CATEGORIAS_REC)
            if c3.button("Salvar"):
                conn = sqlite3.connect(DB_NAME); conn.execute("UPDATE receitas SET categoria=? WHERE natureza=?", (sel_c, sel_n)); conn.commit(); conn.close(); st.rerun()
        f1, f2, f3 = st.columns(3)
        ms_r = f1.multiselect("Meses:", sorted(df_rec['mes'].unique()), default=df_rec['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="msr")
        ct_r = f2.multiselect("Categoria:", sorted(df_rec['categoria'].unique()), default=sorted(df_rec['categoria'].unique()), key="ctr")
        nt_r = f3.multiselect("Natureza:", sorted(df_rec['natureza'].unique()), key="ntr")
        df_rf = df_rec[(df_rec['mes'].isin(ms_r)) & (df_rec['categoria'].isin(ct_r))]
        if nt_r: df_rf = df_rf[df_rf['natureza'].isin(nt_r)]
        if not df_rf.empty:
            v_real = df_rf['realizado'].sum(); v_orc = df_rec[df_rec['mes'] == max(ms_r)].groupby('codigo_full')['orcado'].max().sum()
            k1, k2, k3 = st.columns(3); k1.metric("Orçado", f"R$ {v_orc:,.2f}"); k2.metric("Realizado", f"R$ {v_real:,.2f}"); k3.metric("Atingimento", f"{(v_real/v_orc*100 if v_orc!=0 else 0):.1f}%")
            df_g = df_rf.groupby('mes').agg({'realizado':'sum'}).reset_index()
            df_g['previsao'] = [df_rf[df_rf['mes'] == m].groupby('codigo_full')['previsao'].max().sum() for m in df_g['mes']]
            fig = go.Figure(); fig.add_trace(go.Bar(x=df_g['mes'].map(lambda x: MESES_NOMES[x-1]), y=df_g['realizado'], name="Realizado", marker_color='#2E7D32'))
            fig.add_trace(go.Scatter(x=df_g['mes'].map(lambda x: MESES_NOMES[x-1]), y=df_g['previsao'], name="Previsão", line=dict(color='#FF9800', width=3, dash='dot')))
            fig.update_layout(height=350, margin=dict(l=0,r=0,t=30,b=0), legend=dict(orientation="h", y=1.02, x=1)); st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_rf[['categoria', 'natureza', 'realizado', 'orcado']].style.format({'realizado': '{:,.2f}', 'orcado': '{:,.2f}'}), width='stretch')

with tab2:
    if not df_desp.empty:
        f1, f2, f3 = st.columns(3)
        ms_d = f1.multiselect("Meses:", sorted(df_desp['mes'].unique()), default=df_desp['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1], key="msd")
        ug_d = f2.multiselect("UG:", sorted(df_desp['ug'].unique()), default=sorted(df_desp['ug'].unique()), key="ugd")
        fs_d = f3.multiselect("Função:", sorted(df_desp['funcao'].unique()), key="fsd")
        f4, f5, f6 = st.columns(3)
        sf_d = f4.multiselect("Subfunção:", sorted(df_desp['subfuncao'].unique()), key="sfd")
        ps_d = f5.multiselect("Programa:", sorted(df_desp['programa'].unique()), key="psd")
        bd_d = f6.text_input("Natureza (Contém):", key="bdd")
        
        df_f = df_desp[(df_desp['mes'].isin(ms_d)) & (df_desp['ug'].isin(ug_d))]
        if fs_d: df_f = df_f[df_f['funcao'].isin(fs_d)]
        if sf_d: df_f = df_f[df_f['subfuncao'].isin(sf_d)]
        if ps_d: df_f = df_f[df_f['programa'].isin(ps_d)]
        if bd_d: df_f = df_f[df_f['natureza'].str.contains(bd_d, case=False, na=False)]
        
        if not df_f.empty:
            m_max = max(ms_d); ch = ['ug', 'funcao', 'subfuncao', 'programa', 'projeto', 'natureza', 'fonte']
            df_ex = df_f.groupby(ch, as_index=False)[['empenhado', 'liquidado', 'pago']].sum()
            df_at = df_f[df_f['mes']==m_max].groupby(ch, as_index=False)[['cred_autorizado']].sum()
            df_v = df_ex.merge(df_at, on=ch, how='left').fillna(0)
            k1, k2, k3, k4 = st.columns(4); k1.metric("Créd. Aut.", f"R$ {df_v['cred_autorizado'].sum():,.2f}"); k2.metric("Empenhado", f"R$ {df_v['empenhado'].sum():,.2f}"); k3.metric("Liquidado", f"R$ {df_v['liquidado'].sum():,.2f}"); k4.metric("Pago", f"R$ {df_v['pago'].sum():,.2f}")
            st.dataframe(df_v[['ug', 'funcao', 'subfuncao', 'natureza', 'cred_autorizado', 'empenhado', 'liquidado', 'pago']].style.format({'cred_autorizado': '{:,.2f}', 'empenhado': '{:,.2f}', 'liquidado': '{:,.2f}', 'pago': '{:,.2f}'}), width='stretch')

with tab3:
    if not df_rec.empty or not df_desp.empty:
        st.subheader("⚖️ Confronto Financeiro")
        ms_c = st.multiselect("Meses:", sorted(list(set(df_rec['mes'].unique()) | set(df_desp['mes'].unique()))), default=sorted(list(set(df_rec['mes'].unique()) | set(df_desp['mes'].unique()))), format_func=lambda x: MESES_NOMES[x-1], key="msc")
        tr = df_rec[df_rec['mes'].isin(ms_c)]['realizado'].sum()
        te = df_desp[df_desp['mes'].isin(ms_c)]['empenhado'].sum()
        tp = df_desp[df_desp['mes'].isin(ms_c)]['pago'].sum()
        c1, c2 = st.columns(2); c1.info(f"**Superávit Financeiro:** R$ {tr - tp:,.2f}"); c2.warning(f"**Superávit Orçamentário:** R$ {tr - te:,.2f}")
        fig_c = go.Figure(); fig_c.add_trace(go.Bar(name='Receita', x=['Total'], y=[tr], marker_color='green')); fig_c.add_trace(go.Bar(name='Empenhado', x=['Total'], y=[te], marker_color='orange'))
        fig_c.update_layout(height=400, barmode='group'); st.plotly_chart(fig_c, use_container_width=True)

with tab4:
    st.subheader("📄 Anexos LRF")
    if not df_rec.empty and not df_desp.empty:
        bim = st.selectbox("Bimestre:", list(BIMESTRES.keys()))
        m_ac = list(range(1, max(BIMESTRES[bim]) + 1))
        c1, c2, c3 = st.columns(3)
        df_a1 = df_rec[df_rec['mes'].isin(m_ac)].groupby(['categoria', 'natureza']).agg({'orcado':'max', 'realizado':'sum'}).reset_index()
        c1.write("**Anexo I**"); c1.download_button("📥 Baixar Anexo I", data=gerar_excel_lrf(df_a1), file_name="AnexoI.xlsx", key="lrf1")
        df_a1a = df_desp[df_desp['mes'].isin(m_ac)].groupby(['natureza']).agg({'cred_autorizado':'max', 'empenhado':'sum', 'liquidado':'sum', 'pago':'sum'}).reset_index()
        c2.write("**Anexo IA**"); c2.download_button("📥 Baixar Anexo IA", data=gerar_excel_lrf(df_a1a), file_name="AnexoIA.xlsx", key="lrf1a")
        df_a2 = df_desp[df_desp['mes'].isin(m_ac)].groupby(['funcao', 'subfuncao']).agg({'cred_autorizado':'max', 'empenhado':'sum', 'liquidado':'sum'}).reset_index()
        c3.write("**Anexo II**"); c3.download_button("📥 Baixar Anexo II", data=gerar_excel_lrf(df_a2), file_name="AnexoII.xlsx", key="lrf2")
