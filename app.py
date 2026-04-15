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
MESES_LONGO = {
    1: "JANEIRO", 2: "FEVEREIRO", 3: "MARÇO", 4: "ABRIL", 5: "MAIO", 6: "JUNHO",
    7: "JULHO", 8: "AGOSTO", 9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO"
}
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
CATEGORIAS_REC = [
    "Receita Tributária",
    "Receita Patrimonial",
    "Receita de Serviços",
    "Repasses Correntes",
    "Demais Receitas"
]

FUNCOES_MAP = {
    "1": "LEGISLATIVA", "2": "JUDICIÁRIA", "3": "ESSENCIAL À JUSTIÇA", "4": "ADMINISTRAÇÃO",
    "6": "SEGURANÇA PÚBLICA", "8": "ASSISTÊNCIA SOCIAL", "9": "PREVIDÊNCIA SOCIAL",
    "10": "SAÚDE", "12": "EDUCAÇÃO", "13": "CULTURA", "14": "DIREITOS DA CIDADANIA",
    "15": "URBANISMO", "16": "HABITAÇÃO", "17": "SANEAMENTO", "18": "GESTÃO AMBIENTAL",
    "19": "CIÊNCIA E TECNOLOGIA", "20": "AGRICULTURA", "22": "INDÚSTRIA",
    "23": "COMÉRCIO E SERVIÇOS", "24": "COMUNICAÇÕES", "26": "TRANSPORTE",
    "27": "DESPORTO E LAZER", "28": "ENCARGOS ESPECIAIS"
}

SUBFUNCOES_MAP = {
    "61": "Ação Judiciária", "62": "Defesa do Interesse Público", "91": "Defesa da Ordem Jurídica",
    "92": "Representação Judicial e Extrajudicial", "122": "Administração Geral",
    "123": "Administração Financeira", "126": "Tecnologia da Informação",
    "128": "Formação de Recursos Humanos", "131": "Comunicação Social",
    "272": "Previdência do Regime Estatutário", "331": "Proteção e Benefícios ao Trabalhador",
    "332": "Relações de Trabalho", "846": "Outros Encargos Especiais"
}

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

    # Adicionado coluna UG
    conn.execute('''
        CREATE TABLE IF NOT EXISTS despesas (
            mes INTEGER, ano INTEGER, uo TEXT, ug TEXT, funcao TEXT, subfuncao TEXT,
            programa TEXT, projeto TEXT, natureza TEXT, fonte TEXT,
            orcado_inicial REAL, cred_autorizado REAL, empenhado REAL, liquidado REAL, pago REAL
        )
    ''')
    # Script para garantir que a coluna UG exista caso o banco seja antigo
    try:
        conn.execute("ALTER TABLE despesas ADD COLUMN ug TEXT")
    except:
        pass
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

def limpar_todos_dados():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM receitas"); conn.execute("DELETE FROM despesas")
    conn.commit(); conn.close()

def safe_div(n, d):
    return (n / d) if d not in [0, None] else 0.0

def periodo_bimestre_extenso(meses_bim):
    meses_bim = sorted(meses_bim)
    if len(meses_bim) == 1: return MESES_LONGO.get(meses_bim[0], "")
    if len(meses_bim) == 2: return f"{MESES_LONGO.get(meses_bim[0], '')} E {MESES_LONGO.get(meses_bim[1], '')}"
    return " A ".join([MESES_LONGO.get(m, str(m)) for m in meses_bim])

def natureza_para_str(v):
    s = re.sub(r"\D", "", str(v)) if pd.notna(v) else ""
    return s

def modalidade_da_natureza(natureza):
    s = natureza_para_str(natureza)
    return s[2:4] if len(s) >= 4 else ""

def grupo_natureza(natureza):
    s = natureza_para_str(natureza)
    return s[0] if s else ""

def nome_funcao(cod):
    return FUNCOES_MAP.get(str(cod), f"FUNÇÃO {cod}")

def nome_subfuncao(cod):
    return SUBFUNCOES_MAP.get(str(cod), f"Subfunção {cod}")

