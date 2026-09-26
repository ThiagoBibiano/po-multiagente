# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/);
o projeto segue [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não publicado]

### Adicionado

- Fundação do repositório (F0): pacote `po_multiagente` em layout `src/`,
  camadas com contratos de importação (import-linter), ruff, mypy estrito,
  pytest com hypothesis, pre-commit e CI.
- Objetos de domínio: quadro de especificação, requisitos, fontes de dados e
  origem, solicitações de tratamento, representação intermediária do modelo,
  resultado do solver e parecer do Validador.
- CLI mínima (`po-multiagente --versao`).
- ADR-001 a ADR-010.
- Núcleo determinístico (F1):
  - `dados`: leitura somente leitura de CSV (separador e notação numérica
    detectados) e XLSX (uma fonte por aba), inventário com SHA-256, conferência
    de integridade e ligação de valores com o motivo do tratamento necessário;
  - `modelo`: gramática da mini-linguagem, compilação com erros localizados,
    instanciação do modelo neutro, checagem de unidades e formulação em LaTeX;
  - `solver`: contrato `SolverBackend`, registro por entry points, adaptador
    PuLP/CBC 2.10.3 e suíte de conformidade;
  - `validacao`: sinais S1 a S5, com localização de inviabilidade e ilimitação.
- Documentação da mini-linguagem (`docs/gramatica.md`).
- `Verificacao.confirmacao`: o S5 pergunta ao usuário, em vez de reprovar,
  quando o valor objetivo coincide com uma cota trivial (ADR-011).
