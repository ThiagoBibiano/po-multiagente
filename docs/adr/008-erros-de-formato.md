# ADR-008: Erros de formato tratados no Modelador

- **Estado:** aceita
- **Data:** 2026-09-25

## Contexto

Com o compilador determinístico (ADR-002), um JSON malformado ou uma
expressão fora da gramática não compila. Se esse retorno ficasse no
Validador, a configuração sem Validador falharia em qualquer deslize de
formato, e o efeito medido do Validador ficaria inflado.

## Decisão

Erros de sintaxe e de esquema geram **nova tentativa dentro do próprio
Modelador**, com limite fixo, **igual nas duas configurações**. O Validador
trata apenas dos sinais semânticos S1–S5.

## Consequências

- O experimento mede só o efeito semântico do Validador.
- Coerente com o Capítulo 3: "o laço é um retorno à formulação, e não uma
  nova tentativa após erro de código".
- As tentativas de formato são registradas à parte no dossiê.
