# Fontes de dados e rastreabilidade

## Princípio de leitura

“Oficial” identifica o mantenedor, não garante cobertura completa, precisão local, ausência de viés ou atualização adequada ao uso. Cada item abaixo distingue observação/catalogação, reanálise, estimativa derivada, artefato de modelo e dado de interface.

## Inventário das fontes

| Fonte | Natureza | Aquisição implementada | Uso | Limites verificados |
|---|---|---|---|---|
| [NASA POWER Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) | reanálise/produto meteorológico em grade; não é estação local | navegador; pipeline novo 2001–2017 com `time-standard=LST` (`weather_pipeline.py`) | chuva, umidade do solo, temperatura, tendências e modelo de disparo | produto varia por período; piloto histórico retornou MERRA2. Grade não é observação local e a coleta nova ainda está incompleta |
| Global Landslide Catalog (GLC) | registros compilados a partir de mídia, bases e relatórios | snapshot imutável e manifesto em `data/sources/glc/2026-11-15/` | pontos, mortes registradas, gatilhos e treino dos dois modelos | cobertura de notícias desigual; ausência de registro não indica ausência de deslizamento |
| [NASA Open Data — Global Landslide Catalog Export](https://data.nasa.gov/dataset/global-landslide-catalog-export) | exportação pública descrita como única | `build_catalog.py` verifica o hash do snapshot | origem do catálogo v2 | licença não especificada; descrição “atual até 07/03/2016” conflita com registros até 2017 no arquivo servido |
| [NASA COOLR](https://gpm.nasa.gov/applications/landslides/coolr) | sistema com catálogos baseados em relatos e inventários baseados em eventos | auditoria dos quatro FeatureServer; snapshot de Reports Points | mapa e históricos locais; não altera os modelos publicados | integração usa `event_id`: COOLR substitui ID comum e IDs exclusivos são preservados; versão/licença continuam não informadas nos metadados auditados |
| [NOAA CPC ONI](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v5/) | média móvel de 3 meses de anomalia SST ERSSTv5 | `scripts/fetch_enso.py` baixa o ASCII para `data/enso.json` | fases e análises ENSO | valores recentes podem ser revistos; desde 2026 o monitoramento oficial usa RONI, embora a página ONI continue histórica |
| [Open-Meteo Elevation API](https://open-meteo.com/en/docs/elevation-api) | DEM Copernicus GLO-90, 90 m | cinco coordenadas por lugar (`app.js:254-258`) | altitude e gradiente aproximado | resolução nominal não é precisão; cálculo local não é declividade média nem mapeamento de suscetibilidade |
| [Open-Meteo Geocoding API](https://open-meteo.com/en/docs/geocoding-api) | índice de localidades baseado em GeoNames | busca pelo navegador (`app.js:260-263`) | nome/coordenada da pesquisa | resultado é localidade candidata, não valida endereço ou encosta |
| [Nominatim](https://operations.osmfoundation.org/policies/nominatim/) | geocodificação reversa OpenStreetMap | um pedido após clique (`app.js:264-270`) | nome do ponto | serviço público sem SLA; política limita uso e recomenda cache/proxy para escala; retorno nulo não altera coordenada |
| NASA GIBS/Worldview | visualizações geoespaciais WMS | `data/gibs.json` resolve `TIME` offline; WMS no navegador | IMERG, SMAP, VIIRS e camada NDH | imagem serve a exploração; não entra nos modelos. UI mostra fallback/data representada; snapshot precisa atualização |
| `world-atlas@2.0.2` / Natural Earth | limites generalizados 1:110m | arquivo externo incorporado por `build_catalog.py` | máscara terrestre e nomes de países | geometria pequena escala; não serve a limites locais. Arquivo bruto/versão não existem separadamente no repositório |
| Telegram Bot API | canal operacional, não fonte científica | `server.py` chama `sendMessage` quando habilitado | envio manual de resumo técnico | token/`chat_id` somente no ambiente do servidor; não é alerta oficial; limite em memória não substitui proteção de borda em produção |

## Artefatos versionados

Resultados obtidos em 15/11/2026 com `jq` e `sha256sum`:

| Artefato | Conteúdo observado | SHA-256 | Metadados ausentes |
|---|---|---|---|
| `data/catalog.json` | schema v3; 14.753 IDs, 64.584 mortes registradas, 3.865 fatalidades ausentes, 157 países; datas presentes 1915–2025 | `d17708747705a49fd091e8cbbba1cad3040a9739e1739c9ed566dc59f583f85f` | versão semântica/licença do COOLR; 1.637 datas e 27 coordenadas ausentes/inválidas |
| `data/gibs.json` | quatro camadas, `TIME`, fallback e verificação em 15/11/2026 | `eddbb9e262e8567e37b2c793f8f0f70dcecd69b14dce3133b88eb04e8eb870cc` | política/agendamento de atualização |
| `data/enso.json` | 921 estações mensais centrais; jan/1950 a set/2026 (ASO), campo `updated=2026-11-14` | `424945e0bd31766de18904df6b276f06179ada9d49672910680f71b63c2cd298` | versão/revisão NOAA; `updated` é data de execução do script, não data oficial de publicação |
| `data/models.json` | 9.321 células estruturais e 200 árvores de disparo | `ef64dcb5d42a159b505a718711dba5cfbed21d395981ed43b0454cd48d88ee4f` | versão semântica, data de treino, commit, versões Python/numpy/scikit-learn, checksums das entradas e horizonte explícito |

### Distribuição temporal e integração do catálogo

O catálogo publicado passou ao schema v3 por `scripts/integrate_coolr_catalog.py`. A regra é identificável e reversível: para os 11.030 `event_id` comuns, a linha COOLR substitui a local; 3.720 IDs apenas COOLR entram; três IDs apenas GLC são preservados. Nenhum registro é deduplicado por proximidade/data. Resultado: 14.753 IDs únicos, 14.726 com coordenadas válidas e 13.116 com data, entre 1915-12-15 e 2025-05-18. O mapa usa os registros com coordenada; gráficos temporais exigem data. Os dois modelos continuam com entradas antigas até 2017.

O site originalmente associava todos os 11.033 pontos a 2007–2017, mas 45 são anteriores a 2007. Há 10.988 registros em 2007–2017. Evidência: `python3 scripts/audit_data.py --summary` e `data/catalog.json.events[*].event_date`.

`prepare_events.py` e `train_structural.py` filtram explicitamente 2007–2017, mas `build_catalog.py` não filtra ano (`scripts/build_catalog.py:7-17`, `scripts/prepare_events.py:7-10`, `scripts/train_structural.py:9-14`). Assim, o mapa e históricos por raio usam o período integral do artefato, enquanto gráficos ENSO/ano e modelos usam 2007–2017.

## Tabela de rastreabilidade do que aparece no site

| Informação exibida | Tipo correto | Origem | Transformação implementada | Observação/limite |
|---|---|---|---|---|
| total de eventos | registros catalogados | `data/catalog.json.events` | comprimento do schema v3 | 14.753 IDs; não implica 14.753 eventos factualmente independentes; 1.637 sem data e 27 sem coordenada |
| mortes | mortes registradas no catálogo | `events[*].fatality_count` | soma visual usa zero para nulo, mas `fatKnown` preserva distinção | 1.385 valores ausentes não são observações de zero |
| “disparados por chuva” | classificação declarada do catálogo | gatilho de cada ponto | pertence a cinco rótulos (`app.js:39-40`) | taxonomia manual; não é atribuição causal independente |
| “Último ONI disponível” | último ONI do arquivo, estimado/revisável | `data/enso.json.oni[-1]` | regra de cinco estações e força por limiar (`app.js:47-64`) | não é leitura instantânea; a interface agora informa que RONI é o indicador oficial atual da NOAA |
| pontos do catálogo no globo | registros observados/catalogados | `catalog.json` v3 | 14.726 registros com coordenadas válidas | cobertura desigual; `location_accuracy` varia e 30 valores estão ausentes |
| saída estrutural no globo | previsão histórica do modelo | `models.json.grid.cells` | mensal ou união `1-∏(1-p_m)` (`app.js:103-106`, `198`) | união assume independência mensal; não validada como probabilidade calibrada |
| camadas GIBS | visualização remota | WMS GIBS + `data/gibs.json` | `TIME` explícito e composição sobre textura | fallback/data aparecem; camada não entra no score |
| nome do lugar pesquisado | dado de referência | Open-Meteo/GeoNames | primeiro resultado selecionado | ambiguidade possível |
| nome do ponto clicado | dado de referência | Nominatim/OSM | reverse zoom 10 | falha mantém rótulo genérico |
| “Índice meteorológico recente” | score do classificador | POWER + árvores em `models.json.trig` | 16 atributos, soma de árvores e sigmoide, exibido em pontos (`app.js:278-303`, `117-121`) | não é probabilidade calibrada nem alerta; dados POWER podem ter defasagem |
| faixa Normal/Elevado/Alto/Muito alto | classe relativa | controles não usados no treino final | percentis 90/97/99 dos scores (`scripts/train_trigger.py:72-76`, `98-101`) | limiares do conjunto de construção, não limites físicos universais |
| chuva de 7 dias e percentil | estimativa em grade e derivada | POWER PRECTOTCORR | soma móvel; ECDF 2001–2017 (`app.js:280-303`) | não é pluviômetro local |
| umidade do solo e percentil | reanálise e derivada | POWER GWETTOP | valor de `t-1`; ECDF 2001–2017 | interface chama “solo superficial”; escala 0–1 não é medição de saturação geotécnica |
| recorrência histórica em pontos | score histórico de recorrência de registro | `models.json.grid.cells` | somente a célula que contém o ponto; união mensal (`app.js:103-115`, `367-386`) | não é risco; entradas não descrevem estrutura física atual; horizonte final é passado; fora da cobertura aparece “não estimado” |
| declividade | estimativa derivada | cinco altitudes GLO-90 | gradiente central e arctan (`app.js:254-258`) | não é média em raio; sem incerteza/validação local |
| histórico por raio | registros catalogados | `catalog.json` | distância de Haversine e filtro (`app.js:352-389`) | “nenhum” significa nenhum registro no artefato/raio, não nenhum evento real |
| tendências | estatística derivada | POWER 1981–data disponível | anos com ≥360 dias; OLS/IC, Mann-Kendall e Sen (`app.js:82-93`, `320-322`) | teste MK não corrige autocorrelação/serialidade; IC é do OLS, não da inclinação de Sen |
| “dias de disparo” | indicador demonstrativo derivado | POWER | R7 > q95 e GWETTOP anterior > q80, percentis da série completa (`app.js:304-318`) | não são dias com deslizamento observado nem saída do modelo |
| efeito local de El Niño/La Niña | estimativa histórica | POWER + ONI | anomalias mensais, Welch e médias (`app.js:323-330`) | associação, não causalidade nem previsão do episódio atual |
| correlação defasada ONI × chuva | estimativa histórica | POWER + ONI | Pearson lags 0–6; `n_eff` por autocorrelação lag 1 (`app.js:331-337`) | múltiplos testes sem correção; aproximação de significância |
| eventos globais por fase ENSO | estatística de registros | catálogo + ONI | normalização pela média anual e Welch (`app.js:706-744`) | 2007–2017, cobertura variável; indício, não prova |
| métricas dos modelos | resultado de treino armazenado | `models.json.*.metrics` | apenas formatação (`app.js:772-779`) | execução original e ambiente não estão preservados |
| CSV | dado derivado exportado | análise do lugar | linhas mensais e cabeçalhos (`app.js:612-621`) | não inclui série diária bruta, versão do modelo, checksums nem incerteza |

## Valores ausentes, imputação e arredondamento

- POWER: o valor de preenchimento retornado no cabeçalho vira `NaN`; não há imputação (`app.js:249-252`).
- Treino POWER: `-999` vira `NaN`; janelas com ausentes são descartadas, mas a soma cumulativa usa zero internamente e marca a janela inválida com contador (`scripts/train_trigger.py:29-35`, `47-58`).
- Catálogo v3: os 14.753 IDs permanecem no JSON; 27 coordenadas inválidas e 1.637 datas ausentes ficam como `null` e são contadas em `quality`, sem virar zero ou risco baixo.
- Modelo estrutural armazena probabilidades multiplicadas por 1.000 e arredondadas para inteiro; o navegador divide por 1.000 (`scripts/train_structural.py:70-74`, `app.js:104`).
- Não há dados demonstrativos explicitamente marcados no fluxo atual.

## Lacunas de procedência

1. O GLC novo tem snapshot/manifesto; a entrada usada no catálogo histórico anterior continua impossível de provar retroativamente.
2. Intermediários do treino antigo (`train_events.json`, `power/`, `trigger.json`, `structural.json`) não são preservados; DD-027 permanece bloqueada.
3. Os modelos atuais ainda não registram comando, ambiente, commit, data de geração ou licença.
4. COOLR Reports Points foi integrado ao mapa/histórico por política de `event_id`; versão semântica e licença explícita continuam não verificadas, e a integração não atualiza os modelos.
5. A coleta POWER nova está incompleta e o domínio estrutural independente deixa 51 registros fora.

Até essas lacunas serem resolvidas, as métricas locais são reprodutíveis apenas a partir dos JSONs finais, não a partir das fontes originais.
