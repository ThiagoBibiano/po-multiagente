"""Coleção das fontes de dados de uma sessão, lidas de um diretório."""

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path

from po_multiagente.dados.erros import ErroDados
from po_multiagente.dados.leitura import Tabela, ler_csv, ler_xlsx
from po_multiagente.dominio import Coluna, FonteDados

EXTENSOES = frozenset({".csv", ".xlsx"})
"""Formatos aceitos. XLS e ODS precisam ser salvos como XLSX pelo usuário."""

_BLOCO_HASH = 1 << 16
_ABA = re.compile(r"^(?P<arquivo>.+\.xlsx)\[(?P<aba>.+)\]$", re.IGNORECASE)


def arquivo_da_fonte(nome: str) -> str:
    """Arquivo de uma fonte: ``custos.xlsx[Março]`` está em ``custos.xlsx``."""
    aba = _ABA.fullmatch(nome)
    return aba["arquivo"] if aba else nome


def sha256_arquivo(caminho: Path) -> str:
    """Resumo SHA-256 do conteúdo do arquivo, em hexadecimal minúsculo."""
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        while bloco := arquivo.read(_BLOCO_HASH):
            resumo.update(bloco)
    return resumo.hexdigest()


class Fontes:
    """Fontes de dados de uma sessão, com acesso somente leitura.

    Cada arquivo é lido uma vez e guardado em memória. Os arquivos nunca são
    abertos para escrita; ``conferir_integridade`` compara o hash atual com o
    registrado no inventário para provar isso a cada execução.

    Args:
        diretorio: Diretório com os arquivos do usuário. Só os arquivos
            diretamente nele, com extensão aceita, são fontes.
        adicionais: Outros diretórios da mesma sessão, como o dos arquivos
            tratados que o usuário devolve em resposta às solicitações.

    Raises:
        NotADirectoryError: Se algum diretório não existir.
        ErroDados: Se o mesmo nome de arquivo aparecer em dois diretórios.
    """

    def __init__(self, diretorio: Path, *adicionais: Path) -> None:
        self._caminhos: dict[str, Path] = {}
        for pasta in (diretorio, *adicionais):
            if not pasta.is_dir():
                raise NotADirectoryError(pasta)
            for caminho in sorted(pasta.iterdir()):
                if not (caminho.is_file() and caminho.suffix.lower() in EXTENSOES):
                    continue
                if caminho.name in self._caminhos:
                    raise ErroDados(
                        f"O arquivo {caminho.name!r} aparece em mais de um diretório",
                        arquivo=caminho.name,
                    )
                self._caminhos[caminho.name] = caminho
        self._tabelas: dict[str, tuple[Tabela, ...]] = {}

    @property
    def arquivos(self) -> tuple[str, ...]:
        """Nomes dos arquivos de dados, em ordem alfabética."""
        return tuple(sorted(self._caminhos))

    def tabelas(self, arquivo: str) -> tuple[Tabela, ...]:
        """Tabelas de um arquivo: uma para CSV, uma por aba para XLSX.

        Raises:
            ErroDados: Se o arquivo não for uma fonte do diretório ou não
                puder ser lido.
        """
        if arquivo not in self._tabelas:
            caminho = self._caminho(arquivo)
            if caminho.suffix.lower() == ".csv":
                self._tabelas[arquivo] = (ler_csv(caminho),)
            else:
                self._tabelas[arquivo] = ler_xlsx(caminho)
        return self._tabelas[arquivo]

    def tabela(self, nome: str) -> Tabela:
        """Tabela pelo nome da fonte: ``arquivo`` ou ``arquivo.xlsx[aba]``.

        Raises:
            ErroDados: Se não houver fonte com esse nome.
        """
        for tabela in self.tabelas(arquivo_da_fonte(nome)):
            if tabela.nome == nome:
                return tabela
        raise ErroDados(f"Não há fonte chamada {nome!r}", arquivo=nome)

    def inventario(self) -> tuple[FonteDados, ...]:
        """Inventário de todas as fontes: nome, hash e colunas com tipo."""
        fontes: list[FonteDados] = []
        for arquivo in self.arquivos:
            sha256 = sha256_arquivo(self._caminho(arquivo))
            fontes.extend(
                FonteDados(
                    arquivo=tabela.nome,
                    sha256=sha256,
                    colunas=tuple(
                        Coluna(nome=nome, tipo=tipo)
                        for nome, tipo in zip(tabela.colunas, tabela.tipos, strict=True)
                    ),
                )
                for tabela in self.tabelas(arquivo)
            )
        return tuple(fontes)

    def conferir_integridade(self, fontes: Iterable[FonteDados]) -> tuple[str, ...]:
        """Fontes cujo arquivo mudou ou sumiu desde o inventário.

        Returns:
            Nomes das fontes alteradas; vazio quando nada mudou.
        """
        alteradas = []
        for fonte in fontes:
            caminho = self._caminhos.get(arquivo_da_fonte(fonte.arquivo))
            if caminho is None or not caminho.is_file() or sha256_arquivo(caminho) != fonte.sha256:
                alteradas.append(fonte.arquivo)
        return tuple(alteradas)

    def _caminho(self, arquivo: str) -> Path:
        # Só arquivos listados na criação: impede ler fora dos diretórios (``../``).
        if arquivo not in self._caminhos:
            raise ErroDados(f"Não há arquivo de dados chamado {arquivo!r}", arquivo=arquivo)
        return self._caminhos[arquivo]
