import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import unicodedata
import re

DB_NAME = 'dados_gestao_integrada.db'
st.set_page_config(page_title="FIPLAN - GESTAO INTEGRADA", layout="wide")

MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun",
               "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# Mapa sem acento para comparacao robusta (MARCO em vez de MARCO com cedilha)
MESES_SEM_ACENTO = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4,
    "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
    "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12
}

CATEGORIAS_REC = [
    "Receita Tributaria", "Receita Patrimonial", "Receita de Servicos",
    "Repasses Correntes", "Demais Receitas"
]

st.markdown(
    "<style>[data-testid='stMetricValue']"
    "{font-size:1.4rem!important;font-weight:700}</style>",
    unsafe_allow_html=True
)


# ---------------------------------------------------------------------------
# AUXILIARES
# ---------------------------------------------------------------------------
def sem_acento(txt):
    """Remove acentos de uma string para comparacao case-insensitive."""
    return "".join(
        c for c in unicodedata.normalize("NFD", txt)
        if unicodedata.category(c) != "Mn"
    )


def detectar_mes(arquivo):
    """Detecta o mes de referencia nas primeiras 10 linhas do Excel."""
    m_final = 1
    try:
        df_scan = pd.read_excel(arquivo, nrows=10, header=None)
        for r in range(len(df_scan)):
            for celula in df_scan.iloc[r]:
                txt = sem_acento(str(celula)).upper()
                for nome, num in MESES_SEM_ACENTO.items():
                    if nome in txt:
                        m_final = num
    except Exception:
        pass
    return m_final


