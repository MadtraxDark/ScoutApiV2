# PENDING-022 — Validar matching de CPU em lojas reais

- Status: RESOLVED
- Tipo: TESTING
- Prioridade: P1
- Área: matching/cpu
- Origem: 2026-09-24 — falha de discovery no Ryzen 7 5800X3D
- Atualizado: 2026-09-24

## Contexto

Foi corrigida a geração de queries e a comparação semântica de CPUs. A validação
unitária passou, mas falta confirmar o resultado pós-correção nas SERPs/PDPs
reais de Nissei e Visão VIP e observar o runtime do browser no ambiente
integrado.

## Feito

- Logs reais anteriores analisados: Nissei retornou cinco modelos diferentes e
  nenhum candidato 5800X3D; Visão VIP falhou aguardando slot do browser e, em
  outra execução, terminou com zero candidatos.
- Foram encontrados títulos atuais correspondentes na categoria pública da
  Nissei e no produto Visão VIP código 59017.
- Testado via AMD que 10th Anniversary Edition mantém o processador
  Ryzen 7 5800X3D/AM4; boxed e tray usam OPNs distintos.
- Correção coberta por testes de identificação, sufixo, socket, OPN, query e
  títulos reais das duas lojas.
- Nova execução pelo `POST /match` com `persist=false`, limitada a Nissei e
  Visão VIP: o produto de origem foi extraído corretamente como Ryzen 7
  5800X3D / AM4 / 8 núcleos.
- Visão VIP executou três tentativas da estratégia A e retornou `NO_RESULTS`
  em 4,9 s; nenhum candidato foi criado ou enviado ao scraping.
- Nissei falhou antes da navegação SERP com `BROWSER_LAUNCH_ERROR`, depois de
  45,7 s no `launch_persistent_context`; nenhum candidato foi criado.
- A chamada completa levou 51,6 s. Os tempos por loja foram 4,9 s na Visão VIP
  e 45,7 s na Nissei.
- A resposta teve zero matches e zero candidatos com PDP extraída; não houve
  decisão de matching nem escrita de oferta nesta repetição.
- Instrumentação do Product Match foi ajustada para imprimir queries, URLs SERP,
  candidatos limitados, rejeições de título, atributos/decisões PDP e resumo por
  loja no texto dos logs. URLs de candidatos omitem query strings.
- Os três módulos de regressão passaram novamente: 121 testes; Ruff e mypy dos
  dois serviços de matching passaram.
- Reprodução com os módulos atuais no container, limitada às duas lojas,
  encontrou e raspou os dois SKUs; ambos receberam `auto_match` com confiança
  `0.9800`.
- Reexecução com `persist=true` e `canonical_product_id` do produto PriceScout
  criou listings ativos da Nissei e Visão VIP no produto existente.

## Resolução final

### Causa da falha original

- **Nissei — discovery:** os logs anteriores mostravam query concatenada
  `amd ryzen75800x3d`. A busca devolvia CPUs próximas, mas não o 5800X3D; o
  matcher as rejeitava corretamente pelo conflito de modelo. A query legível
  `amd ryzen 7 5800x3d` agora retorna o SKU correto entre cinco candidatos.
- **Visão VIP — discovery:** as queries geradas anteriormente terminavam em
  `NO_RESULTS` na estratégia A. Com a query progressiva corrigida, a estratégia
  retorna o SKU `59017` na primeira tentativa.
- **Runtime Nissei durante o diagnóstico:** o perfil `locale_es_py` tinha
  `.parentlock` e `lock` stale deixados por launch expirado. Após remover apenas
  esses marcadores e caches descartáveis (cookies e sessão preservados), o
  browser iniciou e completou busca e scraping. Não foi necessário afrouxar
  seccomp, desativar sandbox, mudar fetch/proxy/fingerprint/waits ou alterar C1.

### Resultado live pós-correção

- Query nas duas lojas: `amd ryzen 7 5800x3d`.
- **Nissei:** SERP retornou cinco produtos. Primeiro candidato: “Processador AMD
  Ryzen 7 5800X3D AM4 8 Núcleos até 4.5 GHz 96 MB 3D V-Cache (Sem Cooler)”; PDP
  atual `/br/procesador-amd-ryzen-7-5800x3d-am4-8-nucleos-hasta-4-5-ghz-96-mb-3d-v-cache-sin-cooler`,
  SKU `159342`, com `parent_product_id=1705851`. O legado pedido resolve para
  essa variante atual. Socket AM4 e modelo foram extraídos; decisão
  `auto_match`, confiança `0.9800`, razão `processor_model_exact`.
- **Visão VIP:** estratégia A retornou SKU `59017`, título “Processador AMD
  Ryzen 7 5800X3D 10th Anniversary Edition Socket AM4 / 3.4GHz / 100MB”; PDP
  raspada com modelo, socket AM4, clock, cache, 8 cores, 16 threads, TDP 105 W e
  embalagem BOX. Decisão `auto_match`, confiança `0.9800`, razão
  `processor_model_exact`. A edição comercial não alterou a identidade do CPU.
- A normalização de CPU preserva o modelo/sufixo completo; a assinatura exata
  confirma `5800X3D` e exclui `9800X3D`, `7800X3D`, `5900XT` e `5700X`. Socket
  ausente permanece desconhecido; socket explicitamente diferente é conflito.
  OPN/MPN é evidência complementar à identidade do hardware e embalagem/edição.
