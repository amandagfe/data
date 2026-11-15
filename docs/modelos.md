# Modelos

## Conclusão científica

Os dois modelos respondem a perguntas distintas, mas os rótulos atuais exageram o alcance:

- o **modelo de disparo** produz um score de semelhança entre condições meteorológicas regionais recentes e condições de dias com registro de deslizamento;
- o **modelo estrutural** produz uma estimativa histórica de recorrência de registros em células próximas a registros anteriores.

Nenhum dos dois estima **risco** no sentido técnico, porque não modela exposição e vulnerabilidade. O segundo também não é um modelo físico de **suscetibilidade estrutural**: não usa declividade, geologia, solo, cobertura ou intervenções. O primeiro, isoladamente, não constitui uma estimativa validada de **perigo** nem um alerta.

## Comparação rápida

| Aspecto | Modelo de disparo | Modelo chamado “estrutural” |
|---|---|---|
| Pergunta aproximada | condições meteorológicas se parecem com dias registrados? | onde/mês o catálogo tende a voltar a registrar evento? |
| Unidade | célula POWER × dia | célula de 1° × mês |
| Fonte principal | GLC + POWER | somente GLC e coordenadas/tempo derivados |
| Alvo | dia com registro versus controle amostrado | ao menos um registro no mesmo mês do calendário nos dois anos seguintes |
| Saída publicada | 200 árvores + base + limiares | 12 valores pré-calculados por célula |
| Inferência | no navegador sobre POWER recente | não há inferência no navegador; consulta a tabela congelada |
| Atualização | dados meteorológicos novos, modelo congelado | totalmente congelada |
| Interpretação segura | score/índice de condição de disparo | índice de recorrência de registros no período de referência |

## Modelo de disparo

### Dados e amostragem

1. `prepare_events.py` conserva eventos de 2007–2017 com acurácia declarada `exact`, `1km`, `5km`, `10km` ou `25km` e os associa à grade POWER arredondando latitude/0,5 e longitude/0,625 (`scripts/prepare_events.py:3-13`).
2. `fetch_power.py` baixa PRECTOTCORR, GWETTOP e GWETROOT de 2001–2017 para cada célula (`scripts/fetch_power.py:4-15`).
3. O treino exclui oito gatilhos explicitamente não meteorológicos. Isso não significa que todos os restantes sejam confirmadamente meteorológicos; `unknown`, `no_apparent_trigger`, neve/degelo, inundação e outros rótulos não excluídos podem entrar (`scripts/train_trigger.py:17-27`).
4. Um caso é um dia com evento registrado e atributos completos. Para cada caso tenta-se amostrar quatro controles na mesma célula, em 2007–2017, afastados mais de dez dias de qualquer evento dessa célula (`scripts/train_trigger.py:59-76`).
5. O artefato informa 26.805 amostras, 5.361 casos e 922 lugares/células (`data/models.json.trig.metrics`).

Não há evidência de deduplicação por tempestade ou por múltiplos eventos no mesmo dia/célula. `by_cell` usa um conjunto de dias, portanto vários registros na mesma célula/dia viram um caso (`scripts/train_trigger.py:22-27`).

### Entradas

As 16 entradas, na ordem do artefato, são:

`r1`, `r3`, `r7`, `r14`, `r30`, `rante`, `pr1`, `pr3`, `pr7`, `pr14`, `gt`, `gr`, `pgt`, `pgr`, `map`, `ratio7`.

- `r1`: maior chuva do dia atual/anterior;
- `r3`, `r7`, `r14`, `r30`: acumulados móveis;
- `rante`: chuva do dia 8 ao 30 (`r30-r7`);
- `pr*`: posição empírica na climatologia 2001–2017 da célula;
- `gt`, `gr`: GWETTOP/GWETROOT do dia anterior;
- `pgt`, `pgr`: posições empíricas da umidade;
- `map`: média diária × 365,25;
- `ratio7`: R7 dividido por, no mínimo, o q95 local.

