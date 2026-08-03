from __future__ import annotations

from pathlib import Path

from bpmn.parser import BpmnParser
from pipeline.service import ProcedureGenerationPipeline
from procedure.mapper import ProcedureMapper
from procedure.models import ProcedureModel


ROOT = Path(__file__).resolve().parents[1]


def _real_procedure(relative_path: str) -> ProcedureModel:
    return ProcedureGenerationPipeline().run(
        ROOT / relative_path
    ).procedure_model


def _map_xml(
    tmp_path: Path,
    xml: str,
    process_id: str = "Process_1",
) -> ProcedureModel:
    path = tmp_path / "fixture.bpmn"
    path.write_text(xml, encoding="utf-8")
    model = BpmnParser().parse_file(path)
    return ProcedureMapper().map_process(
        model=model,
        process_id=process_id,
    )


def _operation_by_name(
    procedure: ProcedureModel,
    name: str,
):
    return next(
        operation
        for operation in procedure.operations
        if operation.raw_name == name
    )


def test_determination_marks_only_the_shared_continuation() -> None:
    procedure = _real_procedure(
        "bpmn_files/Détermination des besoins d'appro.bpmn"
    )

    consumption = _operation_by_name(
        procedure,
        "Renseigner le niveau de la consommation moyenne prévisionnelle",
    )
    calculation = _operation_by_name(
        procedure,
        "Lancer le calcul des besoins (CBN) sur le SI",
    )

    assert consumption.is_common_continuation is False
    assert consumption.convergence_gateway_ids == []

    assert calculation.is_common_continuation is True
    assert calculation.convergence_gateway_ids
    assert len(set(calculation.previous_operation_ids)) == 2
    assert calculation.order_ambiguous is False


def test_suivi_marks_receptions_but_not_the_validation_loop() -> None:
    procedure = _real_procedure(
        "bpmn_files/Suivi des commandes.bpmn"
    )

    reception = _operation_by_name(
        procedure,
        "Gestion des réceptions",
    )
    reminder_letter = _operation_by_name(
        procedure,
        "Générer les lettres de relance",
    )

    assert reception.is_common_continuation is True
    assert reception.convergence_gateway_ids

    # This activity has a normal incoming path and a validation loop-back.
    # It must never be classified as a branch convergence.
    assert reminder_letter.is_common_continuation is False
    assert reminder_letter.convergence_gateway_ids == []


THREE_BRANCH_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    targetNamespace="https://example.com/convergence">
  <bpmn:process id="Process_1" name="Three branches" isExecutable="false">
    <bpmn:startEvent id="Start_1">
      <bpmn:outgoing>F1</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:userTask id="Task_Open" name="Open case">
      <bpmn:incoming>F1</bpmn:incoming>
      <bpmn:outgoing>F2</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:exclusiveGateway id="Gateway_Decision" name="Choose route">
      <bpmn:incoming>F2</bpmn:incoming>
      <bpmn:outgoing>FA</bpmn:outgoing>
      <bpmn:outgoing>FB</bpmn:outgoing>
      <bpmn:outgoing>FC</bpmn:outgoing>
    </bpmn:exclusiveGateway>
    <bpmn:userTask id="Task_A" name="Route A">
      <bpmn:incoming>FA</bpmn:incoming>
      <bpmn:outgoing>FAJ</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:userTask id="Task_B" name="Route B">
      <bpmn:incoming>FB</bpmn:incoming>
      <bpmn:outgoing>FBJ</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:userTask id="Task_C" name="Route C">
      <bpmn:incoming>FC</bpmn:incoming>
      <bpmn:outgoing>FCJ</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:exclusiveGateway id="Gateway_Join">
      <bpmn:incoming>FAJ</bpmn:incoming>
      <bpmn:incoming>FBJ</bpmn:incoming>
      <bpmn:incoming>FCJ</bpmn:incoming>
      <bpmn:outgoing>FJ</bpmn:outgoing>
    </bpmn:exclusiveGateway>
    <bpmn:userTask id="Task_Common" name="Shared continuation">
      <bpmn:incoming>FJ</bpmn:incoming>
      <bpmn:outgoing>FEnd</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:endEvent id="End_1">
      <bpmn:incoming>FEnd</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="F1" sourceRef="Start_1" targetRef="Task_Open" />
    <bpmn:sequenceFlow id="F2" sourceRef="Task_Open" targetRef="Gateway_Decision" />
    <bpmn:sequenceFlow id="FA" name="A" sourceRef="Gateway_Decision" targetRef="Task_A" />
    <bpmn:sequenceFlow id="FB" name="B" sourceRef="Gateway_Decision" targetRef="Task_B" />
    <bpmn:sequenceFlow id="FC" name="C" sourceRef="Gateway_Decision" targetRef="Task_C" />
    <bpmn:sequenceFlow id="FAJ" sourceRef="Task_A" targetRef="Gateway_Join" />
    <bpmn:sequenceFlow id="FBJ" sourceRef="Task_B" targetRef="Gateway_Join" />
    <bpmn:sequenceFlow id="FCJ" sourceRef="Task_C" targetRef="Gateway_Join" />
    <bpmn:sequenceFlow id="FJ" sourceRef="Gateway_Join" targetRef="Task_Common" />
    <bpmn:sequenceFlow id="FEnd" sourceRef="Task_Common" targetRef="End_1" />
  </bpmn:process>