def somar_campos(df, cols):
    if df.empty: return {c: 0.0 for c in cols}
    return {c: float(df[c].sum()) for c in cols}

def normalizar_texto_cabecalho(txt):
    txt = "" if pd.isna(txt) else str(txt)
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return txt.upper().strip()

def extrair_mes_ano_arquivo(arquivo):
    try: arquivo.seek(0)
    except: pass
    cab = pd.read_excel(arquivo, header=None, nrows=6)
    textos = []
    if len(cab) > 3:
        linha4 = " ".join(cab.iloc[3].fillna("").astype(str).tolist())
        textos.append(linha4)
    for i in range(min(len(cab), 6)):
        linha = " ".join(cab.iloc[i].fillna("").astype(str).tolist())
        textos.append(linha)
    texto_norm = normalizar_texto_cabecalho(" | ".join(textos))
    mes_encontrado = None
    for nome_mes, num_mes in MESES_MAPA.items():
        if normalizar_texto_cabecalho(nome_mes) in texto_norm:
            mes_encontrado = num_mes; break
    ano_match = re.search(r'\b(20\d{2})\b', texto_norm)
    ano_encontrado = int(ano_match.group(1)) if ano_match else None
    try: arquivo.seek(0)
    except: pass
    if mes_encontrado is None or ano_encontrado is None:
        raise ValueError("Não foi possível identificar mês e ano no cabeçalho. Verifique a linha 4 da planilha.")
    return mes_encontrado, ano_encontrado