Implementações Python e JavaScript correspondem por inspeção (`scripts/train_trigger.py:29-58`, `app.js:278-303`). O script original também testa numericamente a exportação das árvores e exige diferença `<1e-4`, mas o log dessa execução não está versionado (`scripts/train_trigger.py:103-123`).

### Algoritmo e validação

`HistGradientBoostingClassifier` com 200 iterações, taxa 0,05, 15 folhas máximas, folha mínima 50, L2=1 e `random_state=7` (`scripts/train_trigger.py:81-82`).

Métricas armazenadas:

| Métrica | Valor | Desenho |
|---|---:|---|
| AUC espacial | 0,858 | GroupKFold 5, célula inteira fora do treino |
| AUC usando apenas `pr7` | 0,827 | mesma amostra; comparação simples |
| AUC temporal | 0,836 | treino até 2014, teste 2015–2017 |
| recall acima de “Alto” | 0,364 | limiar no percentil 97 dos controles OOF |
| especificidade declarada de “Alto” | 0,97 | definida pelo percentil, não por validação externa |

Evidência: `scripts/train_trigger.py:83-101` e `data/models.json.trig.metrics`.

Limitações da validação:

- controles amostrados não representam a frequência real de todos os dias sem evento;
- um “negativo” pode conter deslizamento não catalogado;
- cobertura noticiosa afeta positivos e negativos;
- não há validação externa, calibração (Brier/reliability), intervalo de confiança ou desempenho por região;
- AUC mede ordenação, não calibração nem utilidade operacional;
- o modelo temporal usado para importância não é o modelo final publicado.

### Saída e faixas

O navegador soma a base e as folhas das 200 árvores e aplica sigmoide (`app.js:116-121`). Como o treino usa proporção artificial de aproximadamente 1 caso para 4 controles, essa saída não deve ser chamada de chance de deslizamento. A interface a multiplica por 100 e a apresenta como pontos; a leitura segura é “score de 0 a 100”.

As faixas Elevado/Alto/Muito alto são percentis 90/97/99 do score do modelo final em controles adicionais (`scripts/train_trigger.py:72-76`, `98-101`):

- Elevado: 0,3627954843;
- Alto: 0,6265175401;
- Muito alto: 0,7562736536.

São classes relativas ao conjunto de construção, não probabilidades, níveis oficiais ou limiares geotécnicos.

## Modelo chamado “estrutural”

### Domínio e alvo

O script filtra GLC 2007–2017 e cria células de 1° em um quadrado de até duas células ao redor de cada célula com registro (`scripts/train_structural.py:7-21`). Esse domínio condicionado ao histórico exclui grande parte do planeta; não é amostra global uniforme.

Para cada célula e mês, o alvo vale 1 quando há pelo menos um registro naquele mesmo mês do calendário no intervalo futuro de dois anos (`scripts/train_structural.py:51-55`). Desenhos:

- treino: atributos 2007–2012 → rótulos 2013–2014;
- teste: atributos 2009–2014 → rótulos 2015–2016;
- final: concatena os dois conjuntos rotulados, ajusta novamente e prevê com atributos 2012–2017 (`scripts/train_structural.py:54-68`).

Logo, a saída final corresponde ao horizonte histórico após 2017, não a 2026–2028. O script não grava esse horizonte no JSON.

### Entradas

São 16 variáveis construídas apenas do catálogo e de coordenadas/calendário (`scripts/train_structural.py:22-50`):

- contagens na célula, no mesmo mês e em vizinhanças de 1 e 2 células;
- mortes na região, fração de registros atribuídos à chuva e anos ativos;
- latitude, latitude absoluta, seno/cosseno da longitude e do mês, interação hemisfério × mês.

Contagens são normalizadas por `1000 / total_de_eventos` do intervalo. Mortes recebem `log1p`; fração de chuva ausente vira -1 (`scripts/train_structural.py:36-49`). Não entram terreno, geologia, precipitação, uso do solo, obras ou exposição atual.

