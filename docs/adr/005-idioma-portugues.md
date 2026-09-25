# ADR-005: Identificadores em português sem acento

- **Estado:** aceita
- **Data:** 2026-09-25

## Contexto

O domínio, a interface, o TG e a banca são em português. Misturar inglês no
código criaria uma tradução a mais entre o texto e a implementação.

## Decisão

Identificadores em **português sem acento** (`quadro_especificacao`,
`exigir_unicos`); docstrings, mensagens e documentação em português com
acentuação.

## Consequências

- Os nomes do código coincidem com os do Capítulo 3.
- Nomes vindos de bibliotecas externas continuam em inglês.
- Mensagens de erro evitam flexão de gênero dependente do contexto
  ("com repetição", "sem declaração").
