# boletos-em-lote

[![ci](https://github.com/rafaelgoncalvesml/boletos-em-lote/actions/workflows/ci.yml/badge.svg)](https://github.com/rafaelgoncalvesml/boletos-em-lote/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.12+-blue)
![licença](https://img.shields.io/badge/licen%C3%A7a-MIT-green)

Emitir boleto um a um no painel do provedor toma tempo e abre espaço para erro de digitação e cobrança em duplicidade. Este projeto lê uma planilha de clientes, valida, emite os boletos no sandbox do Asaas, prepara o e-mail de cada cliente como rascunho e deixa o envio na mão de quem aprova.

> Todos os dados deste repositório são fictícios. Os e-mails de exemplo usam o domínio `.test` e o provedor de pagamento é o sandbox do Asaas. Não use com dados reais de clientes.

Saída real da demonstração (trecho):

```
$ boletos importar demo/clientes.csv
25 linhas lidas, 20 cobranças criadas, 4 rejeitadas.
  rejeitada: linha 22, coluna documento: dígitos verificadores do documento não conferem
  rejeitada: linha 23, coluna vencimento: vencimento precisa ser a partir de amanhã
  rejeitada: linha 24, coluna valor: valor com mais de duas casas decimais
  rejeitada: linha 25, coluna email: e-mail inválido
  aviso: linha 26 repete a linha 4 e foi ignorada

$ boletos emitir --lote 1
Cobranças por estado:
- emitida: 20
Valor total emitido: R$ 52.057,00

$ boletos aprovar --lote 1
20 cobranças aprovadas.
```

## Rodar a demonstração

A demonstração usa o gateway fake. Não precisa de conta no Asaas nem de chave do Claude, e nenhum e-mail é enviado.

```bash
uv sync
uv run python scripts/demo.py
cat demo/rascunhos/1/00001.eml
```

O script gera uma planilha de 25 linhas (20 válidas, 4 com erro de propósito e 1 repetida), importa, emite, gera os rascunhos, aprova e lista o que o envio faria.

## Como funciona

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

| Comando | O que faz | Opções |
|---|---|---|
| `boletos importar ARQUIVO` | Valida a planilha e grava um lote. Mostra as rejeições. | `--dry-run` |
| `boletos emitir --lote N` | Emite as cobranças validadas. | `--retomar`, `--gateway fake\|asaas` |
| `boletos rascunhos --lote N` | Gera os e-mails e salva os `.eml`. | `--sem-claude` |
| `boletos aprovar` | Libera rascunhos para envio. | `--lote N` ou `--cobranca ID` |
| `boletos enviar --lote N` | Envia as aprovadas. | `--confirmar`, `--reenviar` |
| `boletos relatorio --lote N` | Resumo do lote. | `--formato md\|csv` |
| `boletos reprocessar --cobranca ID` | Leva uma cobrança em erro de volta para validada. | |

Códigos de saída: 0 sucesso, 1 erro de configuração, credencial ou envio, 2 entrada recusada, 3 lote pausado por falhas seguidas.

Os estados da cobrança e o que cada comando lê e grava estão em [docs/fluxo.md](docs/fluxo.md).

## Decisões de design

**Idempotência.** Cada cobrança tem uma chave calculada a partir de documento, competência, valor e vencimento, com índice único no banco. A mesma chave vai como referência externa no provedor. Antes de cada emissão o sistema consulta o provedor pela referência, então reexecutar um lote, mesmo depois de uma interrupção ou de um timeout, não cria cobrança nova.

**Guard do e-mail.** O Claude escreve só a saudação e um parágrafo curto. Valor, vencimento, descrição e link entram por template. Um guard confere o que o Claude escreveu: se aparecer valor em reais, data, URL, número, e-mail ou palavra de pagamento (pix, banco, mês e parecidas), ou se o texto final perder o valor, o vencimento ou o link, o e-mail usa o modelo fixo. Se o Claude falhar ou o teto diário de chamadas acabar, o lote segue com o modelo fixo.

**Aprovação humana.** Nenhum e-mail sai sem `aprovar` e sem `--confirmar`. Sem a flag, `enviar` só lista os destinatários, com o e-mail mascarado.

As razões e o que foi descartado em cada uma estão em [docs/decisoes.md](docs/decisoes.md).

## Configuração

As variáveis vêm do ambiente ou de um arquivo `.env` na raiz, que o git ignora. O `.env.example` traz as chaves sem valor. Cada comando confere o que precisa antes de tocar no banco.

| Variável | Obrigatória | Padrão | Uso |
|---|---|---|---|
| `ASAAS_API_KEY` | para `--gateway asaas` | | Chave do sandbox |
| `ASAAS_BASE_URL` | não | sandbox do Asaas | Troca de ambiente |
| `ANTHROPIC_API_KEY` | não | | Sem ela, só o modelo fixo |
| `CLAUDE_MODEL` | não | `claude-haiku-5-5` | Modelo usado nos e-mails |
| `MAX_CLAUDE_CALLS_DIA` | não | 200 | Teto de chamadas ao Claude por dia |
| `SMTP_HOST`, `SMTP_PORT` | para `enviar --confirmar` | | Servidor de envio |
| `SMTP_USER`, `SMTP_PASS` | não | | Só valem juntos |
| `SMTP_FROM` | não | `cobranca@exemplo.test` | Remetente dos `.eml` |
| `VALOR_MAXIMO_CENT` | não | 5000000 | Valor máximo por cobrança, em centavos |
| `LINHAS_POR_LOTE` | não | 500 | Linhas aceitas por arquivo |
| `PAUSA_ENTRE_REQ_MS` | não | 300 | Pausa entre requisições ao provedor |
| `FALHAS_PARA_PAUSAR` | não | 5 | Falhas seguidas que pausam o lote |
| `BOLETOS_DB` | não | `boletos.db` | Caminho do banco |
| `BOLETOS_RASCUNHOS` | não | `rascunhos` | Pasta dos `.eml` |
| `BOLETOS_LOGS` | não | `logs` | Pasta dos logs |

## Testes

```bash
uv run pytest
```

Roda os testes unitários e de integração, que usam o gateway fake, um cliente do Claude simulado e um servidor SMTP de captura local. O CI roda só esses.

Dois testes ficam de fora do CI porque precisam de chave:

```bash
ASAAS_API_KEY=... uv run pytest -m sandbox
ANTHROPIC_API_KEY=... uv run pytest -m claude_real
```

O primeiro emite um boleto de teste no sandbox do Asaas e o busca pela referência. O segundo chama o Claude de verdade e confere se o texto passa no guard. Sem a chave, os dois são pulados.

## Limitações

A versão 1 não faz:

- webhook de confirmação de pagamento, segunda via, cancelamento e baixa;
- multa, juros, desconto e parcelamento;
- boleto híbrido com Pix;
- interface web e múltiplos usuários;
- uso com dados reais.

Também vale saber:

- O gateway fake não guarda estado entre execuções. Serve à demonstração e aos testes.
- A planilha de exemplo usa datas relativas ao dia em que foi gerada. Gere de novo com `uv run python scripts/gerar_exemplo.py` quando os vencimentos passarem.
- O texto editado à mão num `.eml` não passa pelo guard.