def criar_formatos_excel(workbook):
    base = {'font_name': 'Arial', 'font_size': 8}
    return {
        'fmt_header': workbook.add_format({**base, 'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'bg_color': '#BFBFBF', 'text_wrap': True}),
        'fmt_group': workbook.add_format({**base, 'bold': True, 'border': 1, 'bg_color': '#D9D9D9'}),
        'fmt_subgroup': workbook.add_format({**base, 'bold': True, 'border': 1, 'bg_color': '#EDEDED'}),
        'fmt_item': workbook.add_format({**base, 'border': 1, 'indent': 1}),
        'fmt_subitem': workbook.add_format({**base, 'border': 1, 'indent': 2}),
        'fmt_total_text': workbook.add_format({**base, 'bold': True, 'border': 1, 'bg_color': '#EDEDED'}),
        'fmt_money': workbook.add_format({**base, 'border': 1, 'num_format': '#,##0.00'}),
        'fmt_money_bold': workbook.add_format({**base, 'bold': True, 'border': 1, 'bg_color': '#EDEDED', 'num_format': '#,##0.00'}),
        'fmt_money_total': workbook.add_format({**base, 'bold': True, 'border': 1, 'bg_color': '#EDEDED', 'num_format': '#,##0.00'}),
        'fmt_pct': workbook.add_format({**base, 'border': 1, 'num_format': '0.00%'}),
        'fmt_pct_bold': workbook.add_format({**base, 'bold': True, 'border': 1, 'bg_color': '#EDEDED', 'num_format': '0.00%'}),
        'fmt_pct_total': workbook.add_format({**base, 'bold': True, 'border': 1, 'bg_color': '#EDEDED', 'num_format': '0.00%'})
    }

# --- PREPARAÇÃO DE DADOS LRF ---
def preparar_base_receitas_lrf(df_rec, meses_bim, meses_ate_agora):
    if df_rec.empty: return pd.DataFrame()
    df_base = df_rec[~df_rec['codigo_full'].astype(str).str.startswith('9')].copy()
    chaves = ['categoria', 'natureza']
    df_orcado = df_base[df_base['mes'].isin(meses_ate_agora)].groupby(chaves, as_index=False).agg({'orcado': 'max'}).rename(columns={'orcado': 'previsao_atualizada'})
    df_orcado['previsao_inicial'] = df_orcado['previsao_atualizada']
    df_bim = df_base[df_base['mes'].isin(meses_bim)].groupby(chaves, as_index=False)['realizado'].sum().rename(columns={'realizado': 'no_bimestre'})
    df_ate = df_base[df_base['mes'].isin(meses_ate_agora)].groupby(chaves, as_index=False)['realizado'].sum().rename(columns={'realizado': 'ate_bimestre'})
    base = df_orcado.merge(df_bim, on=chaves, how='left').merge(df_ate, on=chaves, how='left').fillna(0)
    base['saldo'] = base['previsao_atualizada'] - base['ate_bimestre']
    base['perc_bim'] = base.apply(lambda r: safe_div(r['no_bimestre'], r['previsao_atualizada']), axis=1)
    base['perc_ate'] = base.apply(lambda r: safe_div(r['ate_bimestre'], r['previsao_atualizada']), axis=1)
    return base

def preparar_deducoes_receitas_lrf(df_rec, meses_bim, meses_ate_agora):
    df_ded = df_rec[df_rec['codigo_full'].astype(str).str.startswith('9')].copy()
    if df_ded.empty: return {'previsao_inicial': 0.0, 'previsao_atualizada': 0.0, 'no_bimestre': 0.0, 'ate_bimestre': 0.0, 'saldo': 0.0, 'perc_bim': 0.0, 'perc_ate': 0.0}
    prev_at = float(df_ded[df_ded['mes'].isin(meses_ate_agora)].groupby('codigo_full')['orcado'].max().sum())
    no_bim = float(df_ded[df_ded['mes'].isin(meses_bim)]['realizado'].sum())
    ate_bim = float(df_ded[df_ded['mes'].isin(meses_ate_agora)]['realizado'].sum())
    return {'previsao_inicial': prev_at, 'previsao_atualizada': prev_at, 'no_bimestre': no_bim, 'ate_bimestre': ate_bim, 'saldo': prev_at - ate_bim, 'perc_bim': safe_div(no_bim, prev_at), 'perc_ate': safe_div(ate_bim, prev_at)}

def preparar_base_despesas_lrf(df_desp, meses_bim, meses_ate_agora):
    if df_desp.empty: return pd.DataFrame()
    chaves = ['natureza']; m_max = max(meses_ate_agora)
    df_last = df_desp[df_desp['mes'] == m_max].groupby(chaves, as_index=False).agg({'orcado_inicial': 'sum', 'cred_autorizado': 'sum'})
    df_bim = df_desp[df_desp['mes'].isin(meses_bim)].groupby(chaves, as_index=False).agg({'empenhado': 'sum', 'liquidado': 'sum'}).rename(columns={'empenhado': 'emp_no_bim', 'liquidado': 'liq_no_bim'})
    df_ate = df_desp[df_desp['mes'].isin(meses_ate_agora)].groupby(chaves, as_index=False).agg({'empenhado': 'sum', 'liquidado': 'sum', 'pago': 'sum'}).rename(columns={'empenhado': 'emp_ate', 'liquidado': 'liq_ate', 'pago': 'pago_ate'})
    base = df_last.merge(df_bim, on=chaves, how='outer').merge(df_ate, on=chaves, how='outer').fillna(0)
    base['modalidade'] = base['natureza'].apply(modalidade_da_natureza)
    base['grupo'] = base['natureza'].apply(grupo_natureza)
    return base

def preparar_base_funcional_lrf(df_desp, meses_bim, meses_ate_agora):
    if df_desp.empty: return pd.DataFrame()
    chaves = ['funcao', 'subfuncao']; m_max = max(meses_ate_agora)
    df_last = df_desp[df_desp['mes'] == m_max].groupby(chaves, as_index=False).agg({'orcado_inicial': 'sum', 'cred_autorizado': 'sum'})
    df_bim = df_desp[df_desp['mes'].isin(meses_bim)].groupby(chaves, as_index=False).agg({'empenhado': 'sum', 'liquidado': 'sum'}).rename(columns={'empenhado': 'emp_no_bim', 'liquidado': 'liq_no_bim'})
    df_ate = df_desp[df_desp['mes'].isin(meses_ate_agora)].groupby(chaves, as_index=False).agg({'empenhado': 'sum', 'liquidado': 'sum'}).rename(columns={'empenhado': 'emp_ate', 'liquidado': 'liq_ate'})
    return df_last.merge(df_bim, on=chaves, how='outer').merge(df_ate, on=chaves, how='outer').fillna(0)

# --- GERADORES EXCEL ---
def gerar_excel_anexo1(df_rec, meses_bim, meses_ate_agora):
    base = preparar_base_receitas_lrf(df_rec, meses_bim, meses_ate_agora)
    deducoes = preparar_deducoes_receitas_lrf(df_rec, meses_bim, meses_ate_agora)
    periodo = periodo_bimestre_extenso(meses_bim)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book; worksheet = workbook.add_worksheet('Anexo_I')
        formatos = criar_formatos_excel(workbook)
        worksheet.set_column('A:A', 42); worksheet.set_column('B:D', 18); worksheet.set_column('E:E', 10); worksheet.set_column('F:F', 18); worksheet.set_column('G:G', 10); worksheet.set_column('H:H', 18)
        worksheet.merge_range(0, 0, 1, 0, 'RECEITAS', formatos['fmt_header'])
        worksheet.merge_range(0, 1, 1, 1, 'PREVISÃO INICIAL', formatos['fmt_header'])
        worksheet.merge_range(0, 2, 1, 2, 'PREVISÃO ATUALIZADA (A)', formatos['fmt_header'])
        worksheet.merge_range(0, 3, 0, 7, 'RECEITAS REALIZADAS', formatos['fmt_header'])
        worksheet.write(1, 3, f'NO BIMESTRE\n{periodo}', formatos['fmt_header'])
        worksheet.write(1, 4, '%\n(B/A)', formatos['fmt_header'])
        worksheet.write(1, 5, f'ATÉ O BIMESTRE\n{periodo}', formatos['fmt_header'])
        worksheet.write(1, 6, '%\n(C/A)', formatos['fmt_header'])
        worksheet.write(1, 7, 'SALDO A REALIZAR', formatos['fmt_header'])
        row = 2
        for _, r in base.iterrows():
            worksheet.write(row, 0, str(r['natureza']), formatos['fmt_item'])
            worksheet.write_number(row, 1, r['previsao_inicial'], formatos['fmt_money'])
            worksheet.write_number(row, 2, r['previsao_atualizada'], formatos['fmt_money'])
            worksheet.write_number(row, 3, r['no_bimestre'], formatos['fmt_money'])
            worksheet.write_number(row, 4, r['perc_bim'], formatos['fmt_pct'])
            worksheet.write_number(row, 5, r['ate_bimestre'], formatos['fmt_money'])
            worksheet.write_number(row, 6, r['perc_ate'], formatos['fmt_pct'])
            worksheet.write_number(row, 7, r['saldo'], formatos['fmt_money'])
            row += 1
    return output.getvalue()

def gerar_excel_anexo1a(df_desp, df_rec, meses_bim, meses_ate_agora):
    base = preparar_base_despesas_lrf(df_desp, meses_bim, meses_ate_agora)
    periodo = periodo_bimestre_extenso(meses_bim)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book; worksheet = workbook.add_worksheet('Anexo_IA')
        formatos = criar_formatos_excel(workbook)
        worksheet.set_column('A:A', 48); worksheet.set_column('B:K', 16)
        worksheet.merge_range(0, 0, 2, 0, 'DESPESAS', formatos['fmt_header'])
        worksheet.merge_range(0, 1, 2, 1, 'DOTAÇÃO INICIAL', formatos['fmt_header'])
        worksheet.merge_range(0, 2, 2, 2, 'DOTAÇÃO ATUALIZADA', formatos['fmt_header'])
        row = 3
        for _, r in base.iterrows():
            worksheet.write(row, 0, str(r['natureza']), formatos['fmt_item'])
            worksheet.write_number(row, 1, r['orcado_inicial'], formatos['fmt_money'])
            worksheet.write_number(row, 2, r['cred_autorizado'], formatos['fmt_money'])
            worksheet.write_number(row, 4, r['emp_ate'], formatos['fmt_money'])
            worksheet.write_number(row, 7, r['liq_ate'], formatos['fmt_money'])
            worksheet.write_number(row, 9, r['pago_ate'], formatos['fmt_money'])
            row += 1
    return output.getvalue()

def gerar_excel_anexo2(df_desp, meses_bim, meses_ate_agora):
    base = preparar_base_funcional_lrf(df_desp, meses_bim, meses_ate_agora)
    periodo = periodo_bimestre_extenso(meses_bim)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book; worksheet = workbook.add_worksheet('Anexo_II')
        formatos = criar_formatos_excel(workbook)
        worksheet.set_column('A:A', 32); worksheet.set_column('B:C', 16); worksheet.set_column('D:K', 14)
        worksheet.merge_range(0, 0, 2, 0, 'FUNÇÃO/SUBFUNÇÃO', formatos['fmt_header'])
        row = 3
        for _, r in base.iterrows():
            worksheet.write(row, 0, f"{nome_funcao(r['funcao'])} / {nome_subfuncao(r['subfuncao'])}", formatos['fmt_item'])
            worksheet.write_number(row, 1, r['orcado_inicial'], formatos['fmt_money'])
            worksheet.write_number(row, 2, r['cred_autorizado'], formatos['fmt_money'])
            worksheet.write_number(row, 4, r['emp_ate'], formatos['fmt_money'])
            worksheet.write_number(row, 8, r['liq_ate'], formatos['fmt_money'])
            row += 1
    return output.getvalue()

# --- INICIALIZAÇÃO ---
inicializar_banco()

# --- SIDEBAR ---
with st.sidebar:
    st.subheader("📥 Importar Dados")
    tipo_dado = st.radio("Tipo:", ["Receita", "Despesa"])
    arquivo = st.file_uploader(f"Arquivo {tipo_dado}", type=["xlsx"])

    if arquivo and st.button("🚀 Processar Dados"):
        try:
            m_final, ano_final = extrair_mes_ano_arquivo(arquivo)
            st.info(f"Competência: {MESES_NOMES[m_final-1]}/{ano_final}")
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
                        dados.append((m_final, ano_final, cod, str(row.iloc[1]).replace('"', ''), limpar_f(row.iloc[3]), real, limpar_f(row.iloc[5]), cat_atual))
                conn.execute("DELETE FROM receitas WHERE ano = ? AND mes = ?", (ano_final, m_final))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?,?)", dados)
            else:
                df = pd.read_excel(arquivo, skiprows=6); df.columns = df.columns.str.strip().str.upper()
                linhas = []
                for _, row in df.iterrows():
                    uo = normalizar_chave(row.get('UO', ''))
                    ug = normalizar_chave(row.get('UG', '')) # UG CAPTURADA
                    if uo != "":
                        elem = limpar_f(row.get('ELEMENTO', 0)); tem_ex = (ug != '0' and elem != 0)
                        linhas.append({'uo': uo, 'ug': ug, 'funcao': normalizar_chave(row.get('FUNÇÃO', '')), 'subfuncao': normalizar_chave(row.get('SUBFUNÇÃO', '')), 'programa': normalizar_chave(row.get('PROGRAMA', '')), 'projeto': normalizar_chave(row.get('PAOE', '')), 'natureza': normalizar_chave(row.get('NATUREZA DESPESA', '')), 'fonte': normalizar_chave(row.get('FONTE', '')), 'orcado_inicial': limpar_f(row.get('ORÇADO INICIAL', 0)), 'cred_autorizado': limpar_f(row.get('CRÉDITO AUTORIZADO', 0)), 'empenhado_cum': limpar_f(row.get('EMPENHADO', 0)) if tem_ex else 0.0, 'liquidado_cum': limpar_f(row.get('LIQUIDADO', 0)) if tem_ex else 0.0, 'pago_cum': limpar_f(row.get('PAGO', 0)) if tem_ex else 0.0})
                if linhas:
                    df_mes = pd.DataFrame(linhas); chaves = ['uo', 'ug', 'funcao', 'subfuncao', 'programa', 'projeto', 'natureza', 'fonte']
                    df_mes = df_mes.groupby(chaves, as_index=False).agg({'orcado_inicial': 'sum', 'cred_autorizado': 'sum', 'empenhado_cum': 'sum', 'liquidado_cum': 'sum', 'pago_cum': 'sum'})
                    if m_final > 1:
                        df_ant = pd.read_sql("SELECT uo, ug, funcao, subfuncao, programa, projeto, natureza, fonte, SUM(empenhado) AS empenhado_ant, SUM(liquidado) AS liquidado_ant, SUM(pago) AS pago_ant FROM despesas WHERE ano = ? AND mes < ? GROUP BY uo, ug, funcao, subfuncao, programa, projeto, natureza, fonte", conn, params=(ano_final, m_final))
                    else:
                        df_ant = pd.DataFrame(columns=chaves + ['empenhado_ant', 'liquidado_ant', 'pago_ant'])
                    df_mes = df_mes.merge(df_ant, on=chaves, how='left').fillna(0)
                    df_mes['empenhado'] = df_mes['empenhado_cum'] - df_mes['empenhado_ant']
                    df_mes['liquidado'] = df_mes['liquidado_cum'] - df_mes['liquidado_ant']
                    df_mes['pago'] = df_mes['pago_cum'] - df_mes['pago_ant']
                    dados = [(m_final, ano_final, r['uo'], r['ug'], r['funcao'], r['subfuncao'], r['programa'], r['projeto'], r['natureza'], r['fonte'], float(r['orcado_inicial']), float(r['cred_autorizado']), float(r['empenhado']), float(r['liquidado']), float(r['pago'])) for _, r in df_mes.iterrows()]
                    conn.execute("DELETE FROM despesas WHERE ano = ? AND mes = ?", (ano_final, m_final))
                    conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
            conn.commit(); conn.close(); st.success("Sucesso!"); st.rerun()
        except Exception as e: st.error(f"Erro: {e}")

    st.divider()
    st.subheader("💾 Backup/Limpeza")
    conn = sqlite3.connect(DB_NAME); df_bkp = pd.read_sql("SELECT * FROM receitas", conn); conn.close()
    if not df_bkp.empty:
        st.download_button("📥 Baixar Backup", data=df_bkp.to_csv(index=False).encode('utf-8'), file_name="backup_fiplan.csv", mime="text/csv")
    confirma = st.checkbox("Confirmo apagar tudo")
    if st.button("🗑️ Limpar Dados") and confirma: limpar_todos_dados(); st.rerun()

# --- CARGA ---
conn = sqlite3.connect(DB_NAME)
df_rec = pd.read_sql("SELECT * FROM receitas", conn)
df_desp = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

tab1, tab2, tab3, tab4 = st.tabs(["📊 Receitas", "💸 Despesas", "⚖️ Comparativo", "📄 Relatórios LRF"])

with tab1:
    if not df_rec.empty:
        with st.expander("🏷️ Classificar Categorias de Receita"):
            c1, c2, c3 = st.columns([2, 2, 1])
            sel_nat = c1.selectbox("Natureza:", sorted(df_rec['natureza'].unique()), key="sel_nat_class")
            sel_cat = c2.selectbox("Atribuir Categoria:", CATEGORIAS_REC, key="sel_cat_class")
            if c3.button("Salvar Categoria"):
                conn = sqlite3.connect(DB_NAME); conn.execute("UPDATE receitas SET categoria = ? WHERE natureza = ?", (sel_cat, sel_nat))
                conn.commit(); conn.close(); st.rerun()
        st.divider()
        f0, f1, f2, f3 = st.columns(4)
        anos_disp = sorted(df_rec['ano'].unique())
        anos_sel = f0.multiselect("Ano:", anos_disp, default=anos_disp, key="ano_rec")
        df_base = df_rec[df_rec['ano'].isin(anos_sel)] if anos_sel else df_rec.iloc[0:0]
        ms_r = f1.multiselect("Meses:", sorted(df_base['mes'].unique()), default=sorted(df_base['mes'].unique()), format_func=lambda x: MESES_NOMES[x-1], key="ms_rec")
        cat_sel = f2.multiselect("Categoria:", sorted(df_base['categoria'].unique()), default=sorted(df_base['categoria'].unique()), key="cat_rec")
        nat_sel = f3.multiselect("Natureza:", sorted(df_base['natureza'].unique()), default=sorted(df_base['natureza'].unique()), key="nat_rec")
        df_rf = df_base[df_base['mes'].isin(ms_r) & df_base['categoria'].isin(cat_sel) & df_base['natureza'].isin(nat_sel)]
        if not df_rf.empty:
            v_real = df_rf['realizado'].sum(); u_c = df_rf[['ano','mes']].drop_duplicates().sort_values(['ano','mes']).iloc[-1]
            v_orc = df_base[(df_base['ano']==u_c['ano'])&(df_base['mes']==u_c['mes'])&(df_base['categoria'].isin(cat_sel))&(df_base['natureza'].isin(nat_sel))].groupby('codigo_full')['orcado'].max().sum()
            k1, k2, k3 = st.columns(3); k1.metric("Orçado Atual", f"R$ {v_orc:,.2f}"); k2.metric("Realizado", f"R$ {v_real:,.2f}"); k3.metric("Atingimento", f"{(v_real/v_orc*100 if v_orc!=0 else 0):.1f}%")
            df_g = df_rf.groupby(['ano','mes'], as_index=False).agg({'realizado':'sum'})
            df_g['comp'] = df_g.apply(lambda r: f"{MESES_NOMES[int(r['mes'])-1]}/{int(r['ano'])}", axis=1)
            fig = go.Figure(); fig.add_trace(go.Bar(x=df_g['comp'], y=df_g['realizado'], name="Realizado", marker_color='#2E7D32'))
            fig.update_layout(height=350, margin=dict(l=0,r=0,t=30,b=0)); st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_rf[['ano','mes','categoria','natureza','realizado','orcado']].style.format({'realizado':'{:,.2f}','orcado':'{:,.2f}'}), width='stretch')

