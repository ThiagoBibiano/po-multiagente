"""Conversa: o fluxo do ``Assistente`` em forma de chat, sem depender do Gradio.

Cada mensagem do usuário (texto e anexos) avança a conversa conforme a fase:

- **pedido:** junta a descrição e as planilhas, em uma ou várias mensagens, e
  executa quando tem as duas;
- **solicitações:** o fluxo pediu planilhas ajustadas; os anexos respondem a
  elas, pelo nome do arquivo ou pela ordem da lista;
- **confirmação:** o resultado coincide com uma cota trivial (ADR-011); o
  usuário diz se faz sentido e, se não, o que falta;
- **resultado:** a resposta foi dada; um texto vira ajuste do pedido (o fluxo
  é refeito com as mesmas planilhas, depois de confirmado), e anexos começam
  um problema novo.

Os pontos que o Interpretador marcou como ambíguos aparecem no chat, com a
leitura adotada, sem interromper o fluxo. Nada aqui muda os agentes nem o
grafo: a conversa só traduz as interrupções que já existem.
"""

import shutil
import tempfile
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from po_multiagente.dominio import AlertaAmbiguidade, Especificacao, Solicitacao
from po_multiagente.interface import apresentacao
from po_multiagente.interface.assistente import Assistente, ErroAssistente, Etapa, Resultado
from po_multiagente.llm import ErroLLM

Fase = Literal["pedido", "solicitacoes", "confirmacao", "observacao", "resultado", "ajuste"]
Progresso = Callable[[str], None]

SIM = "Sim, faz sentido"
NAO = "Não faz sentido"
REFAZER = "Refazer com esse ajuste"
NOVO = "Começar um problema novo"
SEGUIR_SEM = "Seguir sem esse ajuste"

BOAS_VINDAS = """\
Olá! Eu ajudo a decidir quanto produzir, comprar, transportar ou misturar para \
ter o melhor resultado, seja o maior lucro ou o menor custo, dentro dos limites \
do seu negócio.

**Para começar, me conte:**
- o que você quer decidir (por exemplo, quanto produzir de cada produto);
- o que quer maximizar ou minimizar (por exemplo, a margem total);
- quais limites existem (por exemplo, a madeira e as horas de montagem do mês).

E **anexe as planilhas** com os números (CSV ou Excel, uma tabela por arquivo ou \
aba, com cabeçalho). Os números vêm sempre das planilhas, e não do texto.

Pode mandar tudo numa mensagem ou em partes. Se quiser ver como funciona, use o \
exemplo da marcenaria."""

_NEGATIVAS = ("nao", "n ", "errado", "falta", "nao faz")
_AFIRMATIVAS = ("sim", "faz sentido", "ok", "pode", "isso", "correto", "certo", "confirmo")
_SEM_ARQUIVO = ("nao tenho", "pular", "seguir sem", "continuar sem", "sem ajuste", "nao consigo")


@dataclass(frozen=True)
class Mensagem:
    """Uma mensagem da plataforma no chat.

    Attributes:
        texto: Markdown, com LaTeX entre ``$$``.
        titulo: Se houver, a mensagem aparece recolhida sob esse título
            (detalhes técnicos).
        arquivo: Arquivo para baixar.
        opcoes: Respostas rápidas, que o usuário pode clicar em vez de escrever.
    """

    texto: str = ""
    titulo: str | None = None
    arquivo: Path | None = None
    opcoes: tuple[str, ...] = ()


