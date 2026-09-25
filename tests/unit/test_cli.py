import pytest

from po_multiagente import __version__
from po_multiagente.cli import main


def test_versao(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as saida:
        main(["--versao"])
    assert saida.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_sem_argumentos_mostra_ajuda(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "po-multiagente" in capsys.readouterr().out
