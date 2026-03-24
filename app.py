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
    "1": "LEGISLATIVA",
    "2": "JUDICIÁRIA",
    "3": "ESSENCIAL À JUSTIÇA",
    "4": "ADMINISTRAÇÃO",
    "6": "SEGURANÇA PÚBLICA",
    "8": "ASSISTÊNCIA SOCIAL",
    "9": "PREVIDÊNCIA SOCIAL",
    "10": "SAÚDE",
    "12": "EDUCAÇÃO",
    "13": "CULTURA",
    "14": "DIREITOS DA CIDADANIA",
    "15": "URBANISMO",
    "16": "HABITAÇÃO",
    "17": "SANEAMENTO",
    "18": "GESTÃO AMBIENTAL",
    "19": "CIÊNCIA E TECNOLOGIA",
    "20": "AGRICULTURA",
    "22": "INDÚSTRIA",
    "23": "COMÉRCIO E SERVIÇOS",
    "24": "COMUNICAÇÕES",
    "26": "TRANSPORTE",
    "27": "DESPORTO E LAZER",
    "28": "ENCARGOS ESPECIAIS"
}

SUBFUNCOES_MAP = {
    "61": "Ação Judiciária",
    "62": "Defesa do Interesse Público",
    "91": "Defesa da Ordem Jurídica",
    "92": "Representação Judicial e Extrajudicial",
    "122": "Administração Geral",
    "123": "Administração Financeira",
    "126": "Tecnologia da Informação",
    "128": "Formação de Recursos Humanos",
    "131": "Comunicação Social",
    "272": "Previdência do Regime Estatutário",
    "331": "Proteção e Benefícios ao Trabalhador",
    "332": "Relações de Trabalho",
    "846": "Outros Encargos Especiais"
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
    conn.execute('''
        CREATE TABLE IF NOT EXISTS despesas (
            mes INTEGER, ano INTEGER, uo TEXT, funcao TEXT, subfuncao TEXT,
            programa TEXT, projeto TEXT, natureza TEXT, fonte TEXT,
            orcado_inicial REAL, cred_autorizado REAL, empenhado REAL, liquidado REAL, pago REAL
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

def safe_div(n, d):
    return (n / d) if d not in [0, None] else 0.0

def periodo_bimestre_extenso(meses_bim):
    meses_bim = sorted(meses_bim)
    if len(meses_bim) == 1:
        return MESES_LONGO.get(meses_bim[0], "")
    if len(meses_bim) == 2:
        return f"{MESES_LONGO.get(meses_bim[0], '')} E {MESES_LONGO.get(meses_bim[1], '')}"
    return " A ".join([MESES_LONGO.get(m, str(m)) for m in meses_bim])

def natureza_para_str(v):
    s = re.sub(r"\D", "", str(v)) if pd.notna(v) else ""
    return s

def modalidade_da_natureza(natureza):
    s = natureza_para_str(natureza)
    if len(s) >= 4:
        return s[2:4]
    return ""

def grupo_natureza(natureza):
    s = natureza_para_str(natureza)
    if not s:
        return ""
    return s[0]

def nome_funcao(cod):
    cod = str(cod)
    return FUNCOES_MAP.get(cod, f"FUNÇÃO {cod}")

def nome_subfuncao(cod):
    cod = str(cod)
    return SUBFUNCOES_MAP.get(cod, f"Subfunção {cod}")

def somar_campos(df, cols):
    if df.empty:
        return {c: 0.0 for c in cols}
    return {c: float(df[c].sum()) for c in cols}

def preparar_base_receitas_lrf(df_rec, meses_bim, meses_ate_agora):
    if df_rec.empty:
        return pd.DataFrame(columns=[
            'categoria', 'natureza', 'previsao_inicial', 'previsao_atualizada',
            'no_bimestre', 'ate_bimestre', 'saldo', 'perc_bim', 'perc_ate'
        ])

    chaves = ['categoria', 'natureza']

    df_prev = (
        df_rec[df_rec['mes'].isin(meses_ate_agora)]
        .groupby(chaves, as_index=False)
        .agg({
            'orcado': 'max',
            'previsao': 'max'
        })
        .rename(columns={
            'orcado': 'previsao_inicial',
            'previsao': 'previsao_atualizada'
        })
    )

    df_bim = (
        df_rec[df_rec['mes'].isin(meses_bim)]
        .groupby(chaves, as_index=False)['realizado']
        .sum()
        .rename(columns={'realizado': 'no_bimestre'})
    )

    df_ate = (
        df_rec[df_rec['mes'].isin(meses_ate_agora)]
        .groupby(chaves, as_index=False)['realizado']
        .sum()
        .rename(columns={'realizado': 'ate_bimestre'})
    )

    base = df_prev.merge(df_bim, on=chaves, how='left').merge(df_ate, on=chaves, how='left')
    base = base.fillna(0)
    base['saldo'] = base['previsao_atualizada'] - base['ate_bimestre']
    base['perc_bim'] = base.apply(lambda r: safe_div(r['no_bimestre'], r['previsao_atualizada']), axis=1)
    base['perc_ate'] = base.apply(lambda r: safe_div(r['ate_bimestre'], r['previsao_atualizada']), axis=1)
    return base

def preparar_base_despesas_lrf(df_desp, meses_bim, meses_ate_agora):
    if df_desp.empty:
        return pd.DataFrame(columns=[
            'natureza', 'orcado_inicial', 'cred_autorizado', 'emp_no_bim', 'emp_ate',
            'liq_no_bim', 'liq_ate', 'pago_ate', 'modalidade', 'grupo'
        ])

    chaves = ['natureza']
    m_max = max(meses_ate_agora)

    df_last = (
        df_desp[df_desp['mes'] == m_max]
        .groupby(chaves, as_index=False)
        .agg({
            'orcado_inicial': 'sum',
            'cred_autorizado': 'sum'
        })
    )

    df_bim = (
        df_desp[df_desp['mes'].isin(meses_bim)]
        .groupby(chaves, as_index=False)
        .agg({
            'empenhado': 'sum',
            'liquidado': 'sum'
        })
        .rename(columns={
            'empenhado': 'emp_no_bim',
            'liquidado': 'liq_no_bim'
        })
    )

    df_ate = (
        df_desp[df_desp['mes'].isin(meses_ate_agora)]
        .groupby(chaves, as_index=False)
        .agg({
            'empenhado': 'sum',
            'liquidado': 'sum',
            'pago': 'sum'
        })
        .rename(columns={
            'empenhado': 'emp_ate',
            'liquidado': 'liq_ate',
            'pago': 'pago_ate'
        })
    )

    base = df_last.merge(df_bim, on=chaves, how='outer').merge(df_ate, on=chaves, how='outer')
    base = base.fillna(0)
    base['modalidade'] = base['natureza'].apply(modalidade_da_natureza)
    base['grupo'] = base['natureza'].apply(grupo_natureza)
    return base

def preparar_base_funcional_lrf(df_desp, meses_bim, meses_ate_agora):
    if df_desp.empty:
        return pd.DataFrame(columns=[
            'funcao', 'subfuncao', 'orcado_inicial', 'cred_autorizado',
            'emp_no_bim', 'emp_ate', 'liq_no_bim', 'liq_ate'
        ])

    chaves = ['funcao', 'subfuncao']
    m_max = max(meses_ate_agora)

    df_last = (
        df_desp[df_desp['mes'] == m_max]
        .groupby(chaves, as_index=False)
        .agg({
            'orcado_inicial': 'sum',
            'cred_autorizado': 'sum'
        })
    )

    df_bim = (
        df_desp[df_desp['mes'].isin(meses_bim)]
        .groupby(chaves, as_index=False)
        .agg({
            'empenhado': 'sum',
            'liquidado': 'sum'
        })
        .rename(columns={
            'empenhado': 'emp_no_bim',
            'liquidado': 'liq_no_bim'
        })
    )

    df_ate = (
        df_desp[df_desp['mes'].isin(meses_ate_agora)]
        .groupby(chaves, as_index=False)
        .agg({
            'empenhado': 'sum',
            'liquidado': 'sum'
        })
        .rename(columns={
            'empenhado': 'emp_ate',
            'liquidado': 'liq_ate'
        })
    )

    base = df_last.merge(df_bim, on=chaves, how='outer').merge(df_ate, on=chaves, how='outer')
    base = base.fillna(0)
    return base

def gerar_excel_anexo1(df_rec, meses_bim, meses_ate_agora):
    base = preparar_base_receitas_lrf(df_rec, meses_bim, meses_ate_agora)
    periodo = periodo_bimestre_extenso(meses_bim)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        worksheet = workbook.add_worksheet('Anexo_I')
        writer.sheets['Anexo_I'] = worksheet

        fmt_header = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#BFBFBF', 'text_wrap': True
        })
        fmt_group = workbook.add_format({
            'bold': True, 'border': 1, 'bg_color': '#D9D9D9'
        })
        fmt_subgroup = workbook.add_format({
            'bold': True, 'border': 1
        })
        fmt_item = workbook.add_format({
            'border': 1, 'indent': 1
        })
        fmt_total = workbook.add_format({
            'bold': True, 'border': 1, 'bg_color': '#EDEDED'
        })
        fmt_money = workbook.add_format({
            'border': 1, 'num_format': '#,##0.00'
        })
        fmt_money_bold = workbook.add_format({
            'bold': True, 'border': 1, 'bg_color': '#EDEDED', 'num_format': '#,##0.00'
        })
        fmt_pct = workbook.add_format({
            'border': 1, 'num_format': '0.00%'
        })
        fmt_pct_bold = workbook.add_format({
            'bold': True, 'border': 1, 'bg_color': '#EDEDED', 'num_format': '0.00%'
        })
        fmt_text_total = workbook.add_format({
            'bold': True, 'border': 1, 'bg_color': '#EDEDED'
        })

        worksheet.set_column('A:A', 42)
        worksheet.set_column('B:C', 18)
        worksheet.set_column('D:D', 18)
        worksheet.set_column('E:E', 10)
        worksheet.set_column('F:F', 18)
        worksheet.set_column('G:G', 10)
        worksheet.set_column('H:H', 18)

        worksheet.merge_range(0, 0, 1, 0, 'RECEITAS', fmt_header)
        worksheet.merge_range(0, 1, 1, 1, 'PREVISÃO INICIAL', fmt_header)
        worksheet.merge_range(0, 2, 1, 2, 'PREVISÃO ATUALIZADA (A)', fmt_header)
        worksheet.merge_range(0, 3, 0, 7, 'RECEITAS REALIZADAS', fmt_header)

        worksheet.write(1, 3, f'NO BIMESTRE\n{periodo}', fmt_header)
        worksheet.write(1, 4, '%\n(B/A)', fmt_header)
        worksheet.write(1, 5, f'ATÉ O BIMESTRE\n{periodo}', fmt_header)
        worksheet.write(1, 6, '%\n(C/A)', fmt_header)
        worksheet.write(1, 7, 'SALDO A\nREALIZAR\n(A-C)', fmt_header)

        ordem_categorias = [
            "Receita Tributária",
            "Receita Patrimonial",
            "Receita de Serviços",
            "Repasses Correntes",
            "Demais Receitas"
        ]
        grupos = {
            "RECEITAS CORRENTES": ["Receita Tributária", "Receita Patrimonial", "Receita de Serviços", "Repasses Correntes"],
            "DEMAIS RECEITAS CORRENTES": ["Demais Receitas"]
        }

        row = 2

        def write_row(descricao, vals, fmt_desc, fmt_num, fmt_perc):
            nonlocal row
            worksheet.write(row, 0, descricao, fmt_desc)
            worksheet.write_number(row, 1, vals.get('previsao_inicial', 0), fmt_num)
            worksheet.write_number(row, 2, vals.get('previsao_atualizada', 0), fmt_num)
            worksheet.write_number(row, 3, vals.get('no_bimestre', 0), fmt_num)
            worksheet.write_number(row, 4, vals.get('perc_bim', 0), fmt_perc)
            worksheet.write_number(row, 5, vals.get('ate_bimestre', 0), fmt_num)
            worksheet.write_number(row, 6, vals.get('perc_ate', 0), fmt_perc)
            worksheet.write_number(row, 7, vals.get('saldo', 0), fmt_num)
            row += 1

        total_geral = {'previsao_inicial': 0, 'previsao_atualizada': 0, 'no_bimestre': 0, 'ate_bimestre': 0, 'saldo': 0, 'perc_bim': 0, 'perc_ate': 0}

        for nome_grupo, cats in grupos.items():
            df_g = base[base['categoria'].isin(cats)].copy()
            if df_g.empty:
                continue

            soma_g = {
                'previsao_inicial': float(df_g['previsao_inicial'].sum()),
                'previsao_atualizada': float(df_g['previsao_atualizada'].sum()),
                'no_bimestre': float(df_g['no_bimestre'].sum()),
                'ate_bimestre': float(df_g['ate_bimestre'].sum()),
                'saldo': float(df_g['saldo'].sum())
            }
            soma_g['perc_bim'] = safe_div(soma_g['no_bimestre'], soma_g['previsao_atualizada'])
            soma_g['perc_ate'] = safe_div(soma_g['ate_bimestre'], soma_g['previsao_atualizada'])

            write_row(nome_grupo, soma_g, fmt_group, fmt_money, fmt_pct)

            for cat in [c for c in ordem_categorias if c in cats]:
                df_c = df_g[df_g['categoria'] == cat].copy()
                if df_c.empty:
                    continue

                soma_c = {
                    'previsao_inicial': float(df_c['previsao_inicial'].sum()),
                    'previsao_atualizada': float(df_c['previsao_atualizada'].sum()),
                    'no_bimestre': float(df_c['no_bimestre'].sum()),
                    'ate_bimestre': float(df_c['ate_bimestre'].sum()),
                    'saldo': float(df_c['saldo'].sum())
                }
                soma_c['perc_bim'] = safe_div(soma_c['no_bimestre'], soma_c['previsao_atualizada'])
                soma_c['perc_ate'] = safe_div(soma_c['ate_bimestre'], soma_c['previsao_atualizada'])

                write_row(cat.upper(), soma_c, fmt_subgroup, fmt_money, fmt_pct)

                for _, r in df_c.sort_values('natureza').iterrows():
                    vals = {
                        'previsao_inicial': float(r['previsao_inicial']),
                        'previsao_atualizada': float(r['previsao_atualizada']),
                        'no_bimestre': float(r['no_bimestre']),
                        'ate_bimestre': float(r['ate_bimestre']),
                        'saldo': float(r['saldo']),
                        'perc_bim': float(r['perc_bim']),
                        'perc_ate': float(r['perc_ate'])
                    }
                    write_row(str(r['natureza']), vals, fmt_item, fmt_money, fmt_pct)

            total_geral['previsao_inicial'] += soma_g['previsao_inicial']
            total_geral['previsao_atualizada'] += soma_g['previsao_atualizada']
            total_geral['no_bimestre'] += soma_g['no_bimestre']
            total_geral['ate_bimestre'] += soma_g['ate_bimestre']
            total_geral['saldo'] += soma_g['saldo']

        total_geral['perc_bim'] = safe_div(total_geral['no_bimestre'], total_geral['previsao_atualizada'])
        total_geral['perc_ate'] = safe_div(total_geral['ate_bimestre'], total_geral['previsao_atualizada'])

        linhas_finais = [
            ('SUBTOTAL DA RECEITA (I)', total_geral),
            ('DEFICIT (II)', {'previsao_inicial': 0, 'previsao_atualizada': 0, 'no_bimestre': 0, 'ate_bimestre': 0, 'saldo': 0, 'perc_bim': 0, 'perc_ate': 0}),
            ('TOTAL (III) = I + II', total_geral),
            ('Dedução-Custas Processuais Justiça Estadual e Recursos Vinculados', {'previsao_inicial': 0, 'previsao_atualizada': 0, 'no_bimestre': 0, 'ate_bimestre': 0, 'saldo': 0, 'perc_bim': 0, 'perc_ate': 0}),
            ('SALDO DE EXERCÍCIOS ANTERIORES', {'previsao_inicial': 0, 'previsao_atualizada': 0, 'no_bimestre': 0, 'ate_bimestre': 0, 'saldo': 0, 'perc_bim': 0, 'perc_ate': 0}),
            ('SUPERÁVIT FINANCEIRO', {'previsao_inicial': 0, 'previsao_atualizada': 0, 'no_bimestre': 0, 'ate_bimestre': 0, 'saldo': 0, 'perc_bim': 0, 'perc_ate': 0}),
            ('TOTAL DA RECEITA (IV)', total_geral)
        ]

        for descricao, vals in linhas_finais:
            worksheet.write(row, 0, descricao, fmt_text_total)
            worksheet.write_number(row, 1, vals.get('previsao_inicial', 0), fmt_money_bold)
            worksheet.write_number(row, 2, vals.get('previsao_atualizada', 0), fmt_money_bold)
            worksheet.write_number(row, 3, vals.get('no_bimestre', 0), fmt_money_bold)
            worksheet.write_number(row, 4, vals.get('perc_bim', 0), fmt_pct_bold)
            worksheet.write_number(row, 5, vals.get('ate_bimestre', 0), fmt_money_bold)
            worksheet.write_number(row, 6, vals.get('perc_ate', 0), fmt_pct_bold)
            worksheet.write_number(row, 7, vals.get('saldo', 0), fmt_money_bold)
            row += 1

        worksheet.freeze_panes(2, 1)

    return output.getvalue()

def gerar_excel_anexo1a(df_desp, df_rec, meses_bim, meses_ate_agora):
    base = preparar_base_despesas_lrf(df_desp, meses_bim, meses_ate_agora)
    periodo = periodo_bimestre_extenso(meses_bim)

    receita_bim = float(df_rec[df_rec['mes'].isin(meses_bim)]['realizado'].sum()) if not df_rec.empty else 0.0
    receita_ate = float(df_rec[df_rec['mes'].isin(meses_ate_agora)]['realizado'].sum()) if not df_rec.empty else 0.0

    def bloco(mask):
        df = base[mask].copy() if not base.empty else pd.DataFrame()
        vals = somar_campos(df, ['orcado_inicial', 'cred_autorizado', 'emp_no_bim', 'emp_ate', 'liq_no_bim', 'liq_ate', 'pago_ate'])
        vals['saldo_emp'] = vals['cred_autorizado'] - vals['emp_ate']
        vals['saldo_liq'] = vals['cred_autorizado'] - vals['liq_ate']
        vals['restos'] = 0.0
        return vals

    mask_correntes = (base['grupo'] == '3') & (base['modalidade'] != '91')
    mask_corr_50 = mask_correntes & (base['modalidade'] == '50')
    mask_corr_90 = mask_correntes & (base['modalidade'] == '90')
    mask_capital = (base['grupo'] == '4') & (base['modalidade'] != '91')
    mask_cap_90 = mask_capital & (base['modalidade'] == '90')
    mask_intra = base['modalidade'] == '91'

    v_correntes = bloco(mask_correntes)
    v_corr_50 = bloco(mask_corr_50)
    v_corr_90 = bloco(mask_corr_90)
    v_capital = bloco(mask_capital)
    v_cap_90 = bloco(mask_cap_90)
    v_intra = bloco(mask_intra)
    v_exceto_intra = bloco(mask_correntes | mask_capital)
    v_subtotal = bloco(pd.Series([True] * len(base), index=base.index) if not base.empty else pd.Series(dtype=bool))

    v_divida_zero = {
        'orcado_inicial': 0.0, 'cred_autorizado': 0.0, 'emp_no_bim': 0.0, 'emp_ate': 0.0,
        'saldo_emp': 0.0, 'liq_no_bim': 0.0, 'liq_ate': 0.0, 'saldo_liq': 0.0,
        'pago_ate': 0.0, 'restos': 0.0
    }

    v_total_desp = v_subtotal.copy()

    v_superavit = {
        'orcado_inicial': 0.0,
        'cred_autorizado': 0.0,
        'emp_no_bim': max(receita_bim - v_total_desp['emp_no_bim'], 0),
        'emp_ate': max(receita_ate - v_total_desp['emp_ate'], 0),
        'saldo_emp': 0.0,
        'liq_no_bim': max(receita_bim - v_total_desp['liq_no_bim'], 0),
        'liq_ate': max(receita_ate - v_total_desp['liq_ate'], 0),
        'saldo_liq': 0.0,
        'pago_ate': max(receita_ate - v_total_desp['pago_ate'], 0),
        'restos': 0.0
    }

    v_total_com_superavit = {
        'orcado_inicial': v_total_desp['orcado_inicial'],
        'cred_autorizado': v_total_desp['cred_autorizado'],
        'emp_no_bim': v_total_desp['emp_no_bim'] + v_superavit['emp_no_bim'],
        'emp_ate': v_total_desp['emp_ate'] + v_superavit['emp_ate'],
        'saldo_emp': v_total_desp['saldo_emp'],
        'liq_no_bim': v_total_desp['liq_no_bim'] + v_superavit['liq_no_bim'],
        'liq_ate': v_total_desp['liq_ate'] + v_superavit['liq_ate'],
        'saldo_liq': v_total_desp['saldo_liq'],
        'pago_ate': v_total_desp['pago_ate'] + v_superavit['pago_ate'],
        'restos': 0.0
    }

    linhas = [
        ('DESPESAS (EXCETO INTRA-ORÇAMENTÁRIAS) (VIII)', v_exceto_intra, 'total'),
        ('DESPESAS CORRENTES', v_correntes, 'grupo'),
        ('Instituições privadas sem fins lucrativos (modalidade 50)', v_corr_50, 'item'),
        ('Outras Desp.Correntes (modalidade 90)', v_corr_90, 'item'),
        ('DESPESAS DE CAPITAL', v_capital, 'grupo'),
        ('Investimentos (modalidade 90)', v_cap_90, 'item'),
        ('DESPESAS (INTRA-ORÇAMENTÁRIAS) (IX) (91)', v_intra, 'grupo'),
        ('SUBTOTAL DESPESAS (X) = (VIII+IX)', v_subtotal, 'total'),
        ('AMORTIZAÇÃO DA DÍVIDA / REFINANCIAMENTO (XI)', v_divida_zero, 'grupo'),
        ('Amortização da Dívida Interna', v_divida_zero, 'item'),
        ('   Dívida Mobiliária', v_divida_zero, 'subitem'),
        ('   Dívida Contratual', v_divida_zero, 'subitem'),
        ('Amortização da Dívida Externa', v_divida_zero, 'item'),
        ('   Dívida Mobiliária', v_divida_zero, 'subitem'),
        ('TOTAL DAS DESPESAS (XII) = (X+XI)', v_total_desp, 'total'),
        ('SUPERÁVIT (XIII)', v_superavit, 'total'),
        ('TOTAL COM SUPERÁVIT (XIV) = (XII+XIII)', v_total_com_superavit, 'total')
    ]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        worksheet = workbook.add_worksheet('Anexo_IA')
        writer.sheets['Anexo_IA'] = worksheet

        fmt_header = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#BFBFBF', 'text_wrap': True
        })
        fmt_group = workbook.add_format({'bold': True, 'border': 1})
        fmt_item = workbook.add_format({'border': 1, 'indent': 1})
        fmt_subitem = workbook.add_format({'border': 1, 'indent': 2})
        fmt_total_text = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#EDEDED'})
        fmt_money = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        fmt_money_total = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#EDEDED', 'num_format': '#,##0.00'})

        worksheet.set_column('A:A', 48)
        worksheet.set_column('B:C', 16)
        worksheet.set_column('D:K', 16)

        worksheet.merge_range(0, 0, 2, 0, 'DESPESAS', fmt_header)
        worksheet.merge_range(0, 1, 2, 1, 'DOTAÇÃO INICIAL\n(a)', fmt_header)
        worksheet.merge_range(0, 2, 2, 2, 'DOTAÇÃO\nATUALIZADA\n(c)', fmt_header)

        worksheet.merge_range(0, 3, 0, 5, 'DESPESAS EMPENHADAS', fmt_header)
        worksheet.write(1, 3, f'NO BIMESTRE\n{periodo}', fmt_header)
        worksheet.write(1, 4, f'ATÉ O BIMESTRE\n{periodo}', fmt_header)
        worksheet.write(1, 5, 'Saldo\n(g) = c-f', fmt_header)

        worksheet.merge_range(0, 6, 0, 8, 'DESPESAS EXECUTADAS', fmt_header)
        worksheet.write(1, 6, 'LIQUIDADAS', fmt_header)
        worksheet.write(1, 7, 'LIQUIDADAS', fmt_header)
        worksheet.write(1, 8, 'Saldo\n(i) = c-h', fmt_header)
        worksheet.write(2, 3, '', fmt_header)
        worksheet.write(2, 4, '', fmt_header)
        worksheet.write(2, 5, '', fmt_header)
        worksheet.write(2, 6, f'NO BIMESTRE\n{periodo}', fmt_header)
        worksheet.write(2, 7, f'ATÉ O BIMESTRE\n{periodo}', fmt_header)
        worksheet.write(2, 8, '', fmt_header)

        worksheet.merge_range(0, 9, 2, 9, 'Despesas pagas\naté o mês\n(j)', fmt_header)
        worksheet.merge_range(0, 10, 2, 10, 'INSCRITAS EM\nRESTOS A\nPAGAR NÃO\nPROCESSADOS (k)', fmt_header)

        row = 3
        for descricao, vals, tipo in linhas:
            if tipo == 'total':
                fmt_desc = fmt_total_text
                fmt_num = fmt_money_total
            elif tipo == 'grupo':
                fmt_desc = fmt_group
                fmt_num = fmt_money
            elif tipo == 'subitem':
                fmt_desc = fmt_subitem
                fmt_num = fmt_money
            else:
                fmt_desc = fmt_item
                fmt_num = fmt_money

            worksheet.write(row, 0, descricao, fmt_desc)
            worksheet.write_number(row, 1, vals.get('orcado_inicial', 0), fmt_num)
            worksheet.write_number(row, 2, vals.get('cred_autorizado', 0), fmt_num)
            worksheet.write_number(row, 3, vals.get('emp_no_bim', 0), fmt_num)
            worksheet.write_number(row, 4, vals.get('emp_ate', 0), fmt_num)
            worksheet.write_number(row, 5, vals.get('saldo_emp', 0), fmt_num)
            worksheet.write_number(row, 6, vals.get('liq_no_bim', 0), fmt_num)
            worksheet.write_number(row, 7, vals.get('liq_ate', 0), fmt_num)
            worksheet.write_number(row, 8, vals.get('saldo_liq', 0), fmt_num)
            worksheet.write_number(row, 9, vals.get('pago_ate', 0), fmt_num)
            worksheet.write_number(row, 10, vals.get('restos', 0), fmt_num)
            row += 1

        worksheet.freeze_panes(3, 1)

    return output.getvalue()

def gerar_excel_anexo2(df_desp, meses_bim, meses_ate_agora):
    base = preparar_base_funcional_lrf(df_desp, meses_bim, meses_ate_agora)
    periodo = periodo_bimestre_extenso(meses_bim)

    total_emp = float(base['emp_ate'].sum()) if not base.empty else 0.0
    total_liq = float(base['liq_ate'].sum()) if not base.empty else 0.0

    linhas = []

    if not base.empty:
        funcoes_ordenadas = sorted(base['funcao'].astype(str).unique(), key=lambda x: int(float(x)) if str(x).replace('.', '', 1).isdigit() else 9999)

        for funcao in funcoes_ordenadas:
            df_f = base[base['funcao'].astype(str) == str(funcao)].copy()

            vals_f = {
                'orcado_inicial': float(df_f['orcado_inicial'].sum()),
                'cred_autorizado': float(df_f['cred_autorizado'].sum()),
                'emp_no_bim': float(df_f['emp_no_bim'].sum()),
                'emp_ate': float(df_f['emp_ate'].sum()),
                'perc_emp': safe_div(float(df_f['emp_ate'].sum()), total_emp),
                'saldo_emp': float(df_f['cred_autorizado'].sum() - df_f['emp_ate'].sum()),
                'liq_no_bim': float(df_f['liq_no_bim'].sum()),
                'liq_ate': float(df_f['liq_ate'].sum()),
                'perc_liq': safe_div(float(df_f['liq_ate'].sum()), total_liq),
                'saldo_liq': float(df_f['cred_autorizado'].sum() - df_f['liq_ate'].sum()),
                'restos': 0.0
            }

            linhas.append((f"{nome_funcao(str(funcao))} - {str(funcao)}", vals_f, 'grupo'))

            subfs = sorted(df_f['subfuncao'].astype(str).unique(), key=lambda x: int(float(x)) if str(x).replace('.', '', 1).isdigit() else 9999)
            for subf in subfs:
                df_s = df_f[df_f['subfuncao'].astype(str) == str(subf)].copy()
                vals_s = {
                    'orcado_inicial': float(df_s['orcado_inicial'].sum()),
                    'cred_autorizado': float(df_s['cred_autorizado'].sum()),
                    'emp_no_bim': float(df_s['emp_no_bim'].sum()),
                    'emp_ate': float(df_s['emp_ate'].sum()),
                    'perc_emp': safe_div(float(df_s['emp_ate'].sum()), total_emp),
                    'saldo_emp': float(df_s['cred_autorizado'].sum() - df_s['emp_ate'].sum()),
                    'liq_no_bim': float(df_s['liq_no_bim'].sum()),
                    'liq_ate': float(df_s['liq_ate'].sum()),
                    'perc_liq': safe_div(float(df_s['liq_ate'].sum()), total_liq),
                    'saldo_liq': float(df_s['cred_autorizado'].sum() - df_s['liq_ate'].sum()),
                    'restos': 0.0
                }
                linhas.append((f"{nome_subfuncao(str(subf))} - {str(subf)}", vals_s, 'item'))

    total_vals = {
        'orcado_inicial': float(base['orcado_inicial'].sum()) if not base.empty else 0.0,
        'cred_autorizado': float(base['cred_autorizado'].sum()) if not base.empty else 0.0,
        'emp_no_bim': float(base['emp_no_bim'].sum()) if not base.empty else 0.0,
        'emp_ate': float(base['emp_ate'].sum()) if not base.empty else 0.0,
        'perc_emp': 1.0 if total_emp > 0 else 0.0,
        'saldo_emp': float(base['cred_autorizado'].sum() - base['emp_ate'].sum()) if not base.empty else 0.0,
        'liq_no_bim': float(base['liq_no_bim'].sum()) if not base.empty else 0.0,
        'liq_ate': float(base['liq_ate'].sum()) if not base.empty else 0.0,
        'perc_liq': 1.0 if total_liq > 0 else 0.0,
        'saldo_liq': float(base['cred_autorizado'].sum() - base['liq_ate'].sum()) if not base.empty else 0.0,
        'restos': 0.0
    }
    linhas.append(('TOTAL', total_vals, 'total'))

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        worksheet = workbook.add_worksheet('Anexo_II')
        writer.sheets['Anexo_II'] = worksheet

        fmt_header = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#BFBFBF', 'text_wrap': True
        })
        fmt_group = workbook.add_format({'bold': True, 'border': 1})
        fmt_item = workbook.add_format({'border': 1, 'indent': 1})
        fmt_total_text = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#EDEDED'})
        fmt_money = workbook.add_format({'border': 1, 'num_format': '#,##0.00'})
        fmt_money_total = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#EDEDED', 'num_format': '#,##0.00'})
        fmt_pct = workbook.add_format({'border': 1, 'num_format': '0.00%'})
        fmt_pct_total = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#EDEDED', 'num_format': '0.00%'})

        worksheet.set_column('A:A', 32)
        worksheet.set_column('B:C', 16)
        worksheet.set_column('D:K', 14)

        worksheet.merge_range(0, 0, 2, 0, 'FUNÇÃO/\nSUBFUNÇÃO', fmt_header)
        worksheet.merge_range(0, 1, 2, 1, 'DOTAÇÃO\nINICIAL', fmt_header)
        worksheet.merge_range(0, 2, 2, 2, 'DOTAÇÃO\nATUALIZADA\n(a)', fmt_header)

        worksheet.merge_range(0, 3, 0, 6, 'DESPESA EMPENHADA', fmt_header)
        worksheet.write(1, 3, f'NO BIMESTRE\n{periodo}', fmt_header)
        worksheet.write(1, 4, f'ATÉ O BIMESTRE\n{periodo}\n(b)', fmt_header)
        worksheet.write(1, 5, '%\n(b/total b)', fmt_header)
        worksheet.write(1, 6, 'SALDO\n(c)=(a-b)', fmt_header)

        worksheet.merge_range(0, 7, 0, 10, 'DESPESA LIQUIDADA', fmt_header)
        worksheet.write(1, 7, f'NO BIMESTRE\n{periodo}', fmt_header)
        worksheet.write(1, 8, f'ATÉ O BIMESTRE\n{periodo}\n(d)', fmt_header)
        worksheet.write(1, 9, '%\n(d/total d)', fmt_header)
        worksheet.write(1, 10, 'SALDO\n(e)=(a-d)', fmt_header)

        worksheet.merge_range(0, 11, 2, 11, 'INSCRITAS EM\nRESTOS A\nPAGAR NÃO\nPROCESSADOS (f)', fmt_header)

        for c in range(3, 11):
            worksheet.write(2, c, '', fmt_header)

        row = 3
        for descricao, vals, tipo in linhas:
            if tipo == 'total':
                fmt_desc = fmt_total_text
                fmt_num = fmt_money_total
                fmt_perc = fmt_pct_total
            elif tipo == 'grupo':
                fmt_desc = fmt_group
                fmt_num = fmt_money
                fmt_perc = fmt_pct
            else:
                fmt_desc = fmt_item
                fmt_num = fmt_money
                fmt_perc = fmt_pct

            worksheet.write(row, 0, descricao, fmt_desc)
            worksheet.write_number(row, 1, vals.get('orcado_inicial', 0), fmt_num)
            worksheet.write_number(row, 2, vals.get('cred_autorizado', 0), fmt_num)
            worksheet.write_number(row, 3, vals.get('emp_no_bim', 0), fmt_num)
            worksheet.write_number(row, 4, vals.get('emp_ate', 0), fmt_num)
            worksheet.write_number(row, 5, vals.get('perc_emp', 0), fmt_perc)
            worksheet.write_number(row, 6, vals.get('saldo_emp', 0), fmt_num)
            worksheet.write_number(row, 7, vals.get('liq_no_bim', 0), fmt_num)
