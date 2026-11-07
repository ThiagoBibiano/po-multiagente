"""Avaliação do artefato contra os gabaritos (Passo 7).

- ``instancia``: leitura e validação das instâncias com gabarito;
- ``associacao``: acurácia da associação parâmetro → coluna;
- ``formulacao``: critério 1, por componente, com normalização e
  equivalência conferida pelo solver;
- ``resultados``: maioria entre repetições, McNemar exato, recortes por
  faixa e origem, critério 4, categoria sugerida das falhas e tabelas
  ``.tex``.

Nenhum módulo do caminho de execução pode importar este pacote (contrato no
``pyproject.toml``).
"""
