"""Camada de solver agnóstica (ADR-006).

Contrato ``SolverBackend``, registro de adaptadores por entry points e o
adaptador PuLP/CBC. É o único ponto do código que conhece o solver; nome,
motor e versão entram em todo resultado.
"""

from po_multiagente.solver.contrato import ErroSolver, ExecucaoSolver, OpcoesSolver, SolverBackend
from po_multiagente.solver.registro import GRUPO, backends_disponiveis, obter_backend

__all__ = [
    "GRUPO",
    "ErroSolver",
    "ExecucaoSolver",
    "OpcoesSolver",
    "SolverBackend",
    "backends_disponiveis",
    "obter_backend",
]
