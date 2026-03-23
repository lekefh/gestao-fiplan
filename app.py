import streamlit as st
import pandas as pd
import sqlite3
import plotly.graph_objects as go
import re

# --- CONFIGURAÇÃO ---
DB_NAME = 'dados_gestao_integrada.db'
st.set_page_config(page_title="Gestão Integrada FIPLAN", layout="wide")
MESES_NOMES = ["Jan", "Fev", "Mar", "Abr", "Maio", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
MESES_MAPA = {"JANEIRO": 1, "FEVEREIRO": 2, "MARÇO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}

st.markdown("<style>[data-testid='stMetricValue'] { font-size: 1.4rem !important; font-weight: 700; }</style>", unsafe_allow_html=True)

def inicializar_banco():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS receitas (mes INTEGER, ano INTEGER, codigo_full TEXT, natureza TEXT, orcado REAL, realizado REAL, previsao REAL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS despesas (mes INTEGER, ano INTEGER, uo TEXT, funcao TEXT, subfuncao TEXT, programa TEXT, projeto TEXT, natureza TEXT, fonte TEXT, orcado_inicial REAL, cred_autorizado REAL, empenhado REAL, liquidado REAL, pago REAL)''')
    conn.close()

def limpar_f(v):
    if pd.isna(v) or v == "" or v == "-": return 0.0
    if isinstance(v, (int, float)): return float(v)
    v = str(v).replace('.', '').replace(',', '.')
    try: return float(v)
    except: return 0.0

def detectar_mes(arquivo):
    try:
        df_scan = pd.read_excel(arquivo, nrows=10, header=None)
        for r in range(len(df_scan)):
            for celula in df_scan.iloc[r]:
                texto = str(celula).upper()
                for nome, num in MESES_MAPA.items():
                    if nome in texto: return num
    except: return None
    return None

inicializar_banco()

# --- SIDEBAR: IMPORTAÇÃO ---
with st.sidebar:
    st.subheader("📥 Importar Dados")
    tipo_dado = st.radio("Tipo:", ["Receita", "Despesa"])
    arquivo = st.file_uploader(f"Arquivo {tipo_dado}", type=["xlsx"])
    if arquivo and st.button("🚀 Processar Dados"):
        m_final = detectar_mes(arquivo)
        if not m_final:
            st.error("Mês não detectado no cabeçalho.")
            st.stop()
        conn = sqlite3.connect(DB_NAME)
        try:
            if tipo_dado == "Receita":
                df = pd.read_excel(arquivo, skiprows=7)
                dados = []
                for _, row in df.iterrows():
                    cod = str(row.iloc[0]).strip()
                    if re.match(r'^\d', cod) and len(cod) >= 11:
                        dados.append((m_final, 2026, cod, str(row.iloc[1]), limpar_f(row.iloc[3]), limpar_f(row.iloc[6]), limpar_f(row.iloc[5])))
                conn.execute("DELETE FROM receitas WHERE mes=?", (m_final,))
                conn.executemany("INSERT INTO receitas VALUES (?,?,?,?,?,?,?)", dados)
            else:
                df = pd.read_excel(arquivo, skiprows=6)
                df.columns = df.columns.str.strip().str.upper()
                
                # IMPORTAÇÃO INTELIGENTE FIP 616:
                # Armazenamos os valores ACUMULADOS diretamente do relatório
                dados = []
                for _, row in df.iterrows():
                    uo = str(row.get('UO', '')).strip()
                    if uo != "" and uo != "nan":
                        ug = str(row.get('UG', '')).strip()
                        elem = limpar_f(row.get('ELEMENTO', 0))
                        
                        # Valores de execução acumulados (vêm do relatório)
                        v_emp = limpar_f(row.get('EMPENHADO', 0)) if (ug != '0' and elem != 0) else 0.0
                        v_liq = limpar_f(row.get('LIQUIDADO', 0)) if (ug != '0' and elem != 0) else 0.0
                        v_pag = limpar_f(row.get('PAGO', 0)) if (ug != '0' and elem != 0) else 0.0
                        
                        # Crédito e Orçado Inicial
                        v_aut = limpar_f(row.get('CRÉDITO AUTORIZADO', 0))
                        v_ini = limpar_f(row.get('ORÇADO INICIAL', 0))

                        if v_aut > 0 or v_emp > 0 or v_liq > 0 or v_pag > 0:
                            dados.append((m_final, 2026, uo, str(row.get('FUNÇÃO', '')), str(row.get('SUBFUNÇÃO', '')), 
                                         str(row.get('PROGRAMA', '')), str(row.get('PAOE', '')), str(row.get('NATUREZA DESPESA', '')), 
                                         str(row.get('FONTE', '')), v_ini, v_aut, v_emp, v_liq, v_pag))
                
                conn.execute("DELETE FROM despesas WHERE mes=?", (m_final,))
                conn.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dados)
            
            conn.commit()
            st.success(f"✅ Importado: {MESES_NOMES[m_final-1]}")
            st.rerun()
        except Exception as e: st.error(f"Erro: {e}")
        finally: conn.close()

    if st.button("🔴 LIMPAR TUDO"):
        conn = sqlite3.connect(DB_NAME); conn.execute("DROP TABLE IF EXISTS receitas"); conn.execute("DROP TABLE IF EXISTS despesas")
        conn.commit(); conn.close(); inicializar_banco(); st.rerun()

# --- CARGA ---
conn = sqlite3.connect(DB_NAME)
df_rec = pd.read_sql("SELECT * FROM receitas", conn)
df_desp = pd.read_sql("SELECT * FROM despesas", conn)
conn.close()

tab1, tab2 = st.tabs(["📊 Receitas", "💸 Despesas"])

with tab2:
    if not df_desp.empty:
        # FILTROS
        f1, f2, f3 = st.columns(3)
        meses_disponiveis = sorted(df_desp['mes'].unique())
        ms_d = f1.multiselect("Meses:", meses_disponiveis, default=meses_disponiveis, format_func=lambda x: MESES_NOMES[x-1], key="msd")
        ss = f2.multiselect("Subfunção:", sorted(df_desp['subfuncao'].unique()))
        ps = f3.multiselect("Programa:", sorted(df_desp['programa'].unique()))

        f4, f5, f6 = st.columns(3)
        pjs = f4.multiselect("Projeto/PAOE:", sorted(df_desp['projeto'].unique()))
        fts = f5.multiselect("Fonte:", sorted(df_desp['fonte'].unique()))
        bd = f6.text_input("Natureza (Contém):", placeholder="Ex: 3390", key="bd")
        
        # Aplicar filtros básicos
        df_f = df_desp[df_desp['mes'].isin(ms_d)]
        if ss: df_f = df_f[df_f['subfuncao'].isin(ss)]
        if ps: df_f = df_f[df_f['programa'].isin(ps)]
        if pjs: df_f = df_f[df_f['projeto'].isin(pjs)]
        if fts: df_f = df_f[df_f['fonte'].isin(fts)]
        if bd: df_f = df_f[df_f['natureza'].str.contains(bd, case=False, na=False)]
        
        if not df_f.empty:
            # Função para calcular valores mensais a partir dos acumulados
            def calcular_valores_mensais(df, coluna_valor):
                """
                Converte valores acumulados em valores mensais.
                Para cada combinação de chaves (uo, funcao, subfuncao, programa, projeto, natureza, fonte),
                calcula a diferença entre o valor do mês atual e o mês anterior.
                """
                # Agrupar por todas as dimensões exceto mês
                colunas_chave = ['uo', 'funcao', 'subfuncao', 'programa', 'projeto', 'natureza', 'fonte']
                
                # Ordenar por mês
                df_ordenado = df.sort_values('mes')
                
                # Calcular valores mensais
                valores_mensais = []
                
                for (chave), grupo in df_ordenado.groupby(colunas_chave):
                    grupo = grupo.sort_values('mes')
                    meses_grupo = grupo['mes'].tolist()
                    valores_acumulados = grupo[coluna_valor].tolist()
                    
                    # Primeiro mês: o valor mensal é igual ao acumulado
                    valores_mensais_grupo = [valores_acumulados[0]]
                    
                    # Para os demais meses: valor mensal = acumulado atual - acumulado anterior
                    for i in range(1, len(valores_acumulados)):
                        valor_mensal = max(0, valores_acumulados[i] - valores_acumulados[i-1])
                        valores_mensais_grupo.append(valor_mensal)
                    
                    # Adicionar ao resultado
                    for idx, row in grupo.iterrows():
                        posicao = meses_grupo.index(row['mes'])
                        valores_mensais.append(valores_mensais_grupo[posicao])
                
                return valores_mensais
            
            # Calcular valores mensais para empenhado, liquidado e pago
            # Para o crédito autorizado, mantemos o valor do último mês selecionado
            m_max = max(ms_d) if ms_d else df_f['mes'].max()
            
            # Criar uma cópia do dataframe para trabalhar
            df_trabalho = df_f.copy()
            
            # Calcular valores mensais para as colunas de execução
            df_trabalho['empenhado_mensal'] = calcular_valores_mensais(df_f, 'empenhado')
            df_trabalho['liquidado_mensal'] = calcular_valores_mensais(df_f, 'liquidado')
            df_trabalho['pago_mensal'] = calcular_valores_mensais(df_f, 'pago')
            
            # Para o crédito autorizado, usamos o valor do último mês do filtro
            df_credito = df_f[df_f['mes'] == m_max].copy()
            # Agrupar crédito por dimensões e pegar o máximo
            colunas_credito = ['uo', 'funcao', 'subfuncao', 'programa', 'projeto', 'natureza', 'fonte']
            df_credito_agrupado = df_credito.groupby(colunas_credito)['cred_autorizado'].max().reset_index()
            
            # Criar um dicionário para mapear crédito por combinação de chaves
            credito_dict = {}
            for _, row in df_credito_agrupado.iterrows():
                chave = tuple(row[colunas_credito])
                credito_dict[chave] = row['cred_autorizado']
            
            # Adicionar crédito ao dataframe de trabalho
            def get_credito(row):
                chave = tuple(row[colunas_credito])
                return credito_dict.get(chave, 0)
            
            df_trabalho['cred_autorizado_mensal'] = df_trabalho.apply(get_credito, axis=1)
            
            # Agregar apenas os valores mensais para o resumo (considerando apenas um registro por mês por combinação)
            # Para evitar duplicação, agrupamos novamente
            colunas_agrupamento = colunas_credito + ['mes']
            df_resumo = df_trabalho.groupby(colunas_agrupamento).agg({
                'empenhado_mensal': 'sum',
                'liquidado_mensal': 'sum',
                'pago_mensal': 'sum',
                'cred_autorizado_mensal': 'max'  # Crédito é o mesmo para todos os meses, pega o máximo
            }).reset_index()
            
            # Soma total para os KPI
            v_aut = df_resumo['cred_autorizado_mensal'].sum()
            ve = df_resumo['empenhado_mensal'].sum()
            vl = df_resumo['liquidado_mensal'].sum()
            vp = df_resumo['pago_mensal'].sum()
            
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Créd. Autorizado", f"R$ {v_aut:,.2f}")
            k2.metric("Empenhado", f"R$ {ve:,.2f}")
            k3.metric("Liquidado", f"R$ {vl:,.2f}")
            k4.metric("Pago", f"R$ {vp:,.2f}")
            
            # Preparar dataframe para exibição
            df_exibicao = df_resumo.copy()
            df_exibicao = df_exibicao.rename(columns={
                'empenhado_mensal': 'empenhado',
                'liquidado_mensal': 'liquidado',
                'pago_mensal': 'pago',
                'cred_autorizado_mensal': 'cred_autorizado'
            })
            
            # Ordenar por mês para melhor visualização
            df_exibicao = df_exibicao.sort_values('mes')
            
            st.dataframe(df_exibicao[['mes', 'funcao', 'subfuncao', 'programa', 'projeto', 'fonte', 'natureza', 
                                      'cred_autorizado', 'empenhado', 'liquidado', 'pago']].style.format({
                'cred_autorizado': '{:,.2f}', 
                'empenhado': '{:,.2f}', 
                'liquidado': '{:,.2f}', 
                'pago': '{:,.2f}'
            }).format({'mes': lambda x: MESES_NOMES[x-1]}), width='stretch')
            
        else:
            st.warning("Nenhum dado encontrado com os filtros selecionados.")
    else:
        st.info("Nenhum dado de despesa importado ainda.")