def limpar_f(v):
    """Converte valor brasileiro (1.234,56) para float."""
    if pd.isna(v) or str(v).strip() in ("", "-", "nan"):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace('"', "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def norm(v):
    """Normaliza chave: converte float inteiro para string inteira."""
    if pd.isna(v):
        return ""
    s = str(v).strip().replace('"', "").replace("\xa0", "")
    try:
        f = float(s)
        if f == int(f):
            return str(int(f))
    except Exception:
        pass
    return s


# ---------------------------------------------------------------------------
# BANCO DE DADOS
# ---------------------------------------------------------------------------
def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS receitas ("
        "mes INTEGER, ano INTEGER, codigo_full TEXT, natureza TEXT, "
        "orcado REAL, realizado REAL, previsao REAL, "
        "categoria TEXT DEFAULT 'Nao Classificada')"
    )
    try:
        conn.execute(
            "ALTER TABLE receitas ADD COLUMN categoria TEXT DEFAULT 'Nao Classificada'"
        )
    except Exception:
        pass

    conn.execute(
        "CREATE TABLE IF NOT EXISTS despesas ("
        "mes INTEGER, ano INTEGER, uo TEXT, ug TEXT, funcao TEXT, subfuncao TEXT, "
        "programa TEXT, projeto TEXT, natureza TEXT, fonte TEXT, "
        "orcado_inicial REAL, cred_autorizado REAL, "
        "empenhado REAL, liquidado REAL, pago REAL)"
    )
    try:
        conn.execute("ALTER TABLE despesas ADD COLUMN ug TEXT DEFAULT ''")
    except Exception:
        pass

    conn.execute(
        "CREATE TABLE IF NOT EXISTS sub_elementos ("
        "mes INTEGER, ano INTEGER, paoe TEXT, natureza_cod TEXT, natureza_desc TEXT, "
        "subelemento_cod TEXT, subelemento_desc TEXT, "
        "liquidado REAL, pago REAL)"
    )
    conn.commit()
    conn.close()


def limpar_todos_dados():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM receitas")
    conn.execute("DELETE FROM despesas")
    conn.execute("DELETE FROM sub_elementos")
    conn.commit()
    conn.close()


inicializar_banco()


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
with st.sidebar:
    st.subheader("Importar Dados")
    tipo_dado = st.radio(
        "Tipo:", ["Receita (FIP 729)", "Despesa (FIP 616)", "Sub-elemento (FIP 701)"]
    )
    arquivo = st.file_uploader("Arquivo Excel", type=["xlsx"])

    if arquivo and st.button("Processar Dados"):
        try:
            m_final = detectar_mes(arquivo)
            conn = sqlite3.connect(DB_NAME)

            # ------------------------------------------------------------
            # RECEITA (FIP 729)
            # Linha 8+ de dados; col[0]=cod, col[1]=natureza,
            # col[3]=orcado, col[5]=previsao, col[6]=realizado
            # ------------------------------------------------------------
            if tipo_dado == "Receita (FIP 729)":
                df = pd.read_excel(arquivo, skiprows=7, header=0)
                dados = []
                for _, row in df.iterrows():
                    try:
                        cod = str(row.iloc[0]).strip().replace('"', "")
                        if not re.match(r"^\d", cod) or cod[-1] == "0":
                            continue
                        real = limpar_f(row.iloc[6])
                        if cod.startswith("9"):
                            real = -abs(real)
                        cur = conn.execute(
                            "SELECT categoria FROM receitas WHERE codigo_full=?", (cod,)
                        )
                        r_cat = cur.fetchone()
                        cat = r_cat[0] if r_cat else "Nao Classificada"
                        dados.append((
                            m_final, 2026, cod,
                            str(row.iloc[1]).replace('"', ""),
                            limpar_f(row.iloc[3]), real, limpar_f(row.iloc[5]), cat
                        ))
                    except Exception:
                        continue
                conn.execute(
                    "DELETE FROM receitas WHERE ano=2026 AND mes=?", (m_final,)
                )
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?,?)", dados)
                conn.commit()
                st.success(
                    "Receita " + MESES_NOMES[m_final - 1]
                    + "/2026: " + str(len(dados)) + " registros"
                )

            # ------------------------------------------------------------
            # DESPESA (FIP 616) - acesso por posicao de coluna (iloc)
            #
            # Estrutura fixa apos skiprows=6 (linha 7 do Excel = header):
            #  [0]PODER  [1]UO  [2]UG  [3]FUNCAO  [4]SUBFUNCAO  [5]PROGRAMA
            #  [6]PAOE   [7]NATUREZA DESPESA  [8]MODALIDADE  [9]ELEMENTO
            #  [10]FONTE [11]ORCADO INICIAL   [12]CREDITO AUTORIZADO
            #  [13]REDUCAO(ANULADO) [14]EMPENHADO [15]LIQUIDADO [16]PAGO
            # ------------------------------------------------------------
            elif tipo_dado == "Despesa (FIP 616)":
                df = pd.read_excel(arquivo, skiprows=6, header=0)
                n = len(df.columns)

                def gc(row, i, default=0):
                    return row.iloc[i] if i < n else default

                linhas = []
                for _, row in df.iterrows():
                    try:
                        uo = norm(gc(row, 1))
                        if not uo or uo in ("nan", ""):
                            continue
                        ug        = norm(gc(row, 2))
                        funcao    = norm(gc(row, 3))
                        subfuncao = norm(gc(row, 4))
                        programa  = norm(gc(row, 5))
                        projeto   = norm(gc(row, 6))
                        natureza  = norm(gc(row, 7))
                        elemento  = limpar_f(gc(row, 9, 0))
                        fonte     = norm(gc(row, 10))
                        orc_ini   = limpar_f(gc(row, 11, 0))
                        cred_aut  = limpar_f(gc(row, 12, 0))

                        # Execucao so existe quando ha UG real (nao zero)
                        # e elemento de despesa informado
                        tem_exec = ug not in ("0", "", "nan") and elemento != 0
                        emp_cum  = limpar_f(gc(row, 14, 0)) if tem_exec else 0.0
                        liq_cum  = limpar_f(gc(row, 15, 0)) if tem_exec else 0.0
                        pag_cum  = limpar_f(gc(row, 16, 0)) if tem_exec else 0.0

                        linhas.append({
                            "uo": uo, "ug": ug, "funcao": funcao,
                            "subfuncao": subfuncao, "programa": programa,
                            "projeto": projeto, "natureza": natureza, "fonte": fonte,
                            "orc_ini": orc_ini, "cred_aut": cred_aut,
                            "emp_cum": emp_cum, "liq_cum": liq_cum, "pag_cum": pag_cum,
                        })
                    except Exception:
                        continue

                if not linhas:
                    st.warning("Nenhuma linha valida encontrada no arquivo.")
                else:
                    chaves = [
                        "uo", "ug", "funcao", "subfuncao",
                        "programa", "projeto", "natureza", "fonte"
                    ]
                    df_mes = (
                        pd.DataFrame(linhas)
                        .groupby(chaves, as_index=False)
                        .agg(
                            orc_ini=("orc_ini", "sum"),
                            cred_aut=("cred_aut", "sum"),
                            emp_cum=("emp_cum", "sum"),
                            liq_cum=("liq_cum", "sum"),
                            pag_cum=("pag_cum", "sum"),
                        )
                    )

                    # Subtrai acumulado dos meses anteriores -> valor mensal
                    if m_final > 1:
                        df_ant = pd.read_sql(
                            "SELECT uo,ug,funcao,subfuncao,programa,projeto,natureza,fonte,"
                            "SUM(empenhado) AS emp_ant,"
                            "SUM(liquidado) AS liq_ant,"
                            "SUM(pago) AS pag_ant "
                            "FROM despesas WHERE ano=2026 AND mes<? "
                            "GROUP BY uo,ug,funcao,subfuncao,programa,projeto,natureza,fonte",
                            conn, params=(m_final,)
                        )
                    else:
                        df_ant = pd.DataFrame(
                            columns=chaves + ["emp_ant", "liq_ant", "pag_ant"]
                        )

                    df_mes = df_mes.merge(df_ant, on=chaves, how="left").fillna(0)
                    df_mes["empenhado"] = (
                        df_mes["emp_cum"] - df_mes["emp_ant"]
                    ).clip(lower=0)
                    df_mes["liquidado"] = (
                        df_mes["liq_cum"] - df_mes["liq_ant"]
                    ).clip(lower=0)
                    df_mes["pago"] = (
                        df_mes["pag_cum"] - df_mes["pag_ant"]
                    ).clip(lower=0)

                    dados = [
                        (
                            m_final, 2026,
                            r.uo, r.ug, r.funcao, r.subfuncao, r.programa,
                            r.projeto, r.natureza, r.fonte,
                            float(r.orc_ini), float(r.cred_aut),
                            float(r.empenhado), float(r.liquidado), float(r.pago),
                        )
                        for r in df_mes.itertuples()
                    ]
                    conn.execute(
                        "DELETE FROM despesas WHERE ano=2026 AND mes=?", (m_final,)
                    )
                    conn.executemany(
                        "INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        dados
                    )
                    conn.commit()

                    ugs = sorted(df_mes["ug"].unique().tolist())
                    emp_total = df_mes["empenhado"].sum()
                    liq_total = df_mes["liquidado"].sum()
                    pag_total = df_mes["pago"].sum()
                    st.success(
                        "Despesa " + MESES_NOMES[m_final - 1] + "/2026: "
                        + str(len(dados)) + " grupos | "
                        + "Emp R$ {:,.0f} | Liq R$ {:,.0f} | Pago R$ {:,.0f}".format(
                            emp_total, liq_total, pag_total
                        )
                    )
                    st.info("UGs: " + str(ugs))

            # ------------------------------------------------------------
            # SUB-ELEMENTO (FIP 701)
            # Estrutura hierarquica: PROJ/ATIV -> NATUREZA -> sub-elementos
            # Colunas: [0]=descricao/codigo  [1]=LIQUIDADO  [2]=PAGO
            # ------------------------------------------------------------
            elif tipo_dado == "Sub-elemento (FIP 701)":
                df701 = pd.read_excel(arquivo, header=None)
                linhas = []
                cur_paoe = ""
                cur_nat_cod = ""
                cur_nat_desc = ""

                for i, row in df701.iterrows():
                    text = str(row.iloc[0]).strip().replace("\xa0", " ")
                    if i < 8 or not text or text == "nan":
                        continue
                    tu = sem_acento(text).upper()

                    if "PROJ/ATIV" in tu and ":" in tu:
                        m = re.search(r"(\d{5,8})", text)
                        if m:
                            cur_paoe = m.group(1)
                        continue

                    if "NATUREZA" in tu and "DESPESA" in tu and ":" in tu:
                        m = re.search(r":\s*(\d+)\s*-\s*(.*)", text)
                        if m:
                            cur_nat_cod = m.group(1).strip()
                            raw = m.group(2).replace("\xa0", " ").strip()
                            cur_nat_desc = (
                                raw.split(" - ")[0].strip()
                                if " - " in raw else raw
                            )
                        continue

                    if tu.startswith("TOTAL") or tu.startswith("CONSOLID") or tu.startswith("DOTA"):
                        continue

                    if re.match(r"^\d+\.\d+", text) and cur_paoe and cur_nat_cod:
                        parts = text.split(" ", 1)
                        sub_cod  = parts[0].strip()
                        sub_desc = parts[1].strip() if len(parts) > 1 else ""
                        liq_cum  = limpar_f(row.iloc[1]) if pd.notna(row.iloc[1]) else 0.0
                        pag_cum  = limpar_f(row.iloc[2]) if pd.notna(row.iloc[2]) else 0.0
                        linhas.append({
                            "paoe": cur_paoe,
                            "nat_cod": cur_nat_cod,
                            "nat_desc": cur_nat_desc,
                            "sub_cod": sub_cod,
                            "sub_desc": sub_desc,
                            "liq_cum": liq_cum,
                            "pag_cum": pag_cum,
                        })

                if not linhas:
                    st.warning("Nenhum sub-elemento valido encontrado.")
                else:
                    chaves_701 = ["paoe", "nat_cod", "sub_cod"]
                    df_mes = (
                        pd.DataFrame(linhas)
                        .groupby(chaves_701 + ["nat_desc", "sub_desc"], as_index=False)
                        .agg(liq_cum=("liq_cum", "sum"), pag_cum=("pag_cum", "sum"))
                    )

                    if m_final > 1:
                        df_ant = pd.read_sql(
                            "SELECT paoe, natureza_cod AS nat_cod,"
                            "subelemento_cod AS sub_cod,"
                            "SUM(liquidado) AS liq_ant, SUM(pago) AS pag_ant "
                            "FROM sub_elementos WHERE ano=2026 AND mes<? "
                            "GROUP BY paoe, natureza_cod, subelemento_cod",
                            conn, params=(m_final,)
                        )
                    else:
                        df_ant = pd.DataFrame(
                            columns=chaves_701 + ["liq_ant", "pag_ant"]
                        )

                    df_mes = df_mes.merge(df_ant, on=chaves_701, how="left").fillna(0)
                    df_mes["liquidado"] = (
                        df_mes["liq_cum"] - df_mes["liq_ant"]
                    ).clip(lower=0)
                    df_mes["pago"] = (
                        df_mes["pag_cum"] - df_mes["pag_ant"]
                    ).clip(lower=0)

                    dados = [
                        (
                            m_final, 2026,
                            r.paoe, r.nat_cod, r.nat_desc,
                            r.sub_cod, r.sub_desc,
                            float(r.liquidado), float(r.pago),
                        )
                        for r in df_mes.itertuples()
                    ]
                    conn.execute(
                        "DELETE FROM sub_elementos WHERE ano=2026 AND mes=?", (m_final,)
                    )
                    conn.executemany(
                        "INSERT INTO sub_elementos VALUES (?,?,?,?,?,?,?,?,?)", dados
                    )
                    conn.commit()
                    st.success(
                        "Sub-elemento " + MESES_NOMES[m_final - 1] + "/2026: "
                        + str(len(dados)) + " registros"
                    )

            conn.close()

        except Exception as e:
            st.error("Erro: " + str(e))
            import traceback
            st.code(traceback.format_exc())

    st.divider()
    st.subheader("Backup Receitas")
    conn_b = sqlite3.connect(DB_NAME)
    df_bkp = pd.read_sql("SELECT * FROM receitas", conn_b)
    conn_b.close()
    if not df_bkp.empty:
        csv = df_bkp.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Baixar CSV", data=csv,
            file_name="backup_receitas.csv", mime="text/csv"
        )
    file_restore = st.file_uploader("Restaurar (CSV)", type=["csv"])
    if file_restore and st.button("Restaurar"):
        df_res = pd.read_csv(file_restore)
        conn_r = sqlite3.connect(DB_NAME)
        df_res.to_sql("receitas", conn_r, if_exists="replace", index=False)
        conn_r.commit()
        conn_r.close()
        st.success("Restaurado!")
        st.rerun()

    st.divider()
    st.subheader("Limpeza Geral")
    confirma = st.checkbox("Confirmo apagar TODOS os dados")
    if st.button("Limpar Tudo"):
        if confirma:
            limpar_todos_dados()
            st.rerun()
        else:
            st.warning("Marque a caixa de confirmacao.")


