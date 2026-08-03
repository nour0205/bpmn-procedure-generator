from document.loader import load_generated_procedure


def test_load_generated_procedure() -> None:
    procedure = load_generated_procedure(
        "output/determination_des_besoins/llm/generated_procedure.json"
    )

    assert procedure.operation_count == 13
    assert len(procedure.operations) == 13
    assert procedure.title
