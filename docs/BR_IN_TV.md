# BR IN TV na exportação oficial

Atualização de 22/09/2026, aplicada ao exportador local e ao GitHub.

O projeto `BR IN TV` (1331967) foi confirmado na Reportei com integrações ativas de Facebook (`BR IN TV`), Instagram (`brintvoficial`) e YouTube (`BRIN TV Oficial`). Ele entra junto dos demais produtos; a exclusão de `Agro Agenda` continua vigente.

O exportador consulta a lista de projetos na API a cada execução, mesmo quando o cache ainda está válido. Assim, o cache anterior de dez projetos não impede a descoberta do novo produto. A lista atualizada é salva no cache. Se a consulta falhar e houver cache disponível, o exportador emite aviso e usa esse fallback; nesse caso, um produto novo pode ficar ausente até a API se recuperar. Integrações e catálogos mantêm seus TTLs atuais.

Na aba `Base`, preparar as colunas A:C com produto `BR IN TV`, rede `Facebook`, `Instagram` ou `YouTube` e as datas desejadas. O modo `update_values` continua alterando somente D:G nas linhas existentes, sem criar linhas, reformatar datas ou apagar histórico. O workflow continua recalculando o mês corrente até ontem. O cadastro do produto não define uma data de corte nova: o período solicitado e as linhas existentes determinam o recorte.

O workflow GitHub e o agendador Windows já chamam `Exportação_Oficial.py` e incluem essas três redes; não precisam de outra lista de produtos. Filtros explícitos por `--project-names` continuam sendo respeitados. Em execução manual local, informar o período desejado, por exemplo `--period current_month_until_yesterday`, pois as datas padrão pessoais foram preservadas.

Validação offline: compilação dos scripts, CLIs com `--help`, `pip check` e `python -m unittest discover -s tests -p test_project_discovery.py`. Os testes simulam cache válido sem BR IN TV, falha da API com fallback e falha sem cache. Nenhuma carga ou escrita na planilha foi executada nesta mudança.
