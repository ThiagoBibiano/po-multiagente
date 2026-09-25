# Plano: pacote do artefato multiagente (TG2) — 25/09/2026

Implementa a plataforma do Capítulo 3 (Passo 3: cinco agentes sobre um estado compartilhado) como um pacote Python instalável, consumido no Google Colab por meio de uma interface. O mesmo núcleo atende a dois públicos:

1. **Usuário final no Colab**: descreve o problema, sobe arquivos, responde às solicitações de tratamento e lê a explicação.
2. **Autor no experimento do Passo 7**: 24 instâncias × 2 configurações × 3 execuções, sem interface e sem intervenção (R2), com a pilha congelada.

A interface é uma camada fina por cima do núcleo.

## 0. Decisões

| # | Decisão | Estado |
|---|---|---|
| D1 | Interface em **Gradio** | Aprovada |
| D2 | Gerador-Executor é um **compilador determinístico**; o formato da representação intermediária é livre (seção 3) | Aprovada |
| D3 | LLM **agnóstico**; candidatos gpt-6-luna (OpenAI) e DeepSeek-V4.1-Flash (DeepSeek) | Aprovada |
| D4 | **Código público**; conjunto-teste **privado até a defesa** | Aprovada |
| D5 | Idioma dos identificadores: **português sem acento** (`quadro_especificacao`) | Aprovada |
| D6 | **PuLP/CBC por ora**, com camada de solver agnóstica | Aprovada |
| D7 | Orquestração com **LangGraph** | Aprovada |
| D8 | Erros de sintaxe e esquema da representação intermediária: **nova tentativa dentro do Modelador, igual nas duas configurações**; o Validador fica só com S1–S5 | Aprovada |
| D9 | Operação com três repositórios, vizinhos no disco, com fluxo de mão única código → texto (seção 8) | Aprovada |
| D10 | Arquitetura em camadas verificada por contratos de importação (seção 2) | Tomada na F0 |

Nome aprovado: `po-multiagente` (pacote `po_multiagente`). Falta o **prazo do TG2**, para datar as fases.

Cada decisão tem um registro em [`adr/`](adr/README.md).

## 1. Princípios de arquitetura

| Princípio | Como aparece no código |
|---|---|
| Núcleo determinístico, LLM na borda | Leitura de dados, representação intermediária, compilação, solver, sinais S1–S5 e métricas são funções puras, testáveis sem LLM. O LLM só interpreta, formula e explica. |
| O LLM nunca vê nem produz números | O Interpretador recebe esquema e amostra das colunas. O modelo aponta para `(arquivo, coluna, chave)` e o código liga os valores. Isso resolve a falha do piloto (solução afirmada pelo LLM), reduz tokens e protege os dados. |
| O artefato não transforma dados | A camada de dados é somente leitura. Um hash SHA-256 de cada arquivo é registrado no início e no fim da execução. |
| Solver atrás de um contrato | Só `solver/` conhece o backend. Nome e versão entram em cada execução (seção 4). |
| Validador removível | O grafo é montado com ou sem o nó (`validador: bool`). O Validador é removido, e não ignorado (Passo 7). |
| Gabarito inacessível aos agentes | Contrato do import-linter: `agentes/` e `orquestracao/` não importam `avaliacao/` nem leem gabaritos. O CI quebra se alguém tentar. |
| Rastreabilidade (R5) | Toda execução gera um **dossiê**: especificação, modelo, formulação em LaTeX, log do solver, validações, prompts e respostas, configuração, versões e hashes. |

## 2. Estrutura do repositório de código

