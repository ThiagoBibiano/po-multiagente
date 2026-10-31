"""Resultados do experimento (cap. 3, Passos 7 e 8).

Trabalha sobre os registros de execução gravados pelo executor
(``execucoes/*.json``), sem depender dele:

1. **Reavaliação.** O critério 1 é recalculado a partir do modelo e do quadro
   gravados, e os metadados (faixa, origem, família, classe) vêm do
   conjunto, e não do que foi gravado na hora.
2. **Maioria.** Cada instância é correta numa configuração quando acerta em
   mais da metade das repetições (duas de três), separadamente nos
   critérios 1, 2 e 3.
3. **Comparação pareada.** Tabela de McNemar por critério e teste exato
   (binomial bilateral sobre as células b e c).
4. **Recortes.** Proporções por faixa, origem e família, em cada
   configuração; critério 4 (acionamentos, iterações e sinais).
5. **Falhas.** Sugestão da categoria da taxonomia pela primeira etapa em que
   a divergência aparece; a classificação final é conferida à mão.

Saídas: ``avaliacao.md`` e ``tabelas/*.tex`` (para o texto do TG).
"""

import json
import math
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from po_multiagente.avaliacao.instancia import (
    ErroInstancia,
    Instancia,
    avaliar_formulacao,
    carregar_instancia,
)
from po_multiagente.dominio import Especificacao, ModeloIR

Registro = dict[str, Any]

COM, SEM = "com_validador", "sem_validador"
CONFIGURACOES = (COM, SEM)
CRITERIOS = {
    "1": ("formulacao_correta", "Formulação correta"),
    "2": ("ponta_a_ponta", "Resolução de ponta a ponta"),
    "3": ("correta", "Solução correta"),
}
RECORTES = {"faixa": "Faixa", "origem": "Origem", "familia": "Família", "classe": "Classe"}
NOMES_CONFIGURACAO = {COM: "Com Validador", SEM: "Sem Validador"}


@dataclass(frozen=True)
class Decisao:
    """Uma instância numa configuração, depois da maioria entre as repetições."""

    instancia: str
    configuracao: str
    execucoes: int
    criterios: dict[str, bool]
    meta: dict[str, Any]


@dataclass(frozen=True)
class Pareada:
    """Tabela de McNemar de um critério (cap. 3, Tabela de pares)."""

    criterio: str
    a: int
    b: int
    c: int
    d: int

    @property
    def p_valor(self) -> float:
        """Valor-p do teste de McNemar exato."""
        return mcnemar_exato(self.b, self.c)


# --------------------------------------------------------------- leitura


def ler_registros(saida: Path) -> list[Registro]:
    """Registros de execução gravados em ``saida/execucoes``."""
    return [
        json.loads(caminho.read_text(encoding="utf-8"))
        for caminho in sorted((saida / "execucoes").glob("*.json"))
    ]


def reavaliar(
    registros: Iterable[Registro],
    conjunto: Path,
    formulacao: Callable[[Instancia, ModeloIR, Especificacao], Any] = avaliar_formulacao,
) -> list[Registro]:
    """Medidas com o critério 1 recalculado e os metadados do conjunto.

    Args:
        registros: Conteúdo dos arquivos de ``execucoes/``.
        conjunto: Pasta com as instâncias.
        formulacao: Comparação do critério 1 (substituível nos testes).
    """
    instancias: dict[str, Instancia | None] = {}
    medidas = []
    for registro in registros:
        medida = dict(registro["medida"])
        nome = medida["instancia"]
        if nome not in instancias:
            try:
                instancias[nome] = carregar_instancia(conjunto / nome)
            except ErroInstancia:
                instancias[nome] = None
        instancia = instancias[nome]
        if instancia is not None:
            for chave in ("faixa", "origem", "familia", "classe"):
                medida[chave] = instancia.meta.get(chave)
            comparacao = None
            if registro.get("modelo") and registro.get("especificacao"):
                comparacao = formulacao(
                    instancia,
                    ModeloIR.model_validate(registro["modelo"]),
                    Especificacao.model_validate(registro["especificacao"]),
                )
            medida["formulacao_correta"] = comparacao is not None and comparacao.correta
            medida["formulacao"] = (
                {k: [c.precisao, c.revocacao] for k, c in comparacao.componentes.items()}
                if comparacao
                else {}
            )
            medida["divergencias_formulacao"] = list(comparacao.divergencias) if comparacao else []
        medidas.append(medida)
    return medidas


# ----------------------------------------------------------- estatística


