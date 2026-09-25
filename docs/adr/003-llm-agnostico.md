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
