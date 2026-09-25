# Como contribuir

## Ambiente

Requer [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-groups          # cria .venv com as dependências fixadas em uv.lock
uv run pre-commit install     # ativa os hooks
```

## Verificações

Todas rodam no pre-commit e no CI; um PR só entra com todas passando.

| Comando | Verifica |
|---|---|
| `uv run ruff check` e `uv run ruff format --check` | Estilo e erros comuns |
| `uv run mypy` | Tipos (modo estrito) |
| `uv run lint-imports` | Contratos de camada (ADR-010) |
| `uv run pytest --cov` | Testes e cobertura |

## Arquitetura

As camadas e o que cada uma pode importar estão no `pyproject.toml`
(`[tool.importlinter]`) e justificados no ADR-010. Para mudar um contrato,
escreva ou atualize um ADR no mesmo PR.

## Convenções

- **Idioma:** identificadores em português sem acento; textos, docstrings e
  mensagens em português (ADR-005).
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/pt-br/)
  (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`).
- **Branches:** `main` recebe só releases; o trabalho vai para `develop` em
  PRs pequenos, a partir de branches `tipo/descricao-curta`.
- **Dependências:** entram na fase que as usa; o pacote não declara o que não
  importa.
- **CHANGELOG:** toda mudança visível ao usuário entra em `[Não publicado]`.