with tab2:
    if not df_desp.empty:
        f0, f1, f2, f3 = st.columns(4)
        anos_sel = f0.multiselect("Ano:", sorted(df_desp['ano'].unique()), default=sorted(df_desp['ano'].unique()), key="ano_desp")
        df_base = df_desp[df_desp['ano'].isin(anos_sel)]
        ms_d = f1.multiselect("Meses:", sorted(df_base['mes'].unique()), default=sorted(df_base['mes'].unique()), format_func=lambda x: MESES_NOMES[x-1], key="ms_desp")
        ug_sel = f2.multiselect("UG:", sorted(df_base['ug'].unique()), default=sorted(df_base['ug'].unique()), key="ug_desp") # NOVO FILTRO UG
        fs = f3.multiselect("Função:", sorted(df_base['funcao'].unique()), key="func_desp")
        f4, f5, f6 = st.columns(3)
        sf = f4.multiselect("Subfunção:", sorted(df_base['subfuncao'].unique()), key="subf_desp")
        fts = f5.multiselect("Fonte:", sorted(df_base['fonte'].unique()), key="font_desp")
        bd = f6.text_input("Natureza (Contém):", key="busca_desp")
        
        df_f = df_base[df_base['mes'].isin(ms_d) & df_base['ug'].isin(ug_sel)]
        if fs: df_f = df_f[df_f['funcao'].isin(fs)]
        if sf: df_f = df_f[df_f['subfuncao'].isin(sf)]
        if fts: df_f = df_f[df_f['fonte'].isin(fts)]
        if bd: df_f = df_f[df_f['natureza'].str.contains(bd, case=False, na=False)]
        
        if not df_f.empty:
            u_c = df_f[['ano','mes']].drop_duplicates().sort_values(['ano','mes']).iloc[-1]
            col_ch = ['ug', 'funcao', 'subfuncao', 'programa', 'projeto', 'fonte', 'natureza']
            df_exec = df_f.groupby(col_ch, as_index=False)[['empenhado','liquidado','pago']].sum()
            df_aut = df_f[(df_f['ano']==u_c['ano'])&(df_f['mes']==u_c['mes'])].groupby(col_ch, as_index=False)[['cred_autorizado']].sum()
            df_view = df_exec.merge(df_aut, on=col_ch, how='left').fillna(0)
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Créd. Autorizado", f"R$ {df_view['cred_autorizado'].sum():,.2f}")
            k2.metric("Empenhado", f"R$ {df_view['empenhado'].sum():,.2f}")
            k3.metric("Liquidado", f"R$ {df_view['liquidado'].sum():,.2f}")
            k4.metric("Pago", f"R$ {df_view['pago'].sum():,.2f}")
            st.dataframe(df_view.style.format({'cred_autorizado':'{:,.2f}','empenhado':'{:,.2f}','liquidado':'{:,.2f}','pago':'{:,.2f}'}), width='stretch')

