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
    "Receita Tributária",
    "Receita Patrimonial",
    "Receita de Serviços",
    "Repasses Correntes",
    "Demais Receitas"
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
            mes INTEGER,
            ano INTEGER,
            codigo_full TEXT,
            natureza TEXT,
            orcado REAL,
            realizado REAL,
            previsao REAL,
            categoria TEXT DEFAULT 'Não Classificada'
        )
    ''')

    try:
        conn.execute("ALTER TABLE receitas ADD COLUMN categoria TEXT DEFAULT 'Não Classificada'")
    except:
        pass

    conn.execute('''
        CREATE TABLE IF NOT EXISTS despesas (
            mes INTEGER,
            ano INTEGER,
            uo TEXT,
            funcao TEXT,
            subfuncao TEXT,
            programa TEXT,
            projeto TEXT,
            natureza TEXT,
            fonte TEXT,
            orcado_inicial REAL,
            cred_autorizado REAL,
            empenhado REAL,
            liquidado REAL,
            pago REAL
        )
    ''')

    conn.close()


def limpar_f(v):
    if pd.isna(v) or v == "" or v == "-":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    v = str(v).replace('"', '').replace('.', '').replace(',', '.')
    try:
        return float(v)
    except:
        return 0.0


def normalizar_chave(v):
    """
    Normaliza valores numéricos/textuais para evitar diferenças do tipo:
    3601 vs 3601.0 entre arquivos de meses diferentes.
    """
    if pd.isna(v):
        return ""
    s = str(v).strip().replace('"', '')
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except:
        pass
    return s


def limpar_todos_dados():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM receitas")
    conn.execute("DELETE FROM despesas")
    conn.commit()
    conn.close()


inicializar_banco()

# --- SIDEBAR ---
with st.sidebar:
    st.subheader("📥 Importar Dados")
    tipo_dado = st.radio("Tipo:", ["Receita", "Despesa"])
    arquivo = st.file_uploader(f"Arquivo {tipo_dado}", type=["xlsx"])

    if arquivo and st.button("🚀 Processar Dados"):
        m_final = 1

        # identifica mês a partir do cabeçalho
        df_scan = pd.read_excel(arquivo, nrows=10, header=None)
        for r in range(len(df_scan)):
            for celula in df_scan.iloc[r]:
                for nome, num in MESES_MAPA.items():
                    if nome in str(celula).upper():
                        m_final = num

        conn = sqlite3.connect(DB_NAME)

        if tipo_dado == "Receita":
            df = pd.read_excel(arquivo, skiprows=7)
            dados = []

            for _, row in df.iterrows():
                cod = str(row.iloc[0]).strip().replace('"', '')

                if re.match(r'^\d', cod) and cod[-1] != '0':
                    real = limpar_f(row.iloc[6])
                    if cod.startswith('9'):
                        real = -abs(real)

                    cur = conn.execute("SELECT categoria FROM receitas WHERE codigo_full = ?", (cod,))
                    r_cat = cur.fetchone()
                    cat_atual = r_cat[0] if r_cat else "Não Classificada"

                    dados.append((
                        m_final,
                        2026,
                        cod,
                        str(row.iloc[1]).replace('"', ''),
                        limpar_f(row.iloc[3]),
                        real,
                        limpar_f(row.iloc[5]),
                        cat_atual
                    ))

            conn.execute("DELETE FROM receitas WHERE ano = ? AND mes = ?", (2026, m_final))
            conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?,?)", dados)

        else:
            # --- DESPESA ---
            # EMPENHADO / LIQUIDADO / PAGO vêm acumulados no 616
            # e serão convertidos para valor mensal antes de salvar no banco.
            df = pd.read_excel(arquivo, skiprows=6)
            df.columns = df.columns.str.strip().str.upper()

            linhas = []

            for _, row in df.iterrows():
                uo = normalizar_chave(row.get('UO', ''))
                ug = normalizar_chave(row.get('UG', ''))

                if uo != "":
                    elem = limpar_f(row.get('ELEMENTO', 0))
                    tem_execucao = (ug != '0' and elem != 0)

                    v_emp_cum = limpar_f(row.get('EMPENHADO', 0)) if tem_execucao else 0.0
                    v_liq_cum = limpar_f(row.get('LIQUIDADO', 0)) if tem_execucao else 0.0
                    v_pag_cum = limpar_f(row.get('PAGO', 0)) if tem_execucao else 0.0

                    v_aut = limpar_f(row.get('CRÉDITO AUTORIZADO', 0))
                    v_ini = limpar_f(row.get('ORÇADO INICIAL', 0))

                    if v_aut > 0 or v_emp_cum > 0 or v_liq_cum > 0 or v_pag_cum > 0:
                        linhas.append({
                            'uo': uo,
                            'funcao': normalizar_chave(row.get('FUNÇÃO', '')),
                            'subfuncao': normalizar_chave(row.get('SUBFUNÇÃO', '')),
                            'programa': normalizar_chave(row.get('PROGRAMA', '')),
                            'projeto': normalizar_chave(row.get('PAOE', '')),
                            'natureza': normalizar_chave(row.get('NATUREZA DESPESA', '')),
                            'fonte': normalizar_chave(row.get('FONTE', '')),
                            'orcado_inicial': v_ini,
                            'cred_autorizado': v_aut,
                            'empenhado_cum': v_emp_cum,
                            'liquidado_cum': v_liq_cum,
                            'pago_cum': v_pag_cum
                        })

            if linhas:
                df_mes = pd.DataFrame(linhas)

                chaves = ['uo', 'funcao', 'subfuncao', 'programa', 'projeto', 'natureza', 'fonte']

                # Agrupa o arquivo do mês na mesma granularidade salva no banco
                df_mes = df_mes.groupby(chaves, as_index=False).agg({
                    'orcado_inicial': 'sum',
                    'cred_autorizado': 'sum',
                    'empenhado_cum': 'sum',
                    'liquidado_cum': 'sum',
                    'pago_cum': 'sum'
                })

                # Busca o acumulado já salvo até o mês anterior
                if m_final > 1:
                    df_ant = pd.read_sql("""
                        SELECT
                            uo,
                            funcao,
                            subfuncao,
                            programa,
                            projeto,
                            natureza,
                            fonte,
                            SUM(empenhado) AS empenhado_ant,
                            SUM(liquidado) AS liquidado_ant,
                            SUM(pago) AS pago_ant
                        FROM despesas
                        WHERE ano = ? AND mes < ?
                        GROUP BY uo, funcao, subfuncao, programa, projeto, natureza, fonte
                    """, conn, params=(2026, m_final))
                else:
                    df_ant = pd.DataFrame(columns=chaves + ['empenhado_ant', 'liquidado_ant', 'pago_ant'])

                df_mes = df_mes.merge(df_ant, on=chaves, how='left').fillna(0)

                # Converte acumulado em valor mensal
                df_mes['empenhado'] = df_mes['empenhado_cum'] - df_mes['empenhado_ant']
                df_mes['liquidado'] = df_mes['liquidado_cum'] - df_mes['liquidado_ant']
                df_mes['pago'] = df_mes['pago_cum'] - df_mes['pago_ant']

                dados = [
                    (
                        m_final,
                        2026,
                        r['uo'],
                        r['funcao'],
                        r['subfuncao'],
                        r['programa'],
                        r['projeto'],
                        r['natureza'],
                        r['fonte'],
                        float(r['orcado_inicial']),
                        float(r['cred_autorizado']),
                        float(r['empenhado']),
                        float(r['liquidado']),
                        float(r['pago'])
                    )
                    for _, r in df_mes.iterrows()
                ]

                conn.execute("DELETE FROM despesas WHERE ano = ? AND mes = ?", (2026, m_final))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)

        conn.commit()
        conn.close()
        st.rerun()

    st.divider()

    st.subheader("💾 Backup")
    conn = sqlite3.connect(DB_NAME)
    df_bkp = pd.read_sql("SELECT * FROM receitas", conn)
    conn.close()

    if not df_bkp.empty:
        csv = df_bkp.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Baixar Backup",
            data=csv,
            file_name="backup_fiplan.csv",
            mime="text/csv"
        )

    file_restore = st.file_uploader("📂 Restaurar", type=["csv"])
    if file_restore and st.button("🔄 Restaurar"):
        df_res = pd.read_csv(file_restore)
        conn = sqlite3.connect(DB_NAME)
        df_res.to_sql("receitas", conn, if_exists="replace", index=False)
        conn.commit()
        conn.close()
        st.success("Restaurado!")
        st.rerun()

    st.divider()

    st.subheader("🗑️ Limpeza")
    confirma_limpeza = st.checkbox("Confirmo que desejo apagar todas as receitas e despesas")

    if st.button("🗑️ Limpar Dados", type="secondary"):
        if confirma_limpeza:
            limpar_todos_dados()
            st.success("Todos os dados foram apagados com sucesso.")
            st.rerun()
        else:
            st.warning("Marque a confirmação antes de limpar os dados.")

# --- CARGA ---
conn = sqlite3.connect(DB_NAME)
df_rec = pd.read_sql("SELECT * FROM receitas", conn)
df_desp = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

tab1, tab2 = st.tabs(["📊 Receitas", "💸 Despesas"])

# --- ABA RECEITAS ---
with tab1:
    if not df_rec.empty:
        f1, f2, f3 = st.columns(3)

        ms_r = f1.multiselect(
            "Meses:",
            sorted(df_rec['mes'].unique()),
            default=df_rec['mes'].unique(),
            format_func=lambda x: MESES_NOMES[x - 1],
            key="ms_receita"
        )

        cat_sel = f2.multiselect(
            "Categoria:",
            sorted(df_rec['categoria'].unique()),
            default=sorted(df_rec['categoria'].unique()),
            key="cat_receita"
        )

        nat_sel = f3.multiselect(
            "Natureza:",
            sorted(df_rec['natureza'].unique()),
            key="nat_receita"
        )

        df_rf = df_rec[(df_rec['mes'].isin(ms_r)) & (df_rec['categoria'].isin(cat_sel))]
        if nat_sel:
            df_rf = df_rf[df_rf['natureza'].isin(nat_sel)]

        if not df_rf.empty:
            v_real = df_rf['realizado'].sum()
            v_orc = df_rec[df_rec['mes'] == max(ms_r)].groupby('codigo_full')['orcado'].max().sum()

            k1, k2, k3 = st.columns(3)
            k1.metric("Orçado Atual", f"R$ {v_orc:,.2f}")
            k2.metric("Realizado", f"R$ {v_real:,.2f}")
            k3.metric("Atingimento", f"{(v_real / v_orc * 100 if v_orc != 0 else 0):.1f}%")

            df_g = df_rf.groupby('mes').agg({'realizado': 'sum'}).reset_index()
            df_g['previsao'] = [
                df_rf[df_rf['mes'] == m].groupby('codigo_full')['previsao'].max().sum()
                for m in df_g['mes']
            ]

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=df_g['mes'].map(lambda x: MESES_NOMES[x - 1]),
                y=df_g['realizado'],
                name="Realizado",
                marker_color='#2E7D32'
            ))
            fig.add_trace(go.Scatter(
                x=df_g['mes'].map(lambda x: MESES_NOMES[x - 1]),
                y=df_g['previsao'],
                name="Previsão",
                line=dict(color='#FF9800', width=3, dash='dot')
            ))
            fig.update_layout(
                height=350,
                margin=dict(l=0, r=0, t=30, b=0),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )

            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(
                df_rf[['categoria', 'codigo_full', 'natureza', 'realizado', 'orcado']].style.format({
                    'realizado': '{:,.2f}',
                    'orcado': '{:,.2f}'
                }),
                width='stretch'
            )

            with st.expander("🏷️ Gerenciar Categorias"):
                c1, c2, c3 = st.columns([2, 2, 1])
                sel_n = c1.selectbox("Natureza:", sorted(df_rec['natureza'].unique()))
                sel_c = c2.selectbox("Categoria:", CATEGORIAS_REC)

                if c3.button("Salvar"):
                    conn = sqlite3.connect(DB_NAME)
                    conn.execute("UPDATE receitas SET categoria = ? WHERE natureza = ?", (sel_c, sel_n))
                    conn.commit()
                    conn.close()
                    st.rerun()

# --- ABA DESPESAS ---
with tab2:
    if not df_desp.empty:
        f1, f2, f3 = st.columns(3)
        ms_d = f1.multiselect(
            "Meses:",
            sorted(df_desp['mes'].unique()),
            default=df_desp['mes'].unique(),
            format_func=lambda x: MESES_NOMES[x - 1],
            key="ms_despesa"
        )
        fs = f2.multiselect("Função:", sorted(df_desp['funcao'].unique()), key="func_despesa")
        sf = f3.multiselect("Subfunção:", sorted(df_desp['subfuncao'].unique()), key="subf_despesa")

        f4, f5, f6 = st.columns(3)
        ps = f4.multiselect("Programa:", sorted(df_desp['programa'].unique()), key="prog_despesa")
        fts = f5.multiselect("Fonte:", sorted(df_desp['fonte'].unique()), key="font_despesa")
        bd = f6.text_input("Natureza (Contém):", key="busca_despesa")

        df_f = df_desp[df_desp['mes'].isin(ms_d)]

        if fs:
            df_f = df_f[df_f['funcao'].isin(fs)]
        if sf:
            df_f = df_f[df_f['subfuncao'].isin(sf)]
        if ps:
            df_f = df_f[df_f['programa'].isin(ps)]
        if fts:
            df_f = df_f[df_f['fonte'].isin(fts)]
        if bd:
            df_f = df_f[df_f['natureza'].str.contains(bd, case=False, na=False)]

        if not df_f.empty:
            m_max = max(ms_d)

            col_chave = ['funcao', 'subfuncao', 'programa', 'projeto', 'fonte', 'natureza']

            # execução = soma dos meses filtrados
            df_exec = df_f.groupby(col_chave, as_index=False)[['empenhado', 'liquidado', 'pago']].sum()

            # crédito autorizado = apenas o último mês do filtro
            df_aut = (
                df_f[df_f['mes'] == m_max]
                .groupby(col_chave, as_index=False)[['cred_autorizado']]
                .sum()
            )

            df_view = df_exec.merge(df_aut, on=col_chave, how='left').fillna({'cred_autorizado': 0})

            v_aut = df_view['cred_autorizado'].sum()
            ve = df_view['empenhado'].sum()
            vl = df_view['liquidado'].sum()
            vp = df_view['pago'].sum()

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Créd. Autorizado", f"R$ {v_aut:,.2f}")
            k2.metric("Empenhado", f"R$ {ve:,.2f}")
            k3.metric("Liquidado", f"R$ {vl:,.2f}")
            k4.metric("Pago", f"R$ {vp:,.2f}")

            st.dataframe(
                df_view[[
                    'funcao', 'subfuncao', 'programa', 'projeto', 'fonte', 'natureza',
                    'cred_autorizado', 'empenhado', 'liquidado', 'pago'
                ]].style.format({
                    'cred_autorizado': '{:,.2f}',
                    'empenhado': '{:,.2f}',
                    'liquidado': '{:,.2f}',
                    'pago': '{:,.2f}'
                }),
                width='stretch'
            )

            st.caption(
                "Empenhado, liquidado e pago consideram os valores mensais dos meses selecionados. "
                "Crédito autorizado considera apenas o último mês do filtro."
            )
