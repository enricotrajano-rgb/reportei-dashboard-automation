# Atualização do Dashboard Reportei pelo GitHub Actions

Agendamento local e remoto revisado em 09/09/2026.

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
30 3 * * *
```

Esse horário corresponde a 00:30 em São Paulo (03:30 UTC), seis horas antes do cron anterior. O workflow mantém um único disparo diário. O minuto 30 evita o início da hora, que o GitHub documenta como um período de carga elevada; isso não elimina nem limita os atrasos.

Em 05–08/09, as execuções já usavam o cron correto `30 9 * * *`, mas o GitHub só as criou entre 09:58 e 12:10 locais. Os processamentos terminaram poucos minutos depois. A antecipação é uma mitigação desse atraso anterior ao Python, ainda sujeita a validação real. Veja [evidências e critérios de validação](docs/SCHEDULING_2026-09-09.md).

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

1. Confirmar que `Exportação_Oficial.py` está presente e que o wrapper compatível, se necessário, aponta para ele; `export_reportei_csv.py` está aposentado e não deve ser restaurado como dependência.
2. Confirmar que o workflow remoto e o arquivo local são equivalentes.
3. Executar verificação offline e um teste CSV de um dia/rede/produto.
4. Testar escrita em uma planilha não produtiva.
5. Confirmar a expansão de `A:C` da Base para o período atual.
6. Retomar o cron e verificar todas as redes no primeiro run.

Para o runbook completo, consulte `docs/OPERATIONS.md`.

