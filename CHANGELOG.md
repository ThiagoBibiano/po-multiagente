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
- `po-multiagente validar-instancia`: confere a referência de uma instância
  (esquemas, compilação, ligação, sinais, valor objetivo ou status esperado).
- `Origem.filtros` (célula de tabela longa), `Conjunto.subconjunto_de`,
  `Variavel.requisitos` e fontes em vários diretórios.
- Agentes e orquestração (F2): porta de LLM com adaptador para a API de
  Respostas (gpt-6-luna), esquema estrito derivado do domínio, gravação e
  reprodução de chamadas; Interpretador, Modelador, Gerador-Executor,
  Validador e Explicador; grafo LangGraph com e sem Validador, interrupções
  para tratamento de dados e perguntas ao usuário; comando `calibrar`, com
  respondedor simulado e métricas dos critérios 2 e 3.
- Perfil `sabiazinho-4` (Maritaca), para testes iniciais de baixo custo: o
  perfil passa a definir o endpoint (`url_base`), a variável da chave
  (`variavel_chave`) e a moeda dos preços; `calibrar --perfil` escolhe o
  modelo. O experimento segue com o gpt-6-luna (ADR-012).
- Recusa do provedor por saída fora do esquema (a Maritaca confere a saída
  estrita no servidor e devolve erro 400) vira erro de formato, com nova
  tentativa do agente (ADR-008); o cassete grava e reproduz a recusa.
- Saída cortada no limite de tokens (`max_tokens_reached` na Maritaca,
  `incomplete` por `max_output_tokens` na OpenAI) também vira erro de
  formato, com motivo curto no lugar do texto parcial.
- Erro de referência não declarada lista também as declaradas (por exemplo,
  `Conjuntos sem declaração: produto (declarados: PRODUTOS)`), para que a
  nova tentativa do agente saiba com o que substituí-la.
- Prompt do Modelador: `indices` e `para_todo` recebem o `id` do conjunto,
  nunca o nome do índice, com exemplo.
- Prompt do Modelador: tabela do que a linguagem não tem (`if`, funções,
  pares, `and`) e da forma equivalente em cada caso.
- `Verificacao.confirmacao`: o S5 pergunta ao usuário, em vez de reprovar,
  quando o valor objetivo coincide com uma cota trivial (ADR-011).
