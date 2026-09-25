# ADR-009: Três repositórios com fluxo de mão única

- **Estado:** aceita
- **Data:** 2026-09-25

## Contexto

O repositório do TG é público; o código também (ADR-004); o conjunto-teste
precisa ser privado. O autor escreve o TG e o código em paralelo.

## Decisão

| Repositório | Visibilidade | Conteúdo |
|---|---|---|
| `tg-plataforma-multiagente-po` | Público | Texto, resultados importados, `artefato.lock` |
| `po-multiagente` | Público | Código, testes, documentação |
| `po-multiagente-conjunto-teste` | Privado até a defesa | As 24 instâncias e gabaritos |

- Diretórios vizinhos em `~/Documentos/`, sem submódulos.
- Fluxo de mão única, código → texto: o TG registra em `artefato.lock` a tag,
  o commit e o DOI usados, e importa os resultados por script.
- O código localiza o conjunto-teste pela variável `PO_CONJUNTO_TESTE`.

## Consequências

- Alternativas descartadas: submódulo (o TG só precisa das saídas) e
  conjunto-teste no `.gitignore` do código (perderia histórico, cópia remota e
  acesso do revisor).
- Uma pessoa revisora dos gabaritos entra como colaboradora do repositório privado.
