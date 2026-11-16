# Fluxo

## Diagrama

```
 planilha.csv / .xlsx
      |
      v
 [importar] --> [validar] --> [deduplicar] --> [emitir no gateway] --> SQLite
                                                       |
                                                       v
                                         [redigir e-mail] --> rascunho (.eml + banco)
                                                       |
                                         (você revisa e aprova)
                                                       v
                                            [enviar por SMTP] --> relatório do lote
```


## Estados da cobrança

| Estado | Significado | Vai para | Comando que dispara |
|---|---|---|---|
| validada | Passou nas regras de validação e está no banco. | emitida, erro | `importar` |
| emitida | O boleto existe no gateway. Link e linha digitável guardados. | rascunho, erro | `emitir` |
| rascunho | E-mail preparado, aguardando revisão. | aprovada, erro | `rascunhos` |
| aprovada | Liberada para envio. | enviada | `aprovar` |
| enviada | O e-mail saiu. Estado final. | nenhum | `enviar` |
| erro | Falhou em alguma etapa. O campo `etapa_falha` diz qual. | validada | qualquer etapa; `reprocessar` leva de volta a validada |

Linhas rejeitadas na validação não viram cobrança. Ficam na tabela `rejeicoes` e no relatório. Nenhuma transição volta para trás, exceto `erro` para `validada` pelo comando `reprocessar`. Toda mudança grava uma linha em `eventos` com data, cobrança, estado anterior, estado novo e detalhe.

## Comandos

**`importar ARQUIVO`** lê o CSV ou XLSX, normaliza os cabeçalhos e valida a planilha inteira antes de gravar qualquer coisa. Grava o lote (`lotes`), uma cobrança `validada` por linha aceita (`cobrancas`), as linhas recusadas com linha, coluna e motivo (`rejeicoes`) e os avisos de duplicidade em `eventos`. Com `--dry-run` só mostra o resultado. Se faltar coluna obrigatória, ou se o arquivo passar do limite de linhas, recusa tudo e sai com código 2.

**`emitir --lote N`** lê as cobranças `validadas` do lote e chama o gateway uma por vez, com pausa entre as requisições. Cria o cliente no gateway uma vez por documento e emite o boleto com a chave de idempotência como referência externa. Grava `id_cliente_gw`, `id_cobranca_gw`, `link_boleto` e `linha_digitavel`, e leva a cobrança para `emitida` ou `erro`. Antes de cada tentativa, a primeira inclusive, consulta o gateway pela referência e usa o boleto que ele devolver em vez de emitir outro. Se as tentativas acabarem em timeout ou erro 5xx, faz uma última consulta antes de marcar `erro`. Cinco falhas seguidas pausam o lote e o comando sai com código 3; `--retomar` continua de onde parou. Uma resposta 401 ou 403 interrompe tudo na hora com código 1.

**`rascunhos --lote N`** lê as cobranças `emitidas`, pede ao Claude a saudação e o parágrafo de contexto (se houver `ANTHROPIC_API_KEY` e `--sem-claude` não estiver ligado), passa o resultado pelo guard e monta o e-mail com o template. Grava um `.eml` por cobrança em `rascunhos/N/` e uma linha em `envios`, e leva a cobrança para `rascunho`. Se o Claude falhar, estourar o teto diário ou o guard reprovar o texto, usa o modelo fixo e registra `fallback_modelo`.

**`aprovar --lote N` ou `--cobranca ID`** leva `rascunho` para `aprovada` e grava `aprovado_em` em `envios`. É o único comando que faz essa transição.

**`enviar --lote N`** lê as cobranças `aprovadas`. Sem `--confirmar` só lista o que enviaria, com e-mails mascarados, e termina sem tocar em nada. Com `--confirmar` envia por SMTP, grava `enviado_em` e leva a cobrança para `enviada`. Se um envio falhar, a cobrança continua `aprovada`, o erro fica em `envios` e em `eventos`, e o comando sai com código 1; dá para repetir. `--reenviar` inclui as já enviadas e grava um evento `reenvio`.

**`relatorio --lote N`** só lê. Mostra a quantidade por estado, o valor total emitido, as rejeições e os erros, em Markdown ou CSV (`--formato`). Os outros comandos imprimem o mesmo resumo no final.

**`reprocessar --cobranca ID`** leva uma cobrança em `erro` de volta para `validada`. Se o boleto já existir no gateway, a consulta por referência que o `emitir` faz antes da primeira tentativa evita reemitir.

## Códigos de saída

| Código | Quando |
|---|---|
| 0 | Sucesso. |
| 1 | Erro de configuração, credencial recusada, banco ilegível ou falha de envio. |
| 2 | Entrada recusada (planilha inválida, lote inexistente, opção desconhecida). |
| 3 | Lote pausado por falhas seguidas. |