</bpmn:definitions>
"""


def test_three_branch_gateway_has_one_nearest_common_continuation(
    tmp_path: Path,
) -> None:
    procedure = _map_xml(tmp_path, THREE_BRANCH_BPMN)

    common = procedure.operation_by_id("Task_Common")
    assert common is not None
    assert common.is_common_continuation is True
    assert common.convergence_gateway_ids == ["Gateway_Decision"]

    for operation_id in ("Task_A", "Task_B", "Task_C"):
        branch_operation = procedure.operation_by_id(operation_id)
        assert branch_operation is not None
        assert branch_operation.is_common_continuation is False


NESTED_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    targetNamespace="https://example.com/nested">
  <bpmn:process id="Process_1" name="Nested decisions" isExecutable="false">
    <bpmn:startEvent id="Start_1"><bpmn:outgoing>F1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="Task_Start" name="Start work">
      <bpmn:incoming>F1</bpmn:incoming><bpmn:outgoing>F2</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:exclusiveGateway id="G_Outer" name="Outer decision">
      <bpmn:incoming>F2</bpmn:incoming><bpmn:outgoing>FOY</bpmn:outgoing><bpmn:outgoing>FON</bpmn:outgoing>
    </bpmn:exclusiveGateway>
    <bpmn:userTask id="Task_OuterYes" name="Outer yes">
      <bpmn:incoming>FOY</bpmn:incoming><bpmn:outgoing>F3</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:exclusiveGateway id="G_Inner" name="Inner decision">
      <bpmn:incoming>F3</bpmn:incoming><bpmn:outgoing>FIA</bpmn:outgoing><bpmn:outgoing>FIB</bpmn:outgoing>
    </bpmn:exclusiveGateway>
    <bpmn:userTask id="Task_InnerA" name="Inner A">
      <bpmn:incoming>FIA</bpmn:incoming><bpmn:outgoing>FIAJ</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:userTask id="Task_InnerB" name="Inner B">
      <bpmn:incoming>FIB</bpmn:incoming><bpmn:outgoing>FIBJ</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:exclusiveGateway id="G_InnerJoin">
      <bpmn:incoming>FIAJ</bpmn:incoming><bpmn:incoming>FIBJ</bpmn:incoming><bpmn:outgoing>FIJ</bpmn:outgoing>
    </bpmn:exclusiveGateway>
    <bpmn:userTask id="Task_AfterInner" name="After inner decision">
      <bpmn:incoming>FIJ</bpmn:incoming><bpmn:outgoing>FYJ</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:userTask id="Task_OuterNo" name="Outer no">
      <bpmn:incoming>FON</bpmn:incoming><bpmn:outgoing>FNJ</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:exclusiveGateway id="G_OuterJoin">
      <bpmn:incoming>FYJ</bpmn:incoming><bpmn:incoming>FNJ</bpmn:incoming><bpmn:outgoing>FOJ</bpmn:outgoing>
    </bpmn:exclusiveGateway>
    <bpmn:userTask id="Task_Final" name="Final shared continuation">
      <bpmn:incoming>FOJ</bpmn:incoming><bpmn:outgoing>FEnd</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:endEvent id="End_1"><bpmn:incoming>FEnd</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="F1" sourceRef="Start_1" targetRef="Task_Start" />
    <bpmn:sequenceFlow id="F2" sourceRef="Task_Start" targetRef="G_Outer" />
    <bpmn:sequenceFlow id="FOY" name="Yes" sourceRef="G_Outer" targetRef="Task_OuterYes" />
    <bpmn:sequenceFlow id="FON" name="No" sourceRef="G_Outer" targetRef="Task_OuterNo" />
    <bpmn:sequenceFlow id="F3" sourceRef="Task_OuterYes" targetRef="G_Inner" />
    <bpmn:sequenceFlow id="FIA" name="A" sourceRef="G_Inner" targetRef="Task_InnerA" />
    <bpmn:sequenceFlow id="FIB" name="B" sourceRef="G_Inner" targetRef="Task_InnerB" />
    <bpmn:sequenceFlow id="FIAJ" sourceRef="Task_InnerA" targetRef="G_InnerJoin" />
    <bpmn:sequenceFlow id="FIBJ" sourceRef="Task_InnerB" targetRef="G_InnerJoin" />
    <bpmn:sequenceFlow id="FIJ" sourceRef="G_InnerJoin" targetRef="Task_AfterInner" />
    <bpmn:sequenceFlow id="FYJ" sourceRef="Task_AfterInner" targetRef="G_OuterJoin" />
    <bpmn:sequenceFlow id="FNJ" sourceRef="Task_OuterNo" targetRef="G_OuterJoin" />
    <bpmn:sequenceFlow id="FOJ" sourceRef="G_OuterJoin" targetRef="Task_Final" />
    <bpmn:sequenceFlow id="FEnd" sourceRef="Task_Final" targetRef="End_1" />
  </bpmn:process>
</bpmn:definitions>
"""


