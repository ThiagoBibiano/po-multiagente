"""Execução de um conjunto de instâncias com gabarito: calibração e, depois, experimento.

Para cada instância e configuração (com e sem Validador), roda o grafo com o
respondedor simulado e mede, sem juízo do modelo de linguagem:

- critério 2 (ponta a ponta): o fluxo termina com explicação e com o status
  esperado, sem falha de agente;
- critério 3 (solução correta): status esperado e, com solução, valor
  objetivo dentro de 1% da referência;
- associação parâmetro → coluna (parte do critério 1);
- iterações e sinais do Validador, tentativas de formato, solicitações, tokens
  e custo.
"""

import json
import tempfile
import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from po_multiagente.avaliacao.associacao import acuracia_associacao
from po_multiagente.avaliacao.instancia import EPSILON, Instancia, carregar_instancia
from po_multiagente.config import ConfiguracaoExecucao, carregar_perfil
from po_multiagente.dominio import StatusSolucao
from po_multiagente.experimento.respondedor import RespondedorSimulado
from po_multiagente.experimento.roteiro import roteiro_do_gabarito
from po_multiagente.llm import AdaptadorOpenAI, Cassete, LLMPort
from po_multiagente.orquestracao import Estado, Interrupcao, Sessao
from po_multiagente.prompts import AGENTES_COM_INSTRUCAO, carregar_instrucao

ModoLLM = Literal["chamar", "gravar", "reproduzir", "roteiro"]
MAX_INTERRUPCOES = 6


@dataclass(frozen=True)
class Medida:
    """Resultado de uma execução de uma instância numa configuração."""

    instancia: str
    particao: str
    familia: str
    classe: str
    configuracao: str
    repeticao: int
    ponta_a_ponta: bool
    correta: bool
    status: str
    valor_obtido: float | None
    valor_esperado: float | None
    falha: str | None
    associacao_precisao: float | None
    associacao_revocacao: float | None
    iteracoes_validador: int
    validador_acionado: bool
    sinais_acionados: tuple[str, ...]
    confirmacoes: int
    tentativas_formato: tuple[int, ...]
    solicitacoes_emitidas: int
    solicitacoes_nao_atendidas: int
    chamadas_llm: int
    tokens_entrada: int
    tokens_saida: int
    custo: float
    moeda: str
    duracao_s: float
    eventos: list[dict[str, Any]] = field(default_factory=list)


def pastas_da_particao(conjunto: Path, particao: str, ids: Sequence[str] = ()) -> list[Path]:
    """Instâncias do conjunto na partição pedida (``todas`` para não filtrar)."""
    pastas = sorted(p.parent for p in conjunto.glob("*/meta.yaml"))
    selecionadas = []
    for pasta in pastas:
        instancia = carregar_instancia(pasta)
        if ids and pasta.name not in ids:
            continue
        if particao != "todas" and instancia.meta.get("particao") != particao:
            continue
        selecionadas.append(pasta)
    return selecionadas


def criar_llm(
    modo: ModoLLM, configuracao: ConfiguracaoExecucao, cassete: Path, instancia: Instancia
) -> LLMPort:
    """Modelo de linguagem conforme o modo."""
    if modo == "roteiro":
        return roteiro_do_gabarito(instancia)
    perfil = carregar_perfil(configuracao.perfil_modelo)
    if modo == "reproduzir":
        return Cassete(cassete, "reproduzir", modelo=perfil.modelo)
    real = AdaptadorOpenAI(perfil)
    return Cassete(cassete, "gravar", real) if modo == "gravar" else real


