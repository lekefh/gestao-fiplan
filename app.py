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
MESES_MAPA = {"JANEIRO": 1, "FEVEREIRO": 2, "MARÇO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}
CATEGORIAS_REC = ["Receita Tributária", "Receita Patrimonial", "Receita de Serviços", "Repasses Correntes", "Demais Receitas"]

st.markdown("<style>[data-testid='stMetricValue'] { font-size: 1.4rem !important; font-weight: 700; }</style>", unsafe_allow_html=True)

def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS receitas 
        (mes INTEGER, ano INTEGER, codigo_full TEXT, natureza TEXT, orcado REAL, realizado REAL, previsao REAL, categoria TEXT DEFAULT 'Não Classificada')''')
    try: conn.execute("ALTER TABLE receitas ADD COLUMN categoria TEXT DEFAULT 'Não Classificada'")
    except: pass
    conn.execute('''CREATE TABLE IF NOT EXISTS despesas 
        (mes INTEGER, ano INTEGER, uo TEXT, funcao TEXT, subfuncao TEXT, programa TEXT, projeto TEXT, natureza TEXT, fonte TEXT, orcado_inicial REAL, cred_autorizado REAL, empenhado REAL, liquidado REAL, pago REAL)''')
    conn.close()

def limpar_f(v):
    if pd.isna(v) or v == "" or v == "-": return 0.0
    if isinstance(v, (int, float)): return float(v)
    v = str(v).replace('"', '').replace('.', '').replace(',', '.')
    try: return float(v)
    except: return 0.0

inicializar_banco()

# --- SIDEBAR: IMPORTAÇÃO E BACKUP ---
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
        try:
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
                conn.execute("DELETE FROM receitas WHERE mes=?", (m_final,))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?,?)", dados)
            else:
                df = pd.read_excel(arquivo, skiprows=6); df.columns = df.columns.str.strip().str.upper()
                dados = []
                for _, row in df.iterrows():
                    uo, ug = str(row.get('UO', '')).strip(), str(row.get('UG', '')).strip()
                    if uo != "" and uo != "nan":
                        elem = limpar_f(row.get('ELEMENTO', 0))
                        v_emp = limpar_f(row.get('EMPENHADO', 0)) if (ug != '0' and elem != 0) else 0.0
                        v_liq = limpar_f(row.get('LIQUIDADO', 0)) if (ug != '0' and elem != 0) else 0.0
                        v_pag = limpar_f(row.get('PAGO', 0)) if (ug != '0' and elem != 0) else 0.0
                        v_aut = limpar_f(row.get('CRÉDITO AUTORIZADO', 0))
                        v_ini = limpar_f(row.get('ORÇADO INICIAL', 0))
                        if v_aut > 0 or v_emp > 0 or v_liq > 0 or v_pag > 0:
                            dados.append((m_final, 2026, uo, str(row.get('FUNÇÃO', '')), str(row.get('SUBFUNÇÃO', '')), str(row.get('PROGRAMA', '')), str(row.get('PAOE', '')), str(row.get('NATUREZA DESPESA', '')), str(row.get('FONTE', '')), v_ini, v_aut, v_emp, v_liq, v_pag))
                conn.execute("DELETE FROM despesas WHERE mes=?", (m_final,))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
            conn.commit(); st.success("✅ Sucesso!"); st.rerun()
        except Exception as e: st.error(f"Erro: {e}")
        finally: conn.close()

    st.divider()
    st.subheader("💾 Backup de Categorias")
    conn = sqlite3.connect(DB_NAME)
    df_bkp = pd.read_sql("SELECT * FROM receitas", conn)
    conn.close()
    if not df_bkp.empty:
        csv = df_bkp.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar Backup (CSV)", data=csv, file_name="backup_fiplan.csv", mime="text/csv")
    
    file_restore = st.file_uploader("📂 Restaurar Backup", type=["csv"])
    if file_restore and st.button("🔄 Restaurar Agora"):
        df_res = pd.read_csv(file_restore)
        conn = sqlite3.connect(DB_NAME); df_res.to_sql("receitas", conn, if_exists="replace", index=False)
        conn.commit(); conn.close(); st.success("Backup Restaurado!"); st.rerun()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DROP TABLE IF EXISTS receitas"); conn.execute("DROP TABLE IF EXISTS despesas")
        conn.commit(); conn.close(); inicializar_banco(); st.rerun()

# --- CARGA ---
conn = sqlite3.connect(DB_NAME)
df_rec = pd.read_sql("SELECT * FROM receitas", conn)
df_desp = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

tab1, tab2 = st.tabs(["📊 Receitas", "💸 Despesas"])

with tab1:
    if not df_rec.empty:
        f1, f2, f3 = st.columns(3)
        ms_r = f1.multiselect("Meses:", sorted(df_rec['mes'].unique()), default=df_rec['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1])
        cat_sel = f2.multiselect("Categoria:", sorted(df_rec['categoria'].unique()), default=sorted(df_rec['categoria'].unique()))
        nat_sel = f3.multiselect("Natureza:", sorted(df_rec['natureza'].unique()))

        df_rf = df_rec[(df_rec['mes'].isin(ms_r)) & (df_rec['categoria'].isin(cat_sel))]
        if nat_sel: df_rf = df_rf[df_rf['natureza'].isin(nat_sel)]
        
        if not df_rf.empty:
            v_real = df_rf['realizado'].sum(); m_ultima = max(ms_r)
            v_orc = df_rec[df_rec['mes'] == m_ultima].groupby('codigo_full')['orcado'].max().sum()
            k1, k2, k3 = st.columns(3); k1.metric("Orçado Atual", f"R$ {v_orc:,.2f}"); k2.metric("Realizado", f"R$ {v_real:,.2f}"); k3.metric("Atingimento", f"{(v_real/v_orc*100 if v_orc != 0 else 0):.1f}%")

            df_g = df_rf.groupby('mes').agg({'realizado': 'sum'}).reset_index()
            df_g['previsao'] = [df_rf[df_rf['mes'] == m].groupby('codigo_full')['previsao'].max().sum() for m in df_g['mes']]
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_g['mes'].map(lambda x: MESES_NOMES[x-1]), y=df_g['realizado'], name="Realizado", marker_color='#2E7D32'))
            fig.add_trace(go.Scatter(x=df_g['mes'].map(lambda x: MESES_NOMES[x-1]), y=df_g['previsao'], name="Previsão", line=dict(color='#FF9800', width=3, dash='dot')))
            fig.update_layout(height=350, margin=dict(l=0, r=0, t=30, b=0), hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_rf[['categoria', 'codigo_full', 'natureza', 'realizado', 'orcado']].style.format({'realizado': '{:,.2f}', 'orcado': '{:,.2f}'}), width='stretch')
            with st.expander("🏷️ Gerenciar Categorias"):
                c1, c2, c3 = st.columns([2, 2, 1])
                sel_n = c1.selectbox("Natureza:", sorted(df_rec['natureza'].unique()))
                sel_c = c2.selectbox("Categoria:", CATEGORIAS_REC)
                if c3.button("Salvar"):
                    conn = sqlite3.connect(DB_NAME); conn.execute("UPDATE receitas SET categoria = ? WHERE natureza = ?", (sel_c, sel_n))
                    conn.commit(); conn.close(); st.rerun()

with tab2:
    if not df_desp.empty:
        # RESTAURAÇÃO DOS FILTROS COMPLETOS
        f1, f2, f3 = st.columns(3)
        ms_d = f1.multiselect("Meses:", sorted(df_desp['mes'].unique()), default=df_desp['mes'].unique(), format_func=lambda x: MESES_NOMES[x-1])
        fs = f2.multiselect("Função:", sorted(df_desp['funcao'].unique()))
        sf = f3.multiselect("Subfunção:", sorted(df_desp['subfuncao'].unique()))

        f4, f5, f6 = st.columns(3)
        ps = f4.multiselect("Programa:", sorted(df_desp['programa'].unique()))
        fts = f5.multiselect("Fonte:", sorted(df_desp['fonte'].unique()))
        bd = f6.text_input("Natureza (Contém):", key="bd_d")
        
        df_f = df_desp[df_desp['mes'].isin(ms_d)]
        if fs: df_f = df_f[df_f['funcao'].isin(fs)]
        if sf: df_f = df_f[df_f['subfuncao'].isin(sf)]
        if ps: df_f = df_f[df_f['programa'].isin(ps)]
        if fts: df_f = df_f[df_f['fonte'].isin(fts)]
        if bd: df_f = df_f[df_f['natureza'].str.contains(bd, case=False, na=False)]
        
        if not df_f.empty:
            m_max = max(ms_d)
            v_aut = df_desp[df_desp['mes'] == m_max].groupby(['uo','funcao','subfuncao','programa','projeto','natureza','fonte'])['cred_autorizado'].max().sum()
            ve, vl, vp = df_f['empenhado'].sum(), df_f['liquidado'].sum(), df_f['pago'].sum()
            k1, k2, k3, k4 = st.columns(4); k1.metric("Créd. Autorizado", f"R$ {v_aut:,.2f}"); k2.metric("Empenhado", f"R$ {ve:,.2f}"); k3.metric("Liquidado", f"R$ {vl:,.2f}"); k4.metric("Pago", f"R$ {vp:,.2f}")
            st.dataframe(df_f[['funcao', 'subfuncao', 'programa', 'projeto', 'fonte', 'natureza', 'cred_autorizado', 'empenhado', 'liquidado', 'pago']].style.format({'cred_autorizado': '{:,.2f}', 'empenhado': '{:,.2f}', 'liquidado': '{:,.2f}', 'pago': '{:,.2f}'}), width='stretch')
