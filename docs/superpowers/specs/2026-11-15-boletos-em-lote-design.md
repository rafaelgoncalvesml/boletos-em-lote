# boletos-em-lote: especificação de design

Data: 2026-11-15
Base: `docs/planta-v0.1.pdf` (planta de produção v0.1, de 10/11/2026)
Estado: aguardando revisão do dono do projeto. Nada implementado.

## 1. Propósito

CLI em Python que lê uma planilha de clientes (CSV ou XLSX), emite os boletos no sandbox do Asaas, prepara um e-mail por cliente com ajuda do Claude e só envia depois de aprovação explícita.

É um projeto de portfólio. Usa só dados fictícios e provedor em sandbox. O que ele precisa mostrar: integração com API de pagamento, idempotência, falha parcial, LLM com conferência determinística da saída, aprovação humana antes de ação externa e testes sobre fluxo financeiro.

Sucesso é cumprir os critérios de aceite da seção 12 da planta.

## 2. Como ler este documento

A planta é normativa para tudo que não aparece abaixo: regras RN-01 a RN-32, estados da cobrança, modelo de dados, contratos (planilha, gateway, Claude, modelo fixo), comandos da CLI, configuração, tratamento de erros, plano de testes, critérios de aceite e marcos.

Este documento registra só o que mudou e o que foi decidido na conversa de 2026-11-15. Se houver conflito, vale este.

## 3. Ajustes sobre a planta

### A1. Guard sobre o texto do Claude (altera RN-20)

Na planta, o guard confere o texto final inteiro e reprova se achar outro valor em reais ou outra URL. Só que `nome` e `descricao` vêm da planilha e entram pelo template. Uma descrição com "R$ 10,00" ou uma URL reprovaria o e-mail por causa do dado, e o evento `fallback_modelo` apontaria o Claude como culpado sem ser.

Novo comportamento:

- O guard confere o que o Claude escreveu (`saudacao` e `contexto`): nenhum valor em reais, nenhuma data (DD/MM, DD/MM/AAAA, AAAA-MM-DD) e nenhuma URL.
- Como rede de segurança, confere também que o texto final contém o valor formatado, o vencimento e o link. O template garante isso, a checagem pega regressão futura.
- Qualquer falha usa o modelo fixo e grava `fallback_modelo`, como na planta.

### A1b. Nova regra RN-33 (consequência de A1)

Sem a checagem de ausência no texto final, uma URL ou um valor colado em `nome` ou `descricao` chegaria ao cliente dentro de um e-mail de cobrança. Para manter a garantia da planta:

- RN-33: linha com `nome` ou `descricao` contendo URL (`http://`, `https://`, `www.`) ou o padrão `R$` é rejeitada na importação, com linha, coluna e motivo, igual a RN-08.

Esta regra não estava na planta e precisa da sua revisão.

### A2. Aviso de possível duplicidade por competência (complementa RN-09 e RN-10)

A chave de idempotência inclui valor e vencimento. Corrigir o valor de um cliente na mesma competência gera uma segunda cobrança, sem aviso.

- A regra de chave continua igual. Não bloqueia, porque duas cobranças legítimas na mesma competência são possíveis.
- Na importação, se já existir cobrança com o mesmo `documento` e `competencia` e chave diferente (no banco ou no mesmo arquivo), a nova é criada e o relatório lista um aviso com o ID da existente.
- Evento gravado: `aviso_competencia_repetida`.

### A3. Gestão de dependências com uv

- `pyproject.toml` gerenciado por `uv`, `uv.lock` versionado, `requires-python = ">=3.12"`.
- Dependências de execução: typer, pydantic, httpx, openpyxl, anthropic.
- Grupo de desenvolvimento: pytest, ruff, pip-audit, e um servidor SMTP de captura (ver seção 4).
- CI instala com `uv sync --locked`. O `pip-audit` roda sobre o lockfile exportado.
- O nome de cada pacote é conferido antes da primeira instalação (typosquatting).

### A4. Pasta e repositório

- O projeto vive em `boletos-em-lote/`, dentro de `Emissão de boleto/`, com `git init` na branch `main`.
- A planta em PDF fica em `docs/planta-v0.1.pdf`.
- O primeiro commit já traz o `.gitignore` com `.env`, `*.db`, `rascunhos/` e planilhas fora de `sample_data/`.
- Repositório remoto no GitHub só quando você pedir.

## 4. Decisões de implementação

Defaults que escolhi. Mudam sem custo agora e com custo depois do marco 1.

| Tema | Decisão |
|---|---|
| Modelo do Claude | `CLAUDE_MODEL` padrão `claude-haiku-5-5`. Temperatura baixa, `max_tokens` 300, como na planta. |
| Testabilidade do composer | O composer recebe o cliente do Claude por injeção. Testes e CI usam um cliente simulado. Um único teste marcado `claude_real` roda fora do CI. |
| SMTP de teste | Servidor de captura local com `aiosmtpd` como dependência de desenvolvimento. O Python 3.12 não traz mais `smtpd`. A escolha final é sua e só é necessária no marco 3. |
| API do Asaas | URL do sandbox e nomes de campos são conferidos na documentação oficial no começo do marco 2, antes de escrever `gateway/asaas.py`. Um teste de contrato cobre a diferença. |
| Marcador de testes | `unit`, `integration` e `sandbox`. O CI roda só os dois primeiros. |
| Estados e transições | Como na seção 4 da planta. `reprocessar` leva `erro` para `validada`, e RN-11 impede reemissão se o boleto já existe no gateway. |

## 5. Ordem de construção e dependências suas

Marcos da planta, sem mudança: 1 importação, validação e FakeGateway; 2 banco, idempotência e Asaas; 3 e-mail, guard, aprovação e envio; 4 acabamento.

Os marcos 1 e 3 rodam inteiros com `FakeGateway` e Claude simulado. O que depende de você:

| Quando | O que preciso |
|---|---|
| Marco 2 | Conta sandbox no Asaas e a `ASAAS_API_KEY`, só no `.env` local. |
| Marco 3, teste real | `ANTHROPIC_API_KEY` no `.env` local. |
| Marco 3 | Confirmar o SMTP de captura (seção 4). |
| Marco 4 | GIF da demonstração e criação do repositório remoto, se quiser publicar. |

## 6. Segurança e confiança

Blocos do baseline aplicados: A (segredos), B (entrada e prompt injection), D (custo do Claude), E (erros e logs), F (dependências) e J (verificação). Os detalhes de projeto estão na seção 10 da planta. Evidências planejadas para o fim de cada marco:

- `gitleaks` no repositório e no histórico, e conferência do `.gitignore`.
- `pip-audit` sobre o lockfile.
- Testes que provam: rejeição de entrada maliciosa (incluindo RN-33), guard reprovando texto alterado, `enviar` sem `--confirmar` não enviando nada, 401 do gateway parando o lote.
- Logs conferidos por teste para garantir máscara de CPF, CNPJ e e-mail e ausência de segredo.

Não se aplicam: login, banco exposto, página pública, cookies, política de privacidade e termos. O projeto é local e usa só dados fictícios. Isso aparece no README, como a planta pede.

## 7. Fora do escopo

O mesmo da seção 1.2 da planta: webhook, segunda via, cancelamento, multa e juros, boleto híbrido com Pix, interface web e dados reais.

## 8. Próximo passo

Depois da sua revisão deste arquivo, escrevo o plano de implementação por marcos, com testes primeiro (TDD), e você escolhe como executá-lo.