```
po-multiagente/
├── pyproject.toml · uv.lock · README.md · LICENSE (MIT) · CITATION.cff · CHANGELOG.md
├── notebooks/
│   ├── plataforma.ipynb          # usuário final — "Open in Colab", 3 células
│   └── experimento.ipynb         # Passo 7 no Colab (retomável)
├── src/po_multiagente/
│   ├── __init__.py               # API pública: iniciar(), Plataforma
│   ├── config/                   # pydantic-settings + perfis YAML (padrao, experimento, modelos/*.yaml)
│   ├── dominio/                  # Pydantic, sem dependências: Requisito, Especificacao, Parametro/Origem,
│   │                             #   ModeloIR, Restricao(requisito_id), Solicitacao, ResultadoSolver,
│   │                             #   Validacao, Explicacao
│   ├── dados/                    # leitura CSV/XLSX, inventário de colunas, hash, ligação de valores
│   ├── llm/                      # LLMPort, adaptador OpenAICompativel, perfis, gravar/reproduzir, custo
│   ├── prompts/                  # *.md versionados, com hash registrado em cada execução
│   ├── agentes/                  # interpretador · modelador · gerador_executor · validador · explicador
│   ├── modelo/                   # gramática (Lark), checagem, instanciação neutra, render LaTeX
│   ├── solver/                   # contrato SolverBackend, registro, adaptadores (pulp)
│   ├── validacao/sinais/         # s1_status · s2_unidades · s3_parametros · s4_requisitos · s5_limites
│   ├── orquestracao/             # grafo LangGraph, estado, checkpointer, interrupções
│   ├── rastreabilidade/          # dossiê, manifesto, exportação HTML/ZIP
│   ├── interface/                # app Gradio (só usa a API pública)
│   ├── avaliacao/                # critérios 1–4, normalização de restrições, McNemar, taxonomia, export .tex
│   ├── experimento/              # executor pareado, intercalado, retomável; respondedor simulado
│   └── cli.py                    # executar | experimento | avaliar | validar-instancia
├── tests/{unit,integracao,e2e,conformidade_solver}/ · tests/fixtures/gravacoes/
├── docs/                         # mkdocs-material + docs/adr/ (ADR-001 a ADR-010)
└── .github/workflows/
```

**Camadas** (import-linter, ADR-010), de cima para baixo; cada uma só importa as de baixo, e as separadas por `|` não se importam entre si:

```
interface | cli | experimento
orquestracao | avaliacao
agentes
validacao | rastreabilidade
solver | llm
modelo | dados
config
dominio
```

Dois contratos adicionais: nenhum módulo do caminho de execução importa `avaliacao`, e `avaliacao` não importa `agentes`, `orquestracao`, `llm` nem `interface`.

## 3. Representação intermediária (D2)

- **Formato: JSON definido por esquema Pydantic.** É o que os dois provedores geram com mais confiabilidade em saída estruturada. Para leitura humana, o modelo é renderizado em LaTeX.
- **Modelo algébrico indexado**, e não expandido: conjuntos, parâmetros indexados, variáveis indexadas e restrições "para todo i em I". O tamanho não cresce com os dados, e a comparação com o gabarito por componente (critério 1) fica natural.
- **Estrutura em JSON, expressões em texto.** Cada restrição é um objeto com `id`, `requisito_id`, domínio e sentido. A expressão é uma string em mini-linguagem algébrica restrita, convertida por gramática Lark em árvore de sintaxe; exemplo: `sum(custo[i] * x[i] for i in PRODUTOS) <= orcamento`.
- **Parâmetros apontam para dados:** `{"id": "custo", "indices": ["PRODUTOS"], "origem": {"arquivo", "coluna", "chave"}, "unidade": "R$/un"}`.
- **Compilador em três estágios:** ModeloIR → (parse e checagem de tipos, índices e unidades) → modelo instanciado neutro → adaptador do solver.
- **Oportunidade (não compromisso):** com o modelo neutro, os duais e custos reduzidos saem do CBC em PL. Isso pode eliminar a limitação (g) da seção 3.11 e reduzir a desvantagem no indicador "Relatórios".
- **Efeito no texto do TG2:** a categoria "Geração de código" da taxonomia vira **"Compilação do modelo"**.

