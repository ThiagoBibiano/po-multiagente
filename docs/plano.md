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
| D3 | LLM **agnóstico**; modelo escolhido: **gemini-3.5-flash-lite** (Google, nível gratuito), na ADR-014; antes, gpt-6-luna (ADR-012) | Aprovada |
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
| F0 Fundação | Três repositórios, ferramentas, CI, esqueleto, `dominio`, ADR-001 a ADR-010, workspace e `additionalDirectories` | Não | Concluída |
| F1 Núcleo determinístico | `dados`, `modelo` (gramática, checagem, instanciação), `solver` com conformidade, S1–S5; piloto como 1ª instância | Não | Concluída, exceto o piloto (seção 10) |
| F1b Conjunto de calibração | 36 instâncias (repositório privado, `CALIBRACAO.md`), `validar-instancia` | Não | Concluída: 36/36 válidas |
| F2 Agentes e orquestração | Porta de LLM, perfis, prompts, os cinco agentes, grafo com e sem Validador, interrupções, gravações | Sim | Concluída: meta atingida na conferência; prompts congelados (seção 11) |
| F3 Rastreabilidade | Dossiê, manifesto, HTML | Não | Pendente |
| F4 Interface e Colab | Gradio, notebook, Drive, aviso de privacidade; **teste com o usuário** quando a F2 atingir a meta na partição de conferência | — | Mínima implementada (seção 11): Gradio, notebook e aviso. Faltam Drive, retomada e o teste com o usuário |
| F5 Conjunto-teste (paralelo desde F1) | Formato, `validar-instancia`, 24 instâncias, revisão cruzada | Não | Pendente |
| F6 Avaliação e experimento | Critérios 1–4, McNemar, taxonomia, executor, exportação `.tex` | Sim | Pendente |
| F7 Congelamento | v1.0 + DOI → experimento → `importa_resultados.py` → TG2 | — | Pendente |

**Meta de versão efetiva (aprovada em 26/09/2026):** na partição de conferência, ≥ 80% de ponta a ponta (critério 2) e ≥ 70% de solução correta (critério 3).

**Ordem de trabalho (decidida em 26/09/2026):** F1 → F1b → F2, calibrada no conjunto de calibração → F4 mínima (interface) → teste com o usuário → F3, F5 e F6. O conjunto-teste só é executado depois que os prompts forem congelados.

**Critério de pronto da F0:** `uv run pre-commit run -a` e `uv run pytest` passando, e um import proibido quebrando o build. A criação dos repositórios no GitHub e o primeiro push são feitos com confirmação do autor.

## 10. Notas da F1 (26/09/2026)

**Entregue.** `dados` (CSV/XLSX somente leitura, inventário, hash, ligação), `modelo` (gramática Lark, compilação, instanciação neutra, unidades, LaTeX), `solver` (contrato, registro, PuLP/CBC 2.10.3, suíte de conformidade) e `validacao` (S1–S5). Um teste de integração percorre o núcleo de ponta a ponta numa instância sintética. A mini-linguagem está documentada em [gramatica.md](gramatica.md), que servirá de base ao prompt do Modelador.

**Decisões tomadas na implementação** (revisáveis antes da F7):

| Decisão | Motivo |
|---|---|
| Não linearidade (produto de variáveis, divisão por variável) é erro de compilação, e não sinal do Validador | O modelo não chega ao solver; pela ADR-008, volta ao Modelador igual nas duas configurações |
| S1 localiza a causa: famílias de restrições incompatíveis (filtro de deleção) ou variáveis sem limite | O CBC não fornece IIS; sem localização, o S1 não atende ao princípio de "localizar" do cap. 3 |
| S5 = viabilidade da solução conferida com os dados + **pergunta ao usuário** na cota trivial | ADR-011 |
| `Origem.filtros`, `Conjunto.subconjunto_de`, `Variavel.requisitos`, fontes em várias pastas | Lacunas encontradas ao montar a calibração (tabelas longas, subconjuntos, requisito atendido pelo domínio, arquivos tratados) |
| Constantes na expressão (`<= 200`) são aceitas e adotam a unidade do outro lado | Ver ponto em aberto 1 |
| `pulp>=3.3,<4` | O PuLP 4 remove o CBC 2.10.3 embutido (ADR-006) |

**Pontos em aberto para o autor:**

