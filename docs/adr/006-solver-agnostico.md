# ADR-006: Camada de solver agnóstica, com PuLP/CBC por ora

- **Estado:** aceita
- **Data:** 2026-09-25

## Contexto

O TG fixa o CBC 2.10.3 via PuLP, mas outros solvers podem ser necessários
(SCIP como contingência em PLIM, HiGHS). O sinal S1 depende de um mapeamento
correto de status.

## Decisão

- Um contrato `SolverBackend` recebe o modelo instanciado neutro e devolve
  um `dominio.ResultadoSolver` canônico.
- Os adaptadores são registrados por **entry points**; a configuração tem dois
  eixos: `backend` (ex.: `pulp`) e `motor` (ex.: `cbc`).
- Uma **suíte de conformidade** compartilhada (PL e PLIM com ótimo
  conhecido, inviável, ilimitado) é obrigatória para todo adaptador.

## Consequências

- Um solver novo exige um arquivo de adaptador e uma linha no
  `pyproject.toml`.
- O solver é definido num único ponto e registrado em toda execução, como
  exige o Passo 4.