with tab3:
    if not df_rec.empty or not df_desp.empty:
        st.subheader("⚖️ Confronto Geral Financeiro e Orçamentário")
        a0, a1 = st.columns(2)
        anos_c = sorted(list(set(df_rec['ano'].unique()) | set(df_desp['ano'].unique())))
        anos_sel = a0.multiselect("Anos:", anos_c, default=anos_c, key="anos_conf")
        ms_c = a1.multiselect("Meses:", range(1,13), default=range(1,13), format_func=lambda x: MESES_NOMES[x-1], key="ms_conf")
        tr = df_rec[df_rec['ano'].isin(anos_sel) & df_rec['mes'].isin(ms_c)]['realizado'].sum()
        tp = df_desp[df_desp['ano'].isin(anos_sel) & df_desp['mes'].isin(ms_c)]['pago'].sum()
        te = df_desp[df_desp['ano'].isin(anos_sel) & df_desp['mes'].isin(ms_c)]['empenhado'].sum()
        k1, k2, k3 = st.columns(3); k1.metric("Receita Arrecadada", f"R$ {tr:,.2f}"); k2.metric("Despesa Paga", f"R$ {tp:,.2f}"); k3.metric("Despesa Empenhada", f"R$ {te:,.2f}")
        st.info(f"**Superávit Financeiro:** R$ {tr - tp:,.2f}"); st.warning(f"**Superávit Orçamentário:** R$ {tr - te:,.2f}")