## 4. LLM e solver agnósticos (D3, D6)

**LLM.** Um único adaptador, `OpenAICompativel(base_url, modelo)`, com o SDK `openai`, cobre a OpenAI e a DeepSeek. Não há LangChain nos modelos: o LangGraph só orquestra. Cada modelo tem um perfil YAML com as seguintes capacidades:

- saída estruturada estrita, ou modo JSON com validação e nova tentativa;
- aceita `temperature` (o manifesto grava o valor **efetivamente aplicado**);
- aceita `seed`;
- preço por token.

Os identificadores exatos e as capacidades são conferidos na documentação dos provedores na F2. Atenção: a saída estruturada estrita da OpenAI exige todos os campos como obrigatórios; por isso, o adaptador deriva o esquema enviado ao modelo a partir dos objetos de domínio, e não os envia sem ajuste.

**Solver.** A configuração tem dois eixos: `solver: {backend: pulp, motor: cbc, opcoes: {...}}`.

- O contrato `SolverBackend` recebe o modelo neutro e devolve um `ResultadoSolver` canônico: status padronizado, valores, objetivo, duais, nome e versão.
- Os adaptadores são registrados por entry points. Um solver novo exige um arquivo de adaptador e uma linha no `pyproject.toml`.
- Uma **suíte de conformidade** compartilhada é obrigatória para todo adaptador: PL e PLIM com ótimo conhecido, um caso inviável e um ilimitado. Ela garante o mapeamento de status do qual o S1 depende.

## 5. Experiência no Colab

```python
!pip install -q "po-multiagente @ git+https://github.com/ThiagoBibiano/po-multiagente@v1.0.0"
from po_multiagente import iniciar   # chave da API lida dos Secrets do Colab
iniciar()
```

A interface é um assistente em etapas:

1. **Configurar:** chave, modelo e aviso de privacidade (LGPD).
2. **Descrever:** texto em português, upload das fontes e um botão "carregar exemplo".
3. **Esclarecer:** solicitações de tratamento (arquivo, coluna, forma esperada; o usuário sobe o arquivo tratado) e alertas de ambiguidade. O usuário nunca julga a formulação.
4. **Executar:** progresso por agente e laço do Validador ao vivo.
5. **Resultado:** a explicação vem primeiro; em abas técnicas ficam a especificação, a formulação em LaTeX, o JSON, o log do solver, as validações e o custo.
6. **Exportar dossiê:** ZIP ou HTML, com opção de salvar no Drive.

A sessão pode ser retomada após queda do Colab (checkpointer SQLite no Drive). Há também uma API programática: `Plataforma.nova_sessao(descricao, arquivos).executar()`.

## 6. Itens além do pedido original

1. **Respondedor simulado.** No experimento, as solicitações de tratamento são respondidas com `dados_tratados/` da instância, e só quando batem com `solicitacoes_esperadas.yaml`. Se não baterem, o caso conta como falha de "Solicitação de tratamento".
2. **Executor retomável**, intercalado por instância, com data e hora; 3 execuções com decisão por maioria.
3. **Avaliação pronta para o TG2:** normalização de restrições, precisão e revocação por componente, acurácia de associação, tolerância de 1%, McNemar exato e **exportação de tabelas `.tex`**.
4. **`validar-instancia`:** confere se a referência executa, se bate com a solução e se o gabarito cobre todos os parâmetros.
5. **Reprodutibilidade:** `uv.lock`, hash dos prompts e da configuração, manifesto por execução e **release v1.0 congelada (tag + DOI no Zenodo) antes do experimento**.
6. **Gravar e reproduzir chamadas ao LLM**, para que o CI rode sem rede e sem custo.
7. **Orçamento de tokens** por execução e estimativa de custo antes do experimento.
8. **ADRs** em `docs/adr/`, que servem de base para o capítulo de desenvolvimento do TG2.

