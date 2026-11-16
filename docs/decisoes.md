# Decisões

Uma entrada por decisão, com o motivo e o que ficou de fora. As regras citadas (RN-nn) vêm da planta em `docs/planta-v0.1.pdf`. Os ajustes (A1, A2...) e as interpretações (I2, I5...) vêm da especificação e do plano em `docs/superpowers/`.

## Idempotência por chave e consulta por referência (RN-09 e RN-11)

Cada cobrança tem uma chave, `sha256(documento | competencia | valor_cent | vencimento)`, com índice único no banco. A mesma chave vai como referência externa no gateway. Antes de cada emissão o sistema consulta o gateway por essa referência e só emite se não achar nada (ver a entrada sobre a consulta antes da primeira emissão).

Motivo: o caso ruim é o gateway criar o boleto e a resposta se perder. Reexecutar sem a consulta cobraria o cliente duas vezes.
Descartado: guardar só o id devolvido pelo gateway, que não existe justamente quando a resposta se perde; e confiar na unicidade da referência no Asaas, que a documentação não promete (ver abaixo). Por isso a chave é um hash dos quatro campos e o código usa o primeiro resultado da busca.

## Guard sobre o texto do Claude, e a RN-33 (A1 e A1b)

Na planta, o guard reprovava o e-mail inteiro se achasse outro valor em reais ou outra URL. Só que `nome` e `descricao` vêm da planilha e entram pelo template, então uma descrição com "R$ 10,00" derrubaria o e-mail e o evento `fallback_modelo` culparia o Claude por um dado que não era dele.

Hoje o guard confere só o que o Claude escreveu (`saudacao` e `contexto`): nenhum valor em reais, nenhuma data, nenhuma URL. Como rede de segurança, confere também que o texto final traz o valor, o vencimento e o link. Para não perder a garantia da planta, a RN-33 rejeita na importação a linha cujo `nome` ou `descricao` tenha URL ou `R$`.
Descartado: deixar a regra da planta como estava e aceitar os falsos positivos; e limpar o campo da planilha em silêncio, que esconderia o problema de quem preparou o arquivo.

## Aviso de duplicidade por competência (A2)

A chave inclui valor e vencimento. Corrigir o valor de um cliente na mesma competência gera uma segunda cobrança, e nada avisa. Agora a importação cria a nova cobrança e lista um aviso com o id da existente, além do evento `aviso_competencia_repetida`.
Descartado: bloquear. Duas cobranças legítimas na mesma competência existem (parcela extra, serviço avulso).

## Aprovação humana e `--confirmar`

O envio exige duas coisas: a cobrança estar `aprovada` (só `aprovar` faz isso) e o comando levar `--confirmar`. Sem a flag, `enviar` só lista os destinatários mascarados.
Motivo: e-mail é ação externa e não tem volta. O padrão é não enviar.
Descartado: uma etapa só (aprovar já enviando) e confirmação interativa, que atrapalharia scripts e testes.

## Consulta ao provedor antes da primeira emissão (RN-11)

`_emitir_com_tentativas` consulta o gateway pela referência antes de todo POST, inclusive o primeiro, e faz uma última consulta antes de marcar `erro` quando as tentativas acabam em erro temporário. Se essa última consulta também falhar, vale o erro da emissão.

Motivo: a consulta só entre as tentativas deixava dois caminhos abertos. Um processo interrompido depois do POST e antes do commit deixava a cobrança em `validada` com o boleto já criado, e a reexecução emitia outro. O mesmo acontecia quando a última tentativa criava o boleto e dava timeout, e o operador rodava `reprocessar`. O Asaas não deduplica pela referência, então seriam dois boletos para o mesmo cliente.
Custo: um GET a mais por cobrança.
Descartado: gravar um marcador "tentativa iniciada" antes do POST e consultar só quando ele existir. O marcador não fecha a janela entre o POST e o commit, e ainda exigiria tratar o caso de o marcador ter sido gravado sem o POST ter saído.

## Guard mais restrito sobre o texto do Claude

O guard antigo só pegava `R$`, valores no formato `1.250,00`, URLs e datas numéricas. "1.500 reais", "10 de dezembro" e "pague pelo Pix" passavam. Agora `saudacao` e `contexto` são reprovados se tiverem qualquer dígito, `@`, ou uma destas palavras inteiras (sem diferenciar maiúsculas): reais, real, pix, transferência, transferir, transfere, depósito, ted, banco, bancário e bancária, e os doze meses. O texto fixo do template não passa por essa conferência. O prompt de sistema também pede ao Claude que evite esses itens.

Um falso positivo só custa o fallback para o modelo fixo, que é um e-mail correto, só menos personalizado. Ficaram de fora "conta" e "doc", comuns demais em frases normais.

## Tentativas em `lote.py`, não no gateway (I2)

As repetições (1 s, 3 s e 9 s para timeout, 5xx e 429) ficam em `lote.py`. A RN-11 pede a consulta por referência entre as tentativas, e quem sabe consultar é o orquestrador. Repetir também em `gateway/asaas.py` daria 3 x 3 tentativas.

