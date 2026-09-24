# ADR 0041: Metadados administrativos de lojas registradas

- Status: Accepted
- Data: 2026-09-24

## Contexto

O catálogo de lojas e suas integrações são definidos em `STORE_CONFIGS`. Nome
de exibição, domínios, país e moeda participam do comportamento dos adapters,
scrapers e Product Match. O painel oferecia edição desses campos, mas seu client
respondia `STORES_REGISTRY_ONLY`; não existiam rota nem persistência.

## Decisão

Manter o registry como fonte de verdade estrutural e persistir em
`store_metadata` somente `display_name` e `logo_svg`, indexados pela chave
existente do registry. A API expõe `PATCH /admin/stores/{store_key}`, exige
papel de administrador quando autenticação está ativa; com `AUTH_REQUIRED=false`
fora de produção, aceita somente o principal fixo do bypass de desenvolvimento.
JWT de usuário comum continua sem acesso. `GET /stores` combina
os metadados persistidos com a configuração estrutural do registry.

Domínio, chave, adapter, país, moeda e capabilities permanecem somente leitura.
Logo aceita apenas SVG dentro do limite de 1 MB, sem scripts, handlers,
referências externas ou declarações de entidade/DOCTYPE.

## Consequências

- A edição de nome e logo sobrevive a reinícios via PostgreSQL/Alembic.
- Não é possível cadastrar sites arbitrários pelo painel.
- Alterações de país/moeda ou domínio exigem mudança revisada no registry e
  nos adapters correspondentes.
- Sem `DATABASE_URL`, a listagem usa o registry e edição retorna
  indisponibilidade. Se a conexão estiver configurada mas o banco estiver
  inacessível, a leitura de metadados também falha para evitar exibir valores
  desatualizados.
