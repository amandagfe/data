# Visão geral do Data Detectives

## Estado desta documentação

Auditoria feita em 15/11/2026 sobre o commit `d7332cf` e alterações locais. Depois da contenção inicial, o Telegram foi reintroduzido por backend sem segredo no navegador, e o snapshot COOLR Reports Points foi aplicado ao catálogo exibido por política explícita de `event_id`.

Convenções usadas nestes documentos:

- **Verificado**: confirmado no código, em um artefato versionado, em uma execução registrada abaixo ou em documentação oficial ligada diretamente.
- **Inferência**: interpretação compatível com a implementação, mas não declarada em um requisito versionado.
- **Não verificado**: não há evidência suficiente no repositório ou a verificação depende de serviço externo/ambiente não disponível.

## O que é o produto

**Verificado.** Data Detectives é uma aplicação web estática, trilíngue (português, inglês e espanhol), que explora registros de deslizamentos, séries meteorológicas, ENSO, relevo e duas saídas de modelos de *gradient boosting*. O objetivo declarado é investigar tendências e condições associadas a deslizamentos no desafio “Earth System Trend Detective” (`README.md:1-4`, `index.html:35-40`, `i18n.js`).

**Inferência sobre o público.** A navegação, as explicações de fórmulas e os avisos indicam dois públicos principais:

1. público geral e estudantes que pesquisam um lugar e precisam de explicações sem jargão;
2. público técnico que compara lugares, exporta CSV e examina métricas e métodos.

Uma alteração anterior de Telegram sugeria equipes de Defesa Civil como terceiro público, mas não havia requisito, validação, autorização institucional ou canal operacional. A função foi removida; esse público pretendido continua **não verificado**.

## O que a pessoa consegue fazer

| Jornada | Implementação verificada | Resultado |
|---|---|---|
| Explorar o globo | Seleção de camadas e clique no globo (`app.js:183-232`, `app.js:648-657`) | catálogo, saída estrutural e imagens GIBS |
| Pesquisar um lugar | Open-Meteo Geocoding (`app.js:260-263`, `app.js:624-647`) | nome, coordenadas e início do estudo |
| Usar a localização do dispositivo | API de geolocalização chamada somente depois do clique; coordenada arredondada a 3 casas e nome obtido por Nominatim (`geo-btn` em `index.html`; callback em `app.js`) | mesma análise da busca, com precisão declarada e correção pela busca |
| Analisar um lugar | NASA POWER e Open-Meteo Elevation chamados pelo navegador (`app.js:243-258`, `app.js:278-348`) | índice meteorológico, séries, tendências, ENSO e declividade aproximada |
| Consultar histórico próximo | filtro geodésico do catálogo por raio de 50, 100, 250 ou 500 km (`app.js:352-389`) | registros, mortes registradas, gatilhos e sazonalidade |
| Comparar lugares | lugares salvos em `localStorage`; novas consultas POWER por lugar (`app.js:660-704`) | comparação de índices e tendências |
| Exportar | CSV montado no navegador (`app.js:612-621`) | séries mensais derivadas, ONI e metadados mínimos |
| Consultar métodos e limites | seções 4 a 7 de `index.html` | modelos, fórmulas, fontes e limitações |

## Duas camadas de apresentação

**Verificado.** `#resumo-local` apresenta primeiro local, score meteorológico, fatores, período, fonte, escala, cobertura estrutural e orientação oficial. `#advanced-content` preserva mapas, filtros, modelos, métricas, métodos, fontes, limitações, referências e CSV, sendo aberto pelos botões “Explorar dados e metodologia”.

As duas camadas usam o mesmo estado `current` e o mesmo resultado `current.A`: `selectPlace` inicia uma única execução de `study`; `renderSimpleResult` e `renderPlace` apresentam níveis diferentes de explicação desse objeto. Não existe modelo nem chamada de dados exclusiva da visão simplificada.

O estado inicial também distingue em texto, e não só por cor: resultado calculado, dados insuficientes, dados desatualizados (referência meteorológica com mais de sete dias), falha de consulta e ausência de cobertura do modelo histórico. Esta última não é convertida em faixa baixa.

## Explicações e acessibilidade