def mcnemar_exato(b: int, c: int) -> float:
    """Valor-p bilateral do teste de McNemar exato (binomial com p = 1/2)."""
    n = b + c
    if n == 0:
        return 1.0
    cauda = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / math.pow(2, n)
    return min(1.0, 2 * cauda)


def decidir(medidas: Iterable[Registro]) -> dict[tuple[str, str], Decisao]:
    """Maioria entre as repetições, por instância e configuração."""
    grupos: dict[tuple[str, str], list[Registro]] = {}
    for medida in medidas:
        grupos.setdefault((medida["instancia"], medida["configuracao"]), []).append(medida)
    decisoes = {}
    for (instancia, configuracao), grupo in sorted(grupos.items()):
        n = len(grupo)
        decisoes[instancia, configuracao] = Decisao(
            instancia=instancia,
            configuracao=configuracao,
            execucoes=n,
            criterios={
                c: 2 * sum(bool(m.get(campo)) for m in grupo) > n
                for c, (campo, _) in CRITERIOS.items()
            },
            meta={k: grupo[0].get(k) for k in RECORTES},
        )
    return decisoes


def pareadas(decisoes: Mapping[tuple[str, str], Decisao]) -> list[Pareada]:
    """Tabela de McNemar de cada critério, só com instâncias nas duas configurações."""
    instancias = sorted({i for i, _ in decisoes if (i, COM) in decisoes and (i, SEM) in decisoes})
    tabelas = []
    for criterio in CRITERIOS:
        celulas = Counter(
            (decisoes[i, COM].criterios[criterio], decisoes[i, SEM].criterios[criterio])
            for i in instancias
        )
        tabelas.append(
            Pareada(
                criterio,
                a=celulas[True, True],
                b=celulas[True, False],
                c=celulas[False, True],
                d=celulas[False, False],
            )
        )
    return tabelas


def proporcoes(
    decisoes: Mapping[tuple[str, str], Decisao], recorte: str | None = None
) -> dict[tuple[str, str, str], tuple[int, int]]:
    """Acertos e total por (grupo do recorte, configuração, critério)."""
    contagem: dict[tuple[str, str, str], tuple[int, int]] = {}
    for decisao in decisoes.values():
        grupo = "todas" if recorte is None else str(decisao.meta.get(recorte) or "—")
        for criterio, certo in decisao.criterios.items():
            chave = (grupo, decisao.configuracao, criterio)
            acertos, total = contagem.get(chave, (0, 0))
            contagem[chave] = (acertos + certo, total + 1)
    return contagem


def criterio_4(medidas: Sequence[Registro]) -> dict[str, Any]:
    """Acionamentos, iterações e sinais do Validador, por execução com Validador."""
    com = [m for m in medidas if m["configuracao"] == COM]
    sinais = Counter(s for m in com for s in m.get("sinais_acionados") or ())
    return {
        "execucoes": len(com),
        "acionado": sum(bool(m.get("validador_acionado")) for m in com),
        "iteracoes_media": (
            sum(m.get("iteracoes_validador", 0) for m in com) / len(com) if com else 0.0
        ),
        "iteracoes_max": max((m.get("iteracoes_validador", 0) for m in com), default=0),
        "sinais": dict(sorted(sinais.items())),
    }


def associacao_media(medidas: Sequence[Registro]) -> dict[str, tuple[float, float]]:
    """Precisão e revocação médias da associação, por configuração."""
    medias = {}
    for configuracao in CONFIGURACOES:
        grupo = [
            m
            for m in medidas
            if m["configuracao"] == configuracao and m.get("associacao_precisao") is not None
        ]
        if grupo:
            medias[configuracao] = (
                sum(m["associacao_precisao"] for m in grupo) / len(grupo),
                sum(m["associacao_revocacao"] for m in grupo) / len(grupo),
            )
    return medias


# --------------------------------------------------------------- falhas


def categoria_sugerida(medida: Registro) -> str | None:
    """Primeira etapa em que a divergência aparece (taxonomia do Passo 8).

    Só usa o que é medido sem juízo; ``Interpretação`` (requisitos) e
    ``Interação`` dependem de leitura humana. Devolve ``None`` numa execução
    correta nos três critérios.
    """
    if medida.get("correta") and medida.get("formulacao_correta"):
        return None
    if medida.get("solicitacoes_nao_atendidas"):
        return "Solicitação de tratamento"
    if medida.get("associacao_precisao") is None:
        return "Interpretação (sem quadro de especificação)"
    if medida["associacao_precisao"] < 1 or medida["associacao_revocacao"] < 1:
        return "Parametrização"
    if not medida.get("formulacao"):
        return "Compilação do modelo"
    if not medida.get("formulacao_correta"):
        return "Formulação"
    if medida.get("status") == "erro":
        return "Execução"
    return "A classificar"


