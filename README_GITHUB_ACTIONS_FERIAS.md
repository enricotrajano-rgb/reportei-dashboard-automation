# Atualizacao do Dashboard Reportei pelo GitHub Actions

Este projeto pode rodar fora do PC local usando GitHub Actions.

## O que ele faz

- Roda `export_reportei_dashboard.py`.
- Atualiza a Google Sheet oficial na aba `Base`.
- Usa o modo `update_values`, ou seja, atualiza somente as metricas nas colunas `D:G`.
- Usa por padrao o periodo `current_month_until_yesterday`.
- Tambem fica disponivel como botao manual em `Actions`.

## Secrets obrigatorios

No GitHub, abra o repositorio e va em:

`Settings -> Secrets and variables -> Actions -> New repository secret`

Crie estes secrets:

```text
REPORTEI_TOKEN
GOOGLE_SERVICE_ACCOUNT_JSON
GOOGLE_SPREADSHEET_ID
```

`GOOGLE_SERVICE_ACCOUNT_JSON` deve ser o conteudo completo do arquivo JSON da service account.

`GOOGLE_SPREADSHEET_ID` e o ID da planilha, por exemplo:

```text
11hFk76IZe1AnCD3lsq6N95hclSZjIdgrkbmI0GWVCrI
```

## Rodar manualmente

No GitHub:

1. Abra o repositorio.
2. Clique em `Actions`.
3. Clique em `Atualizar Dashboard Reportei`.
4. Clique em `Run workflow`.
5. Deixe `period` como `current_month_until_yesterday`.
6. Clique no botao verde `Run workflow`.

Para rodar um intervalo especifico, preencha `start` e `end`.

## Rodar automaticamente

O workflow esta agendado para:

```text
06:30 America/Sao_Paulo
```

No arquivo do GitHub Actions isso aparece como:

```text
30 9 * * *
```

porque o GitHub usa UTC.

## Arquivo principal

```text
.github/workflows/reportei-dashboard.yml
```

## Observacoes

- Nao suba `.env` nem arquivos JSON de credenciais para o GitHub.
- Os logs e historicos locais ficam ignorados pelo `.gitignore`.
- Se a service account perder acesso a planilha, compartilhe a planilha novamente com o email da service account.