### Algoritmo e validação

`HistGradientBoostingClassifier` com 300 iterações, taxa 0,05, 24 folhas máximas, folha mínima 40, L2=1 e `random_state=7` (`scripts/train_structural.py:57-58`).

| Métrica armazenada | Modelo | Baseline |
|---|---:|---:|
| AUC no teste 2015–2016 | 0,893 | 0,858 |
| precisão média (AP) | 0,241 | 0,205 |
| positivos capturados nos 10% de maior score | 0,694 | 0,652 |
| prevalência no teste | 0,0138 | — |
| amostras de teste | 111.852 | — |
| células candidatas | 9.321 | — |

A baseline é uma combinação criada no script de histórico no mesmo mês, vizinhança e célula (`scripts/train_structural.py:59-63`). Não é um modelo físico.

Limitações:

- treino e teste compartilham geografia e janelas históricas sobrepostas; isso pode favorecer persistência de cobertura do catálogo;
- a variável mais importante é `eventos_celula` (queda AUC 0,0776), reforçando que o modelo aprende recorrência de registro;
- não há validação espacial fora de regiões conhecidas;
- não há calibração, incerteza ou avaliação após 2017;
- o domínio foi definido a partir do catálogo completo 2007–2017 antes dos cortes, o que incorpora conhecimento de onde houve registro no período futuro ao delimitar células candidatas (`scripts/train_structural.py:15-21`);
- a saída foi arredondada a milésimos e células sem máximo ≥0,001 foram removidas (`scripts/train_structural.py:70-74`).

### Transformação no navegador

Cada valor mensal inteiro é dividido por 1.000. A tela calcula uma saída de dois anos como:

`p2 = 1 - ∏(1 - p_m)`, para os 12 meses (`app.js:103-106`).

Isso supõe independência entre meses, hipótese não testada. A interface apresenta o valor multiplicado por 100 como score, sem símbolo de probabilidade. Após a auditoria, `nearestCell` passou a aceitar somente a célula que contém o ponto; ausência de cobertura retorna `null`, mostra “Fora da área do modelo” e não exibe score (`app.js:111-115`, `367-386`). Antes dessa correção, o código escolhia silenciosamente o maior `p2` entre oito células vizinhas.

As classes Baixo/Moderado/Alto/Muito alto são percentis 60/85/95 de `p2` entre as células publicadas (`app.js:105-110`), não os quantis mensais `q` gravados pelo treino. São classes relativas, não risco absoluto.

## Versões e promoção

Não há número de versão dos modelos. `data/models.json` não registra data, commit, ambiente, fontes ou assinatura. O único commit visível é `d7332cf` de 14/11/2026, mas isso não prova quando ou com quais entradas os modelos foram treinados.