## Claude: `claude-haiku-5-5`, sem temperatura, `thinking` desligado e `effort` baixo (I5)

O modelo padrão é `claude-haiku-5-5`, trocável por `CLAUDE_MODEL`. Ele rejeita temperatura diferente do padrão (erro 400), então a chamada não manda `temperature`; usa `thinking` desligado e `effort` baixo, com `max_tokens` 300. A variação de texto que sobra é coberta pelo guard e pelo modelo fixo.
Descartado: temperatura baixa como na planta, que a API recusa nesse modelo.

## `uv` e lockfile (A3)

Dependências gerenciadas por `uv`, `uv.lock` versionado, CI com `uv sync --locked`. O `pip-audit` roda sobre o lockfile exportado.
Motivo: o mesmo conjunto de versões no CI e na máquina, e uma auditoria que olha o que de fato foi instalado.

## Pausa do lote e `--retomar` (I3)

Com cinco falhas seguidas o lote pausa e o comando sai com código 3. Rodar `emitir` num lote pausado sem `--retomar` recusa, também com código 3.
Motivo: não insistir no provedor depois de uma sequência de falhas sem ninguém olhar.

## Código de saída 1 em falha de envio (I13)

A planta fixa o estado depois de uma falha de SMTP (a cobrança continua `aprovada`, RN-28), mas não o código. `enviar --confirmar` sai com 1 se qualquer e-mail falhar, para que um script perceba.

## Edição humana do `.eml` não passa pelo guard (I12)

Quem revisa o rascunho pode mudar o texto antes de aprovar. O guard não roda de novo sobre a edição: a revisão humana é a última etapa, e conferir de novo daria a impressão de que o texto editado está garantido.
Limite conhecido: se alguém trocar o valor ou o link no `.eml`, nada pega.

## Outras decisões pequenas

- Gateway fake sem estado (I8). `--gateway fake` é em memória e não guarda nada entre execuções. Serve à demo e aos testes.
- Nome local do SMTP resolvido uma vez por remetente. `socket.getfqdn()` levava cerca de 0,85 s por chamada no Windows, duas por e-mail. O fluxo completo pela CLI caiu de 35 s para 1,8 s, e um lote de 500 não perde mais uns 7 minutos. O nome é o mesmo durante o lote.
- `ruff` com linha de 120 colunas. O código do plano já usava linhas desse tamanho.
- `docs/` fora do `ruff`. O ruff 0.17 reformata blocos de código dentro de arquivos `.md`.
- Demo com `PYTHONIOENCODING=utf-8`. No Windows, a saída da CLI em pipe sai em cp1252 sem isso.

## Diferenças encontradas na documentação do Asaas

Conferidas em 15/11/2026, antes de escrever `gateway/asaas.py`. A base do sandbox é `https://api-sandbox.asaas.com/v3`, a autenticação é pelo cabeçalho `access_token` e o valor é decimal em reais. O que diferiu da hipótese da planta:

- `email` não é obrigatório em `POST /customers` (só `name` e `cpfCnpj`). Seguimos enviando.
- `GET /payments` devolve uma lista paginada (`data`, `hasMore`, `totalCount`) e `externalReference` não é documentado como único. O código usa o primeiro resultado.
- `description` aceita até 500 caracteres. A nossa já sai truncada em 100.
- Contas novas exigem `User-Agent`. Já enviamos.
- O 429 não vem com `Retry-After` e tem três causas: limite por endpoint, cota de 25.000 requisições por 12 horas e 50 GET simultâneos.
- `GET` com corpo responde 403. Não enviamos corpo em GET.
- A chave do sandbox começa com `$aact_hmlg_`.

Nenhuma dessas diferenças mudou o contrato usado pelo código.

## Auditorias e cobertura

Resultados da Tarefa 19, em 15/11/2026.

- `pip-audit` sobre o lockfile exportado: nenhuma vulnerabilidade conhecida.
- `gitleaks git`: 24 commits varridos, nenhum vazamento. `git grep` por chaves da Anthropic e por `access_token` literal: sem resultado. `.env`, `*.db`, `rascunhos/` e planilhas fora de `sample_data/` estão no `.gitignore`; `sample_data/clientes_exemplo.csv` entra no repositório.
- Cobertura (`pytest --cov=boletos`): 97% no total, 215 testes. Camadas que a planta pedia acima de 90%: `validation/` 99% a 100%, `gateway/fake.py` 100%, `mail/guard.py` 100%, `mail/composer.py` 99%, `lote.py` 98%, `store/db.py` 100%. Abaixo disso só o que depende de falhas raras: `gateway/asaas.py` 90%, `cli.py` 90%, `mail/sender.py` 92%.
- Rastreabilidade: `tests/unit/test_cobertura_rn.py` falha se alguma regra de RN-03 a RN-11 e RN-15 a RN-20 ficar sem teste `test_rnNN_`.
- Fora do CI: o teste do sandbox do Asaas (`-m sandbox`) e o do Claude real (`-m claude_real`) precisam de chave e ficam de fora. Sem chave, são pulados.
