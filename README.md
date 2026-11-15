# Data Detectives

Aplicação web estática para explorar registros de deslizamentos, séries meteorológicas da NASA POWER, ENSO e dois modelos experimentais, criada para o desafio **Earth System Trend Detective**.

O projeto é uma ferramenta de estudo. Não é alerta oficial e não estima risco no sentido técnico: exposição, vulnerabilidade e dano esperado não são modelados. A ausência de registro ou de cobertura do modelo não significa ausência de deslizamento nem risco baixo.

## Rodar localmente

```bash
python3 server.py
```

Abra `http://localhost:8000`. É necessário um servidor HTTP porque os artefatos em `data/` são carregados com `fetch`.

O servidor entrega os arquivos estáticos e expõe uma ponte opcional para Telegram. O navegador:

- carrega `data/catalog.json`, `data/models.json`, `data/enso.json`, `data/gibs.json` e `data/coolr-status.json`;
- chama NASA POWER, NASA GIBS, Open-Meteo e Nominatim;
- calcula tendências, composições ENSO e inferência do modelo de disparo;
- renderiza o globo, gráficos e comparações.

Coleta para treino e treinamento são scripts offline e não rodam durante requisições dos usuários.

### Telegram sem token no navegador

O envio fica desativado sem configuração. Defina os valores apenas no ambiente do processo — nunca em `app.js`, HTML ou arquivo versionado:

```bash
export TELEGRAM_ALERTS_ENABLED=1
export TELEGRAM_BOT_TOKEN='TOKEN_CONFIGURADO_NO_SERVIDOR'
export TELEGRAM_CHAT_ID='DESTINATARIO_CONFIGURADO_NO_SERVIDOR'
python3 server.py
```

O cliente envia somente local, coordenada já arredondada para duas casas, score, faixa e data. O backend fixa o destinatário, rejeita texto livre, limita o corpo e aceita no máximo três pedidos por IP a cada dez minutos. `config/telegram.env.example` contém apenas nomes e valores fictícios. Um token compartilhado em navegador, conversa ou log deve ser tratado como exposto e substituído no BotFather.

Para localizar automaticamente o ID de um grupo já acessível pelo bot `@data_dectives_bot`, adicione o bot ao grupo, envie `/start@data_dectives_bot` dentro dele e execute:

```bash
python3 scripts/configure_telegram.py --group "Data Dectives"
```

O token é solicitado sem eco e a configuração é gravada em `.env` com permissão `0600`; o arquivo é ignorado pelo Git e carregado por `server.py`.

## Como interpretar os modelos

- **Modelo de disparo:** gera um score de semelhança entre condições meteorológicas regionais recentes e condições de dias com deslizamento registrado. O score não é probabilidade calibrada.
- **Modelo chamado estrutural na interface:** usa principalmente histórico do catálogo para estimar recorrência de registros por célula/mês. O artefato publicado foi gerado com atributos até 2017 e não representa uma condição atual. Ele não é um modelo físico de suscetibilidade nem uma estimativa de risco.

Veja limitações, métricas e períodos em [docs/modelos.md](docs/modelos.md).

## Documentação auditada

- [Visão geral](docs/visao-geral.md)
- [Arquitetura e fluxo de dados](docs/arquitetura.md)
- [Fontes e rastreabilidade](docs/fontes-de-dados.md)
- [Auditoria das bases e integrações](docs/auditoria-dados.md)
- [Preparação segura dos dados](docs/preparacao-dados.md)
- [Modelos](docs/modelos.md)
- [Operação](docs/operacao.md)
- [Plano de tarefas](docs/plano-de-tarefas.md)

A documentação diferencia fatos verificados, inferências e itens não verificados. O plano prioriza rótulos potencialmente enganosos, procedência, integração sem dupla contagem e testes.

## Refazer artefatos — fluxo atual

O pipeline antigo de treino requer `numpy`, `scikit-learn` e intermediários que não estão no repositório. Não execute treino antes de concluir o plano. O catálogo v2 pode ser reproduzido por:

```bash
python3 scripts/build_catalog.py data/sources/glc/2026-11-15/Global_Landslide_Catalog_Export_rows.csv data/catalog.json /tmp/catalog-v2.json --manifest data/sources/glc/2026-11-15/manifest.json
```

Os comandos históricos, que não garantem reprodução bit a bit do modelo atual, são:

```bash
python scripts/prepare_events.py Global_Landslide_Catalog_Export_rows.csv train_events.json
python scripts/fetch_power.py train_events.json power/
python scripts/train_trigger.py train_events.json power/ trigger.json
python scripts/train_structural.py Global_Landslide_Catalog_Export_rows.csv structural.json
python scripts/build_models.py structural.json trigger.json data/models.json
python scripts/fetch_enso.py data/enso.json
```

Gere candidatos fora de `data/` e só substitua artefatos publicados após validação e revisão. O processo recomendado de promoção e reversão está em [docs/operacao.md](docs/operacao.md#treino-atualização-e-promoção-segura).

## Estado conhecido

- `data/catalog.json` schema v3 contém 14.753 IDs únicos: 11.030 versões COOLR substituem IDs coincidentes, 3.720 IDs existem apenas no snapshot COOLR e três somente no GLC local. As datas presentes vão de 1915 a 2025; 1.637 registros não têm data e 27 não têm coordenada válida.
- `data/enso.json` registra ONI até ASO/2026 e data de download 14/11/2026. ONI recente é revisável, e a NOAA passou a usar RONI no monitoramento oficial em 2026.
- `data/gibs.json` registra o `TIME`/fallback das quatro camadas no snapshot de 15/11/2026;
- não há atualização agendada, CI/CD ou destino de publicação documentado;
- o backend Telegram está implementado e permanece desativado enquanto as variáveis de ambiente não forem configuradas; token e destinatário nunca são entregues ao navegador;
- os modelos publicados continuam treinados com dados até 2017. A atualização do catálogo afeta mapa e históricos locais, não retreina nem altera os modelos.

Consulte o [plano de tarefas](docs/plano-de-tarefas.md) antes de tratar o site como pronto para uso operacional.
# data
