# ADR 0039: BrowserScheduler + bounded queue + profile lock + claim_trial — capacity permanece C1

- Status: Accepted
- Data: 2026-09-23

## Contexto

O Phase 5 (Task 5) do projeto camoufox-visaovip-reliability executou benchmarks de capacidade
C1/C2/C3 usando `scripts/bench_camoufox_capacity.py`:

| Config | Layer 1 throughput Δ | Layer 2 throughput Δ | Layer 2 erros | P95 Δ (L2) | Peak RSS Δ (L2) |
|--------|---------------------|---------------------|---------------|-----------|-----------------|
| C1 (1 slot) | baseline | baseline | 0/5 | baseline | baseline |
| C2 (2 slots) | +116% | +48% | 1/10 | +9.7% | +26 MB |
| C3 (3 slots) | +204% | +144% | 0/15 | +15.4% | +51 MB |

As Phases 1–4 implementaram, respectivamente:
- `BrowserScheduler` com fila FIFO limitada por `CAMOUFOX_BROWSER_CAPACITY` / `CAMOUFOX_QUEUE_MAX_WAITERS`
- `ProfileLock` (Redis primary, fcntl secondary) para impedir que dois processos abram o mesmo diretório de perfil
- `BrowserCircuitBreaker.claim_trial()` — proibe token atômico no estado HALF_OPEN (só 1 caller prova por vez)
- `StoreAttemptBudget` (retry/attempt budgets por loja)

O bench C2 registrou 1 erro de race em L2 (Visão VIP, loja anti-bot) de 10 tentativas, acima do
threshold "sucesso ≈ C1 (100%)". O P95 de C2 e C3 em L2 também não atendeu o critério de melhora
≥15% de P95 requerido na spec. Throughput C2 atendeu o critério ≥20% (OR alternativo da spec), mas
a regra de adjudicação do projeto declara **RELIABILITY → … → THROUGHPUT**: falha de reliability
não é compensada por ganho de throughput.

ADR 0032 já havia rejeitado pool de N browsers com o mesmo perfil.

## Problema / decisão necessária

Fixar a capacidade de produção e documentar a arquitetura de scheduler/queue/lock/circuit
implementada nas Phases 1–4.

## Alternativas consideradas

- **C1 — 1 slot (current):** rejeitado como "temporário" no plano inicial; bench não prova reliability
  equivalente a C1 em loja real anti-bot.
- **C2 — 2 slots, perfis isolados:** throughput +116%/+48%; P95 piorou; 1 erro em L2; bench usou
  harness externo (não `BrowserScheduler` de produção); medição incompleta (apenas 2 camadas, sem
  terceira loja; sem ci no compose). **Rejeitado para produção.**
- **C3 — 3 slots:** P95 piora +18.9% em L1 e +15.4% em L2; memória +51 MB. **Rejeitado.**
- **Worker/service separado por slot:** YAGNI; sem evidência de necessidade hoje.

## Decisão

1. **`CAMOUFOX_BROWSER_CAPACITY` default = 1.** Produção permanece C1.
2. ADR 0032 ("Pool de N browsers Camoufox em paralelo rejeitado") **permanece Accepted e não é
   supersedido.** Esta decisão estende 0032 documentando a arquitetura dos controles construídos.
3. A infraestrutura de `BrowserScheduler` + `ProfileLock` + `claim_trial` é mantida no código:
   prepara C2+ para reativação futura se benchmark com harness de produção e amostra maior provar
   success ≡ C1 **e** P95 não piorar ≥15% em loja real anti-bot.

## Justificativa

- Regra de prioridade do projeto: **RELIABILITY > latência > throughput**.
- C2 L2 (Visão VIP, loja anti-bot): 1 erro / 10 fetches = 90% de sucesso, abaixo de 100% de C1.
- Critério AND (spec): `success ≈ C1` **E** `P95 não piora ≥15%` **E** memória aceitável **E**
  throughput ≥20%. C2 falha no primeiro critério em L2.
- Throughput não compensa falha de reliability sob a regra AND.
- Bench incompleto: harness sem `BrowserScheduler` de produção, sem terceira loja, sem carga compose.

## Consequências positivas

- Comportamento de produção estável e previsível (C1).
- `BrowserScheduler` elimina queue implícita ilimitada: fila saturada levanta `RequestError`
  `BROWSER_QUEUE_SATURATED` em vez de hang indefinido.
- `ProfileLock` previne corruption de perfil entre processos (api / monitor / match-runner).
- `claim_trial()` garante singleflight atômico no HALF_OPEN: sem thundering herd de launch.
- Infraestrutura pronta para C2+ quando benchmark validado.

## Trade-offs / consequências negativas

- Throughput C1 < C2 (esperado; baseline aceito).
- C2+ requer novo benchmark com harness de produção e amostra suficiente antes de ativação.
- `ProfileLock` Redis: se Redis indisponível, fallback `fcntl` ou `NullProfileLock` (WARN).

## Condição para reabertura de C2+

Novo ADR supersedendo este, com evidência de:
- `success_rate(C2_prod) ≥ 100%` em N ≥ 20 fetches por loja real anti-bot
- `P95(C2_prod) ≤ P95(C1_prod) × 1.15` em todas as lojas testadas
- Medição via `BrowserScheduler` de produção (não harness externo)
- Sem falhas de launch ou corruption de perfil no compose completo
