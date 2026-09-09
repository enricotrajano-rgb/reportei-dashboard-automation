# Diagnóstico do atraso do GitHub Actions — 09/09/2026

## Evidência remota

Repositório: `enricotrajano-rgb/reportei-dashboard-automation`, branch padrão `main`. Na consulta de 09/09, havia somente um arquivo em `.github/workflows`: `reportei-dashboard.yml`. As runs 75–78 usaram o commit `a13a25cd342e84f17768f0f33e20f302aa08ea96`, contendo um único cron `30 9 * * *` (06:30 em São Paulo), sem os três fallbacks anteriores.

Todos os horários abaixo são de São Paulo (UTC−3). A API do GitHub registra `created_at` e `run_started_at` iguais nesses exemplos.

| Data | Run | Cron previsto | Run criada | Final da run (`updated_at`) | Atraso até criar |
|---|---|---|---|---|---|
| 05/09/2026 | [75](https://github.com/enricotrajano-rgb/reportei-dashboard-automation/actions/runs/33967546405) | 06:30 | 09:58:25 | 10:04:08 | 3h28m25s |
| 06/09/2026 | [76](https://github.com/enricotrajano-rgb/reportei-dashboard-automation/actions/runs/34034966832) | 06:30 | 10:04:08 | 10:10:58 | 3h34m08s |
| 07/09/2026 | [77](https://github.com/enricotrajano-rgb/reportei-dashboard-automation/actions/runs/34136881210) | 06:30 | 12:10:09 | 12:17:32 | 5h40m09s |
| 08/09/2026 | [78](https://github.com/enricotrajano-rgb/reportei-dashboard-automation/actions/runs/34234180961) | 06:30 | 10:47:44 | 10:56:15 | 4h17m44s |

Na run 77, o job começou às 12:10:13, o step `Atualizar dashboard` às 12:10:24 e terminou às 12:17:25. Portanto, o atraso de horas precedeu tanto o runner quanto a execução Python. Não foi causado por duração da coleta, instalação, espera dentro do script ou pela fila do grupo de concorrência depois da criação da run.

Na run 78, os logs mostram `current_month_until_yesterday: 01/09/2026 - 07/09/2026` nas cinco redes. Isso confirma o recorte solicitado ao exportador, não uma auditoria independente de completude dos dados da Reportei ou de cada célula na planilha.

O workflow do commit `fb0371483594cd6bc2d4712f50e714faa895b3d9`, usado em 21/08, também tinha `30 9 * * *`; a run 60 foi criada às 07:00:10 locais. Assim, a troca do nome Python não explica mecanicamente o atraso atual: esse código só começa depois que o GitHub cria a run.

O GitHub documenta atrasos e até descarte de eventos agendados sob carga em [Troubleshooting workflows](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows) e [Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). Os dados públicos da run não revelam por que este repositório passou a sofrer atrasos maiores; atribuir a causa interna exata exigiria investigação pelo GitHub. Não há evidência de uma configuração das 11h ou 12h no workflow.

## Mudança aplicada

- Substituir o único cron por `30 3 * * *`: 00:30 em São Paulo, seis horas antes do anterior.
- Manter o minuto 30, fora do início da hora mencionado pelo GitHub como período de carga elevada.
- Manter `Exportação_Oficial.py`, `America/Sao_Paulo`, `current_month_until_yesterday`, `update_values` e a agregação Instagram do Bom dia Mercado.
- Não introduzir fallback, novo cron, guard de duplicidade, reset de repositório ou alteração das colunas da Base.

Se o maior atraso recente (5h40) se repetisse, a run seria criada por volta de 06:10. Isso é uma projeção para dimensionar a margem, não uma previsão nem limite garantido. Uma coleta que começar logo após 00:30 também depende da disponibilidade dos dados de ontem na Reportei.

## Validação operacional pendente

A publicação não prova que a pontualidade voltou. Verificar as próximas manhãs, inclusive fins de semana:

1. Uma única execução agendada por data local, usando o commit com o novo cron.
2. Conclusão antes das 09:00 locais; observar também se volta à faixa desejada de 07:00–07:30.
3. Período do dia 1 até ontem local; no dia 1 do mês, mês anterior completo.
4. Step da carga executado, sem erros/avisos de rede e com linhas efetivamente atualizadas; verde isoladamente não basta.
5. Confirmar que os dados de ontem estão disponíveis, pois antecipar o processamento não antecipa a atualização da fonte Reportei.

Usar três dias consecutivos com término antes das 09:00 e recorte correto como evidência inicial, não como garantia permanente. Consultas de monitoramento são somente leitura e não devem disparar novamente o exportador.

Se a mitigação falhar, a alternativa é retirar o disparo diário do `schedule` do GitHub e acionar `workflow_dispatch` com um agendador externo. O projeto já contém uma função de dispatch em `github_actions_run_button.gs`, mas isso não comprova que haja um trigger externo instalado. A migração exige configurar e validar esse acionador e desativar o cron atual na mesma transição, para não produzir execuções duplicadas. Não instalar outro agendador silenciosamente.