def encadeamento_validador(
    medida: Registro, decisoes: Mapping[tuple[str, str], Decisao]
) -> str | None:
    """Sinal de falha de validação, para conferência manual.

    ``erro aprovado``: execução incorreta com Validador que não o acionou.
    ``possível correção indevida``: o Validador agiu numa instância que, sem
    ele, fica correta pela maioria e, com ele, não.
    """
    if medida["configuracao"] != COM or medida.get("correta"):
        return None
    if not medida.get("validador_acionado"):
        return "erro aprovado"
    sem = decisoes.get((medida["instancia"], SEM))
    if sem is not None and sem.criterios["3"]:
        return "possível correção indevida"
    return None


# --------------------------------------------------------------- relatório


def relatorio(medidas: Sequence[Registro]) -> tuple[str, dict[str, str]]:
    """Resumo em Markdown e tabelas em LaTeX."""
    decisoes = decidir(medidas)
    tabelas_mcnemar = pareadas(decisoes)
    md = ["# Avaliação", ""]
    md += [
        f"{len(medidas)} execuções; {len({i for i, _ in decisoes})} instâncias. "
        "Decisão por maioria entre as repetições.",
        "",
        "## Critérios 1 a 3",
        "",
        "| Critério | Com Validador | Sem Validador | a | b | c | d | p (McNemar exato) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    geral = proporcoes(decisoes)
    for t in tabelas_mcnemar:
        com = geral.get(("todas", COM, t.criterio), (0, 0))
        sem = geral.get(("todas", SEM, t.criterio), (0, 0))
        md.append(
            f"| {t.criterio}. {CRITERIOS[t.criterio][1]} | {_pct(*com)} | {_pct(*sem)} "
            f"| {t.a} | {t.b} | {t.c} | {t.d} | {t.p_valor:.3f} |"
        )
    for recorte, titulo in RECORTES.items():
        md += ["", f"## Por {titulo.lower()}", "", _tabela_recorte_md(decisoes, recorte)]
    c4 = criterio_4(medidas)
    md += [
        "",
        "## Critério 4: Validador",
        "",
        f"- Acionado em {_pct(c4['acionado'], c4['execucoes'])} das execuções com Validador.",
        f"- Iterações: média {c4['iteracoes_media']:.2f}, máximo {c4['iteracoes_max']}.",
        "- Sinais que o acionaram: "
        + (", ".join(f"{s} ({n})" for s, n in c4["sinais"].items()) or "nenhum")
        + ".",
    ]
    associacao = associacao_media(medidas)
    if associacao:
        md += ["", "## Associação parâmetro → coluna (média por execução)", ""]
        md += [
            f"- {NOMES_CONFIGURACAO[c]}: precisão {p:.3f}, revocação {r:.3f}"
            for c, (p, r) in associacao.items()
        ]
    md += ["", "## Execuções com falha (categoria sugerida, a conferir)", ""]
    for medida in medidas:
        categoria = categoria_sugerida(medida)
        if categoria is None:
            continue
        validacao = encadeamento_validador(medida, decisoes)
        md.append(
            f"- `{medida['instancia']}` {medida['configuracao']} r{medida.get('repeticao', 1)}: "
            f"{categoria}" + (f"; validação: {validacao}" if validacao else "")
        )
    tex = {
        "criterios": _tex_criterios(tabelas_mcnemar, geral),
        **{
            f"recorte_{recorte}": _tex_recorte(decisoes, recorte, titulo)
            for recorte, titulo in RECORTES.items()
        },
        "validador": _tex_validador(c4),
    }
    return "\n".join(md) + "\n", tex


def avaliar(saida: Path, conjunto: Path) -> str:
    """Reavalia as execuções de ``saida`` e grava ``avaliacao.md`` e ``tabelas/``."""
    medidas = reavaliar(ler_registros(saida), conjunto)
    texto, tabelas = relatorio(medidas)
    (saida / "avaliacao.md").write_text(texto, encoding="utf-8")
    pasta = saida / "tabelas"
    pasta.mkdir(exist_ok=True)
    for nome, conteudo in tabelas.items():
        (pasta / f"{nome}.tex").write_text(conteudo, encoding="utf-8")
    with (saida / "medidas_avaliadas.jsonl").open("w", encoding="utf-8") as arquivo:
        for medida in medidas:
            arquivo.write(json.dumps({**medida, "eventos": None}, ensure_ascii=False) + "\n")
    return texto


# --------------------------------------------------------------- formatação


def _pct(acertos: int, total: int) -> str:
    return f"{acertos}/{total} ({acertos / total:.0%})" if total else "—"


def _pct_tex(acertos: int, total: int) -> str:
    return f"{acertos}/{total} ({round(100 * acertos / total)}\\%)" if total else "---"


def _decimal_tex(valor: float, casas: int = 3) -> str:
    return f"{valor:.{casas}f}".replace(".", "{,}")


def _grupos(decisoes: Mapping[tuple[str, str], Decisao], recorte: str) -> list[str]:
    return sorted({str(d.meta.get(recorte) or "—") for d in decisoes.values()})


def _tabela_recorte_md(decisoes: Mapping[tuple[str, str], Decisao], recorte: str) -> str:
    contagem = proporcoes(decisoes, recorte)
    linhas = [
        "| Grupo | Configuração | " + " | ".join(f"Crit. {c}" for c in CRITERIOS) + " |",
        "|---|---|" + "---|" * len(CRITERIOS),
    ]
    for grupo in _grupos(decisoes, recorte):
        for configuracao in CONFIGURACOES:
            celulas = [_pct(*contagem.get((grupo, configuracao, c), (0, 0))) for c in CRITERIOS]
            linhas.append(
                f"| {grupo} | {NOMES_CONFIGURACAO[configuracao]} | " + " | ".join(celulas) + " |"
            )
    return "\n".join(linhas)


def _ambiente_tex(legenda: str, rotulo: str, colunas: str, corpo: list[str]) -> str:
    return "\n".join(
        [
            "% Gerado por po-multiagente avaliar; não editar à mão.",
            "\\begin{table}[htbp]",
            f"\\caption{{{legenda}}}",
            f"\\label{{t:{rotulo}}}",
            "\\centering",
            "\\small",
            f"\\begin{{tabular}}{{{colunas}}}",
            "\\toprule",
            *corpo,
            "\\bottomrule",
            "\\end{tabular}",
            "\\fontenota{elaborado pelo autor}",
            "\\end{table}",
            "",
        ]
    )


def _tex_criterios(
    tabelas: Sequence[Pareada], geral: Mapping[tuple[str, str, str], tuple[int, int]]
) -> str:
    corpo = [
        "Critério & Com Validador & Sem Validador & $b$ & $c$ & Valor-p \\\\",
        "\\midrule",
    ]
    for t in tabelas:
        com = geral.get(("todas", COM, t.criterio), (0, 0))
        sem = geral.get(("todas", SEM, t.criterio), (0, 0))
        corpo.append(
            f"{t.criterio}. {CRITERIOS[t.criterio][1]} & {_pct_tex(*com)} & {_pct_tex(*sem)} "
            f"& {t.b} & {t.c} & {_decimal_tex(t.p_valor)} \\\\"
        )
    return _ambiente_tex(
        "Critérios 1 a 3 por configuração e teste de McNemar exato",
        "resultado-criterios",
        "@{}l r r r r r@{}",
        corpo,
    )


def _tex_recorte(decisoes: Mapping[tuple[str, str], Decisao], recorte: str, titulo: str) -> str:
    contagem = proporcoes(decisoes, recorte)
    corpo = [
        f"{titulo} & Configuração & " + " & ".join(f"Crit. {c}" for c in CRITERIOS) + " \\\\",
        "\\midrule",
    ]
    for grupo in _grupos(decisoes, recorte):
        for configuracao in CONFIGURACOES:
            celulas = [_pct_tex(*contagem.get((grupo, configuracao, c), (0, 0))) for c in CRITERIOS]
            corpo.append(
                f"{grupo} & {NOMES_CONFIGURACAO[configuracao]} & " + " & ".join(celulas) + " \\\\"
            )
    return _ambiente_tex(
        f"Critérios 1 a 3 por {titulo.lower()}",
        f"resultado-{recorte}",
        "@{}l l r r r@{}",
        corpo,
    )


def _tex_validador(c4: Mapping[str, Any]) -> str:
    sinais = ", ".join(f"{s} ({n})" for s, n in c4["sinais"].items()) or "nenhum"
    corpo = [
        "Medida & Valor \\\\",
        "\\midrule",
        f"Execuções em que o Validador foi acionado & {_pct_tex(c4['acionado'], c4['execucoes'])}"
        " \\\\",
        f"Iterações do laço (média) & {_decimal_tex(c4['iteracoes_media'], 2)} \\\\",
        f"Iterações do laço (máximo) & {c4['iteracoes_max']} \\\\",
        f"Sinais que o acionaram & {sinais} \\\\",
    ]
    return _ambiente_tex(
        "Critério 4: atuação do Validador", "resultado-validador", "@{}l r@{}", corpo
    )