class Conversa:
    """Uma conversa do usuário com a plataforma.

    Args:
        criar_assistente: Cria um ``Assistente`` novo para cada problema (e
            para cada refação com ajuste).
        pasta: Onde guardar as planilhas recebidas; o padrão é uma pasta
            temporária.
    """

    def __init__(
        self, criar_assistente: Callable[[], Assistente], pasta: Path | None = None
    ) -> None:
        self._criar = criar_assistente
        self._raiz = pasta or Path(tempfile.mkdtemp(prefix="po-conversa-"))
        self._recebidos = 0
        self.fase: Fase = "pedido"
        self._descricao = ""
        self._arquivos: list[Path] = []
        self._assistente: Assistente | None = None
        self._etapa: Etapa | None = None
        self._alertas_mostrados: set[str] = set()
        self._ajuste = ""

    def boas_vindas(self) -> list[Mensagem]:
        """Primeira mensagem da plataforma."""
        return [Mensagem(BOAS_VINDAS)]

    def responder(
        self, texto: str, arquivos: Sequence[Path] = (), ao_progresso: Progresso | None = None
    ) -> list[Mensagem]:
        """Mensagens da plataforma em resposta a uma mensagem do usuário.

        Args:
            texto: O que o usuário escreveu (ou a resposta rápida que clicou).
            arquivos: Planilhas anexadas.
            ao_progresso: Recebe a descrição de cada passo do fluxo enquanto ele roda.
        """
        texto = texto.strip()
        recebidos = self._guardar(arquivos)
        try:
            return self._responder(texto, recebidos, ao_progresso)
        except (ErroAssistente, ErroLLM) as erro:
            return [Mensagem(f"⚠️ {erro}")]

    # ------------------------------------------------------------- fases

    def _responder(
        self, texto: str, arquivos: list[Path], ao_progresso: Progresso | None
    ) -> list[Mensagem]:
        if self.fase == "solicitacoes":
            return self._tratar(texto, arquivos, ao_progresso)
        if self.fase == "confirmacao":
            return self._confirmar(texto, ao_progresso)
        if self.fase == "observacao":
            return self._rodar(lambda a: a.confirmar(False, texto or None), ao_progresso)
        if self.fase == "ajuste":
            return self._decidir_ajuste(texto, arquivos, ao_progresso)
        if self.fase == "resultado":
            if arquivos:
                self._reiniciar()
                return self._pedido(texto, arquivos, ao_progresso)
            if not texto:
                return []
            self._ajuste = texto
            self.fase = "ajuste"
            return [
                Mensagem(
                    f"Posso refazer a análise com as mesmas planilhas, acrescentando ao "
                    f"pedido: «{texto}». Quer que eu refaça, ou é um problema novo?",
                    opcoes=(REFAZER, NOVO),
                )
            ]
        return self._pedido(texto, arquivos, ao_progresso)

    def _pedido(
        self, texto: str, arquivos: list[Path], ao_progresso: Progresso | None
    ) -> list[Mensagem]:
        if texto:
            self._descricao = f"{self._descricao}\n\n{texto}".strip()
        self._arquivos += arquivos
        if not self._descricao and not self._arquivos:
            return [Mensagem("Me conte o que você quer decidir e anexe as planilhas.")]
        if not self._arquivos:
            return [
                Mensagem(
                    "Entendi o pedido. Agora **anexe as planilhas** com os números (CSV ou "
                    "Excel): eles vêm sempre das planilhas, e não do texto."
                )
            ]
        if not self._descricao:
            nomes = ", ".join(f"`{a.name}`" for a in self._arquivos)
            return [
                Mensagem(
                    f"Recebi {nomes}. Agora me diga o que você quer decidir, o que quer "
                    "maximizar ou minimizar e quais limites existem."
                )
            ]
        descricao, planilhas = self._descricao, list(self._arquivos)
        return self._rodar(lambda a: a.comecar(descricao, planilhas), ao_progresso, novo=True)

    def _tratar(
        self, texto: str, arquivos: list[Path], ao_progresso: Progresso | None
    ) -> list[Mensagem]:
        pendentes = self._etapa.solicitacoes if self._etapa else ()
        if not arquivos:
            if texto == SEGUIR_SEM or _contem(texto, _SEM_ARQUIVO):
                return self._rodar(lambda a: a.tratar({}), ao_progresso)
            return [
                Mensagem(
                    "Para seguir, preciso da planilha ajustada como **anexo**: os números "
                    "vêm sempre das planilhas, e eu não altero dados por conta própria. "
                    "Se não tiver como ajustar agora, posso seguir sem esse dado, mas o "
                    "resultado pode não sair.",
                    opcoes=(SEGUIR_SEM,),
                )
            ]
        if len(arquivos) > len(pendentes):
            return [
                Mensagem(
                    f"Recebi {len(arquivos)} arquivo(s), mas pedi {len(pendentes)}. "
                    "Mande só as planilhas ajustadas da lista."
                )
            ]
        respostas = _associar(pendentes, arquivos)
        return self._rodar(lambda a: a.tratar(respostas), ao_progresso)

    def _confirmar(self, texto: str, ao_progresso: Progresso | None) -> list[Mensagem]:
        if texto == SIM or (texto != NAO and _afirmativa(texto)):
            return self._rodar(lambda a: a.confirmar(True), ao_progresso)
        if texto == NAO or _negativa(texto):
            observacao = _sem_negacao(texto) if texto != NAO else ""
            if observacao:
                return self._rodar(lambda a: a.confirmar(False, observacao), ao_progresso)
            self.fase = "observacao"
            return [
                Mensagem(
                    "Certo. O que está faltando ou errado? Por exemplo: «falta a produção "
                    "mínima de cada produto». Vou refazer levando isso em conta."
                )
            ]
        return [
            Mensagem(
                "Não entendi se o resultado faz sentido. Responda sim, ou não seguido do "
                "que está faltando.",
                opcoes=(SIM, NAO),
            )
        ]

    def _decidir_ajuste(
        self, texto: str, arquivos: list[Path], ao_progresso: Progresso | None
    ) -> list[Mensagem]:
        if arquivos or texto == NOVO:
            self._reiniciar()
            if arquivos or (texto and texto != NOVO):
                return self._pedido("" if texto == NOVO else texto, arquivos, ao_progresso)
            return [Mensagem("Certo. Descreva o problema novo e anexe as planilhas.")]
        if texto == REFAZER or _afirmativa(texto):
            self._descricao = f"{self._descricao}\n\nAjuste pedido pelo usuário: {self._ajuste}"
            descricao, planilhas = self._descricao, list(self._arquivos)
            return self._rodar(lambda a: a.comecar(descricao, planilhas), ao_progresso, novo=True)
        # Outro texto: substitui o ajuste proposto.
        self._ajuste = texto
        return [Mensagem(f"Refaço acrescentando: «{texto}»?", opcoes=(REFAZER, NOVO))]

    # ------------------------------------------------------------ execução

    def _rodar(
        self,
        passo: Callable[[Assistente], Etapa],
        ao_progresso: Progresso | None,
        *,
        novo: bool = False,
    ) -> list[Mensagem]:
        if novo or self._assistente is None:
            self._assistente = self._criar()
            self._alertas_mostrados = set()
        assistente = self._assistente
        assistente.ao_avancar = ao_progresso
        inicio = time.perf_counter()
        try:
            self._etapa = passo(assistente)
        finally:
            assistente.ao_avancar = None
        return self._apos(self._etapa, assistente.resultado(), time.perf_counter() - inicio)

    def _apos(self, etapa: Etapa, resultado: Resultado, segundos: float) -> list[Mensagem]:
        mensagens = self._alertas(resultado.especificacao)
        if etapa.tipo == "solicitacoes":
            self.fase = "solicitacoes"
            return [*mensagens, Mensagem(texto_solicitacoes(etapa.solicitacoes))]
        if etapa.tipo == "confirmacao":
            self.fase = "confirmacao"
            perguntas = "\n\n".join(etapa.perguntas)
            return [*mensagens, Mensagem(perguntas, opcoes=(SIM, NAO))]
        self.fase = "resultado"
        return [*mensagens, *mensagens_do_resultado(resultado, segundos, self._raiz)]

    def _alertas(self, especificacao: Especificacao | None) -> list[Mensagem]:
        if especificacao is None:
            return []
        novos = [a for a in especificacao.alertas if a.trecho not in self._alertas_mostrados]
        self._alertas_mostrados |= {a.trecho for a in novos}
        return [Mensagem(texto_alerta(a, especificacao)) for a in novos]

    # ------------------------------------------------------------ auxiliares

    def _guardar(self, arquivos: Sequence[Path]) -> list[Path]:
        """Copia os anexos para a pasta da conversa (os do Gradio são temporários)."""
        if not arquivos:
            return []
        self._recebidos += 1
        pasta = self._raiz / f"recebidos_{self._recebidos}"
        pasta.mkdir(parents=True, exist_ok=True)
        return [Path(shutil.copy(a, pasta / Path(a).name)) for a in arquivos]

    def _reiniciar(self) -> None:
        self.fase = "pedido"
        self._descricao = ""
        self._arquivos = []
        self._assistente = None
        self._etapa = None
        self._ajuste = ""


