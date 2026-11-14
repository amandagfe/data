# Data Detectives

Tendências e previsão de deslizamentos de terra com dados da NASA, para o desafio
**Earth System Trend Detective** (NASA Space Apps 2026).

## Rodar

O app é estático, mas precisa de um servidor local (os dados são carregados com `fetch`):

```bash
python3 -m http.server 8000
```

Abra http://localhost:8000. As APIs são chamadas direto do navegador, sem chave:

| API | Uso |
|---|---|
| NASA POWER (`power.larc.nasa.gov`) | chuva, umidade do solo e temperatura diárias (MERRA-2), 1981–hoje |
| Open-Meteo Geocoding | busca de lugares |
| Open-Meteo Elevation (Copernicus DEM 90 m) | altitude e declividade |
| OpenStreetMap Nominatim | nome do ponto clicado no globo |

O índice do El Niño (ONI, NOAA CPC) não pode ser lido direto pelo navegador, então fica em
`data/enso.json`. Para atualizar: `python scripts/fetch_enso.py data/enso.json`.

A NASA POWER limita pedidos em sequência rápida. O app faz uma chamada por vez e tenta de novo
automaticamente.

## O que é calculado no navegador

- **Gatilho agora**: modelo de disparo (gradient boosting) aplicado aos dados mais recentes da NASA POWER.
- **Tendências**: Rx5day, dias de disparo, chuva anual, umidade da zona de raiz e temperatura, 1981 até o
  último ano completo. Reta de mínimos quadrados com IC de 95%, inclinação de Sen e teste de Mann-Kendall.
- **Risco estrutural**: modelo treinado no Global Landslide Catalog, por célula de 1° e mês.
- **Declividade**: a partir de 5 pontos de altitude a ~280 m de distância.

## El Niño e La Niña

- Fases pela regra da NOAA: pelo menos 5 estações seguidas com ONI ≥ +0,5 °C (El Niño) ou ≤ −0,5 °C (La Niña).
- Para cada lugar: anomalia mensal de chuva e dias de disparo por fase (teste t de Welch contra neutro) e
  correlação ONI × chuva com defasagem de 0 a 6 meses (tamanho efetivo de amostra de Bretherton et al., 1999).
- No globo: eventos do catálogo por fase e região, normalizados pela média de cada ano.

## Modelos

### Modelo de disparo (`scripts/train_trigger.py`)
- Casos: 5.361 dias com deslizamento registrado (gatilhos meteorológicos) em 922 células da NASA POWER.
- Controles: 4 dias comuns por caso, no mesmo lugar, a mais de 10 dias de qualquer evento.
- 16 variáveis de chuva e umidade do solo, quase todas em percentil do clima local (2001–2017).
- Validação espacial (GroupKFold por lugar): AUC 0,858. Só o percentil da chuva de 7 dias: 0,827.
- Validação no tempo (treino até 2014, teste 2015–2017): AUC 0,836.
- As faixas Elevado, Alto e Muito alto são os percentis 90, 97 e 99 do índice em dias comuns.
- As árvores são exportadas para JSON e avaliadas em `app.js`, com diferença zero para o scikit-learn.

### Modelo estrutural (`scripts/train_structural.py`)
- Unidade: célula de 1° × mês. Alvo: pelo menos um registro nos 2 anos seguintes.
- Treino 2007–2012 → 2013–14. Teste 2009–2014 → 2015–16: AUC 0,89 (linha de base 0,86).

## Refazer os dados

```bash
python scripts/build_catalog.py Global_Landslide_Catalog_Export_rows.csv countries-110m.json data/catalog.json
python scripts/prepare_events.py Global_Landslide_Catalog_Export_rows.csv train_events.json
python scripts/fetch_power.py train_events.json power/          # lento: respeite o limite da API
python scripts/train_trigger.py train_events.json power/ trigger.json
python scripts/train_structural.py Global_Landslide_Catalog_Export_rows.csv structural.json
python scripts/build_models.py structural.json trigger.json data/models.json
```

Requer `numpy` e `scikit-learn` para o treino.

Fontes: CSV do catálogo em data.nasa.gov ("Global Landslide Catalog Export"); contornos em
`world-atlas@2.0.2/countries-110m.json`.

## Limites

- O catálogo depende de notícias, então tem viés de reporte (EUA: 2.992 eventos e 96 mortes; Índia: 1.265 e 7.069).
- O pixel do MERRA-2 tem ~50 km. O índice mede condições regionais, não prevê o ponto exato.
- Não é alerta oficial. Em risco real, siga a Defesa Civil.