## 7. Qualidade

- **Ferramentas:** `uv`, `ruff`, `mypy --strict`, `pytest` com `hypothesis`, `import-linter`, `pre-commit`.
- **CI:** lint → tipos → contratos → testes → e2e com a instância do piloto (gravada), em Python 3.11, 3.12 e 3.13.
- **Cobertura mínima:** ≥ 90% em `dominio`, `dados`, `modelo`, `solver`, `validacao` e `avaliacao`.
- **Processo:** Conventional Commits, SemVer, CHANGELOG, `main` protegida, trabalho em `develop` com PRs pequenos, Dependabot.

## 8. Operação com os repositórios (D9)

O repositório do TG é **público**. Por isso o conjunto-teste não pode ficar nele e ganha um terceiro repositório, pequeno e privado.

| Repositório | Visibilidade | Conteúdo |
|---|---|---|
| `tg-plataforma-multiagente-po` | Público | Texto do TG, `resultados/` importados, `artefato.lock` |
| `po-multiagente` | Público | Código, testes e documentação; nunca contém gabaritos |
| `po-multiagente-conjunto-teste` | Privado até a defesa | As 24 instâncias; o revisor dos gabaritos entra como colaborador |

**Regras de operação:**

1. **Diretórios vizinhos** em `~/Documentos/`. Não há submódulo: o TG precisa só da versão e das saídas, não do código.
2. **Fluxo de mão única, código → texto.** O código nunca conhece o TG. O TG registra em `artefato.lock` a tag, o commit e o DOI da versão usada.
3. **Importação de resultados:** `scripts/importa_resultados.py`, no repositório do TG, copia as tabelas `.tex` e as figuras geradas pelo experimento para `resultados/` e grava um manifesto. O script recusa a cópia se o código não estiver em uma tag limpa.
4. **O conjunto-teste é lido por caminho configurável** (`PO_CONJUNTO_TESTE`). No Colab, é clonado com token guardado nos Secrets.
5. **Edição simultânea:** um workspace multi-raiz do VS Code (`tg2.code-workspace`) no repositório do TG. No Claude Code, `permissions.additionalDirectories` em `.claude/settings.json` com os dois vizinhos, para trabalhar nos três a partir de uma sessão.
6. **Cuidado:** `artigos/` (PDFs de terceiros) não deve ser versionado no repositório público do TG.

## 9. Roteiro

| Fase | Entrega | LLM? | Estado |
|---|---|---|---|
| F0 Fundação | Três repositórios, ferramentas, CI, esqueleto, `dominio`, ADR-001 a ADR-010, workspace e `additionalDirectories` | Não | Concluída localmente; falta publicar no GitHub |
| F1 Núcleo determinístico | `dados`, `modelo` (gramática, checagem, instanciação), `solver` com conformidade, S1–S5; piloto como 1ª instância | Não | Pendente |
| F2 Agentes e orquestração | Porta de LLM, perfis, prompts, os cinco agentes, grafo com e sem Validador, interrupções, gravações | Sim | Pendente |
| F3 Rastreabilidade | Dossiê, manifesto, HTML | Não | Pendente |
| F4 Interface e Colab | Gradio, notebook, Drive, aviso de privacidade | — | Pendente |
| F5 Conjunto-teste (paralelo desde F1) | Formato, `validar-instancia`, 24 instâncias, revisão cruzada | Não | Pendente |
| F6 Avaliação e experimento | Critérios 1–4, McNemar, taxonomia, executor, exportação `.tex` | Sim | Pendente |
| F7 Congelamento | v1.0 + DOI → experimento → `importa_resultados.py` → TG2 | — | Pendente |

**Critério de pronto da F0:** `uv run pre-commit run -a` e `uv run pytest` passando, e um import proibido quebrando o build. A criação dos repositórios no GitHub e o primeiro push são feitos com confirmação do autor.
