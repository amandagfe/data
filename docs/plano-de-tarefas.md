# Plano de tarefas

## Legenda

- **P0**: pode induzir decisão perigosa, expor segredo ou apresentar resultado fora do domínio.
- **P1**: compromete rastreabilidade, validade científica ou funcionamento confiável.
- **P2**: melhora manutenção, escala, acessibilidade ou experiência.
- Status: `concluído`, `em andamento`, `pendente`, `bloqueado`.

“Bloqueado” só é usado quando falta uma entrada externa indispensável. Itens que podem avançar por decisão técnica permanecem pendentes.

## Triagem das divergências

As linhas abaixo não formam um plano paralelo: cada uma referencia o item do backlog que controla sua correção. “Confirmado” significa que a implementação, o artefato ou uma execução reproduziu o comportamento; “suspeita” exige os dados indicados na coluna de dependências.

### 1. Corrigir antes da auditoria dos dados

| Divergência | Atual → esperado | Evidência | Impacto | Diagnóstico | Pri./dependências | Situação |
|---|---|---|---|---|---|---|
| Saídas chamadas de risco, chance e alerta | score e saída histórica pareciam probabilidade/decisão operacional → índices experimentais, período e limites visíveis | templates `index.html`, `i18n.js`; inferência `app.js`; ausência de calibração em `models.json` | interpretação perigosa e confusão entre suscetibilidade, perigo e risco | confirmado | P0; revisão PT/EN/ES | resolvida por DD-001/DD-002; Telegram removido por DD-003 |
| Ausência de célula virava valor baixo ou vizinho | ponto sem célula podia receber `<1%`/vizinha → “não estimado” e somente célula continente | `nearestCell` e painel estrutural em `app.js`; teste de chave direta | ausência de dados parecia baixa ocorrência | confirmado | P0; nenhuma | resolvida por DD-004 |
| Período do catálogo | catálogo antigo até 2017 → COOLR/GLC integrado com datas 1915–2025 no mapa; modelos continuam até 2017 | `data/catalog.json` v3: 14.753 IDs; 13.116 datas; `integrate_coolr_catalog.py` | evita apresentar mapa vencido sem fingir que o modelo foi atualizado | confirmado | P1; política por `event_id` | resolvida por DD-005/DD-031 |
| Auditoria dependia de consultas manuais | sem verificador → contratos e contagens executáveis | `scripts/audit_data.py`, `scripts/check_integrations.py` | resultados difíceis de repetir ou detectar regressão | confirmado | P1; rede apenas para integrações | implementada; falta CI em DD-013 |

### 2. Investigar durante a auditoria

