# ADR-007: Orquestração com LangGraph

- **Estado:** aceita
- **Data:** 2026-09-25

## Contexto

O Passo 4 prevê um grafo de estados que explicite os nós e o retorno do
laço, o que permite remover o Validador. O Interpretador precisa pausar para
aguardar o tratamento de dados pelo usuário, e o Colab pode desconectar.

## Decisão

Usar **LangGraph**: grafo montado com ou sem o nó Validador, `interrupt()`
para as solicitações de tratamento e checkpointer (SQLite, opcionalmente no
Drive) para retomar sessões.

## Consequências

- A remoção do Validador é estrutural: o nó não existe na configuração sem
  Validador.
- No experimento, as interrupções são atendidas pelo respondedor simulado.
