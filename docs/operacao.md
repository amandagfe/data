# Operação, execução e publicação

## Estado operacional confirmado

- site e API mínima servidos por `server.py`; os arquivos continuam estáticos e o backend só intermedeia Telegram/status;
- análise e inferência no navegador;
- coleta para treino e treinamento apenas por scripts manuais;
- ausência de agendador e CI/CD; há backend Telegram opcional, ledger SQLite offline e testes locais, sem suíte completa de navegador;
- método e destino de publicação não verificados.

## Execução local do site

Pré-requisitos mínimos:

- Python 3 para `server.py`, que serve o site e a ponte Telegram num único processo. Um servidor estático qualquer (`http.server`, por exemplo) carrega o site, mas deixa o Telegram desativado;
- navegador moderno com JavaScript, `fetch`, WebGL/canvas, SVG, `localStorage` e `AbortController`; geolocalização é opcional e exige contexto seguro (`https` ou `localhost`) e permissão do usuário;
- acesso de rede às APIs e CDNs listadas em [arquitetura.md](arquitetura.md#serviços-externos).

Na raiz:

```bash
python3 server.py
```

Abrir `http://localhost:8000`. Abrir `index.html` diretamente por `file://` não é suportado porque os JSONs são carregados por `fetch` (`app.js:34`).

Não há instalação para executar o site. As bibliotecas de interface vêm de CDNs (`index.html:402-404`). Isso simplifica a execução, mas torna o funcionamento dependente da rede e das versões fixadas nas URLs.

## Configuração

### Site

Não há arquivo de ambiente. URLs, períodos, parâmetros e *timeouts* estão codificados em `app.js` e nos scripts.

### Telegram — backend implementado, segredo externo

`server.py` implementa `GET /api/telegram/status` e `POST /api/telegram/notices`. O token e o `chat_id` vêm exclusivamente de `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`; o navegador não recebe nenhum deles. O destinatário é fixo, texto livre é rejeitado, as coordenadas chegam arredondadas a duas casas, o corpo é limitado a 4 KiB e há limite em memória de três envios por IP em dez minutos. O endpoint só habilita com `TELEGRAM_ALERTS_ENABLED=1` e as duas credenciais presentes.

O servidor também carrega `.env` local, desde que o arquivo tenha permissão `0600`; somente as quatro chaves Telegram permitidas são lidas. Para descobrir o ID de um grupo recebido por `@data_dectives_bot` sem exibir o token:

```bash
python3 scripts/configure_telegram.py --group "Data Dectives"
```

O configurador valida que a credencial pertence ao bot esperado, ignora conversas privadas, procura somente grupo/supergrupo/canal em `getUpdates` e grava `.env` ignorado pelo Git. O grupo só aparece depois de adicionar o bot e enviar uma mensagem ou comando nele.

```bash
export TELEGRAM_ALERTS_ENABLED=1
export TELEGRAM_BOT_TOKEN='valor-no-ambiente-do-servidor'
export TELEGRAM_CHAT_ID='destino-no-ambiente-do-servidor'
python3 server.py
```

O token fornecido em conversa durante esta etapa não foi gravado no repositório nem executado. Como foi compartilhado fora do gerenciador de segredos, continua recomendada a revogação no BotFather com `/revoke` e substituição antes de publicação.

Nunca registrar em documentação, Git, prints, logs ou mensagens:

- token do bot;
- `chat_id` privado, se houver restrição operacional;
- conteúdo sensível ou dado pessoal de destinatários.

## Dependências de treinamento

Os scripts importam apenas biblioteca padrão, `numpy` e `scikit-learn`, mas não há `requirements.txt`, `pyproject.toml`, *lockfile* ou versão registrada. O README diz apenas “requer numpy e scikit-learn” (`README.md:70`). Reproduzir exatamente as métricas não é garantido sem versões e entradas originais.

Arquivos antigos ainda ausentes:

- `train_events.json`;
- diretório `power/`;
- intermediários `structural.json` e `trigger.json`.

O CSV GLC novo e seu manifesto agora existem em `data/sources/glc/2026-11-15/`; eles não recuperam os intermediários do treino antigo.

## Pipeline manual atual

Os comandos declarados no README são:

```bash
python scripts/build_catalog.py Global_Landslide_Catalog_Export_rows.csv countries-110m.json data/catalog.json
python scripts/prepare_events.py Global_Landslide_Catalog_Export_rows.csv train_events.json
python scripts/fetch_power.py train_events.json power/
python scripts/train_trigger.py train_events.json power/ trigger.json
python scripts/train_structural.py Global_Landslide_Catalog_Export_rows.csv structural.json
python scripts/build_models.py structural.json trigger.json data/models.json
python scripts/fetch_enso.py data/enso.json
```

O diretório de saída `power/` deve existir antes de `fetch_power.py`; o script não o cria (`scripts/fetch_power.py:2-7`). A coleta usa três threads e cinco tentativas com espera crescente (`scripts/fetch_power.py:11-24`). Isso difere do cliente web, que serializa POWER.

Não executar esses comandos no caminho de uma requisição do usuário. Coleta e treino devem permanecer offline.

### Pipelines candidatos desta etapa

```bash
python3 scripts/build_catalog.py data/sources/glc/2026-11-15/Global_Landslide_Catalog_Export_rows.csv data/catalog.json /tmp/catalog-v2.json --manifest data/sources/glc/2026-11-15/manifest.json
python3 scripts/weather_pipeline.py prepare --run-dir data/runs/weather/2026-11-15-v1
python3 scripts/weather_pipeline.py collect --run-dir data/runs/weather/2026-11-15-v1 --workers 3
python3 scripts/weather_pipeline.py reconcile --run-dir data/runs/weather/2026-11-15-v1
python3 scripts/build_land_grid.py
python3 scripts/prepare_structural_v2.py --output data/runs/structural/2026-11-15-v1/manifest.json
python3 scripts/update_gibs_metadata.py --output data/gibs.json
```

`collect` retoma por ledger SQLite, grava cache atomicamente e registra cada tentativa. `data/runs/` é ignorado pelo Git porque contém caches/estado operacional; snapshots de fonte e manifestos publicados ficam em `data/sources/`. Nenhum comando acima treina ou promove modelo.

## Treino, atualização e promoção segura

Fluxo recomendado, ainda não implementado:

1. baixar a fonte para diretório de *staging*, registrando URL, data, licença, tamanho e SHA-256;
2. validar esquema, cobertura temporal, duplicatas, ausências e mudanças contra a versão publicada;
3. congelar ambiente e sementes; registrar commit e comandos;
4. treinar em arquivos com versão, sem sobrescrever `data/models.json`;
5. gerar relatório por período e região, calibração e comparação com o modelo publicado;
6. testar equivalência Python/JavaScript e contratos dos JSONs;
7. revisar cientificamente rótulos e limitações;
8. publicar em *staging* e executar teste de navegador;
9. promover por troca explícita e revisada do manifesto; nunca automaticamente após treino;
10. manter artefato anterior e manifesto para reversão.

Critério mínimo de reversão: restaurar os três JSONs e a versão de código compatível. Não existe migração de banco.

## Atualizações automáticas

| Item | Situação |
|---|---|
| NASA POWER para lugar | consulta sob demanda no navegador |
| GIBS | consulta sob demanda ao trocar a camada |
| Geocoding/reverse/elevation | consulta sob demanda |
| ONI local | manual por `scripts/fetch_enso.py` |
| catálogo | manual por `build_catalog.py` |
| catálogo COOLR integrado | manual por `integrate_coolr_catalog.py`; verifica hashes e não altera modelos |
| modelos | manual por scripts de treino/empacotamento |
| tarefas agendadas | nenhuma encontrada |
| atualização em segundo plano | nenhuma encontrada |
| promoção automática de modelo | nenhuma encontrada |

O campo `updated` de ENSO usa `datetime.date.today()` da máquina que executa o script (`scripts/fetch_enso.py:15`); ele não prova que a NOAA publicou ou revisou dados nessa data.

## Cache e limites

- estudos ficam em memória pela coordenada arredondada a três casas; recarregar a página perde o cache (`app.js:341-348`);
- texturas GIBS ficam em memória durante a aba (`app.js:172-180`);
- idioma e comparações ficam em `localStorage`;
- não há cache persistente das séries POWER, *service worker*, limite de tamanho ou expiração;
- POWER é serializado e repetido após 4 s e 10 s, três tentativas totais (`app.js:241-245`);
- Nominatim recebe uma consulta por clique, mas não há cache persistente nem controle global de 1 req/s. Antes de escala, revisar a [política oficial](https://operations.osmfoundation.org/policies/nominatim/).

## Tratamento de falhas

| Falha | Comportamento atual | Lacuna |
|---|---|---|
| JSON inicial ou biblioteca ausente | IIFE cai no `catch` e mostra falha genérica (`app.js:804`) | não identifica artefato/causa |
| POWER | três tentativas; falha cancela análise e oferece repetir | sem distinção entre timeout, 429, esquema e CORS |
| elevação | retorna `null`; análise continua | adequado para degradação, mas sem causa na UI |
| geocoding | mensagem “não respondeu” | sem detalhes/telemetria |
| geolocalização | loading e mensagens distintas para permissão negada, posição indisponível, timeout e API ausente; busca continua disponível | permissão/precisão dependem do navegador e dispositivo; teste em dispositivos reais pendente |
| reverse | mantém nome genérico | adequado |
| GIBS | mensagem de erro e cache removido; data/fallback vêm de `data/gibs.json` | sem código HTTP na UI; metadado pode vencer |
| Telegram | status `/api/telegram/status`; sem backend, desativado com motivo `backend_unavailable`; 429 vira “limite atingido” | adequado; envio real depende do token/destino em `.env` |
| dados parciais POWER | valores fill viram `NaN`; anos incompletos são excluídos | não informa porcentagem de ausências ao usuário |

## Verificações executadas em 15/11/2026

| Comando/verificação | Resultado |
|---|---|
| `node --check app.js` | passou, Node v22.22.1 |
| `node --check i18n.js` | passou |
| `python3 -m py_compile scripts/*.py` | passou, Python 3.14.4 |
| `python3 scripts/audit_data.py --strict --summary` | passou; 11.033 registros, 9.321 células, 921 ONI e zero problema estrutural fatal |
| `python3 scripts/audit_data.py --raw-glc /tmp/dd_glc_official.csv --strict` | passou; CSV obtido do portal reproduziu 11.033/11.033 registros locais |
| `python3 scripts/audit_data.py --raw-glc data/sources/glc/2026-11-15/Global_Landslide_Catalog_Export_rows.csv --strict` | passou no schema v2; 11.033 IDs/linhas e campos de rastreabilidade corresponderam |
| `python3 scripts/weather_pipeline.py prepare ...` | 8.197 candidatos = 240 excluídos + 7.957 pendentes; 2.567 células antes do filtro e zero perda silenciosa |
| `weather_pipeline.py collect --limit-cells 3` | três caches, quatro candidatos válidos, produto MERRA2/API v2.10.3, uma tentativa por célula |
| `python3 -m unittest tests/test_temporal_alignment.py -v` | quatro testes passaram |
| `python3 -m unittest discover -s tests -v` após a interface v9 | oito testes passaram |
| `node --check app.js` e `node --check i18n.js` após a interface v9 | passaram |
| parser HTML: IDs duplicados, pares `main` e `details` | zero IDs duplicados; estruturas balanceadas |
| `git diff --check` após a interface v9 | passou |
| Chrome headless, 1440 px e 390 px, via servidor local | renderizou hero e resumo responsivos; Petrópolis retornou referência POWER de 12/11/2026 e os mesmos valores na leitura inicial; capturas em `/tmp` não foram versionadas |
| contraste dos pares principais pelo cálculo WCAG | coral/texto escuro 5,71:1; texto secundário/fundo escuro ≥7,45:1; texto secundário/fundo claro 5,70:1; passaram AA para texto normal |
| contrato estático de acessibilidade | um `main`, nenhum ID duplicado, traduções EN/ES completas, busca com combobox, status ao vivo e rótulos de visualização presentes |
| `python3 scripts/prepare_structural_v2.py ...` | 29.496 células independentes; 51/10.988 registros fora do domínio; nenhum treino |
| `python3 scripts/update_gibs_metadata.py --desired-date 2026-11-14` | 4/4 imagens; IMERG/SMAP com fallback, VIIRS na data pedida, NDH estática |
| `python3 scripts/check_integrations.py --strict` | passou com rede em 15/11/2026; POWER, Elevation, Geocoding, Nominatim, GIBS e ONI compatíveis na amostra; Telegram deliberadamente não chamado |
| carregar `data/*.json` com `json.load` | os três arquivos são JSON válidos |
| servidor `python3 -m http.server 8765 --bind 127.0.0.1` | iniciou após autorização de socket local |
| `HEAD /` | HTTP 200; arquivo final `text/html` com 32.496 bytes |
| `HEAD /app.js?v=8` | HTTP 200; arquivo final `text/javascript` com 66.102 bytes |
| `HEAD /data/models.json` | HTTP 200, `application/json`, 583.748 bytes |
| `HEAD /docs/auditoria-dados.md` | HTTP 200; arquivo final `text/markdown` com 28.222 bytes |
| teste completo/interativo em navegador | **não executado**; as capturas headless não acionaram permissão de geolocalização, teclado/leitor de tela nem o abre/fecha da área técnica |
| chamadas externas ao vivo | contratos de leitura foram executados pelo verificador; teste de navegador ponta a ponta continua não executado |
| retreinamento/download | **não executado**; entradas brutas e ambiente fixado estão ausentes |

Esses resultados confirmam sintaxe, integridade JSON e serviço estático básico. Não confirmam renderização WebGL, CORS futuro, disponibilidade contínua das APIs nem correção estatística.

## Publicação

### GitHub Pages (hospedagem estática)

O site funciona sem backend. Em 15/11/2026, um servidor estático com o site em subcaminho (`/data-detectives/`, como num Pages de projeto) foi aberto em Chrome headless: carregou catálogo, modelos v2 e gráficos sem erro de JavaScript.

Requisitos e comportamento:

- `index.html`, `app.js`, `i18n.js`, `style.css`, `assets/`, `.nojekyll` e os cinco JSONs de `data/` (`catalog`, `models`, `enso`, `gibs`, `coolr-status`) precisam estar commitados. Se faltar um JSON, a página inteira não carrega, porque eles são lidos juntos na abertura.
- Todas as URLs são relativas, então o site funciona na raiz ou em subcaminho.
- O Telegram depende do `server.py`. Sem ele, `api/telegram/status` responde 404 e o painel fica oculto, sem mensagem de erro ao visitante. O token nunca vai para o Pages.
- Tudo que é commitado fica público. `.env`, `data/runs/` e `data/releases/` estão no `.gitignore`. Os JSONs de `data/` não contêm caminhos da máquina: as linhagens do catálogo usam caminhos relativos à raiz desde 15/11/2026.

**Não verificado** no Pages real:

- `git remote -v` não mostrou remoto;
- não há workflow, `CNAME`, Dockerfile ou configuração de hospedagem;
- não há política de headers, cache, CSP ou SRI;
- não há procedimento de publicação/rollback no repositório.

Antes de publicar, registrar destino, domínio, branch/artefato, comando, aprovador, smoke test e rollback. A publicação pode configurar Telegram somente no ambiente/secret manager; nenhum token ou `chat_id` pode entrar nos arquivos servidos ao cliente.

## Checklist de incidente

1. confirmar se o erro é arquivo estático, CDN, POWER, GIBS, Open-Meteo ou Nominatim;
2. preservar console/rede sem copiar segredos;
3. conferir datas e checksums dos três artefatos;
4. se o problema surgiu após troca de dados/modelo, reverter o artefato e código compatíveis;
5. se um token Telegram foi exposto, revogá-lo no BotFather, remover do armazenamento/publicação e revisar acessos;
6. comunicar que o site não é alerta oficial e direcionar a fontes oficiais locais quando houver risco real.

## Próxima ação operacional

Concluir DD-032/DD-033, adicionar manifesto de dependências/modelos, CI e smoke test de navegador. O backend Telegram está pronto, mas a credencial real deve ser configurada diretamente no ambiente e o token compartilhado deve ser substituído antes de publicação.
