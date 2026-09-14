# Documentation index — ScoutApiV2

Mapa rápido para reconstruir contexto sem depender de histórico de chat.

## Precedência

1. Requisito explícito da tarefa
2. [`AGENTS.md`](../AGENTS.md)
3. ADRs **Accepted** em [`adr/`](adr/)
4. [`.cursor/rules/`](../.cursor/rules/)
5. Código atual
6. Skills ([`skills/README.md`](skills/README.md))
7. Genéricos

Governança de documentação: [`.cursor/rules/documentation-governance.mdc`](../.cursor/rules/documentation-governance.mdc).

## Onde ler o quê

| Tópico | Documento canônico |
|---|---|
| Invariantes do agente | [`AGENTS.md`](../AGENTS.md) |
| Decisões arquiteturais | [`adr/README.md`](adr/README.md) |
| Crawler — contratos e erros | [`crawler/contracts.md`](crawler/contracts.md) |
| Crawler — lojas | [`crawler/stores/`](crawler/stores/) |
| Proxy Cost Mode | [`.cursor/rules/proxy-cost-mode.mdc`](../.cursor/rules/proxy-cost-mode.mdc) + [ADR 0014](adr/0014-cost-aware-proxy-routing.md) |
| Challenge/CAPTCHA (obrigatório resolver) | [`.cursor/rules/captcha-challenge-resolution.mdc`](../.cursor/rules/captcha-challenge-resolution.mdc) + [ADR 0017](adr/0017-captcha-challenge-resolution.md) |
| Auth bypass / login wall (obrigatório) | [`.cursor/rules/auth-wall-resolution.mdc`](../.cursor/rules/auth-wall-resolution.mdc) + [ADR 0018](adr/0018-auth-wall-bypass.md) |
| Pesquisa antes de bloquear / paid | [`.cursor/rules/research-and-problem-solving.mdc`](../.cursor/rules/research-and-problem-solving.mdc) |
| Fetch / Camoufox imutáveis | [`.cursor/rules/scraper-camoufox-immutable.mdc`](../.cursor/rules/scraper-camoufox-immutable.mdc) |
| Segurança (URLs, secrets, logs) | [`.cursor/rules/security.mdc`](../.cursor/rules/security.mdc) |
| Testes | [`.cursor/rules/testing.mdc`](../.cursor/rules/testing.mdc) |
| Skills | [`skills/README.md`](skills/README.md) |
| Pendências / trabalho incompleto | [`pending/README.md`](pending/README.md) |
| Idioma do agente (pt-BR) | [`.cursor/rules/language-pt-BR.mdc`](../.cursor/rules/language-pt-BR.mdc) |
| Conclusão de tarefa | [`.cursor/rules/task-completion.mdc`](../.cursor/rules/task-completion.mdc) |
| Operação / endpoints | [`README.md`](../README.md) |

## Crawler — playbooks por loja

| Loja | Doc |
|---|---|
| KaBuM | [`crawler/stores/kabum.md`](crawler/stores/kabum.md) |
| Magazine Luiza | [`crawler/stores/magazineluiza.md`](crawler/stores/magazineluiza.md) |
| Shopee | [`crawler/stores/shopee.md`](crawler/stores/shopee.md) |
| Best Buy | [`crawler/stores/bestbuy.md`](crawler/stores/bestbuy.md) |
| Nissei | [`crawler/stores/nissei.md`](crawler/stores/nissei.md) |
| Shopping China | [`crawler/stores/shoppingchina.md`](crawler/stores/shoppingchina.md) |
| Amazon (BR/US) | [`crawler/stores/amazon.md`](crawler/stores/amazon.md) |
