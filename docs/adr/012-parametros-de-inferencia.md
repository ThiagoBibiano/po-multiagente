# ADR-012: Parâmetros de inferência do gpt-6-luna

- **Estado:** substituída pela [ADR-014](014-modelo-gemini-flash-lite.md) quanto ao modelo
- **Data:** 2026-09-26

## Contexto

O autor escolheu o gpt-6-luna (OpenAI). Conferido na documentação em
26/09/2026: é um modelo de raciocínio (`reasoning.effort` de `none` a `max`,
padrão `medium`), com saída estruturada, US$ 0,10 por milhão de tokens de
entrada e US$ 0,50 de saída. Com esforço diferente de `none`, a API rejeita
`temperature` e `top_p`; a API de Respostas não tem `seed`. O cap. 3 prevê
registrar a temperatura e cita, no piloto, sua redução.

## Decisão

- API de Respostas, com saída estruturada estrita (`strict: true`) e esquema
  derivado dos objetos de domínio.
- Esforço de raciocínio fixo por perfil (`config/modelos/gpt-6-luna.yaml`),
  inicialmente `low`, calibrado na partição de ajuste e congelado antes do
  experimento. Sem `temperature` (a API não aceita com raciocínio).
- Reprodutibilidade por gravação das chamadas (cassetes) e pelas três
  repetições do experimento; o manifesto registra os parâmetros efetivamente
  enviados.

## Consequências

- O texto do cap. 3 deve trocar "temperatura" por "esforço de raciocínio" como
  parâmetro de inferência fixo e registrado.
- Custo estimado de uma execução completa: cerca de um centavo de dólar; uma
  rodada de calibração (24 instâncias, duas configurações), menos de um dólar.
