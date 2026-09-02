# Atualização do Dashboard Reportei pelo GitHub Actions

Estado do arquivo local verificado em 25/08/2026.

## Atenção antes de executar

O workflow desta pasta chama diretamente `Exportação_Oficial.py`; `export_reportei_dashboard.py` permanece apenas como compatibilidade no GitHub.

Também há uma mudança importante em relação a versões anteriores deste documento: `RUN_TOP_POSTS` está atualmente como `false`, então Top Posts não roda no cron nem no disparo manual enquanto esse valor permanecer assim.

## Workflow

Arquivo:

```text
.github/workflows/reportei-dashboard.yml
```

Nome:

```text
Atualizar Dashboard Reportei
```

Agendamento:

```text
7 9 * * *
```

Isso corresponde a 06:07 no horário local (UTC-3). O minuto 07 foi escolhido para reduzir atrasos do GitHub em minutos de pico.

## Secrets obrigatórios

No repositório GitHub, em `Settings -> Secrets and variables -> Actions`, são esperados:

```text
REPORTEI_TOKEN
GOOGLE_SERVICE_ACCOUNT_JSON
GOOGLE_SPREADSHEET_ID
```

`GOOGLE_SERVICE_ACCOUNT_JSON` deve conter o JSON completo da service account. A planilha deve estar compartilhada com o `client_email` dessa conta como Editor.

## Configuração observada

- Python 3.11.
- Timeout do job: 120 minutos.
- Uma execução por vez, sem cancelamento da anterior.
- Cache persistente em `.reportei_cache`.
- Modo `update_values`.
- Aba principal `Base`.
- Redes: Facebook, Instagram, LinkedIn, TikTok e YouTube.
- Projeto excluído: `Agro Agenda`.
- Aba de Top Posts configurada como `Top Posts`, porém a etapa está desativada.

## Execução manual

O `workflow_dispatch` aceita:

- `period`: `current_month_until_yesterday`, `previous_month`, `last_7_days` ou `last_30_days`;
- `start` e `end`: intervalo fixo em `DD/MM/YYYY` ou `YYYY-MM-DD`.

Ao usar intervalo fixo, preencha as duas datas. Se qualquer uma estiver preenchida, o workflow passa ambas ao script; deixar a outra vazia deve causar erro de validação.

## Comportamento por rede

O workflow chama o exportador uma vez para cada rede. Uma falha não impede automaticamente as redes seguintes.

- Se pelo menos uma rede tiver sucesso, o step termina com sucesso e registra avisos para as demais.
- Se todas falharem, o step termina com erro.

Por isso, um workflow verde pode representar atualização parcial. Revise os avisos `Rede ... falhou` no log ou implemente notificação estruturada antes de depender apenas da cor da run.

## Top Posts

A etapa existe, mas só roda quando:

```text
RUN_TOP_POSTS=true
```

Antes de reativá-la, confirme:

1. que `Top_Posts.py` no repositório remoto é a versão esperada;
2. que o Looker usa o schema atual de dez colunas;
3. que a substituição do período foi testada em uma planilha não produtiva;
4. que a falha de uma etapa de Top Posts deve ou não tornar a run inteira vermelha.

## Artifacts

O workflow publica, quando existirem:

```text
reportei_dashboard_run_history.csv
reportei_dashboard_block_history.csv
```

O segundo CSV local possui linhas com uma coluna `erro` adicional que não aparece no cabeçalho original. Corrija/migre esse schema antes de usá-lo em análises automáticas.

## Recuperação da automação

1. Restaurar `export_reportei_dashboard.py` e `export_reportei_csv.py` do repositório canônico.
2. Confirmar que o workflow remoto e o arquivo local são equivalentes.
3. Executar verificação offline e um teste CSV de um dia/rede/produto.
4. Testar escrita em uma planilha não produtiva.
5. Confirmar a expansão de `A:C` da Base para o período atual.
6. Retomar o cron e verificar todas as redes no primeiro run.

Para o runbook completo, consulte `docs/OPERATIONS.md`.

