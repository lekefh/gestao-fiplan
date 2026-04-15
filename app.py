import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re

# --- CONFIGURAÇÃO ---
DB_NAME = 'dados_gestao_integrada.db'
st.set_page_config(page_title="FIPLAN - GESTÃO INTEGRADA", layout="wide")

MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
MESES_MAPA = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARÇO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6,
    "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12
}
CATEGORIAS_REC = [
    "Receita Tributária", "Receita Patrimonial", "Receita de Serviços",
    "Repasses Correntes", "Demais Receitas"
]

st.markdown(
    "<style>[data-testid='stMetricValue'] { font-size: 1.4rem !important; font-weight: 700; }</style>",
    unsafe_allow_html=True
)

# --- FUNÇÕES AUXILIARES ---
def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS receitas (
            mes INTEGER, ano INTEGER, codigo_full TEXT, natureza TEXT,
            orcado REAL, realizado REAL, previsao REAL,
            categoria TEXT DEFAULT 'Não Classificada'
        )
    ''')
    try:
        conn.execute("ALTER TABLE receitas ADD COLUMN categoria TEXT DEFAULT 'Não Classificada'")
    except:
        pass
    # Tabela de despesas COM coluna ug
    conn.execute('''
        CREATE TABLE IF NOT EXISTS despesas (
            mes INTEGER, ano INTEGER, uo TEXT, ug TEXT, funcao TEXT, subfuncao TEXT,
            programa TEXT, projeto TEXT, natureza TEXT, fonte TEXT,
            orcado_inicial REAL, cred_autorizado REAL, empenhado REAL, liquidado REAL, pago REAL
        )
    ''')
    # Migração: adiciona ug se a tabela já existia sem essa coluna
    try:
        conn.execute("ALTER TABLE despesas ADD COLUMN ug TEXT DEFAULT ''")
    except:
        pass
    # Tabela de sub-elementos (FIP 701)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sub_elementos (
            mes INTEGER, ano INTEGER, paoe TEXT, natureza_cod TEXT, natureza_desc TEXT,
            subelemento_cod TEXT, subelemento_desc TEXT,
            liquidado REAL, pago REAL
        )
    ''')
    conn.commit()
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
    except:
        pass
    return s

def limpar_todos_dados():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM receitas")
    conn.execute("DELETE FROM despesas")
    conn.execute("DELETE FROM sub_elementos")
    conn.commit()
    conn.close()

def detectar_mes(arquivo):
    """Detecta o mês de referência lendo as primeiras linhas do arquivo."""
    m = 1
    df_scan = pd.read_excel(arquivo, nrows=10, header=None)
    for r in range(len(df_scan)):
        for celula in df_scan.iloc[r]:
            for nome, num in MESES_MAPA.items():
                if nome in str(celula).upper():
                    m = num
    return m

inicializar_banco()

