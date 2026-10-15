"""Dashboard Profibus PA. Executar com: streamlit run app.py"""
import os
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title='ProfiCloud PA', page_icon='📡', layout='wide')

# Estilo visual melhorado para as métricas e legibilidade
st.markdown('''
<style>
.block-container { padding-top: 1.4rem; }
div[data-testid="stMetric"] {
    background-color: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 10px;
    padding: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
div[data-testid="stMetric"] label {
    color: #57606a !important;
    font-weight: 600;
    font-size: 0.9rem;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    color: #1f2328 !important;
    font-weight: 700;
}
h1, h2, h3 { color: #1f2328; }
</style>
''', unsafe_allow_html=True)

DB_URL = os.getenv('FIREBASE_DATABASE_URL', 'https://proficloudpa-default-rtdb.firebaseio.com').rstrip('/')
TIMEOUT = 12

def request_json(method, url, **kwargs):
    response = requests.request(method, url, timeout=TIMEOUT, **kwargs)
    response.raise_for_status()
    return response.json()

def read(path):
    return request_json('GET', f'{DB_URL}/{path}.json')

def number(value):
    try: return float(value)
    except (ValueError, TypeError): return 0.0

st.title('📡 ProfiCloud PA')

# Seleção fixa da rede ingerida
network_id = 'segmento_01'

with st.sidebar:
    st.subheader('Painel de Controlo')
    st.info(f'Rede ativa: {network_id}')
    st.caption('Atualização automática a cada 10 segundos')

@st.fragment(run_every='10s')
def dashboard(network_id):
    try:
        data = read(f'networks/{network_id}/current')
    except requests.RequestException as exc:
        st.error(f'Falha ao obter dados da rede: {exc}')
        return
    
    if not data:
        st.info('Aguardando o primeiro snapshot desta rede.')
        return
        
    system = data.get('system') or {}
    network = data.get('network') or {}
    counters = data.get('counters') or {}
    devices = data.get('devices') or {}
    
    st.caption(f"{system.get('network_name', network_id)} · {system.get('network_segment', '')} · Medição: {system.get('updated_at', '—')} · Recebido: {data.get('ingested_at', '—')}")
    
    st.header('Visão geral da rede')
    cols = st.columns(5)
    for col, label, value in zip(cols, ['Estado', 'Saúde', 'QI', 'Dispositivos', 'Mensagens'], [network.get('status', '—'), network.get('health', '—'), f"{number(network.get('qi')):.1f}", len(devices), counters.get('nrmessages', 0)]):
        col.metric(label, value)
        
    cols = st.columns(4)
    for col, key, label in zip(cols, ['retries', 'unanswered_messages', 'checksum_errors', 'live_entries'], ['Retries', 'Sem resposta', 'Erros checksum', 'Entradas/saídas']):
        col.metric(label, counters.get(key, 0))
        
    st.progress(min(1.0, max(0.0, number(network.get('qi')) / 100)), text='Índice de qualidade da rede')
    
    with st.expander('Alarmes e condições gerais'):
        for key, value in network.items():
            if key.endswith(('_limit', '_limits')) or key in ['inverted_polarity', 'diagnostics_data_exchange', 'capacitive_shape', 'inductive_shape']:
                st.write(f'{key}: {", ".join(map(str, value)) if isinstance(value, list) and value else "Nenhum"}')
        st.json({'gateway': data.get('gateway'), 'diagnostics': data.get('diagnostics'), 'recent_events': data.get('recent_events')})
        
    st.header('Equipamentos da Live List')
    rows = []
    for addr, dev in sorted(devices.items(), key=lambda x: int(x[0])):
        rows.append({
            'Endereço': int(addr),
            'Tag': dev.get('tag', ''),
            'Estado': dev.get('status', ''),
            'Saúde': dev.get('health', ''),
            'QI': number(dev.get('qi')),
            'Sinal': number(dev.get('average_signal')),
            'Ruído': number(dev.get('average_noise')),
            'Jitter': number(dev.get('jitter')),
            'Retries': number(dev.get('retries')),
            'Sem resposta': number(dev.get('unanswered_messages'))
        })
        
    if not rows:
        st.info('Nenhum equipamento na Live List.')
        return
        
    frame = pd.DataFrame(rows)
    st.dataframe(frame, use_container_width=True, hide_index=True)
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader('Qualidade por endereço')
        st.bar_chart(frame.set_index('Endereço')['QI'])
    with c2:
        st.subheader('Sinal e ruído por endereço')
        st.line_chart(frame.set_index('Endereço')[['Sinal', 'Ruído']])
        
    addr = st.selectbox('Detalhar endereço', sorted(devices, key=int), format_func=lambda x: f'{x} · {devices[x].get("tag", "Equipamento")}')
    dev = devices[addr]
    
    a, b, c, d = st.columns(4)
    a.metric('Qualidade', dev.get('health', '—'))
    b.metric('QI', f"{number(dev.get('qi')):.1f}")
    c.metric('Polaridade', dev.get('polarity', '—'))
    d.metric('Status', dev.get('status', '—'))
    
    st.subheader('Grandezas e diagnóstico')
    pairs = [{'Parâmetro': key, 'Valor': str(value)} for key, value in dev.items() if key != 'address' and not key.startswith(('Input Value', 'Output Value'))]
    st.dataframe(pd.DataFrame(pairs), use_container_width=True, hide_index=True)
    
    cyclic = [{'Campo': key, 'Valor': value} for key, value in dev.items() if key.startswith(('Input Value', 'Output Value'))]
    if cyclic:
        st.subheader('Dados cíclicos de processo')
        st.caption(f"GSD: {dev.get('GSD', '—')} · Label: {dev.get('Label', '—')}")
        st.dataframe(pd.DataFrame(cyclic), use_container_width=True, hide_index=True)

dashboard(network_id)