| Divergência | Atual → esperado | Evidência | Impacto | Diagnóstico | Pri./dependências | Situação |
|---|---|---|---|---|---|---|
| Procedência do GLC | JSON sem manifesto → entrada, hash, licença, obtenção e transformação registrados | bruto imutável + manifesto; auditor reproduz 11.033/11.033 campos rastreáveis | a linhagem nova é reproduzível; a entrada histórica anterior não pode ser provada retroativamente | confirmado e corrigido para a nova linhagem | P1; política append-only | DD-006/DD-030 concluídos |
| Duplicatas após compactação | representações compactas indistinguíveis → preservar identidade sem deduplicar por coincidência | catálogo v3: 14.753 IDs únicos; integração usa apenas `event_id` | evita apagar coocorrências e dupla contagem dos 11.030 IDs comuns | confirmado e corrigido | P1; snapshots preservados | DD-028/DD-031 concluídos |
| Perda de rastreabilidade no modelo de disparo | 7.957 pares célula-data elegíveis antes de POWER viram 5.361 casos em 922 lugares → cada descarte explicado | `prepare_events.py`, CSV comparado e `models.json`; `power/`/`trigger.json` ausentes | não se mede viés de cobertura nem se reproduz o treino | confirmado; causas individuais não verificadas | P1; intermediários POWER originais | DD-027 bloqueado |
| Alinhamento temporal de evento e POWER | evento sem fuso + POWER em LST → regra conservadora D−1 documentada/testada | `weather_pipeline.py`; quatro testes; piloto registra LST e D−30…D−1 | evita usar D/futuro em candidatos novos, mas não reconstrói o treino antigo | limitação confirmada; regra nova verificada | P1; coleta completa | DD-029 concluído para pipeline novo; DD-027 preservado |
| Produto POWER atribuído ao período | toda a série era rotulada MERRA-2 → mostrar a fonte devolvida pela API | amostras 2001/2017 retornaram `MERRA2`; novembro/2026 retornou `GEOSIT` | procedência incorreta para dados recentes | confirmado | P1; cabeçalho da resposta POWER | resolvida na interface; verificador cobre amostra histórica/recente |
| Informação posterior no modelo estrutural | domínio usa todo 2007–2017 → grade independente e testes espacial/temporal intocados | código antigo; `build_land_grid.py` e `prepare_structural_v2.py` | desempenho antigo pode aproveitar conhecimento futuro; domínio novo (1:50m) omite 3 de 12.928 registros | confirmado; candidato v4 treinado sem vazamento de domínio | P1; promoção manual | DD-010/DD-033 concluídos; promoção pendente |
| Valores ausentes de fatalidade | vazio virava zero → ausente distinto de zero observado | catálogo v2 preserva 1.385 ausentes | cobertura de mortalidade agora é mensurável | confirmado e corrigido | P1; metadados de modelos em DD-008 | DD-030 concluído |
| Atualidade e data das camadas | GIBS sem `TIME` → `TIME`, data representada e fallback exibidos | `update_gibs_metadata.py`, `data/gibs.json`, `app.js`; GetMap 4/4 | acesso não é confundido com data do dado; snapshot precisa atualização offline | confirmado e corrigido | P1; job futuro | DD-012 concluído |
| Resolução/localização | pontos compactados pareciam precisos → precisão declarada preservada | catálogo v2 mantém `location_accuracy`, inclusive dois ausentes | análise ainda precisa considerar incerteza, mas o dado não a apaga | confirmado e corrigido no artefato | P1; exibição pode melhorar | DD-030 concluído |

### 3. Melhorias para etapas seguintes

| Divergência | Atual → esperado | Evidência | Impacto | Diagnóstico | Pri./dependências |
|---|---|---|---|---|---|
| Artefatos sem versão/ambiente | JSON final sem linhagem → manifesto, hashes, commit e ambiente | `data/*.json` | dificulta reprodução, promoção e rollback | confirmado | P1; DD-008/DD-015/DD-016 |
| Validade/calibração não medida | AUC e faixas relativas → calibração, incerteza e validação regional/temporal | métricas de `models.json` | score não pode ser interpretado como probabilidade | confirmado | P1; DD-009 e fontes reproduzíveis |
| Testes/observabilidade/cache | verificadores locais, sem CI/browser/SLA → contratos, smoke, cache e telemetria segura | repositório sem workflow/backend | regressões e falhas externas silenciosas | confirmado | P1/P2; DD-013/DD-014/DD-018/DD-020 |
| Publicação e privacidade | token ficava no cliente → envio por backend e credencial em ambiente; geolocalização só após clique | `server.py`, testes do backend, `geo-btn`; status público não contém token/`chat_id` | navegador não recebe segredo; token já compartilhado continua exposto até revogação; coordenadas vão a serviços externos | confirmado; backend concluído, incidente externo pendente | P0/P1; DD-017/DD-019/DD-022/DD-035 |

## Backlog priorizado