# --- SIDEBAR ---
with st.sidebar:
    st.subheader("📥 Importar Dados")
    tipo_dado = st.radio("Tipo:", ["Receita (FIP 729)", "Despesa (FIP 616)", "Sub-elemento (FIP 701)"])
    arquivo = st.file_uploader("Arquivo Excel", type=["xlsx"])

    if arquivo and st.button("🚀 Processar Dados"):
        m_final = detectar_mes(arquivo)
        conn = sqlite3.connect(DB_NAME)

        # ── RECEITA ──────────────────────────────────────────────────────────
        if tipo_dado == "Receita (FIP 729)":
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
                    dados.append((m_final, 2026, cod, str(row.iloc[1]).replace('"', ''),
                                  limpar_f(row.iloc[3]), real, limpar_f(row.iloc[5]), cat_atual))
            conn.execute("DELETE FROM receitas WHERE ano = ? AND mes = ?", (2026, m_final))
            conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?,?)", dados)

        # ── DESPESA FIP 616 ───────────────────────────────────────────────────
        elif tipo_dado == "Despesa (FIP 616)":
            df = pd.read_excel(arquivo, skiprows=6)
            df.columns = df.columns.str.strip().str.upper()

            linhas = []
            for _, row in df.iterrows():
                uo = normalizar_chave(row.get('UO', ''))
                ug = normalizar_chave(row.get('UG', ''))
                if uo == "" or pd.isna(row.get('UO')): continue

                elem = limpar_f(row.get('ELEMENTO', 0))
                # Execução só existe quando há UG real (≠ '0') e elemento ≠ 0
                tem_execucao = (ug != '0' and ug != '' and elem != 0)
                v_emp_cum = limpar_f(row.get('EMPENHADO', 0))   if tem_execucao else 0.0
                v_liq_cum = limpar_f(row.get('LIQUIDADO', 0))   if tem_execucao else 0.0
                v_pag_cum = limpar_f(row.get('PAGO', 0))        if tem_execucao else 0.0

                linhas.append({
                    'uo':       uo,
                    'ug':       ug,
                    'funcao':   normalizar_chave(row.get('FUNÇÃO',          row.get('FUN\u00c7\u00c3O', ''))),
                    'subfuncao':normalizar_chave(row.get('SUBFUNÇÃO',       row.get('SUBFUN\u00c7\u00c3O', ''))),
                    'programa': normalizar_chave(row.get('PROGRAMA', '')),
                    'projeto':  normalizar_chave(row.get('PAOE', '')),
                    'natureza': normalizar_chave(row.get('NATUREZA DESPESA', '')),
                    'fonte':    normalizar_chave(row.get('FONTE', '')),
                    'orcado_inicial':   limpar_f(row.get('ORÇADO INICIAL',      row.get('OR\u00c7ADO INICIAL', 0))),
                    'cred_autorizado':  limpar_f(row.get('CRÉDITO AUTORIZADO',  row.get('CR\u00c9DITO AUTORIZADO', 0))),
                    'empenhado_cum': v_emp_cum,
                    'liquidado_cum': v_liq_cum,
                    'pago_cum':      v_pag_cum,
                })

            if linhas:
                chaves = ['uo', 'ug', 'funcao', 'subfuncao', 'programa', 'projeto', 'natureza', 'fonte']
                df_mes = pd.DataFrame(linhas)
                df_mes = df_mes.groupby(chaves, as_index=False).agg({
                    'orcado_inicial': 'sum', 'cred_autorizado': 'sum',
                    'empenhado_cum': 'sum', 'liquidado_cum': 'sum', 'pago_cum': 'sum'
                })

                # Subtrai acumulado dos meses anteriores para obter valor mensal
                if m_final > 1:
                    df_ant = pd.read_sql(
                        "SELECT uo, ug, funcao, subfuncao, programa, projeto, natureza, fonte, "
                        "SUM(empenhado) AS empenhado_ant, SUM(liquidado) AS liquidado_ant, "
                        "SUM(pago) AS pago_ant "
                        "FROM despesas WHERE ano=2026 AND mes < ? "
                        "GROUP BY uo, ug, funcao, subfuncao, programa, projeto, natureza, fonte",
                        conn, params=(m_final,)
                    )
                else:
                    df_ant = pd.DataFrame(columns=chaves + ['empenhado_ant', 'liquidado_ant', 'pago_ant'])

                df_mes = df_mes.merge(df_ant, on=chaves, how='left').fillna(0)
                df_mes['empenhado'] = (df_mes['empenhado_cum'] - df_mes['empenhado_ant']).clip(lower=0)
                df_mes['liquidado'] = (df_mes['liquidado_cum'] - df_mes['liquidado_ant']).clip(lower=0)
                df_mes['pago']      = (df_mes['pago_cum']      - df_mes['pago_ant']).clip(lower=0)

                dados = [
                    (m_final, 2026,
                     r['uo'], r['ug'], r['funcao'], r['subfuncao'], r['programa'],
                     r['projeto'], r['natureza'], r['fonte'],
                     float(r['orcado_inicial']), float(r['cred_autorizado']),
                     float(r['empenhado']), float(r['liquidado']), float(r['pago']))
                    for _, r in df_mes.iterrows()
                ]
                conn.execute("DELETE FROM despesas WHERE ano = 2026 AND mes = ?", (m_final,))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)

        # ── SUB-ELEMENTO FIP 701 ──────────────────────────────────────────────
        elif tipo_dado == "Sub-elemento (FIP 701)":
            df701 = pd.read_excel(arquivo, header=None)
            linhas = []
            current_paoe = ""
            current_nat_cod = ""
            current_nat_desc = ""

            for i, row in df701.iterrows():
                text = str(row.iloc[0]).strip().replace('\xa0', ' ')
                if i < 8 or not text or text == 'nan':
                    continue
                # Linha de PROJ/ATIV
                if re.search(r'PROJ/ATIV\s*:', text, re.IGNORECASE):
                    m = re.search(r'(\d{5,8})', text)
                    if m: current_paoe = m.group(1)
                    continue
                # Linha de NATUREZA DA DESPESA
                if re.search(r'NATUREZA\s+(?:DA|DE)\s+DESPESA\s*:', text, re.IGNORECASE):
                    m = re.search(r':\s*(\d+)\s*-\s*(.*)', text)
                    if m:
                        current_nat_cod = m.group(1).strip()
                        desc_raw = m.group(2).replace('\xa0', ' ').strip()
                        # Pega só a primeira parte antes de ' - '
                        current_nat_desc = desc_raw.split(' - ')[0].strip() if ' - ' in desc_raw else desc_raw
                    continue
                # Linhas de totais e cabeçalhos — ignora
                tu = text.upper()
                if tu.startswith('TOTAL') or tu.startswith('CONSOLIDADO') or tu.startswith('DOTA'):
                    continue
                # Linha de sub-elemento: começa com padrão numérico N.N.NN...
                if re.match(r'^\d+\.\d+', text) and current_paoe and current_nat_cod:
                    parts = text.split(' ', 1)
                    sub_cod  = parts[0].strip()
                    sub_desc = parts[1].strip() if len(parts) > 1 else ''
                    liq_cum  = limpar_f(row.iloc[1]) if pd.notna(row.iloc[1]) else 0.0
                    pag_cum  = limpar_f(row.iloc[2]) if pd.notna(row.iloc[2]) else 0.0
                    linhas.append({
                        'paoe': current_paoe,
                        'natureza_cod': current_nat_cod,
                        'natureza_desc': current_nat_desc,
                        'subelemento_cod': sub_cod,
                        'subelemento_desc': sub_desc,
                        'liquidado_cum': liq_cum,
                        'pago_cum': pag_cum,
                    })

            if linhas:
                chaves_701 = ['paoe', 'natureza_cod', 'subelemento_cod']
                df_mes = pd.DataFrame(linhas)
                df_mes = df_mes.groupby(
                    chaves_701 + ['natureza_desc', 'subelemento_desc'], as_index=False
                ).agg({'liquidado_cum': 'sum', 'pago_cum': 'sum'})

                # Subtrai acumulado anterior
                if m_final > 1:
                    df_ant = pd.read_sql(
                        "SELECT paoe, natureza_cod, subelemento_cod, "
                        "SUM(liquidado) AS liquidado_ant, SUM(pago) AS pago_ant "
                        "FROM sub_elementos WHERE ano=2026 AND mes < ? "
                        "GROUP BY paoe, natureza_cod, subelemento_cod",
                        conn, params=(m_final,)
                    )
                else:
                    df_ant = pd.DataFrame(columns=chaves_701 + ['liquidado_ant', 'pago_ant'])

                df_mes = df_mes.merge(df_ant, on=chaves_701, how='left').fillna(0)
                df_mes['liquidado'] = (df_mes['liquidado_cum'] - df_mes['liquidado_ant']).clip(lower=0)
                df_mes['pago']      = (df_mes['pago_cum']      - df_mes['pago_ant']).clip(lower=0)

                dados = [
                    (m_final, 2026,
                     r['paoe'], r['natureza_cod'], r['natureza_desc'],
                     r['subelemento_cod'], r['subelemento_desc'],
                     float(r['liquidado']), float(r['pago']))
                    for _, r in df_mes.iterrows()
                ]
                conn.execute("DELETE FROM sub_elementos WHERE ano = 2026 AND mes = ?", (m_final,))
                conn.executemany("INSERT INTO sub_elementos VALUES (?,?,?,?,?,?,?,?,?)", dados)

        conn.commit()
        conn.close()
        st.success(f"✅ {tipo_dado} — {MESES_NOMES[m_final-1]}/2026 importado!")
        st.rerun()

    st.divider()
    st.subheader("💾 Backup")
    conn = sqlite3.connect(DB_NAME)
    df_bkp = pd.read_sql("SELECT * FROM receitas", conn)
    conn.close()
    if not df_bkp.empty:
        csv = df_bkp.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar Backup Receitas", data=csv,
                           file_name="backup_receitas.csv", mime="text/csv")
    file_restore = st.file_uploader("📂 Restaurar Receitas", type=["csv"])
    if file_restore and st.button("🔄 Restaurar"):
        df_res = pd.read_csv(file_restore)
        conn = sqlite3.connect(DB_NAME)
        df_res.to_sql("receitas", conn, if_exists="replace", index=False)
        conn.commit(); conn.close()
        st.success("Restaurado!"); st.rerun()

    st.divider()
    st.subheader("🗑️ Limpeza")
    confirma_limpeza = st.checkbox("Confirmo apagar tudo")
    if st.button("🗑️ Limpar Dados"):
        if confirma_limpeza: limpar_todos_dados(); st.rerun()
        else: st.warning("Marque a confirmação.")

