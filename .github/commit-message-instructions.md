# Instruções para mensagens de commit

Gere mensagens de commit em português do Brasil, com linguagem profissional,
objetiva e tecnicamente precisa.

Baseie a mensagem exclusivamente nas alterações apresentadas e no contexto
fornecido pelo repositório. Não invente comportamento, motivação, requisitos,
testes executados, resultados, issues ou informações que não possam ser
inferidas com segurança.

Antes de escolher o tipo e o resumo, analise o diff completo disponível, incluindo
arquivos adicionados, modificados e removidos. Para alterações em vários arquivos,
identifique a capacidade ou objetivo central que conecta as mudanças e descreva
esse resultado no commit. Não reduza uma mudança funcional ou de infraestrutura a
`chore` apenas porque ela envolve configuração, dependências ou vários arquivos.
Use `chore` somente quando não houver um tipo mais específico aplicável.

Quando o diff tiver mais de um arquivo ou incluir uma nova funcionalidade, gere um
corpo conciso com 2 a 5 itens explicando as principais mudanças e seus efeitos.
Nunca use resumos genéricos como `remove seções vazias de alterações de código`,
`faz ajustes diversos` ou equivalentes se o diff permitir identificar o objetivo
real.

## Formato

Siga Conventional Commits:

`tipo(escopo): resumo`

O escopo é opcional:

`tipo: resumo`

Para breaking changes:

`tipo(escopo)!: resumo`

## Tipo

Escolha o tipo de acordo com o propósito principal da alteração, e não apenas
com os arquivos modificados:

* `feat`: adiciona ou expande uma funcionalidade
* `fix`: corrige comportamento incorreto ou defeito
* `refactor`: reorganiza o código sem alterar seu comportamento observável
* `perf`: altera o código especificamente para melhorar desempenho
* `test`: adiciona, corrige ou reorganiza exclusivamente testes
* `docs`: altera exclusivamente documentação
* `style`: altera apenas formatação ou estilo sem mudar comportamento
* `build`: altera sistema de build, empacotamento ou dependências de build
* `ci`: altera pipelines, workflows ou automações de CI/CD
* `chore`: manutenção que não se enquadra melhor nos tipos anteriores
* `revert`: reverte uma alteração anterior

Quando houver diferentes tipos de mudança no mesmo diff, escolha aquele que
melhor representa a intenção e o impacto principal do commit.

Não classifique automaticamente alterações em arquivos de configuração como
`chore`; considere o efeito real da mudança.

## Escopo

Use um escopo somente quando ele puder ser identificado com clareza e tornar
a mensagem mais informativa.

Prefira nomes curtos, estáveis e relacionados ao domínio, módulo ou componente
afetado, como `auth`, `api`, `crawler`, `config`, `docker` ou `tests`.

Considere os escopos usados recentemente pelo repositório para manter
consistência.

Não invente um escopo quando a mudança atingir várias áreas sem um componente
principal claro.

## Resumo

O resumo deve:

* estar em português do Brasil
* começar com um verbo de ação, como `adiciona`, `corrige`, `remove`, `ajusta`,
  `atualiza`, `impede`, `simplifica` ou `refatora`
* descrever a intenção principal e o efeito concreto da alteração
* ser específico e compreensível sem consultar imediatamente o diff
* ter no máximo 72 caracteres sempre que possível
* não terminar com ponto
* não usar emojis
* evitar termos vagos como `melhora`, `ajustes`, `mudanças`, `atualizações`,
  `correções diversas` ou `melhorias gerais` sem explicar o objeto da mudança

Prefira:

`fix(auth): impede renovação de sessão com token expirado`

em vez de:

`fix(auth): melhora autenticação`

## Corpo

Use corpo somente quando ele acrescentar informação relevante que não cabe no
resumo.

Para mudanças pequenas e autoexplicativas, gere apenas o cabeçalho.

Para mudanças não triviais, explique de forma concisa:

* as alterações funcionais ou técnicas mais relevantes
* impactos observáveis no comportamento
* regras de negócio afetadas
* mudanças de compatibilidade, configuração ou infraestrutura
* riscos ou efeitos colaterais relevantes quando forem evidentes
* o motivo da alteração somente quando puder ser inferido com segurança

Agrupe alterações relacionadas pela intenção ou impacto. Não descreva o diff
arquivo por arquivo e não narre detalhes de implementação sem relevância para
o histórico.

Quando itens forem mais claros que parágrafos, use no máximo 5 itens iniciados
por `-`.

Não repita no corpo o que já está suficientemente explicado no resumo.

## Testes e validações

Mencione testes adicionados, removidos ou modificados quando isso fizer parte
das alterações.

Não afirme que testes foram executados, passaram, falharam ou que uma
validação foi realizada apenas porque existem arquivos de teste no diff.

Não invente resultados de execução.

## Breaking changes

Quando houver incompatibilidade observável, use `!` antes de `:`:

`feat(api)!: altera contrato de autenticação`

Inclua também um footer quando houver informação suficiente para explicar o
impacto:

`BREAKING CHANGE: descreva objetivamente o que deixou de ser compatível`

Descreva a migração necessária somente quando ela puder ser determinada a
partir das alterações. Não invente procedimentos de migração.

## Consistência e precisão

Use commits recentes do repositório como referência para nomenclatura de
escopos e estilo, mas não copie seu conteúdo nem preserve padrões que
conflitem com estas instruções.

Priorize o significado da mudança sobre a lista de arquivos modificados.

Não inclua números de issue, tickets, pull requests, autores, coautores,
revisores ou outras metainformações.

Não invente contexto ausente para tornar a mensagem aparentemente mais
completa.

## Saída

Retorne somente uma única mensagem de commit pronta para uso.

Não inclua aspas, explicações sobre a análise, alternativas, comentários ou
blocos de código Markdown.