- O teste live persistente gravou os dois listings como `active` no produto
  canônico `a9c9041d-503a-4942-8b62-a483bd2f7c78`.
- Timings da reprodução fria limitada: Visão VIP 9,97 s (busca 7,38 s, scrape
  2,58 s); Nissei 23,94 s (busca 18,60 s, scrape 5,33 s); total Product Match
  33,91 s. Persistência repetida servida do cache levou 9,30 s. A busca fria
  segue marcada WARN pelo budget de 2 s por operação de search; o total excede
  o budget de 15 s, sem impedir a conclusão.

## Investigação

### Observabilidade adicionada

Os logs agora incluem query/método/URL SERP; candidatos limitados com ID, título
e URL sem query string; rejeições de título; atributos e razões da decisão PDP;
e resumo de tempos/contagens por loja. Isso tornou visíveis discovery,
candidate generation, scraping e matching na reprodução live.

### O que foi testado

- API local `POST /match`, limitada a `nissei` e `visaovip`, com `persist=false`.
- `ProductMatchService.match_from_item()` local, também sem persistência.
- Testes unitários de match, parser da Nissei e cadeia de busca da Visão VIP:
  121 passaram.
- API local executada com código do workspace e instrumentação, stores limitadas
  a Nissei/Visão VIP, primeiro sem persistir e depois persistindo no UUID
  canônico; resposta, logs e listings ativos conferidos via API.
- `docker compose ps`, logs de API e match-runner, configuração efetiva do
  container, árvore de processos durante o launch e dependências dinâmicas do
  bundle Camoufox inspecionados. Nenhuma alteração de segurança do browser foi
  aplicada.

### Fontes consultadas

- [AMD Ryzen 7 5800X3D Product Specifications](https://www.amd.com/en/products/processors/desktops/ryzen/5000-series/amd-ryzen-7-5800x3d.html)
  confirma socket AM4 e identifica a 10th Anniversary Edition como o mesmo
  processador com item comercial adicional; Intel Processor Numbers/Core Ultra
  naming foram usados para preservar sufixos de SKU.
- [Mozilla Searchfox `SandboxInfo.cpp`](https://searchfox.org/mozilla-central/source/security/sandbox/linux/SandboxInfo.cpp)
  e [Bugzilla 1981001](https://bugzilla.mozilla.org/show_bug.cgi?id=1981001):
  `EPERM` é tratado como incapacidade de criar user namespace e não explica
  sozinho o travamento.
- [Microsoft Playwright Docker docs](https://playwright.dev/python/docs/docker):
  recomenda perfil seccomp de scraping e
  init para recolher processos zumbis; `--ipc=host` é recomendado para Chromium,
  sem evidência de que resolva este launch Firefox.
- Camoufox GitHub [#620](https://github.com/daijro/camoufox/issues/620) / [#619](https://github.com/daijro/camoufox/issues/619):
  relatos semelhantes de processo vivo sem inicialização do Juggler em Docker;
  issue #620 foi fechada sem reprodução confirmada nem correção aplicável
  publicada.
- GitHub/OSS: WDC Products e Ditto; usados apenas como referências para pares
  difíceis e separação de candidate generation e matching.
- Stack Overflow, Hacker News, Reddit, Shopify Engineering, MDN e artigos/papers
  sobre entity resolution e atributos de produto; não foi encontrada abordagem
  que justificasse dependência nova ou threshold global.
- AMD, Nissei e Visão VIP: páginas oficiais/listagens atuais dos produtos
  correspondentes.

### Alternativas avaliadas / descartadas

- Executar o teste real diretamente no host — falhou no lookup externo de IP
  necessário ao Camoufox.
- Desativar o sandbox de conteúdo (`MOZ_DISABLE_CONTENT_SANDBOX`) ou executar
  com seccomp irrestrito — alternativas encontradas em relatos comunitários,
  descartadas porque enfraquecem isolamento ao navegar páginas não confiáveis.
- Aumentar timeout — descartado: o browser não responde ao Juggler e aumentar
  espera não identifica nem corrige a causa.
- Diminuir threshold global — descartado; modelo completo/sufixo e conflitos
  explícitos resolvem a precisão sem enfraquecer a regra geral.

### Condição para continuar

Resolver o launch do Camoufox/Juggler mantendo sandbox ativo, fetch direto
primeiro, Proxy Cost Mode e capacidade C1. Depois, repetir o caso integrado e
registrar a query visível e cada etapa até a decisão/persistência.

## Impacto

O matching de CPU segue coberto unitariamente. Esta execução confirmou a falha
de busca vazia da estratégia A na Visão VIP e o bloqueio anterior à busca na
Nissei; descoberta pós-correção, scraping dos candidatos, decisões e
persistência ainda não foram confirmados live.

## Relacionado

- `src/scout_api/modules/matching/identity.py`
- `src/scout_api/modules/matching/engine.py`
- `tests/unit/test_matching_regression.py`
- `docs/crawler/product-identity.md`
- `docs/matching/README.md`
- `docs/adr/0038-pdp-search-capability-split.md`

## Pronto quando

- Nissei e Visão VIP encontram o modelo 5800X3D com query registrada.
- Os títulos e URLs são extraídos corretamente e recebem `auto_match` por
  assinatura de CPU; ausência de socket não rejeita.
- Os tempos por etapa são registrados e não há aumento significativo de
  runtime nem de falsos positivos em CPUs vizinhas.