# ------------------------------------------------------------------ textos


def texto_solicitacoes(solicitacoes: Sequence[Solicitacao]) -> str:
    """Pedido de planilhas ajustadas, só sobre os dados (nunca sobre a formulação)."""
    linhas = [
        "Para continuar, preciso que você ajuste "
        + ("um dado:" if len(solicitacoes) == 1 else "alguns dados:"),
        "",
    ]
    for numero, solicitacao in enumerate(solicitacoes, start=1):
        coluna = f", coluna `{solicitacao.coluna}`" if solicitacao.coluna else ""
        motivo = apresentacao.MOTIVOS.get(solicitacao.motivo.value, solicitacao.motivo.value)
        linhas.append(
            f"{numero}. Planilha `{solicitacao.arquivo}`{coluna}: o dado {motivo}. "
            f"Como deve ficar: {solicitacao.forma_esperada}"
        )
    linhas += [
        "",
        "Anexe aqui a planilha ajustada"
        + (
            "."
            if len(solicitacoes) == 1
            else "s, todas de uma vez: reconheço cada uma pelo nome do arquivo "
            "original ou, se os nomes mudarem, pela ordem da lista."
        ),
    ]
    return "\n".join(linhas)


def texto_alerta(alerta: AlertaAmbiguidade, especificacao: Especificacao) -> str:
    """Ponto ambíguo do pedido, com a leitura adotada quando ela é conhecida."""
    requisitos = {r.id: r.texto for r in especificacao.requisitos}
    adotada = requisitos.get(alerta.requisito_id or "")
    leituras = "\n".join(f"- {leitura}" for leitura in alerta.leituras)
    considerado = (
        f"\n\nConsiderei: **{adotada}**" if adotada else "\n\nSegui a leitura mais provável."
    )
    return (
        f"🔎 Um trecho do pedido admite mais de uma leitura: «{alerta.trecho}».\n\n"
        f"Leituras possíveis:\n{leituras}{considerado}\n\n"
        "Se não era isso, me diga quando a resposta sair, e eu refaço com o ajuste."
    )