| ID | Pri. | Tarefa | Dependências | Critério de aceite | Status |
|---|---|---|---|---|---|
| DD-001 | P0 | Trocar “risco”, “chance” e “Gatilho agora” por termos compatíveis com as saídas | revisão PT/EN/ES e decisão de produto | interface e CSV distinguem score, registro, estimativa histórica e dado recente; não usam probabilidade sem calibração | concluído |
| DD-002 | P0 | Retirar a saída estrutural congelada do contexto atual ou exibir horizonte histórico explícito | decisão: atualizar/revalidar ou manter como demonstração histórica | nenhum valor de 2012–2017 é apresentado como risco atual/2026; data e domínio aparecem junto ao valor | concluído |
| DD-003 | P0 | Impedir envio Telegram inseguro em publicação pública | credenciais no ambiente do servidor | navegador não recebe token/`chat_id`; destino fixo, payload validado, rate limit e testes | concluído no código por `server.py`; credencial real não persistida; rotação do token exposto recomendada |
| DD-004 | P0 | Não mostrar `<1%`/baixo fora do modelo nem substituir pela maior célula vizinha | mudança em `nearestCell` e UI trilíngue | fora da cobertura mostra “não estimado”; só a célula que contém o ponto é usada; ausência de dados nunca vira baixo risco | concluído |
| DD-005 | P1 | Corrigir período/total do catálogo na interface | integração DD-031 | mapa/histórico dizem 1915–2025 e 14.753 IDs; modelos permanecem rotulados até 2017 | concluído |
| DD-006 | P1 | Reconciliar a origem do GLC local | manter snapshot append-only | manifesto inclui URL, licença, data, tamanho, hash, esquema e cobertura; artefato reproduzível | concluído para nova linhagem; entrada do artefato antigo segue não verificável |
| DD-007 | P1 | Atualizar tratamento ENSO para ONI histórico versus RONI oficial | requisito científico e fonte RONI | tela não chama ONI defasado de “agora”; data/estação aparecem; ONI é mantido para comparações históricas e RONI é identificado como monitor oficial desde 2026 | concluído |
| DD-008 | P1 | Versionar metadados dos artefatos/modelos | formato de manifesto | cada JSON registra versão, geração, commit, hashes de entrada, ambiente, período, domínio e horizonte | pendente |
| DD-009 | P1 | Avaliar calibração e utilidade dos modelos | fontes reproduzíveis; conjunto de avaliação | relatório inclui curva de calibração/Brier, IC, métricas por região/tempo e decisão explícita sobre uso de `%` | depende de DD-006/DD-008 |
| DD-010 | P1 | Corrigir vazamento espacial/temporal do modelo estrutural | decidir tratamento dos 51 registros fora da grade; depois executar candidato | domínio sem eventos futuros; validações espacial/temporal e testes intocados | concluído em 15/11/2026: candidato `structural/2026-11-15-v4` passou o gate nos dois testes reservados; não promovido |
| DD-011 | P1 | Validar e renomear declividade | amostras de referência ou decisão de limitar alegação | texto diz gradiente aproximado GLO-90; remove limiar universal de 15° ou cita/valida critério adequado | concluído pela limitação da alegação; validação local não alegada |
| DD-012 | P1 | Explicitar data real das camadas GIBS | atualizar `data/gibs.json` offline | requisição usa `TIME` válido e UI mostra data/fallback; camada estática é rotulada | concluído; snapshot de 15/11/2026 |
| DD-013 | P1 | Criar testes de contrato e cálculo | manifesto de ambiente | CI testa esquema JSON, contagens, datas, `analyze`, árvores Python×JS, `nearestCell` e traduções | em andamento: auditores de artefatos e integrações criados; CI/browser ainda pendentes |
| DD-014 | P1 | Criar smoke test de navegador | escolher Playwright/WebDriver e ambiente | carrega página, artefatos e Petrópolis com APIs mockadas; testa erro/retry e ausência de console error | pendente |
| DD-015 | P1 | Fixar dependências Python | identificar versão que gerou o modelo atual ou aceitar nova referência | arquivo de ambiente com versões e instrução limpa reproduz execução; mudança de métrica é revisada | pendente |
| DD-016 | P1 | Definir promoção manual e rollback de artefatos | DD-008, DD-013 | treino nunca sobrescreve produção; staging, comparação, aprovação e restauração anterior documentados/testados | pendente |
| DD-017 | P1 | Documentar/publicar política de privacidade e terceiros | decisão de publicação | usuário sabe que buscas/coordenadas vão a terceiros; atribuições/licenças e retenção local estão visíveis | pendente |
| DD-018 | P2 | Implementar cache persistente com expiração/versão | política de atualidade e privacidade | reduz chamadas repetidas sem servir dado obsoleto silenciosamente; usuário vê data da fonte | pendente |
| DD-019 | P2 | Rever Nominatim para escala | estimativa de tráfego/publicação | atende política de uso, cache, identificação e alternativa/proxy configurável | pendente |
| DD-020 | P2 | Adicionar observabilidade sem dados sensíveis | infraestrutura de publicação | erros por serviço/versão são mensuráveis, sem coordenadas precisas ou tokens; runbook define alertas | pendente |
| DD-021 | P2 | Revisar acessibilidade e responsividade | smoke test de navegador | teclado, leitores de tela, contraste, diálogos e fallback WebGL testados | em andamento: painel persistente de texto/contraste/espaçamento/movimento, alternativa textual das seis camadas, foco/Escape, estados ao vivo e responsividade verificados por contrato e Chrome headless; teste manual com NVDA/VoiceOver/TalkBack ainda pendente |
| DD-022 | P2 | Definir CI/CD e destino de publicação | acesso ao repositório remoto/hospedagem | deploy reproduzível, headers/CSP/SRI quando aplicável, ambiente de staging e rollback | bloqueado: destino não informado |
| DD-023 | P2 | Automatizar atualização em job offline, sem autopromoção | DD-008, DD-013, DD-016 | job gera candidato e relatório; publicação exige aprovação humana; falha preserva versão atual | pendente |
| DD-024 | P1 | Documentar implementação real nos seis arquivos solicitados | auditoria do código e artefatos | outra pessoa entende jornadas, arquitetura, fontes, modelos, operação, limites e backlog | concluído |
| DD-025 | P1 | Executar verificação técnica de base | ambiente local | JS/Python/JSON válidos e HTTP estático responde; resultados e limites registrados | concluído |
| DD-026 | P1 | Auditar bases, junções e integrações | acesso de leitura às fontes; sem retreino | `auditoria-dados.md` contém matriz, contagens, amostra rastreada, períodos e limites; verificadores reproduzem os resultados | concluído |
| DD-027 | P1 | Explicar a redução de 7.957 célula-datas elegíveis para 5.361 casos do modelo de disparo | diretório `power/` e intermediários do treino original | descartes por causa, região e ano somam exatamente a diferença e o viés é avaliado | bloqueado: intermediários originais ausentes |
| DD-028 | P1 | Resolver identidade/duplicidade sem apagar eventos distintos | catálogo v2 e auditor | contagens distinguem registros/coocorrências; nenhuma deduplicação por coordenada/data | concluído para o catálogo local |
| DD-029 | P1 | Definir e testar alinhamento de data/fuso entre GLC e POWER | regra conservadora enquanto não houver fuso confiável | LST e D−1 explícitos; fronteiras de mês/ano/bissexto testadas | concluído para execuções novas; histórico coberto por DD-027 |
| DD-030 | P1 | Preservar metadados do GLC no artefato/manifesto | snapshot bruto | `event_id`, precisão, nulidade, URL, data e hash sobrevivem | concluído no schema v2 |
| DD-031 | P1 | Decidir integração do COOLR atual sem dupla contagem | snapshots/manifestos preservados | COOLR substitui mesmo `event_id`; IDs exclusivos preservados; nenhuma união por proximidade; contagens reconciliadas | concluído: 14.753 = 11.030 comuns + 3.720 apenas COOLR + 3 apenas GLC |
| DD-032 | P1 | Concluir nova coleta POWER rastreável | executar 2.493 células restantes fora do site | 8.197 candidatos reconciliados em válidos/excluídos/falhos, com causas e hashes; zero pendente | concluído em 15/11/2026 com o catálogo integrado: 9.537 candidatos = 9.177 válidos + 360 excluídos, zero pendente/falho/célula defasada; candidato meteorológico treinado e não promovido |
| DD-033 | P1 | Fechar domínio estrutural independente | avaliar 51 registros fora da grade e baixa resolução do contorno | domínio explícito, cobertura medida e teste preservado antes de treino | concluído: grade 1:50m sem Antártica, 18.378 células, 3/12.928 registros fora e excluídos sem deslocamento |
| DD-036 | P1 | Decidir promoção dos candidatos v2 | DD-016; revisão dos relatórios | decisão registrada considerando que o ganho espacial do meteorológico não é distinguível de zero (13 casos) e que nenhum score é calibrado; rollback disponível | concluído em 15/11/2026: os dois promovidos por decisão da responsável via `promote_models_v2.py`; anterior em `data/releases/backups/models-ef64dcb5d42a159b.json`; evidências em `data/releases/2026-11-15-v2/` (não servidas); interface atualizada para 2025 e com aviso do teste espacial |
| DD-037 | P2 | Remover caminhos absolutos de manifesto/relatório estrutural | nova execução estrutural | `manifest.json` e `report.json` usam caminhos relativos à raiz | pendente |
| DD-034 | P1 | Separar leitura inicial e investigação sem duplicar resultados | semântica DD-001/DD-002 e estado único da análise | resumo mostra local, significado, fatores, período, atualização, limites e orientação oficial; área técnica usa o mesmo objeto `current.A` | concluído; validação visual automatizada pendente em DD-014 |
| DD-035 | P1 | Adicionar geolocalização com consentimento e retenção mínima | API do navegador e fallback por busca | permissão somente depois do clique; loading/negação/indisponibilidade/timeout tratados; coordenada arredondada não persiste sem ação explícita | concluído no cliente; política ampla de terceiros segue DD-017 |

