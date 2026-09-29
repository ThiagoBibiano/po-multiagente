"""Instâncias com gabarito: leitura e validação (``validar-instancia``).

Formato de uma instância, igual no conjunto de calibração e no conjunto-teste::

    <id>/
    ├── descricao.md            # pedido do gestor, em português
    ├── dados/*.csv|xlsx        # fontes, em vocabulário operacional
    ├── dados_tratados/         # respostas às solicitações de tratamento, se houver
    ├── referencia/quadro.json  # quadro de especificação de referência, sem "fontes"
    ├── referencia/modelo.json  # formulação de referência (ModeloIR)
    ├── solucao.json            # valor objetivo e fonte; ou {"status": "inviavel"}
    └── meta.yaml               # família, classe, origem, partição...

As fontes do quadro são preenchidas pelo inventário dos dados, com o hash de
cada arquivo; o gabarito de associação (parâmetro → arquivo e coluna) é o
próprio quadro de referência.

Este módulo lê gabaritos: por contrato (ADR-010), nenhum módulo do caminho
de execução pode importá-lo.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from po_multiagente.dados import ErroDados, ErroLigacao, Fontes, ligar
from po_multiagente.dominio import (
    Especificacao,
    ModeloIR,
    ResultadoSolver,
    Sinal,
    StatusSolucao,
    TipoVariavel,
    Verificacao,
)
from po_multiagente.modelo import (
    ErroCompilacao,
    ErroInstanciacao,
    ModeloInstanciado,
    compilar,
    instanciar,
)
from po_multiagente.solver import OpcoesSolver, obter_backend
from po_multiagente.validacao import (
    sinal_s1_status,
    sinal_s2_unidades,
    sinal_s3_parametros,
    sinal_s4_requisitos,
    sinal_s5_limites,
)

EPSILON = 0.01
"""Tolerância relativa do critério 3 (cap. 3, Passo 7), fixada antes da coleta."""

FAMILIAS = frozenset({"alocacao", "mistura", "transporte"})
CLASSES = frozenset({"pl", "plim"})


@dataclass(frozen=True)
class Instancia:
    """Instância lida do disco, com o quadro já completado pelo inventário."""

    pasta: Path
    descricao: str
    fontes: Fontes
    especificacao: Especificacao
    modelo: ModeloIR
    status_esperado: StatusSolucao
    valor_esperado: float | None
    meta: dict[str, Any]


@dataclass(frozen=True)
class RelatorioInstancia:
    """Resultado de ``validar_instancia``.

    Attributes:
        problemas: O que impede a instância de entrar no conjunto.
        avisos: O que merece revisão, mas não impede.
    """

    pasta: Path
    problemas: tuple[str, ...]
    avisos: tuple[str, ...] = ()
    valor_obtido: float | None = None
    valor_esperado: float | None = None
    verificacoes: tuple[Verificacao, ...] = field(default=())

    @property
    def valida(self) -> bool:
        """Indica se a instância pode entrar no conjunto."""
        return not self.problemas


class ErroInstancia(Exception):
    """Instância incompleta ou com arquivo ilegível."""


def carregar_instancia(pasta: Path) -> Instancia:
    """Lê a instância de ``pasta``.

    Raises:
        ErroInstancia: Se faltar arquivo ou algum não seguir o esquema.
    """
    try:
        tratados = pasta / "dados_tratados"
        fontes = Fontes(pasta / "dados", *([tratados] if tratados.is_dir() else []))
        quadro = json.loads((pasta / "referencia" / "quadro.json").read_text(encoding="utf-8"))
        quadro["fontes"] = [f.model_dump(mode="json") for f in fontes.inventario()]
        especificacao = Especificacao.model_validate(quadro)
        modelo = ModeloIR.model_validate_json(
            (pasta / "referencia" / "modelo.json").read_text(encoding="utf-8")
        )
        solucao = json.loads((pasta / "solucao.json").read_text(encoding="utf-8"))
        meta = yaml.safe_load((pasta / "meta.yaml").read_text(encoding="utf-8")) or {}
        descricao = (pasta / "descricao.md").read_text(encoding="utf-8").strip()
    except (OSError, ValueError, ErroDados, yaml.YAMLError) as erro:
        raise ErroInstancia(f"{pasta.name}: {erro}") from erro
    return Instancia(
        pasta=pasta,
        descricao=descricao,
        fontes=fontes,
        especificacao=especificacao,
        modelo=modelo,
        status_esperado=StatusSolucao(solucao.get("status", StatusSolucao.OTIMO.value)),
        valor_esperado=(float(solucao["valor_objetivo"]) if "valor_objetivo" in solucao else None),
        meta=meta,
    )


def validar_instancia(
    pasta: Path, *, backend: str = "pulp", motor: str = "cbc", epsilon: float = EPSILON
) -> RelatorioInstancia:
    """Confere se a referência executa, bate com a solução e cobre o quadro.

    Verifica: arquivos e esquemas; metadados (família e classe, e classe
    coerente com os tipos das variáveis); compilação, ligação e resolução da
    referência; os cinco sinais do Validador; o valor objetivo dentro de
    ``epsilon`` da solução registrada; e que todo parâmetro do quadro é usado
    pela referência.
    """
    try:
        instancia = carregar_instancia(pasta)
    except ErroInstancia as erro:
        return RelatorioInstancia(pasta=pasta, problemas=(str(erro),))
    problemas = _problemas_de_meta(instancia)
    avisos: list[str] = []
    usados = {p.id for p in instancia.modelo.parametros}
    problemas += [
        f"parâmetro {p.id!r} do quadro não é usado pela referência"
        for p in instancia.especificacao.parametros
        if p.id not in usados
    ]
    try:
        compilado = compilar(instancia.modelo)
        dados = ligar(instancia.modelo, instancia.especificacao, instancia.fontes)
        modelo = instanciar(compilado, dados.conjuntos, dados.parametros)
    except (ErroCompilacao, ErroLigacao, ErroInstanciacao) as erro:
        return RelatorioInstancia(pasta=pasta, problemas=(*problemas, str(erro)))
    solver = obter_backend(backend)

    def resolver(m: ModeloInstanciado) -> ResultadoSolver:
        return solver.resolver(m, motor=motor, opcoes=OpcoesSolver()).resultado

    resultado = resolver(modelo)
    verificacoes = (
        sinal_s1_status(resultado, modelo, resolver),
        sinal_s2_unidades(compilado, instancia.especificacao),
        sinal_s3_parametros(instancia.modelo, instancia.especificacao),
        sinal_s4_requisitos(instancia.modelo, instancia.especificacao),
        sinal_s5_limites(modelo, resultado, criterio=instancia.especificacao.criterio),
    )
    # Numa instância sem solução por construção, a reprovação do S1 é o esperado.
    problemas += [
        f"{v.sinal.value}: {v.mensagem}"
        for v in verificacoes
        if not v.aprovada
        and not (v.sinal is Sinal.S1 and instancia.status_esperado is not StatusSolucao.OTIMO)
    ]
    avisos += [f"{v.sinal.value}: {v.confirmacao}" for v in verificacoes if v.confirmacao]
    obtido = resultado.valor_objetivo
    esperado = instancia.valor_esperado
    if resultado.status is not instancia.status_esperado:
        problemas.append(
            f"a referência termina com status {resultado.status.value}; a solução registrada "
            f"diz {instancia.status_esperado.value}"
        )
    elif obtido is not None and esperado is None:
        problemas.append("solucao.json não registra o valor objetivo")
    elif (
        obtido is not None
        and esperado is not None
        and abs(obtido - esperado) > epsilon * max(abs(esperado), 1e-9)
    ):
        problemas.append(
            f"valor objetivo da referência ({obtido:g}) difere da solução registrada "
            f"({esperado:g}) além de {epsilon:.0%}"
        )
    if any(ch.isdigit() for ch in instancia.descricao):
        avisos.append("a descrição tem dígitos; os valores deveriam vir só dos dados")
    return RelatorioInstancia(
        pasta=pasta,
        problemas=tuple(problemas),
        avisos=tuple(avisos),
        valor_obtido=obtido,
        valor_esperado=esperado,
        verificacoes=verificacoes,
    )


def _problemas_de_meta(instancia: Instancia) -> list[str]:
    meta = instancia.meta
    problemas = []
    if meta.get("familia") not in FAMILIAS:
        problemas.append(f"meta.yaml: família {meta.get('familia')!r} fora de {sorted(FAMILIAS)}")
    if meta.get("classe") not in CLASSES:
        problemas.append(f"meta.yaml: classe {meta.get('classe')!r} fora de {sorted(CLASSES)}")
    inteira = any(v.tipo is not TipoVariavel.CONTINUA for v in instancia.modelo.variaveis)
    if meta.get("classe") in CLASSES and (meta["classe"] == "plim") != inteira:
        problemas.append(
            f"meta.yaml: classe {meta['classe']!r}, mas a referência "
            + ("tem" if inteira else "não tem")
            + " variável inteira"
        )
    return problemas
