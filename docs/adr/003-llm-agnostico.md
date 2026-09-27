# ADR-003: Acesso agnóstico a modelos de linguagem

- **Estado:** aceita
- **Data:** 2026-09-25

## Contexto

Os candidatos são gpt-6-luna (OpenAI) e DeepSeek-V4.1-Flash (DeepSeek). O
experimento exige que modelo, versão e parâmetros de inferência fiquem
fixos e registrados.

## Decisão

- Um contrato `LLMPort` e um único adaptador, `OpenAICompativel(base_url,
  modelo)`, com o SDK `openai`, que cobre os dois provedores.
- Cada modelo tem um **perfil** declarando capacidades: saída estruturada
  estrita ou apenas modo JSON, suporte a `temperature` e `seed`, preço por
  token.
- Sem LangChain nos modelos; o LangGraph só orquestra (ADR-007).

## Consequências

- Trocar de provedor é trocar de perfil.
- O manifesto registra os parâmetros **efetivamente aplicados**, pois alguns
  modelos ignoram `temperature`.
- A saída estruturada estrita da OpenAI exige todos os campos como
  obrigatórios; o adaptador deriva o esquema enviado a partir do domínio.

## Adendo (2026-09-26)

A Maritaca implementa a API de Respostas com saída estruturada estrita
(conferido na API em 26/09/2026). O adaptador existente serve sem mudança de
chamada: o perfil passa a declarar `url_base` e `variavel_chave`, e os preços
ganham `moeda`, pois a Maritaca cobra em reais. O perfil `sabiazinho-4` serve
a testes iniciais baratos; não substitui o modelo do experimento.

## Adendo (2026-09-27)

O nível flex da Maritaca custa a metade, sujeito a capacidade, e só é
atendido pela API de Chat Completions: a de Respostas ignora `service_tier`.
O adaptador passa a falar as duas APIs, escolhidas por `api` no perfil
(`responses` ou `chat`), com o mesmo tratamento de erros. As duas APIs
aceitam qualquer valor de `service_tier` sem erro, então o registro de cada
chamada guarda o nível informado na resposta, e não o pedido.