## Sequência recomendada

1. **Contenção:** DD-001 a DD-005, principalmente Telegram e saídas apresentadas como atuais/probabilidades.
2. **Rastreabilidade:** DD-006 a DD-008 e DD-015.
3. **Validade:** DD-009 a DD-012.
4. **Confiabilidade de entrega:** DD-013, DD-014, DD-016 e DD-017.
5. **Operação sustentável:** DD-018 a DD-023.

## Registro das etapas desta auditoria

### Etapa 1 — inventário e estado do repositório

- **Analisado:** arquivos versionados/não versionados, Git e documentação existente.
- **Evidência:** `rg --files --hidden`, `git status --short`, `git log`, `git remote -v`.
- **Problemas/impacto:** mudanças locais prévias; apenas um commit; sem remoto/configuração de deploy; nenhum `docs/` anterior.
- **Verificação:** 17 arquivos de produto/script identificados antes desta documentação.
- **Pendência/próxima ação:** DD-022; preservar alterações locais.

### Etapa 2 — interface, arquitetura e jornadas

- **Analisado:** `index.html`, `app.js`, `i18n.js`, `style.css` e integração Telegram local.
- **Evidência:** funções e linhas citadas em [arquitetura.md](arquitetura.md).
- **Problemas/impacto:** sem backend; dependência de serviços externos; token no cliente; rótulos de risco/probabilidade eram inadequados e foram corrigidos na etapa 7.
- **Verificação:** fluxo da pesquisa até renderização e CSV reconstruído por inspeção.
- **Pendência/próxima ação:** DD-003 e DD-014; DD-001/DD-002/DD-004 concluídos.

