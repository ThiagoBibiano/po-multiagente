"""Camada de solver agnóstica.

Contrato ``SolverBackend``, registro de adaptadores por entry points e o
adaptador PuLP/CBC. É o único ponto do código que conhece o solver
(ADR-006). Implementado na F1.
"""