# --- CARGA DOS DADOS ---
conn = sqlite3.connect(DB_NAME)
df_rec  = pd.read_sql("SELECT * FROM receitas",     conn)
df_desp = pd.read_sql("SELECT * FROM despesas",     conn)
df_sub  = pd.read_sql("SELECT * FROM sub_elementos", conn)
conn.close()

# Garante que a coluna ug existe no df (caso banco antigo sem a coluna)
if 'ug' not in df_desp.columns:
    df_desp['ug'] = '0'

tab1, tab2, tab3 = st.tabs(["📊 Receitas", "💸 Despesas", "⚖️ Comparativo"])

# ── ABA 1: RECEITAS ─────────────────────────────────────────────────────────
with tab1:
    if not df_rec.empty:
        with st.expander("🏷️ Classificar Categorias de Receita"):
            c1, c2, c3 = st.columns([2, 2, 1])
            sel_nat = c1.selectbox("Natureza:", sorted(df_rec['natureza'].unique()), key="sel_nat_class")
            sel_cat = c2.selectbox("Atribuir Categoria:", CATEGORIAS_REC, key="sel_cat_class")
            if c3.button("Salvar Categoria"):
                conn = sqlite3.connect(DB_NAME)
                conn.execute("UPDATE receitas SET categoria = ? WHERE natureza = ?", (sel_cat, sel_nat))
                conn.commit(); conn.close(); st.rerun()
        st.divider()

        f1, f2, f3 = st.columns(3)
        ms_r    = f1.multiselect("Meses:", sorted(df_rec['mes'].unique()),
                                 default=df_rec['mes'].unique(),
                                 format_func=lambda x: MESES_NOMES[x-1], key="ms_receita")
        cat_sel = f2.multiselect("Categoria:", sorted(df_rec['categoria'].unique()),
                                 default=sorted(df_rec['categoria'].unique()), key="cat_receita")
        nat_sel = f3.multiselect("Natureza:", sorted(df_rec['natureza'].unique()), key="nat_receita")

        df_rf = df_rec[(df_rec['mes'].isin(ms_r)) & (df_rec['categoria'].isin(cat_sel))]
        if nat_sel: df_rf = df_rf[df_rf['natureza'].isin(nat_sel)]

        if not df_rf.empty:
            v_real = df_rf['realizado'].sum()
            v_orc  = df_rec[df_rec['mes'] == max(ms_r)].groupby('codigo_full')['orcado'].max().sum()
            k1, k2, k3 = st.columns(3)
            k1.metric("Orçado Atual",  f"R$ {v_orc:,.2f}")
            k2.metric("Realizado",     f"R$ {v_real:,.2f}")
            k3.metric("Atingimento",   f"{(v_real/v_orc*100 if v_orc!=0 else 0):.1f}%")

            df_g = df_rf.groupby('mes').agg({'realizado': 'sum'}).reset_index()
            df_g['previsao'] = [
                df_rf[df_rf['mes'] == m].groupby('codigo_full')['previsao'].max().sum()
                for m in df_g['mes']
            ]
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=df_g['mes'].map(lambda x: MESES_NOMES[x-1]), y=df_g['realizado'],
                name="Realizado", marker_color='#2E7D32'))
            fig.add_trace(go.Scatter(
                x=df_g['mes'].map(lambda x: MESES_NOMES[x-1]), y=df_g['previsao'],
                name="Previsão", line=dict(color='#FF9800', width=3, dash='dot')))
            fig.update_layout(height=350, margin=dict(l=0, r=0, t=30, b=0),
                              hovermode="x unified",
                              legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(
                df_rf[['categoria', 'codigo_full', 'natureza', 'realizado', 'orcado']].style.format(
                    {'realizado': '{:,.2f}', 'orcado': '{:,.2f}'}),
                use_container_width=True)
    else:
        st.info("Importe dados de Receita (FIP 729) para visualizar.")

# ── ABA 2: DESPESAS ──────────────────────────────────────────────────────────
with tab2:
    if not df_desp.empty:
        # ── Filtros — Linha 1 ──
        f1, f2, f3 = st.columns(3)
        ms_d = f1.multiselect(
            "Meses:", sorted(df_desp['mes'].unique()),
            default=df_desp['mes'].unique(),
            format_func=lambda x: MESES_NOMES[x-1], key="ms_despesa")

        ugs_disponiveis = sorted(df_desp['ug'].unique())
        ug_sel = f2.multiselect(
            "UG (Unidade Gestora):", ugs_disponiveis,
            default=ugs_disponiveis, key="ug_despesa")

        fs = f3.multiselect("Função:", sorted(df_desp['funcao'].unique()), key="func_despesa")

        # ── Filtros — Linha 2 ──
        f4, f5, f6 = st.columns(3)
        sf  = f4.multiselect("Subfunção:", sorted(df_desp['subfuncao'].unique()), key="subf_despesa")
        ps  = f5.multiselect("Programa:",  sorted(df_desp['programa'].unique()),  key="prog_despesa")
        fts = f6.multiselect("Fonte:",     sorted(df_desp['fonte'].unique()),     key="font_despesa")
        bd  = st.text_input("Natureza (busca por texto):", key="busca_despesa")

        # ── Aplica filtros ──
        df_f = df_desp[df_desp['mes'].isin(ms_d)]
        if ug_sel:  df_f = df_f[df_f['ug'].isin(ug_sel)]
        if fs:      df_f = df_f[df_f['funcao'].isin(fs)]
        if sf:      df_f = df_f[df_f['subfuncao'].isin(sf)]
        if ps:      df_f = df_f[df_f['programa'].isin(ps)]
        if fts:     df_f = df_f[df_f['fonte'].isin(fts)]
        if bd:      df_f = df_f[df_f['natureza'].str.contains(bd, case=False, na=False)]

        if not df_f.empty:
            m_max = max(ms_d)

            # Crédito Autorizado: sempre consolidado do último mês selecionado (sem filtro de UG,
            # pois o orçamento fica nas linhas com UG='0')
            cred_total = df_desp[df_desp['mes'] == m_max]['cred_autorizado'].sum()

            # Execução: soma dos meses selecionados (já convertido para mensal no import)
            emp_total = df_f['empenhado'].sum()
            liq_total = df_f['liquidado'].sum()
            pag_total = df_f['pago'].sum()

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Créd. Autorizado (Orç. Atualizado)", f"R$ {cred_total:,.2f}")
            k2.metric("Empenhado",  f"R$ {emp_total:,.2f}")
            k3.metric("Liquidado",  f"R$ {liq_total:,.2f}")
            k4.metric("Pago",       f"R$ {pag_total:,.2f}")

            # Tabela de detalhamento
            # Inclui UG na chave quando o usuário filtra por UG específica
            ug_filtrada = len(ug_sel) < len(ugs_disponiveis)
            col_chave = (['ug'] if ug_filtrada else []) + \
                        ['funcao', 'subfuncao', 'programa', 'projeto', 'fonte', 'natureza']

            df_exec = df_f.groupby(col_chave, as_index=False)[['empenhado', 'liquidado', 'pago']].sum()
            st.dataframe(
                df_exec[col_chave + ['empenhado', 'liquidado', 'pago']].style.format(
                    {'empenhado': '{:,.2f}', 'liquidado': '{:,.2f}', 'pago': '{:,.2f}'}),
                use_container_width=True)

        # ── Sub-elementos (FIP 701) ──────────────────────────────────────────
        if not df_sub.empty:
            st.divider()
            with st.expander("🔍 Sub-elementos por PAOE (FIP 701)", expanded=False):
                fs1, fs2, fs3 = st.columns(3)
                ms_s = fs1.multiselect(
                    "Meses:", sorted(df_sub['mes'].unique()),
                    default=df_sub['mes'].unique(),
                    format_func=lambda x: MESES_NOMES[x-1], key="ms_sub")
                paoe_sel   = fs2.multiselect("PAOE:",     sorted(df_sub['paoe'].unique()),        key="paoe_sub")
                nat_s_sel  = fs3.multiselect("Natureza:", sorted(df_sub['natureza_cod'].unique()), key="nat_sub")

                df_sf = df_sub[df_sub['mes'].isin(ms_s)]
                if paoe_sel:  df_sf = df_sf[df_sf['paoe'].isin(paoe_sel)]
                if nat_s_sel: df_sf = df_sf[df_sf['natureza_cod'].isin(nat_s_sel)]

                if not df_sf.empty:
                    col_sub = ['paoe', 'natureza_cod', 'natureza_desc', 'subelemento_cod', 'subelemento_desc']
                    df_sv = df_sf.groupby(col_sub, as_index=False)[['liquidado', 'pago']].sum()

                    ks1, ks2 = st.columns(2)
                    ks1.metric("Liquidado (sub-elementos)", f"R$ {df_sv['liquidado'].sum():,.2f}")
                    ks2.metric("Pago (sub-elementos)",      f"R$ {df_sv['pago'].sum():,.2f}")

                    st.dataframe(
                        df_sv[col_sub + ['liquidado', 'pago']].style.format(
                            {'liquidado': '{:,.2f}', 'pago': '{:,.2f}'}),
                        use_container_width=True)
                else:
                    st.info("Nenhum sub-elemento encontrado para os filtros selecionados.")
    else:
        st.info("Importe dados de Despesa (FIP 616) para visualizar.")

# ── ABA 3: COMPARATIVO ───────────────────────────────────────────────────────
with tab3:
    st.subheader("⚖️ Confronto Geral Financeiro e Orçamentário")
    if not df_rec.empty or not df_desp.empty:
        todos_meses = sorted(list(set(
            df_rec['mes'].unique().tolist() + df_desp['mes'].unique().tolist()
        )))
        ms_c = st.multiselect(
            "Filtrar Meses para Confronto:", todos_meses,
            default=todos_meses,
            format_func=lambda x: MESES_NOMES[x-1], key="ms_confronto")

        tr = df_rec[df_rec['mes'].isin(ms_c)]['realizado'].sum()
        te = df_desp[df_desp['mes'].isin(ms_c)]['empenhado'].sum()
        tl = df_desp[df_desp['mes'].isin(ms_c)]['liquidado'].sum()
        tp = df_desp[df_desp['mes'].isin(ms_c)]['pago'].sum()

        kc1, kc2, kc3, kc4 = st.columns(4)
        kc1.metric("Receita Arrecadada", f"R$ {tr:,.2f}")
        kc2.metric("Despesa Empenhada",  f"R$ {te:,.2f}")
        kc3.metric("Despesa Liquidada",  f"R$ {tl:,.2f}")
        kc4.metric("Despesa Paga",       f"R$ {tp:,.2f}")

        st.divider()
        m1, m2 = st.columns(2)
        m1.info(    f"**Superávit Financeiro  (Receita − Pago):**      R$ {tr - tp:,.2f}")
        m2.warning( f"**Superávit Orçamentário (Receita − Empenhado):** R$ {tr - te:,.2f}")

        fig_c = go.Figure()
        fig_c.add_trace(go.Bar(name='Receita Arrecadada', x=['Confronto'], y=[tr], marker_color='green'))
        fig_c.add_trace(go.Bar(name='Desp. Empenhada',    x=['Confronto'], y=[te], marker_color='orange'))
        fig_c.add_trace(go.Bar(name='Desp. Liquidada',    x=['Confronto'], y=[tl], marker_color='#72A0C1'))
        fig_c.add_trace(go.Bar(name='Desp. Paga',         x=['Confronto'], y=[tp], marker_color='red'))
        fig_c.update_layout(height=400, barmode='group', margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_c, use_container_width=True)
    else:
        st.info("Importe dados para visualizar o comparativo.")