O guia “Como ler os números” explica, junto ao resultado, que o score de 0 a 100 é a saída do modelo convertida em pontos e não uma porcentagem de chance. Os limiares das faixas são lidos do artefato atual. Chuva acumulada, percentis, umidade do solo, recorrência histórica, AUC, inclinação por década, p-valor e intervalo de confiança recebem descrições em linguagem simples. O AUC estrutural é explicitamente marcado como validação em revisão, coerente com DD-010.

Recursos implementados no HTML/CSS/JS: atalhos para conteúdo e explicação do globo, `main` único, busca no padrão combobox, foco movido para o título ao abrir a investigação, estados `aria-live`/`aria-busy`, rótulos textuais para SVGs, controles nativos, ajuda por `details`, alvos mínimos de 44 px, foco visível e modo `forced-colors`. Um painel persistido somente no navegador oferece texto maior, alto contraste, espaçamento ampliado e redução de movimento; esta última interrompe também a rotação e os anéis do globo.

`#layer-guide` é a alternativa textual ao globo/WebGL. Para cada uma das seis camadas, informa tipo de dado, significado, fonte/período e limitação principal. O resumo ativo reutiliza `data/gibs.json` para anunciar o `TIME` solicitado, a data representada e eventual fallback; eventos e recorrência distinguem o catálogo integrado até 2025 do modelo congelado até 2017. A mesma camada pode ser selecionada pelos botões dessa lista, sem interação com o canvas.

**Ainda não verificado:** uso integral com NVDA, VoiceOver ou TalkBack, zoom de 200% em dispositivos reais e fallback quando WebGL está indisponível. Os contratos e uma sessão Chrome headless verificaram foco, `Escape`, estados pressionados, alternativa textual e larguras desktop/celular, mas não substituem esses testes. Eles permanecem em DD-021; a implementação não é apresentada como conformidade WCAG certificada.

## O que os resultados significam

Os termos abaixo não são intercambiáveis:

| Conceito | Significado operacional | O site calcula? |
|---|---|---|
| **Suscetibilidade** | propensão espacial relativamente estável, normalmente baseada em terreno, geologia, solo e cobertura | Não de forma validada. A declividade é apenas um indicador isolado; o modelo “estrutural” usa sobretudo histórico de registros. |
| **Perigo** | possibilidade de ocorrência em determinado lugar e intervalo, incluindo gatilho/intensidade | Há indicadores parciais: condições meteorológicas recentes e uma camada externa chamada *hazard*. Eles não formam uma estimativa de perigo local validada. |
| **Risco** | perigo combinado com exposição, vulnerabilidade e consequências | Não. O sistema não modela população, edificações, vulnerabilidade ou dano esperado. |
| **Registro observado** | evento catalogado por alguma fonte | Pontos e contagens do GLC; são registros de cobertura incompleta, não todos os deslizamentos. |
| **Estimativa derivada** | valor calculado de observações/reanálise | tendências, composições ENSO, declividade por diferenças finitas e índices anuais. |
| **Score do modelo** | saída discriminativa usada para ordenar/classificar | “Índice meteorológico recente”. Não há calibração que autorize lê-lo como probabilidade. |
| **Previsão histórica congelada** | saída de modelo produzida previamente para um horizonte passado | Artefato do modelo “estrutural”; as entradas finais usam 2012–2017 (`scripts/train_structural.py:66-72`). |

## Arquitetura em uma frase

O navegador carrega cinco JSONs, consulta APIs públicas, executa análises/inferência localmente e renderiza tudo em uma página. `server.py` serve os arquivos e intermedeia apenas o Telegram; scripts Python manuais constroem os artefatos antes da publicação.

Detalhes: [arquitetura.md](arquitetura.md), [fontes-de-dados.md](fontes-de-dados.md), [modelos.md](modelos.md) e [operacao.md](operacao.md).

## Divergências entre promessa e implementação

