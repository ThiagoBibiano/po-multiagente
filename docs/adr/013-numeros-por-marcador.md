# ADR-013: O Explicador só escreve números por marcador

- **Estado:** aceita
- **Data:** 2026-09-26

## Contexto

No piloto, o modelo de linguagem afirmou uma solução que não correspondia ao
próprio modelo (cap. 3). A solução passou a vir sempre do solver, mas o texto
final ainda poderia trazer um número inventado ou mal copiado.

## Decisão

O Explicador escreve `{{OBJ}}` e `{{VAR:<nome>}}` no lugar dos números. O
código substitui cada marcador pelo valor do solver e monta a ficha de
procedência (R5). Um texto com algarismo fora de marcador, ou com marcador
desconhecido, é recusado e volta ao agente; depois da segunda recusa, o
código monta um texto de reserva. O Interpretador e o Modelador também não
veem números: as colunas numéricas das fontes aparecem sem valores.

## Consequências

- O caminho por onde um número inventado chegaria ao gestor não existe.
- A explicação é menos fluida em números (formato fixo, notação brasileira).
