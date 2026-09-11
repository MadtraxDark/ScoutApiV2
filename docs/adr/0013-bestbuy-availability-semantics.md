# ADR 0013: Semântica de disponibilidade da Best Buy (preço US vs shipping)

- Status: Accepted
- Data: 2026-09-11

## Contexto

O crawler usa a Best Buy como fonte de **preço de referência em USD** para
comparação voltada a usuários brasileiros. Páginas reais frequentemente
mostram “unavailable” por restrições de fulfillment (sem shipping
internacional, ZIP ausente, entrega só em loja nos EUA), sem que a oferta
comercial nos Estados Unidos tenha acabado.

## Problema / decisão necessária

Como normalizar `availability` / `available` no adapter Best Buy sem
confundir **disponibilidade da oferta** com **disponibilidade de envio**?

## Alternativas consideradas

- **Tratar qualquer “unavailable” / ausência de add-to-cart como
  `out_of_stock`:** simples, mas marca ofertas ativas como indisponíveis
  quando o bloqueio é só logístico/localização.
- **Exigir shipping para o Brasil ou ZIP dos EUA para considerar a oferta
  válida:** desalinhado ao objetivo de preço de referência US.
- **Price-first + sinais claros de estoque:** preço/oferta ativa implica
  `available`; só `sold out` / `out of stock` / `discontinued` /
  `buttonState=SOLD_OUT` (e equivalentes) marcam `out_of_stock`.

## Decisão

No adapter Best Buy:

1. Priorizar captura confiável de preço (`price`, `original_price`,
   `discount_percentage`, `currency`).
2. Diferenciar product availability de shipping availability.
3. Não usar ausência de shipping para o Brasil (nem dependência de ZIP /
   pickup local) como critério de `out_of_stock` / `unavailable`.
4. Se existir oferta ativa com preço válido, normalizar
   `availability="available"` e `available=true`.
5. Só marcar indisponível quando houver sinal claro de que a própria
   oferta acabou (sold out, out of stock, discontinued, no longer
   available, `SOLD_OUT`).
6. Não alterar o schema global só para expor `shipping_to_brazil`.

## Justificativa

Para comparação BR, o valor útil é o preço listado nos EUA. Restrições de
fulfillment internacional são logísticas e não apagam a oferta comercial
na Best Buy.

## Consequências positivas

- Ofertas com preço US utilizável deixam de ser descartadas por shipping.
- Pickup em loja / entrega só nos EUA continua válida para comparação.
- Sold-out real continua detectável via sinais explícitos de estoque.

## Trade-offs / consequências negativas

- `available=true` não implica que o usuário brasileiro consiga comprar ou
  receber o produto.
- Páginas sem preço e sem sinal claro de estoque ainda podem resultar em
  `unavailable`.