| Prioridade | Texto/expectativa | Evidência da implementação | Impacto |
|---|---|---|---|
| Crítica — corrigido nesta auditoria | “risco”, “Gatilho agora” e alerta/recomendação operacional | a interface trilíngue usa índice meteorológico, recorrência histórica e resumo experimental; scores aparecem em pontos | reduz interpretação indevida; calibração continua pendente e Telegram foi removido |
| Crítica — corrigido nesta auditoria | saída estrutural parecia atual | artefato final usa atributos de 2012–2017 e a tela agora explicita o horizonte histórico (`scripts/train_structural.py:66-75`, `i18n.js`) | não apresenta mais o valor como risco de 2026 |
| Alta — corrigido nesta auditoria | 11.033 eventos eram descritos como “2007–2017” | `data/catalog.json` contém 45 registros anteriores a 2007, desde 1988; resumo e histórico agora dizem “arquivo local, 1988–2017”, e treino permanece 2007–2017 | evita atribuir período incorreto ao total |
| Alta — corrigido nesta auditoria | ONI/ENSO era apresentado como “agora” | arquivo local foi baixado em 14/11/2026 e termina em ASO/2026; a interface agora diz “último ONI disponível”, nega tempo real e informa que RONI é o monitor oficial da NOAA desde 2026 | preserva ONI para análise histórica sem tratá-lo como condição atual |
| Alta — corrigido nesta auditoria | modelo estrutural “onde” (`index.html:225-229`) | o domínio continua limitado a células até 2° de qualquer célula com registro, mas `nearestCell` agora só aceita a célula que contém o ponto (`scripts/train_structural.py:15-21`, `app.js:111-115`) | fora da cobertura agora aparece sem percentual; a limitação do domínio permanece |
| Alta — corrigido para nova linhagem | catálogo atribuído ao export do portal NASA | bruto imutável, manifesto e catálogo v2 reproduzem 11.033/11.033 registros com IDs/nulidade/precisão | a nova transformação é reproduzível; a revisão usada no artefato antigo não é demonstrável retroativamente |
| Alta — corrigido no código | compartilhamento via Telegram expunha segredo no cliente | `server.py` usa token/`chat_id` do ambiente; cliente recebe só status e envia payload validado | credencial não está no navegador; token compartilhado fora do secret manager continua comprometido até substituição |
| Média — corrigido pela limitação da alegação | declividade era apresentada com precisão/limiar não validados | texto agora diz gradiente aproximado de cinco amostras e nega avaliação de suscetibilidade (`app.js:254-258`, `i18n.js`) | evita interpretar o indicador como diagnóstico geotécnico |
| Média — corrigido | camadas GIBS “último dia disponível” | `data/gibs.json` registra `TIME`, data representada e fallback; a interface exibe esses campos | data fica rastreável ao snapshot; conteúdo do pixel ainda não é validado |

As correções estão ordenadas em [plano-de-tarefas.md](plano-de-tarefas.md).

## Limites já tratados corretamente

- O site afirma que não substitui alertas oficiais (`index.html:309-322`, `index.html:395-399`).
- A seção de limitações reconhece viés de notícias e diferença de escala entre a grade NASA POWER e um deslizamento (`index.html:309-321`).
- A ausência de cobertura agora aparece sem percentual e recebe o aviso de que não implica ausência de deslizamentos nem risco baixo (`app.js:383-386`, `i18n.js:170`).
- O resultado inicial chama a saída de score/indicador meteorológico e explica junto ao valor que não é risco, probabilidade calibrada, alerta ou diagnóstico de um imóvel.
- A geolocalização informa a precisão do dispositivo separadamente da resolução POWER (~0,5° × 0,625°); uma coordenada precisa não aumenta a resolução regional.

Os rótulos enganosos foram corrigidos, Telegram passou ao backend e o COOLR foi aplicado ao mapa/histórico. Permanecem as limitações científicas dos modelos publicados até 2017 e a licença/versão COOLR não verificada. A coleta POWER e o domínio estrutural foram concluídos, e os modelos v2, com dados até 2025, foram publicados em 15/11/2026.

## Verificações desta etapa

- Inventário completo com `rg --files --hidden -g '!.git/**'`.
- Estado local com `git status --short`; havia mudanças prévias em `.gitignore`, `app.js`, `i18n.js`, `index.html`, `style.css` e `telegram.config.example.js`.
- Leitura do código, README, artefatos e scripts.
- Contagens e intervalos calculados com `jq`; detalhes em [fontes-de-dados.md](fontes-de-dados.md).
- Sintaxe e serviço HTTP verificados; detalhes em [operacao.md](operacao.md).

## Próxima ação recomendada

Formalizar o rollback (DD-016) e avaliar a calibração dos modelos v2 (DD-009). O Telegram funciona rodando apenas `server.py`, que serve o site e a ponte no mesmo processo. O token fica em `.env` (`0600`) e nunca chega ao navegador. Veja [preparacao-dados.md](preparacao-dados.md) e o plano P0/P1.