### Etapa 3 — fontes, artefatos e linhagem

- **Analisado:** três JSONs, scripts de coleta/construção e documentação oficial.
- **Evidência:** contagens/checksums em [fontes-de-dados.md](fontes-de-dados.md); links oficiais no mesmo arquivo.
- **Problemas/impacto:** o catálogo não tinha manifesto e o período era inconsistente; ONI era tratado como atual. A exportação disponível foi reconciliada na etapa 7, mas o hash da entrada original segue ausente.
- **Verificação:** `jq`, `sha256sum` e leitura JSON.
- **Pendência/próxima ação:** DD-006/DD-008; DD-005/DD-007 concluídos.

### Etapa 4 — modelos e consistência científica

- **Analisado:** amostragem, atributos, alvos, cortes, métricas, exportação e inferência.
- **Evidência:** [modelos.md](modelos.md) com referências a `scripts/train_*.py`, `app.js` e `models.json`.
- **Problemas/impacto:** score não calibrado; previsão estrutural histórica; domínio condicionado; vazamento de domínio confirmado na etapa 7; uso incorreto de “risco” já corrigido na interface.
- **Verificação:** métricas conferidas no artefato e algoritmos comparados por inspeção; retreino não executado.
- **Pendência/próxima ação:** DD-009 e DD-010; DD-001/DD-002 concluídos.

### Etapa 5 — execução e verificações