def executar_instancia(
    instancia: Instancia,
    configuracao: ConfiguracaoExecucao,
    llm: LLMPort,
    repeticao: int = 1,
) -> tuple[Medida, Estado]:
    """Roda o fluxo inteiro numa instância, respondendo como o usuário simulado."""
    inicio = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="po-tratados-") as pasta:
        respondedor = RespondedorSimulado(instancia, Path(pasta))
        sessao = Sessao(llm, configuracao)
        passo = sessao.iniciar(instancia.descricao, instancia.pasta / "dados")
        confirmacoes = 0
        emitidas = 0
        for _ in range(MAX_INTERRUPCOES):
            if not isinstance(passo, Interrupcao):
                break
            if passo.tipo == "solicitacoes":
                emitidas += len(passo.conteudo["solicitacoes"])
                passo = sessao.responder(
                    respondedor.responder_solicitacoes(passo.conteudo["solicitacoes"])
                )
            else:
                confirmacoes += 1
                passo = sessao.responder(respondedor.responder_confirmacao())
        estado = sessao.estado
    duracao = time.perf_counter() - inicio
    medida = medir(instancia, configuracao, estado, repeticao, duracao)
    medida = replace(
        medida,
        confirmacoes=confirmacoes,
        solicitacoes_emitidas=emitidas,
        solicitacoes_nao_atendidas=len(respondedor.nao_atendidas),
    )
    return medida, estado


def medir(
    instancia: Instancia,
    configuracao: ConfiguracaoExecucao,
    estado: Estado,
    repeticao: int,
    duracao: float,
) -> Medida:
    """Critérios da execução, comparando o estado final com o gabarito."""
    resultado = estado.get("resultado")
    status = resultado.status if resultado is not None else None
    obtido = resultado.valor_objetivo if resultado is not None else None
    esperado = instancia.valor_esperado
    status_certo = status is instancia.status_esperado
    valor_certo = (
        obtido is None
        if instancia.status_esperado is not StatusSolucao.OTIMO
        else obtido is not None
        and esperado is not None
        and abs(obtido - esperado) <= EPSILON * max(abs(esperado), 1e-9)
    )
    ponta_a_ponta = bool(estado.get("explicacao")) and not estado.get("falha") and status_certo
    especificacao = estado.get("especificacao")
    associacao = (
        acuracia_associacao(especificacao, instancia.especificacao) if especificacao else None
    )
    pareceres = estado.get("pareceres", [])
    sinais = sorted({v.sinal.value for p in pareceres for v in p.verificacoes if not v.aprovada})
    chamadas = estado.get("chamadas", [])
    perfil = carregar_perfil(configuracao.perfil_modelo)
    entrada = sum(c["uso"]["entrada"] for c in chamadas)
    cache = sum(c["uso"]["entrada_em_cache"] for c in chamadas)
    saida = sum(c["uso"]["saida"] for c in chamadas)
    return Medida(
        instancia=instancia.pasta.name,
        particao=str(instancia.meta.get("particao")),
        familia=str(instancia.meta.get("familia")),
        classe=str(instancia.meta.get("classe")),
        configuracao="com_validador" if configuracao.validador else "sem_validador",
        repeticao=repeticao,
        ponta_a_ponta=ponta_a_ponta,
        correta=ponta_a_ponta and valor_certo,
        status=status.value if status is not None else "sem_resultado",
        valor_obtido=obtido,
        valor_esperado=esperado,
        falha=estado.get("falha"),
        associacao_precisao=associacao.precisao if associacao else None,
        associacao_revocacao=associacao.revocacao if associacao else None,
        iteracoes_validador=len(pareceres),
        validador_acionado=any(not p.aprovado for p in pareceres),
        sinais_acionados=tuple(sinais),
        confirmacoes=0,
        tentativas_formato=tuple(estado.get("tentativas_formato", [])),
        solicitacoes_emitidas=0,
        solicitacoes_nao_atendidas=0,
        chamadas_llm=len(chamadas),
        tokens_entrada=entrada,
        tokens_saida=saida,
        custo=perfil.custo(entrada, cache, saida),
        moeda=perfil.moeda,
        duracao_s=duracao,
        eventos=list(estado.get("eventos", [])),
    )


