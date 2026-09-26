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
- O CBC 2.10.3 fixado no TG é o binário embutido no PuLP 3.x, acessível só
  por `PULP_CBC_CMD`, que o PuLP 3.3 marca como depreciado (o PuLP 4 passa a
  exigir um CBC instalado à parte). A dependência fica em `pulp>=3.3,<4`, e o
  aviso é silenciado apenas no adaptador. A versão registrada em cada
  execução é lida do cabeçalho do próprio binário. Migrar para o PuLP 4
  exige novo ADR, pois muda a versão do solver.
- O mapeamento de status usa os dois campos do PuLP: com limite de tempo, o
  CBC devolve `Optimal` com solução apenas viável (`sol_status` 2), que o
  adaptador traduz para `limite_tempo`, e não para `otimo`.