- **Analisado:** execução local, sintaxe, JSON e serviço estático.
- **Evidência:** tabela de comandos em [operacao.md](operacao.md#verificações-executadas-em-15112026).
- **Problemas/impacto:** sem testes automatizados, ambiente fixado ou browser test.
- **Verificação:** checagens estáticas e HTTP passaram; limites explicitados.
- **Pendência/próxima ação:** DD-013 a DD-016.

### Etapa 6 — documentação

- **Alterado:** criação de `docs/visao-geral.md`, `arquitetura.md`, `fontes-de-dados.md`, `modelos.md`, `operacao.md` e este plano.
- **Evidência:** arquivos no repositório e links cruzados.
- **Problemas/impacto:** naquele ponto a interface ainda continha alegações inadequadas; elas foram corrigidas incrementalmente na etapa 7.
- **Verificação:** `git diff --check` passou; estrutura e referências Markdown foram inventariadas com `rg`.
- **Próxima ação:** manter os documentos sincronizados com a auditoria e as correções incrementais.

### Etapa 7 — triagem, auditoria das bases e contenção semântica

- **Analisado/alterado:** divergências classificadas nas três categorias solicitadas; CSV GLC atual, artefatos, chaves de junção, duplicidade, precisão, temporalidade, integrações e amostra de Petrópolis. Interface PT/EN/ES passou a usar score/recorrência histórica e resumo experimental, sem percentual/probabilidade ou alerta operacional.
- **Evidência:** [auditoria-dados.md](auditoria-dados.md), `scripts/audit_data.py`, `scripts/check_integrations.py`, `app.js`, `i18n.js` e `index.html`.
- **Problemas/impacto:** perda de ID/precisão no catálogo; 2.596 célula-datas não reconciliáveis no treino meteorológico; vazamento de domínio estrutural; fuso evento×POWER não validado; GIBS sem data explícita; token Telegram no cliente.
- **Verificação:** auditor de artefatos passou; CSV oficial atual reproduziu 11.033/11.033 registros; integrações passaram no teste de leitura; nenhum modelo foi retreinado ou promovido.
- **Pendência/próxima ação naquele momento:** DD-027 dependia dos intermediários; DD-012/DD-028/DD-029/DD-030 foram tratadas na etapa 8 e DD-010 continua em andamento.

### Etapa 8 — segurança, linhagem e preparação pré-treino

- **Analisado/alterado:** remoção do Telegram; bruto/manifesto GLC e catálogo v2; serviços COOLR atuais; ledger POWER; alinhamento D−1; grade/cortes estruturais; datas GIBS.
- **Evidência:** [preparacao-dados.md](preparacao-dados.md), `scripts/weather_pipeline.py`, `scripts/prepare_structural_v2.py`, `data/gibs.json` e manifestos em `data/sources/`.
- **Problemas/impacto:** DD-027 segue bloqueada; COOLR não pode ser unido sem política de sobreposição; 7.953 pares POWER estão pendentes; 51 registros estruturais ficam fora do domínio independente.
- **Verificação:** catálogo 11.033/11.033 reproduzido; COOLR Reports Points 14.750 preservado; piloto POWER reconciliado; quatro testes temporais passaram; GIBS 4/4 respondeu com `TIME`/estado estático; nenhum modelo foi treinado ou promovido.
- **Pendência/próxima ação:** DD-031 a DD-033. Nenhum dos dois modelos está pronto para iniciar treino nesta data.

### Etapa 9 — interface para leitura e aprofundamento

- **Analisado/alterado:** jornada de busca, seleção, estado `current`, inferência, traduções, logo, responsividade e acessibilidade. A abertura agora mostra uma leitura regional curta; “Explorar dados e metodologia” revela a investigação existente sem nova consulta nem cópia do resultado. Um guia explica score/faixas, NASA POWER, recorrência, AUC, tendência e incerteza em linguagem simples.
- **Evidência:** `index.html` (`resumo-local`, `metric-guide` e `advanced-content`), `app.js` (`renderSimpleResult`, `applyVizAccessibility`, `setAdvanced` e evento de `geo-btn`), `i18n.js`, `style.css` e `assets/logo-white.png`.
- **Problemas/impacto:** o score podia ser confundido com risco/probabilidade e a precisão do dispositivo com resolução do dado. A interface agora nega essas interpretações junto ao resultado, mostra a grade POWER e distingue calculado, insuficiente, desatualizado (>7 dias), fora da cobertura estrutural e falha.
- **Verificação:** `node --check app.js`, `node --check i18n.js`, oito testes Python, estrutura HTML sem IDs duplicados e `git diff --check` passaram em 15/11/2026. Teste automatizado de navegador continua pendente em DD-014.
- **Pendência/próxima ação:** validar contraste, fluxo de permissão e leitores de tela em navegadores/dispositivos reais (DD-014/DD-021); publicar política completa de terceiros (DD-017).

### Etapa 10 — Telegram por backend e aplicação do COOLR

- **Analisado/alterado:** `server.py` reintroduz o envio sem segredo no navegador; `integrate_coolr_catalog.py` aplica Reports Points ao mapa/histórico com política por `event_id`; interface separa catálogo atualizado de modelos congelados até 2017.
- **Evidência:** `data/catalog.json` schema v3, `data/coolr-status.json`, oito hashes do manifesto COOLR, `server.py`, `tests/test_telegram_backend.py`, `app.js` e tabela de fontes.
- **Problemas/impacto:** token compartilhado fora do secret manager continua exposto e não foi persistido; licença/versão COOLR permanecem não verificadas; 1.637 registros não têm data e 27 não têm coordenada; modelos não foram retreinados.
- **Verificação:** integração reconciliou 14.753 IDs únicos (11.030 substituídos + 3.720 adicionados + 3 preservados); auditor estrito, `node --check`, `py_compile` e 24 testes passaram em 15/11/2026. O configurador Telegram testa filtro de grupos e permissão `0600`.
- **Pendência/próxima ação:** configurar token/destino diretamente no ambiente, preferencialmente após `/revoke`; executar smoke de navegador; manter DD-009/DD-010/DD-027/DD-032/DD-033 antes de qualquer novo treino.

### Etapa 11 — acessibilidade visual e explicação das camadas

- **Analisado/alterado:** dependência do globo em cor, movimento e ponteiro; navegação por teclado; descrições de fonte, período e limite. Foi criado um painel com texto maior, alto contraste, espaçamento e redução de movimento, salvo apenas em `localStorage`. A redução de movimento também interrompe rotação e anéis WebGL.
- **Evidência:** `index.html` (`a11y-panel`, `layer-guide` e `active-layer-summary`), `style.css` (classes `a11y-*`), `app.js` (`updateA11yUi`, `renderLayerGuide`, `gibsTimeNote`) e traduções PT/EN/ES em `i18n.js`.
- **Problemas/impacto:** antes, leitor de tela recebia apenas um rótulo genérico do globo, as datas GIBS não faziam parte da alternativa textual e a pessoa não podia ampliar/contrastar a interface pelo próprio site. Agora cada camada distingue registro, estimativa, modelo, camada estática ou imagem, e nega interpretações indevidas junto da descrição.
- **Verificação:** 26 testes passaram; `node --check` passou; Chrome headless confirmou abertura/fechamento por `Escape`, preferências aplicadas, troca para IMERG, fallback `TIME=2026-11-13` anunciado e layout inicial em 1440 px e 390 px. O atalho fora de foco foi mantido fora da tela.
- **Pendência/próxima ação:** teste manual com NVDA, VoiceOver e TalkBack, zoom de 200% em navegadores reais e comportamento quando WebGL está indisponível (DD-021/DD-014). Não se alega certificação WCAG.

### Etapa 12 — coleta POWER completa, domínio estrutural e candidatos v2

- **Analisado/alterado:**
  - Execução POWER `2026-11-15-v2` sobre o catálogo integrado.
  - Grade estrutural 1:50m sem Antártica.
  - Treino dos candidatos estrutural (`v4`) e meteorológico (`v2`).
  - Trava de coletor único, status de célula derivado de todos os candidatos, detecção de célula defasada em `reconcile` e comando `repair-cells` em `weather_pipeline.py`.
- **Evidência:** [preparacao-dados.md](preparacao-dados.md), [modelos.md](modelos.md#modelos-v2--publicados-em-15112026), `reconciliation.json`, `report.json` e `bootstrap-final-tests.json` nas pastas de execução.
- **Problemas/impacto:**
  - Dois coletores concorrentes, um deles sem DNS, deixaram 36 células com status defasado; o treino perdeu 124 casos em silêncio até a correção.
  - Os testes finais meteorológicos são pequenos (60/13 casos), e o ganho espacial não é distinguível de zero.
  - O manifesto estrutural ainda grava caminhos absolutos.
- **Verificação:**
  - Reconciliação: 14.753 decisões, perda silenciosa 0, nenhuma célula defasada; 36/36 reparos verificados por hash.
  - 34 testes passaram em 15/11/2026.
  - Paridade de exportação meteorológica 0,0.
  - `data/models.json` não foi alterado.
- **Pendência/próxima ação:** DD-036 (decisão de promoção), DD-016, DD-037 e DD-009 (calibração).

## Regra de atualização

Ao concluir uma tarefa, registrar no próprio item o status e acrescentar evidência objetiva: commit/arquivo, comando de teste, saída resumida e data. Métrica nova só entra na documentação depois de existir em artefato ou relatório reproduzível.