def calibrar(
    pastas: Iterable[Path],
    saida: Path,
    modo: ModoLLM,
    configuracoes: Sequence[ConfiguracaoExecucao],
    repeticoes: int = 1,
) -> list[Medida]:
    """Executa as instâncias em cada configuração e grava os relatórios.

    As configurações são intercaladas por instância (Passo 7): para cada
    instância e repetição, roda-se cada configuração em sequência.
    """
    saida.mkdir(parents=True, exist_ok=True)
    _gravar_manifesto(saida, modo, configuracoes)
    medidas: list[Medida] = []
    for pasta in pastas:
        instancia = carregar_instancia(pasta)
        for repeticao in range(1, repeticoes + 1):
            for configuracao in configuracoes:
                rotulo = f"{pasta.name}__{'com' if configuracao.validador else 'sem'}__r{repeticao}"
                llm = criar_llm(
                    modo, configuracao, saida / "cassetes" / f"{rotulo}.jsonl", instancia
                )
                medida, estado = executar_instancia(instancia, configuracao, llm, repeticao)
                medidas.append(medida)
                _gravar_execucao(saida / "execucoes" / f"{rotulo}.json", medida, estado)
                print(_linha(medida), flush=True)
    (saida / "resumo.md").write_text(resumo(medidas), encoding="utf-8")
    with (saida / "medidas.jsonl").open("w", encoding="utf-8") as arquivo:
        for medida in medidas:
            arquivo.write(
                json.dumps({**asdict(medida), "eventos": None}, ensure_ascii=False) + "\n"
            )
    return medidas


def resumo(medidas: Sequence[Medida]) -> str:
    """Tabela em Markdown por configuração e partição."""
    cabecalho = (
        "Configuração", "Partição", "Execuções", "Ponta a ponta", "Correta",
        "Validador acionado", "Custo",
    )  # fmt: skip
    linhas = ["| " + " | ".join(cabecalho) + " |", "|" + "---|" * len(cabecalho)]
    grupos: dict[tuple[str, str], list[Medida]] = {}
    for medida in medidas:
        grupos.setdefault((medida.configuracao, medida.particao), []).append(medida)
    for (configuracao, particao), grupo in sorted(grupos.items()):
        n = len(grupo)
        celulas = (
            configuracao,
            particao,
            str(n),
            _pct(sum(m.ponta_a_ponta for m in grupo), n),
            _pct(sum(m.correta for m in grupo), n),
            _pct(sum(m.validador_acionado for m in grupo), n),
            f"{grupo[0].moeda} {sum(m.custo for m in grupo):.4f}",
        )
        linhas.append("| " + " | ".join(celulas) + " |")
    falhas = [m for m in medidas if not m.correta]
    if falhas:
        linhas += ["", "## Execuções incorretas", ""]
        linhas += [
            f"- `{m.instancia}` ({m.configuracao}): {m.status}; {m.falha or ''}" for m in falhas
        ]
    return "\n".join(linhas) + "\n"


def _pct(parte: int, total: int) -> str:
    return f"{parte}/{total} ({parte / total:.0%})" if total else "—"


def _linha(medida: Medida) -> str:
    marca = "OK " if medida.correta else ("E2E" if medida.ponta_a_ponta else "---")
    return (
        f"{marca} {medida.instancia:48s} {medida.configuracao:14s} {medida.status:14s} "
        f"obtido={medida.valor_obtido} esperado={medida.valor_esperado} "
        f"it={medida.iteracoes_validador} {medida.moeda} {medida.custo:.4f}"
    )


def _gravar_manifesto(
    saida: Path, modo: str, configuracoes: Sequence[ConfiguracaoExecucao]
) -> None:
    manifesto = {
        "inicio": datetime.now(UTC).isoformat(),
        "modo_llm": modo,
        "versao_pacote": version("po-multiagente"),
        "configuracoes": [c.model_dump() for c in configuracoes],
        "perfis": {
            c.perfil_modelo: carregar_perfil(c.perfil_modelo).model_dump() for c in configuracoes
        },
        "instrucoes_sha256": {a: carregar_instrucao(a).sha256 for a in AGENTES_COM_INSTRUCAO},
    }
    (saida / "manifesto.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _gravar_execucao(caminho: Path, medida: Medida, estado: Estado) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    registro: dict[str, Any] = {"medida": asdict(medida)}
    for chave in ("especificacao", "modelo", "resultado", "explicacao"):
        valor = estado.get(chave)
        registro[chave] = valor.model_dump(mode="json") if isinstance(valor, BaseModel) else None
    registro["pareceres"] = [p.model_dump(mode="json") for p in estado.get("pareceres", [])]
    registro["chamadas"] = estado.get("chamadas", [])
    caminho.write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")