def test_nested_decisions_keep_their_nearest_convergences(
    tmp_path: Path,
) -> None:
    procedure = _map_xml(tmp_path, NESTED_BPMN)

    inner = procedure.operation_by_id("Task_AfterInner")
    outer = procedure.operation_by_id("Task_Final")

    assert inner is not None
    assert outer is not None

    assert inner.is_common_continuation is True
    assert inner.convergence_gateway_ids == ["G_Inner"]

    assert outer.is_common_continuation is True
    assert outer.convergence_gateway_ids == ["G_Outer"]


MULTI_PREDECESSOR_WITHOUT_GATEWAY = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
    xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
    targetNamespace="https://example.com/no-gateway">
  <bpmn:process id="Process_1" name="No source gateway" isExecutable="false">
    <bpmn:startEvent id="Start_A"><bpmn:outgoing>FA1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:startEvent id="Start_B"><bpmn:outgoing>FB1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="Task_A" name="Independent A">
      <bpmn:incoming>FA1</bpmn:incoming><bpmn:outgoing>FA2</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:userTask id="Task_B" name="Independent B">
      <bpmn:incoming>FB1</bpmn:incoming><bpmn:outgoing>FB2</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:userTask id="Task_Target" name="Multiple predecessors without decision">
      <bpmn:incoming>FA2</bpmn:incoming><bpmn:incoming>FB2</bpmn:incoming><bpmn:outgoing>FEnd</bpmn:outgoing>
    </bpmn:userTask>
    <bpmn:endEvent id="End_1"><bpmn:incoming>FEnd</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="FA1" sourceRef="Start_A" targetRef="Task_A" />
    <bpmn:sequenceFlow id="FB1" sourceRef="Start_B" targetRef="Task_B" />
    <bpmn:sequenceFlow id="FA2" sourceRef="Task_A" targetRef="Task_Target" />
    <bpmn:sequenceFlow id="FB2" sourceRef="Task_B" targetRef="Task_Target" />
    <bpmn:sequenceFlow id="FEnd" sourceRef="Task_Target" targetRef="End_1" />
  </bpmn:process>
</bpmn:definitions>
"""


def test_multiple_predecessors_without_a_shared_gateway_are_not_convergence(
    tmp_path: Path,
) -> None:
    procedure = _map_xml(
        tmp_path,
        MULTI_PREDECESSOR_WITHOUT_GATEWAY,
    )

    target = procedure.operation_by_id("Task_Target")
    assert target is not None
    assert len(set(target.previous_operation_ids)) == 2
    assert target.is_common_continuation is False
    assert target.convergence_gateway_ids == []