def mensagens_do_resultado(resultado: Resultado, segundos: float, pasta: Path) -> list[Mensagem]:
    """A resposta primeiro; os detalhes técnicos (R5) recolhidos; o arquivo para baixar."""
    if not resultado.explicacao:
        motivo = resultado.falha or f"status do solver: {resultado.status or 'sem resultado'}"
        return [
            Mensagem(
                f"{apresentacao.destaque(resultado)}\n\n**Não consegui chegar a uma "
                "resposta.** Confira se o pedido diz o que decidir, o que otimizar e quais "
                "limites existem, e se as planilhas trazem os números com cabeçalho. Você "
                "pode escrever um ajuste para eu refazer, ou anexar planilhas corrigidas "
                "para começar de novo.",
            ),
            Mensagem(motivo, titulo="Detalhe técnico"),
        ]
    principal = "\n\n".join(
        parte
        for parte in (
            apresentacao.destaque(resultado),
            resultado.explicacao,
            apresentacao.plano_recomendado(resultado),
            apresentacao.selo_conferencia(resultado).replace(
                "Veja em *Detalhes técnicos → Conferências*.", "Veja em *Conferências*, abaixo."
            ),
        )
        if parte
    )
    destino = Path(tempfile.mkdtemp(prefix="po-resultado-", dir=pasta))
    detalhes = [
        ("Decisões", apresentacao.decisoes(resultado)),
        ("Modelo matemático", apresentacao.modelo_legivel(resultado)),
        ("Conferências", apresentacao.conferencias(resultado.pareceres)),
        ("Entendimento do pedido", apresentacao.entendimento(resultado.especificacao)),
        ("Execução", apresentacao.consumo(resultado, segundos)),
    ]
    return [
        Mensagem(principal),
        *(Mensagem(texto, titulo=titulo) for titulo, texto in detalhes if texto),
        Mensagem(
            "Resultados para baixar: plano em CSV, modelo, conferências e o dossiê "
            "completo da execução (abra `dossie/index.html`).",
            arquivo=apresentacao.empacotar(resultado, destino),
        ),
        Mensagem(
            "Quer ajustar algo? Escreva o que mudar, e eu refaço com as mesmas "
            "planilhas. Para um problema novo, anexe outras planilhas."
        ),
    ]


def _associar(pendentes: Sequence[Solicitacao], arquivos: list[Path]) -> dict[str, Path]:
    """Cada anexo vai para a solicitação do mesmo arquivo; os demais, pela ordem."""
    respostas: dict[str, Path] = {}
    restantes = list(arquivos)
    for solicitacao in pendentes:
        mesmo_nome = next((a for a in restantes if a.name == solicitacao.arquivo), None)
        if mesmo_nome is not None:
            respostas[solicitacao.id] = mesmo_nome
            restantes.remove(mesmo_nome)
    for solicitacao in pendentes:
        if solicitacao.id not in respostas and restantes:
            respostas[solicitacao.id] = restantes.pop(0)
    return respostas


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().replace(",", " ").replace(".", " ").split()) + " "


def _contem(texto: str, termos: Sequence[str]) -> bool:
    normalizado = _normalizar(texto)
    return any(t in normalizado for t in termos)


def _negativa(texto: str) -> bool:
    normalizado = _normalizar(texto)
    return any(normalizado.startswith(t) for t in _NEGATIVAS)


def _afirmativa(texto: str) -> bool:
    return not _negativa(texto) and any(_normalizar(texto).startswith(t) for t in _AFIRMATIVAS)


def _sem_negacao(texto: str) -> str:
    """O que vem depois do «não» inicial: a observação do usuário."""
    restante = texto.strip()
    for prefixo in ("não faz sentido", "nao faz sentido", "não", "nao"):
        if restante.lower().startswith(prefixo):
            restante = restante[len(prefixo) :]
            break
    return restante.strip(" ,.;:-—").strip()
