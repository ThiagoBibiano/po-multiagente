"""Registro dos backends de solver por entry points (grupo ``po_multiagente.solvers``)."""

from importlib.metadata import entry_points

from po_multiagente.solver.contrato import ErroSolver, SolverBackend

GRUPO = "po_multiagente.solvers"


def backends_disponiveis() -> tuple[str, ...]:
    """Nomes dos backends instalados, em ordem alfabética."""
    return tuple(sorted(ponto.name for ponto in entry_points(group=GRUPO)))


def obter_backend(nome: str) -> SolverBackend:
    """Instancia o backend registrado com esse nome.

    Raises:
        ErroSolver: Se não houver backend com esse nome ou se o objeto
            registrado não cumprir o contrato.
    """
    pontos = entry_points(group=GRUPO, name=nome)
    if not pontos:
        disponiveis = ", ".join(backends_disponiveis()) or "nenhum"
        raise ErroSolver(f"Backend de solver {nome!r} não registrado; disponíveis: {disponiveis}")
    (ponto,) = pontos
    backend = ponto.load()()
    if not isinstance(backend, SolverBackend):
        raise ErroSolver(f"O backend {nome!r} não cumpre o contrato SolverBackend")
    return backend