# ---------------------------------------------------------------------------
# CARGA PRINCIPAL
# ---------------------------------------------------------------------------
conn_main = sqlite3.connect(DB_NAME)
df_rec  = pd.read_sql("SELECT * FROM receitas",       conn_main)
df_desp = pd.read_sql("SELECT * FROM despesas",       conn_main)
df_sub  = pd.read_sql("SELECT * FROM sub_elementos",  conn_main)
conn_main.close()

if "ug" not in df_desp.columns:
    df_desp["ug"] = "0"

tab1, tab2, tab3 = st.tabs(["Receitas", "Despesas", "Comparativo"])


# ---------------------------------------------------------------------------
# ABA 1: RECEITAS
# ---------------------------------------------------------------------------
with tab1:
    if df_rec.empty:
        st.info("Importe dados de Receita (FIP 729) para visualizar.")
    else:
        with st.expander("Classificar Categorias"):
            c1, c2, c3 = st.columns([2, 2, 1])
            sel_nat = c1.selectbox(
                "Natureza:", sorted(df_rec["natureza"].unique()), key="sel_nat_c"
            )
            sel_cat = c2.selectbox("Categoria:", CATEGORIAS_REC, key="sel_cat_c")
            if c3.button("Salvar"):
                cu = sqlite3.connect(DB_NAME)
                cu.execute(
                    "UPDATE receitas SET categoria=? WHERE natureza=?",
                    (sel_cat, sel_nat)
                )
                cu.commit()
                cu.close()
                st.rerun()

        st.divider()
        f1, f2, f3 = st.columns(3)
        ms_r = f1.multiselect(
            "Meses:", sorted(df_rec["mes"].unique()),
            default=list(df_rec["mes"].unique()),
            format_func=lambda x: MESES_NOMES[x - 1], key="ms_r"
        )
        cat_sel = f2.multiselect(
            "Categoria:", sorted(df_rec["categoria"].unique()),
            default=list(df_rec["categoria"].unique()), key="cat_r"
        )
        nat_sel = f3.multiselect(
            "Natureza:", sorted(df_rec["natureza"].unique()), key="nat_r"
        )

        df_rf = df_rec[df_rec["mes"].isin(ms_r) & df_rec["categoria"].isin(cat_sel)]
        if nat_sel:
            df_rf = df_rf[df_rf["natureza"].isin(nat_sel)]

        if not df_rf.empty and ms_r:
            v_real = df_rf["realizado"].sum()
            v_orc  = (
                df_rec[df_rec["mes"] == max(ms_r)]
                .groupby("codigo_full")["orcado"].max().sum()
            )
            k1, k2, k3 = st.columns(3)
            k1.metric("Orcado Atual",  "R$ {:,.2f}".format(v_orc))
            k2.metric("Realizado",     "R$ {:,.2f}".format(v_real))
            k3.metric("Atingimento",
                      "{:.1f}%".format(v_real / v_orc * 100 if v_orc != 0 else 0))

            df_g = df_rf.groupby("mes").agg({"realizado": "sum"}).reset_index()
            df_g["previsao"] = [
                df_rf[df_rf["mes"] == m].groupby("codigo_full")["previsao"].max().sum()
                for m in df_g["mes"]
            ]
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=[MESES_NOMES[m - 1] for m in df_g["mes"]],
                y=df_g["realizado"], name="Realizado", marker_color="#2E7D32"
            ))
            fig.add_trace(go.Scatter(
                x=[MESES_NOMES[m - 1] for m in df_g["mes"]],
                y=df_g["previsao"], name="Previsao",
                line=dict(color="#FF9800", width=3, dash="dot")
            ))
            fig.update_layout(
                height=350, margin=dict(l=0, r=0, t=30, b=0),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(
                df_rf[["categoria", "codigo_full", "natureza", "realizado", "orcado"]]
                .style.format({"realizado": "{:,.2f}", "orcado": "{:,.2f}"}),
                use_container_width=True
            )


# ---------------------------------------------------------------------------
# ABA 2: DESPESAS
# ---------------------------------------------------------------------------
with tab2:
    if df_desp.empty:
        st.info("Importe dados de Despesa (FIP 616) para visualizar.")
    else:
        ugs_disp = sorted(df_desp["ug"].unique().tolist())

        f1, f2, f3 = st.columns(3)
        ms_d = f1.multiselect(
            "Meses:", sorted(df_desp["mes"].unique()),
            default=list(df_desp["mes"].unique()),
            format_func=lambda x: MESES_NOMES[x - 1], key="ms_d"
        )
        ug_sel = f2.multiselect(
            "UG (Unidade Gestora):", ugs_disp, default=ugs_disp, key="ug_d"
        )
        fs = f3.multiselect(
            "Funcao:", sorted(df_desp["funcao"].unique()), key="func_d"
        )

        f4, f5, f6 = st.columns(3)
        sf  = f4.multiselect(
            "Subfuncao:", sorted(df_desp["subfuncao"].unique()), key="subf_d"
        )
        ps  = f5.multiselect(
            "Programa:", sorted(df_desp["programa"].unique()), key="prog_d"
        )
        fts = f6.multiselect(
            "Fonte:", sorted(df_desp["fonte"].unique()), key="font_d"
        )
        bd = st.text_input("Natureza (busca por texto):", key="busca_d")

        df_f = df_desp[df_desp["mes"].isin(ms_d)]
        if ug_sel:  df_f = df_f[df_f["ug"].isin(ug_sel)]
        if fs:      df_f = df_f[df_f["funcao"].isin(fs)]
        if sf:      df_f = df_f[df_f["subfuncao"].isin(sf)]
        if ps:      df_f = df_f[df_f["programa"].isin(ps)]
        if fts:     df_f = df_f[df_f["fonte"].isin(fts)]
        if bd:      df_f = df_f[df_f["natureza"].str.contains(bd, case=False, na=False)]

        if not df_f.empty and ms_d:
            m_max = max(ms_d)

            # Credito Autorizado: consolidado do ultimo mes (todas as UGs)
            cred_total = df_desp[df_desp["mes"] == m_max]["cred_autorizado"].sum()

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Cred. Autorizado (Orcamento)", "R$ {:,.2f}".format(cred_total))
            k2.metric("Empenhado",  "R$ {:,.2f}".format(df_f["empenhado"].sum()))
            k3.metric("Liquidado",  "R$ {:,.2f}".format(df_f["liquidado"].sum()))
            k4.metric("Pago",       "R$ {:,.2f}".format(df_f["pago"].sum()))

            # Tabela: adiciona coluna UG quando ha filtro especifico
            ug_filtrada = set(ug_sel) != set(ugs_disp)
            col_chave = (["ug"] if ug_filtrada else []) + [
                "funcao", "subfuncao", "programa", "projeto", "fonte", "natureza"
            ]
            df_exec = df_f.groupby(col_chave, as_index=False)[
                ["empenhado", "liquidado", "pago"]
            ].sum()

            st.dataframe(
                df_exec[col_chave + ["empenhado", "liquidado", "pago"]]
                .style.format({
                    "empenhado": "{:,.2f}",
                    "liquidado": "{:,.2f}",
                    "pago": "{:,.2f}"
                }),
                use_container_width=True
            )

        # Sub-elementos
        if not df_sub.empty:
            st.divider()
            with st.expander("Sub-elementos por PAOE (FIP 701)"):
                fs1, fs2, fs3 = st.columns(3)
                ms_s = fs1.multiselect(
                    "Meses:", sorted(df_sub["mes"].unique()),
                    default=list(df_sub["mes"].unique()),
                    format_func=lambda x: MESES_NOMES[x - 1], key="ms_s"
                )
                paoe_s = fs2.multiselect(
                    "PAOE:", sorted(df_sub["paoe"].unique()), key="paoe_s"
                )
                nat_s = fs3.multiselect(
                    "Natureza:", sorted(df_sub["natureza_cod"].unique()), key="nat_s"
                )

                df_sf = df_sub[df_sub["mes"].isin(ms_s)]
                if paoe_s: df_sf = df_sf[df_sf["paoe"].isin(paoe_s)]
                if nat_s:  df_sf = df_sf[df_sf["natureza_cod"].isin(nat_s)]

                if not df_sf.empty:
                    col_s = [
                        "paoe", "natureza_cod", "natureza_desc",
                        "subelemento_cod", "subelemento_desc"
                    ]
                    df_sv = df_sf.groupby(col_s, as_index=False)[
                        ["liquidado", "pago"]
                    ].sum()
                    ks1, ks2 = st.columns(2)
                    ks1.metric("Liquidado", "R$ {:,.2f}".format(df_sv["liquidado"].sum()))
                    ks2.metric("Pago",      "R$ {:,.2f}".format(df_sv["pago"].sum()))
                    st.dataframe(
                        df_sv[col_s + ["liquidado", "pago"]]
                        .style.format({"liquidado": "{:,.2f}", "pago": "{:,.2f}"}),
                        use_container_width=True
                    )
                else:
                    st.info("Nenhum dado para os filtros selecionados.")


# ---------------------------------------------------------------------------
# ABA 3: COMPARATIVO
# ---------------------------------------------------------------------------
with tab3:
    st.subheader("Confronto Geral - Receita x Despesa")
    if df_rec.empty and df_desp.empty:
        st.info("Importe dados para visualizar.")
    else:
        todos = sorted(set(df_rec["mes"].tolist() + df_desp["mes"].tolist()))
        ms_c = st.multiselect(
            "Meses:", todos, default=todos,
            format_func=lambda x: MESES_NOMES[x - 1], key="ms_c"
        )
        tr = df_rec[df_rec["mes"].isin(ms_c)]["realizado"].sum()
        te = df_desp[df_desp["mes"].isin(ms_c)]["empenhado"].sum()
        tl = df_desp[df_desp["mes"].isin(ms_c)]["liquidado"].sum()
        tp = df_desp[df_desp["mes"].isin(ms_c)]["pago"].sum()

        kc1, kc2, kc3, kc4 = st.columns(4)
        kc1.metric("Receita Arrecadada", "R$ {:,.2f}".format(tr))
        kc2.metric("Desp. Empenhada",    "R$ {:,.2f}".format(te))
        kc3.metric("Desp. Liquidada",    "R$ {:,.2f}".format(tl))
        kc4.metric("Desp. Paga",         "R$ {:,.2f}".format(tp))

        st.divider()
        m1, m2 = st.columns(2)
        m1.info(
            "Superavit Financeiro (Receita - Pago): R$ {:,.2f}".format(tr - tp)
        )
        m2.warning(
            "Superavit Orcamentario (Receita - Empenhado): R$ {:,.2f}".format(tr - te)
        )

        fig_c = go.Figure()
        fig_c.add_trace(go.Bar(name="Receita", x=["Confronto"], y=[tr], marker_color="green"))
        fig_c.add_trace(go.Bar(name="Empenhado", x=["Confronto"], y=[te], marker_color="orange"))
        fig_c.add_trace(go.Bar(name="Liquidado", x=["Confronto"], y=[tl], marker_color="#72A0C1"))
        fig_c.add_trace(go.Bar(name="Pago", x=["Confronto"], y=[tp], marker_color="red"))
        fig_c.update_layout(
            height=400, barmode="group", margin=dict(l=0, r=0, t=30, b=0)
        )
        st.plotly_chart(fig_c, use_container_width=True)