O fluxo atual exige execução manual e substituição direta do JSON. Não existe substituição automática em produção, o que evita promoção acidental, mas também não há *staging* ou critério formal. O processo seguro proposto está em [operacao.md](operacao.md#treino-atualização-e-promoção-segura).

## Termos corrigidos na interface

| Termo anterior | Termo atual/seguro até nova validação |
|---|---|
| Gatilho agora | Índice meteorológico recente |
| `/100` ou `%` na saída dos modelos | pontos de score 0–100 |
| Risco estrutural | Recorrência histórica de registros |
| Chance de ≥1 deslizamento em 2 anos | Saída combinada do modelo histórico |
| Fora da área do modelo → `<1%` (comportamento anterior, corrigido) | Sem cobertura do modelo; risco físico não estimado |
| “risco baixo” | score relativo baixo dentro do domínio e período do modelo |

Qualquer uso de “probabilidade”, “perigo”, “risco atual” ou “alerta” exige calibração, validação prospectiva, definição do domínio e avaliação com especialistas/órgãos responsáveis.

## Modelos v2 — publicados em 15/11/2026

Os dois candidatos foram promovidos para `data/models.json` (sha256 `ca11d36f…af9e`) por `scripts/promote_models_v2.py`, por decisão da responsável (DD-036). A versão anterior está em `data/releases/backups/models-ef64dcb5d42a159b.json`; para voltar atrás, basta copiá-la sobre `data/models.json`, e o site volta a ler o formato v1. As evidências copiadas ficam em `data/releases/2026-11-15-v2/`, que o `server.py` não serve. Ambos produzem **score não calibrado**, e o Brier é informado apenas como diagnóstico. Não devem ser apresentados como probabilidade, risco ou alerta.

### Estrutural — `data/runs/structural/2026-11-15-v4/`

- Domínio: grade 1:50m independente dos eventos, 18.378 células, sem Antártica; 12.925 de 12.928 registros de 2007–2025 usados.
- Alvo: ao menos um registro na célula de 1° × mês, num horizonte de dois anos.
- Hiperparâmetros escolhidos só nas validações: `max_leaf_nodes=12`, `min_samples_leaf=80`, `l2=1.0`.

| Teste reservado | Exemplos | Positivos | AUC (baseline) | AP (baseline) |
|---|---:|---:|---|---|
| temporal (rótulos 2017–2018) | 179.340 | 1.140 | 0,9546 (0,9235) | 0,2218 (0,1698) |
| espacial (blocos reservados) | 17.052 | 152 | 0,9662 (0,9463) | 0,3773 (0,3204) |

Status: `accepted_for_manual_promotion`. O refit de produção usou 1.543.752 exemplos e 4.556 positivos. Artefato: `structural-v2.json`, sha256 `dc9aa9cf…56e9`. Pendência: `manifest.json`/`report.json` ainda gravam caminhos absolutos.

### Meteorológico — `data/runs/weather/2026-11-15-v2/training/`

- Dados: 9.177 pares válidos (MERRA2, LST); variáveis até D−1; percentis com referência fixa 2001–2006; 4 controles por caso, fora de ±10 dias de qualquer registro e nunca depois de 18/05/2025.
- Hiperparâmetros escolhidos só nas validações (AUC média 0,7964): `max_leaf_nodes=12`, `min_samples_leaf=50`, `l2=1.0`.

| Teste reservado (2020–2025) | Casos | Controles | AUC (baseline chuva 7d) | AP (baseline) | ΔAUC IC95% (bootstrap por célula) |
|---|---:|---:|---|---|---|
| temporal | 60 | 239 | 0,8017 (0,7416) | 0,5608 (0,4628) | +0,024 a +0,098 |
| espacial | 13 | 52 | 0,7929 (0,7574) | 0,5955 (0,5178) | −0,077 a +0,151 |

Status: `accepted_for_manual_promotion`, porque o gate exige apenas AUC e AP ≥ baseline. **Leitura correta:** o ganho temporal é robusto, mas o ganho espacial **não é distinguível de zero**. Os testes são pequenos porque o catálogo tem poucos registros datados a partir de 2019 (232 registros; 182 viraram candidatos). O refit de produção usou 45.369 exemplos, 9.177 casos e 2.744 células, com paridade Python/JSON 0,0. Artefato: `weather-v2.json`, sha256 `3a20d4d1…9fb7`. A variável mais importante por permutação foi `percentile_rain_1d`. O bootstrap está em `training/bootstrap-final-tests.json`.

Uma primeira execução, guardada em `training.pre-repair/`, perdeu 124 casos por status de célula defasado. Ela foi descartada após o reparo descrito em [preparacao-dados.md](preparacao-dados.md#execução-completa-2026-11-15-v2-catálogo-integrado-20072025).

Transformações aprendidas futuras só podem usar `selection_train` do respectivo corte. `final_temporal_test` e `final_spatial_test` não podem orientar hiperparâmetros, seleção de atributos, limiares ou explicações. DD-027 permanece separada: o novo ledger não explica retrospectivamente as perdas do treino antigo.

Detalhes e totais: [preparacao-dados.md](preparacao-dados.md).