with tab4:
    st.subheader("📄 Relatórios Bimestrais da LRF (RREO)")
    if df_rec.empty or df_desp.empty: st.info("Importe dados para gerar os anexos.")
    else:
        anos_lrf = sorted(list(set(df_rec['ano'].unique()) & set(df_desp['ano'].unique())))
        if anos_lrf:
            ano_lrf = st.selectbox("Ano:", anos_lrf, index=len(anos_lrf)-1)
            bimestre_sel = st.selectbox("Bimestre:", list(BIMESTRES.keys()))
            m_bim = BIMESTRES[bimestre_sel]; m_ate = list(range(1, max(m_bim)+1))
            df_r_l = df_rec[df_rec['ano']==ano_lrf]; df_d_l = df_desp[df_desp['ano']==ano_lrf]
            c1, c2, c3 = st.columns(3)
            with c1: st.write("Anexo I"); st.download_button("📥 Baixar Anexo I", data=gerar_excel_anexo1(df_r_l, m_bim, m_ate), file_name=f"AnexoI_{ano_lrf}_{bimestre_sel}.xlsx")
            with c2: st.write("Anexo IA"); st.download_button("📥 Baixar Anexo IA", data=gerar_excel_anexo1a(df_d_l, df_r_l, m_bim, m_ate), file_name=f"AnexoIA_{ano_lrf}_{bimestre_sel}.xlsx")
            with c3: st.write("Anexo II"); st.download_button("📥 Baixar Anexo II", data=gerar_excel_anexo2(df_d_l, m_bim, m_ate), file_name=f"AnexoII_{ano_lrf}_{bimestre_sel}.xlsx")