1. **Constantes da descrição.** Um limite escrito no texto ("200 horas") não tem arquivo nem coluna, e `Origem` exige os dois. Hoje ele entra como número na expressão, sem unidade e sem rastreio. Proposta para a F2: uma origem `descricao` com o trecho citado, conferida por código (o número tem de aparecer literalmente no trecho, e o trecho na descrição).
2. **Alcance do S5.** Resolvido pela ADR-011: a cota trivial vira pergunta ao usuário, e não reprovação. Continua em aberto como responder a essa pergunta no experimento (F6).
3. **Piloto como 1ª instância.** Recuperado nos protótipos em Colab (Drive do autor, 28 a 30/07/2026): `piloto_marcenaria`, com mesas e cadeiras, madeira e horas de montagem, margem de 90 e 50, e ótimo inteiro de 4950 (55 mesas e nenhuma cadeira). O mesmo protótipo tem uma variante `hostil_marcenaria` (jargão, unidades divergentes, colunas e linhas irrelevantes, mesmo ótimo) e uma instância de mistura (ração, ótimo de 1420,95). Falta decidir onde essas instâncias entram (ver a proposta de conjunto de desenvolvimento).

## 11. Estado em 28/09/2026

**Calibração na partição de ajuste** (24 instâncias, 1 repetição, com e sem Validador):

| Modelo | Corretas com / sem Validador | Custo da rodada |
|---|---|---|
| gemini-3.5-flash-lite (nível gratuito) | 22/24 e 22/24 (92%) | zero (US$ 0,37 no pago) |
| sabiazinho-4 (Maritaca, flex) | 8/24 e 9/24 | R$ 0,77 |
| gpt-6-luna | não testado: conta da OpenAI sem créditos | — |

- O sabiazinho travava no Modelador (índices, `if` no somatório, `para_todo` duplicado). Os ajustes de prompt levaram-no de 0 a cerca de 10 acertos, mas a variação entre rodadas iguais é do mesmo tamanho. O Gemini quase não precisou de novas tentativas de formato (1 em 62).
- O adaptador fala a API de Respostas e a de Chat Completions (`api` no perfil), trata recusa por esquema e saída cortada como erro de formato (ADR-008) e registra o nível de serviço aplicado. Perfis: `gpt-6-luna`, `sabiazinho-4`, `sabiazinho-4-flex` e `gemini-3.5-flash-lite`.
- Nota: no nível gratuito, a Google usa os dados para melhorar os produtos. O autor aceita isso; o critério é o custo mínimo viável.
- A a07 (banco) falhou com todos os modelos; convém revisar o enunciado e o gabarito.

**Próximos passos:**

1. ~~Decidir o modelo do experimento.~~ Decidido em 28/09/2026: gemini-3.5-flash-lite, no nível gratuito (ADR-014), perfil padrão.
2. ~~Rodar a partição de conferência.~~ Feito em 28/09/2026, com o gemini-3.5-flash-lite:

   | Conferência (12) | Ponta a ponta | Corretas |
   |---|---|---|
   | Com Validador | 11/12 (92%) | 11/12 (92%) |
   | Sem Validador | 12/12 (100%) | 10/12 (83%) |

   Meta atingida nas duas configurações. O Validador corrigiu v08 e v12 (valores errados sem ele) e errou na v02 (esgotou as três iterações nos sinais S1 e S2). **Prompts congelados**: os hashes estão em `tests/unit/test_prompts_congelados.py`, e mudar um prompt quebra o teste.
3. Levar os branches empilhados (F1 → F1b → F2 → PoC) ao `develop` num único PR.
4. ~~F4 mínima.~~ Feita em 29/09/2026 (branch `feat/f4-interface`): `Assistente` testável sem Gradio, interface em etapas, exemplo da marcenaria e notebook `notebooks/colab.ipynb`. O exemplo, com o Gemini, chega a 4950 (55 mesas). Ficam para depois: progresso por agente ao vivo, dossiê (F3), Drive e retomada da sessão.
5. Teste com o usuário no Colab. Primeiras observações do autor (29/09/2026): não havia sinal de execução depois do clique, e o texto não era voltado ao usuário final. Corrigido: andamento por agente ao vivo, textos novos e detalhes técnicos recolhidos. **Em aberto:** usar só com a descrição, sem planilha. Hoje não funciona (o Interpretador não acha origem para os parâmetros), e é coerente com o desenho: os números vêm das planilhas, nunca do modelo de linguagem.

**Observação do teste do exemplo:** a explicação disse que a madeira foi "esgotada", mas o plano usa 275 de 300 m². O Explicador só confere números (ADR-013); afirmações qualitativas sobre folga dos recursos passam sem checagem. Candidato a sinal no Explicador, ou a relatar como limitação.
