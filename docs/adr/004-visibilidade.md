# ADR-004: Código público, conjunto-teste privado até a defesa

- **Estado:** aceita
- **Data:** 2026-09-25

## Contexto

O Colab instala o pacote direto do GitHub, e a reprodutibilidade pede código
aberto. Os gabaritos, se públicos, poderiam entrar nos dados de treino de
modelos futuros e seriam expostos antes da revisão cruzada.

## Decisão

- `po-multiagente` é **público**, sob licença MIT.
- O conjunto-teste é **privado até a defesa** (ver ADR-009).

## Consequências

- Instalação no Colab sem token; release com DOI para citação no TG2.
- Hook do pre-commit, `.gitignore` e checagem do CI impedem que instâncias
  ou gabaritos entrem no repositório público.
