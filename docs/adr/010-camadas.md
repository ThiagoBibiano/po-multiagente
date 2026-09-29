# ADR-010: Arquitetura em camadas verificada por contratos

- **Estado:** aceita
- **Data:** 2026-09-25

## Contexto

O pacote precisa servir à interface e ao experimento com o mesmo núcleo, e
os agentes não podem ter acesso aos gabaritos.

## Decisão

Camadas verificadas pelo **import-linter** (`pyproject.toml`), de cima para
baixo:

```
cli
interface | experimento
orquestracao | avaliacao
agentes
validacao | rastreabilidade
solver | llm
modelo | dados
config
dominio
```

Contratos adicionais: nenhum módulo do caminho de execução importa
`avaliacao`; `avaliacao` não importa `agentes`, `orquestracao`, `llm` nem
`interface`.

## Consequências

- Um import que viole as camadas quebra o pre-commit e o CI.
- Mudar um contrato exige atualizar este ADR no mesmo PR.

## Revisão (26/09/2026)

A CLI subiu para uma camada própria, acima de `interface` e `experimento`: ela
é o ponto de entrada que despacha para as duas (o comando `calibrar` chama o
experimento). As demais regras não mudaram.
