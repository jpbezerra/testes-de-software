"""
Suite de testes para scholarship_eligibility_evaluator.evaluate_scholarship

Cada teste documenta, no docstring, qual técnica de projeto o originou:
  - EC  -> Classe de equivalência (functional / partição de entrada)
  - BV  -> Valor de fronteira (boundary value analysis)
  - DEC -> Decisão/branch estrutural exercitada (if/elif/else do código-fonte)
  - PATH -> Combinação de decisões (caminho de execução)

Valores "baseline" usados para isolar uma variável por vez:
    age=20, gpa=8.5, attendance_rate=90.0,
    has_required_courses=True, disciplinary_record=False
  -> resultado esperado: APPROVED

Convenção de nomenclatura das mensagens (copiadas literalmente do código-base,
pois a suíte verifica também `reasons`, não só `status`):
"""
import pytest

from scholarship_eligibility_evaluator import (
    EvaluationResult,
    Status,
    evaluate_scholarship,
)

# ---------------------------------------------------------------------------
# Helpers / baseline
# ---------------------------------------------------------------------------

BASELINE = dict(
    age=20,
    gpa=8.5,
    attendance_rate=90.0,
    has_required_courses=True,
    disciplinary_record=False,
)

MSG_AGE_REJECT = "Applicant is younger than the minimum age."
MSG_AGE_REVIEW = "Applicant is under 18 and requires manual review."
MSG_GPA_REJECT = "GPA is below the minimum required."
MSG_GPA_REVIEW = "GPA is in the manual review range."
MSG_ATTENDANCE_REJECT = "Attendance rate is below the minimum required."
MSG_ATTENDANCE_REVIEW = "Attendance rate is in the manual review range."
MSG_COURSES_REJECT = "Required courses have not been completed."
MSG_DISCIPLINARY_REJECT = "Applicant has a disciplinary record."
MSG_APPROVED = "Applicant meets all scholarship requirements."

MSG_GPA_RANGE_ERROR = "GPA must be between 0 and 10."
MSG_ATTENDANCE_RANGE_ERROR = "Attendance rate must be between 0 and 100."


def make(**overrides) -> dict:
    """Retorna uma cópia do baseline com os campos indicados sobrescritos."""
    params = dict(BASELINE)
    params.update(overrides)
    return params


def assert_result(result: EvaluationResult, status: Status, reasons: list):
    """Verifica status E a lista de motivos (ordem e conteúdo exatos)."""
    assert result.status == status
    assert result.reasons == reasons


# ---------------------------------------------------------------------------
# 1. Caso base: APPROVED (EC "tudo dentro da faixa aceitável" para as 5 regras)
# ---------------------------------------------------------------------------

def test_approved_when_all_criteria_are_met():
    """EC (age>=18, gpa>=7.0, attendance>=80, courses=True, disciplinary=False)
    DEC: todas as ramificações 'else' (nenhuma rejeição/review) + branch final 'else' (APPROVED)."""
    result = evaluate_scholarship(**make())
    assert_result(result, Status.APPROVED, [MSG_APPROVED])


# ---------------------------------------------------------------------------
# 2. Regra de idade (Rule 1) - EC e BV isolados
# ---------------------------------------------------------------------------

def test_age_below_16_is_rejected():
    """EC: age < 16 (menor de idade mínima). DEC: branch `age < 16` True."""
    result = evaluate_scholarship(**make(age=15))
    assert_result(result, Status.REJECTED, [MSG_AGE_REJECT])


def test_age_boundary_15_16_rejected_then_review():
    """BV: fronteira 15/16 do limite inferior da regra de idade."""
    assert_result(
        evaluate_scholarship(**make(age=15)), Status.REJECTED, [MSG_AGE_REJECT]
    )
    assert_result(
        evaluate_scholarship(**make(age=16)), Status.MANUAL_REVIEW, [MSG_AGE_REVIEW]
    )


def test_age_boundary_17_18_review_then_approved():
    """BV: fronteira 17/18 (limite superior da faixa de revisão manual)."""
    assert_result(
        evaluate_scholarship(**make(age=17)), Status.MANUAL_REVIEW, [MSG_AGE_REVIEW]
    )
    assert_result(
        evaluate_scholarship(**make(age=18)), Status.APPROVED, [MSG_APPROVED]
    )


def test_age_16_and_17_both_trigger_manual_review():
    """EC: 16 <= age <= 17 (faixa de revisão manual). DEC: branch `elif age <= 17` True."""
    for age in (16, 17):
        assert_result(
            evaluate_scholarship(**make(age=age)),
            Status.MANUAL_REVIEW,
            [MSG_AGE_REVIEW],
        )


# ---------------------------------------------------------------------------
# 3. Regra de GPA (Rule 2) - EC e BV isolados
# ---------------------------------------------------------------------------

def test_gpa_below_minimum_is_rejected():
    """EC: gpa < 6.0. DEC: branch `gpa < 6.0` True."""
    result = evaluate_scholarship(**make(gpa=5.0))
    assert_result(result, Status.REJECTED, [MSG_GPA_REJECT])


def test_gpa_boundary_5_9_6_0_rejected_then_review():
    """BV: fronteira 5.9/6.0 do limite inferior da regra de GPA."""
    assert_result(
        evaluate_scholarship(**make(gpa=5.9)), Status.REJECTED, [MSG_GPA_REJECT]
    )
    assert_result(
        evaluate_scholarship(**make(gpa=6.0)), Status.MANUAL_REVIEW, [MSG_GPA_REVIEW]
    )


def test_gpa_boundary_6_9_7_0_review_then_approved():
    """BV: fronteira 6.9/7.0 (limite superior da faixa de revisão manual de GPA)."""
    assert_result(
        evaluate_scholarship(**make(gpa=6.9)), Status.MANUAL_REVIEW, [MSG_GPA_REVIEW]
    )
    assert_result(
        evaluate_scholarship(**make(gpa=7.0)), Status.APPROVED, [MSG_APPROVED]
    )


def test_gpa_manual_review_range():
    """EC: 6.0 <= gpa < 7.0. DEC: branch `elif gpa < 7.0` True."""
    for gpa in (6.0, 6.5, 6.99):
        assert_result(
            evaluate_scholarship(**make(gpa=gpa)),
            Status.MANUAL_REVIEW,
            [MSG_GPA_REVIEW],
        )


# ---------------------------------------------------------------------------
# 4. Regra de frequência / attendance (Rule 3) - EC e BV isolados
# ---------------------------------------------------------------------------

def test_attendance_below_minimum_is_rejected():
    """EC: attendance_rate < 75.0. DEC: branch `attendance_rate < 75.0` True."""
    result = evaluate_scholarship(**make(attendance_rate=60.0))
    assert_result(result, Status.REJECTED, [MSG_ATTENDANCE_REJECT])


def test_attendance_boundary_74_9_75_0_rejected_then_review():
    """BV: fronteira 74.9/75.0 do limite inferior da regra de frequência."""
    assert_result(
        evaluate_scholarship(**make(attendance_rate=74.9)),
        Status.REJECTED,
        [MSG_ATTENDANCE_REJECT],
    )
    assert_result(
        evaluate_scholarship(**make(attendance_rate=75.0)),
        Status.MANUAL_REVIEW,
        [MSG_ATTENDANCE_REVIEW],
    )


def test_attendance_boundary_79_9_80_0_review_then_approved():
    """BV: fronteira 79.9/80.0 (limite superior da faixa de revisão manual)."""
    assert_result(
        evaluate_scholarship(**make(attendance_rate=79.9)),
        Status.MANUAL_REVIEW,
        [MSG_ATTENDANCE_REVIEW],
    )
    assert_result(
        evaluate_scholarship(**make(attendance_rate=80.0)),
        Status.APPROVED,
        [MSG_APPROVED],
    )


def test_attendance_manual_review_range():
    """EC: 75.0 <= attendance_rate < 80.0. DEC: branch `elif attendance_rate < 80.0` True."""
    for rate in (75.0, 77.5, 79.9):
        assert_result(
            evaluate_scholarship(**make(attendance_rate=rate)),
            Status.MANUAL_REVIEW,
            [MSG_ATTENDANCE_REVIEW],
        )


# ---------------------------------------------------------------------------
# 5. Cursos obrigatórios (Rule 4) e histórico disciplinar (Rule 5) - EC booleanas
# ---------------------------------------------------------------------------

def test_missing_required_courses_is_rejected():
    """EC: has_required_courses = False. DEC: branch `not has_required_courses` True."""
    result = evaluate_scholarship(**make(has_required_courses=False))
    assert_result(result, Status.REJECTED, [MSG_COURSES_REJECT])


def test_has_required_courses_true_does_not_reject():
    """EC: has_required_courses = True. DEC: branch `not has_required_courses` False."""
    result = evaluate_scholarship(**make(has_required_courses=True))
    assert_result(result, Status.APPROVED, [MSG_APPROVED])


def test_disciplinary_record_is_rejected():
    """EC: disciplinary_record = True. DEC: branch `if disciplinary_record` True."""
    result = evaluate_scholarship(**make(disciplinary_record=True))
    assert_result(result, Status.REJECTED, [MSG_DISCIPLINARY_REJECT])


def test_no_disciplinary_record_does_not_reject():
    """EC: disciplinary_record = False. DEC: branch `if disciplinary_record` False."""
    result = evaluate_scholarship(**make(disciplinary_record=False))
    assert_result(result, Status.APPROVED, [MSG_APPROVED])


# ---------------------------------------------------------------------------
# 6. Combinações / múltiplos motivos de rejeição (PATH) - reasons em ordem
# ---------------------------------------------------------------------------

def test_courses_and_disciplinary_combined_rejection():
    """PATH: duas regras booleanas disparando juntas, sem envolver idade/gpa/attendance.
    Verifica ORDEM dos motivos (Rule 4 antes de Rule 5)."""
    result = evaluate_scholarship(
        **make(has_required_courses=False, disciplinary_record=True)
    )
    assert_result(
        result, Status.REJECTED, [MSG_COURSES_REJECT, MSG_DISCIPLINARY_REJECT]
    )


def test_all_five_rules_trigger_rejection_in_declared_order():
    """PATH: as 5 regras disparam simultaneamente. Verifica que `reasons` contém
    exatamente as 5 mensagens, na ordem em que as regras aparecem no código
    (age, gpa, attendance, courses, disciplinary)."""
    result = evaluate_scholarship(
        age=15,
        gpa=5.0,
        attendance_rate=60.0,
        has_required_courses=False,
        disciplinary_record=True,
    )
    assert_result(
        result,
        Status.REJECTED,
        [
            MSG_AGE_REJECT,
            MSG_GPA_REJECT,
            MSG_ATTENDANCE_REJECT,
            MSG_COURSES_REJECT,
            MSG_DISCIPLINARY_REJECT,
        ],
    )


def test_review_reason_is_masked_when_a_rejection_also_occurs():
    """PATH crítico: idade cai na faixa de REVISÃO (17) mas o GPA causa REJEIÇÃO.
    O resultado final deve ser REJECTED e `reasons` deve conter APENAS o motivo
    de rejeição do GPA -- o motivo de revisão da idade é descartado pela regra
    final (`if rejection_reasons: return REJECTED(...)`), mesmo tendo sido
    computado internamente em `review_reasons`."""
    result = evaluate_scholarship(
        age=17,
        gpa=5.0,
        attendance_rate=90.0,
        has_required_courses=True,
        disciplinary_record=False,
    )
    assert_result(result, Status.REJECTED, [MSG_GPA_REJECT])


def test_manual_review_with_three_simultaneous_review_reasons():
    """PATH: as 3 regras de faixa (idade, gpa, attendance) caem em revisão manual
    ao mesmo tempo, sem nenhuma rejeição. Verifica ordem das 3 mensagens."""
    result = evaluate_scholarship(
        age=17,
        gpa=6.5,
        attendance_rate=77.0,
        has_required_courses=True,
        disciplinary_record=False,
    )
    assert_result(
        result,
        Status.MANUAL_REVIEW,
        [MSG_AGE_REVIEW, MSG_GPA_REVIEW, MSG_ATTENDANCE_REVIEW],
    )


def test_three_different_rejection_reason_combinations():
    """Garante >= 3 casos REJECTED motivados por regras DIFERENTES entre si
    (requisito mínimo do enunciado), reunidos em um único teste parametrizado
    manualmente para facilitar a leitura do relatório."""
    cases = [
        (make(age=10), [MSG_AGE_REJECT]),
        (make(gpa=3.0), [MSG_GPA_REJECT]),
        (make(attendance_rate=40.0), [MSG_ATTENDANCE_REJECT]),
    ]
    for params, expected_reasons in cases:
        assert_result(
            evaluate_scholarship(**params), Status.REJECTED, expected_reasons
        )


# ---------------------------------------------------------------------------
# 7. Validação de entrada (_validate_inputs) - entradas inválidas + fronteiras
# ---------------------------------------------------------------------------

def test_gpa_below_zero_raises_value_error():
    """Entrada inválida: gpa < 0.0. DEC: branch `gpa < 0.0` True em _validate_inputs.

    Usa comparação EXATA da mensagem (`str(exc) == ...`), e não
    `pytest.raises(match=...)`. `match` faz uma busca de regex (re.search),
    ou seja, aceita qualquer string que CONTENHA o texto esperado como
    substring -- um mutante que envolve a mensagem original com lixo (ex.:
    o operador de mutação de string do mutmut, que gera
    "XX<mensagem original>XX") passaria despercebido por `match`, mas é
    corretamente pego pela igualdade exata. Ver relatório, seção de
    mutantes sobreviventes (lacuna da suíte)."""
    with pytest.raises(ValueError) as exc_info:
        evaluate_scholarship(**make(gpa=-0.1))
    assert str(exc_info.value) == MSG_GPA_RANGE_ERROR


def test_gpa_above_ten_raises_value_error():
    """Entrada inválida: gpa > 10.0. DEC: branch `gpa > 10.0` True em _validate_inputs.
    Ver nota sobre comparação exata de mensagem em test_gpa_below_zero_raises_value_error."""
    with pytest.raises(ValueError) as exc_info:
        evaluate_scholarship(**make(gpa=10.1))
    assert str(exc_info.value) == MSG_GPA_RANGE_ERROR


def test_attendance_below_zero_raises_value_error():
    """Entrada inválida: attendance_rate < 0.0.
    Ver nota sobre comparação exata de mensagem em test_gpa_below_zero_raises_value_error."""
    with pytest.raises(ValueError) as exc_info:
        evaluate_scholarship(**make(attendance_rate=-0.1))
    assert str(exc_info.value) == MSG_ATTENDANCE_RANGE_ERROR


def test_attendance_above_hundred_raises_value_error():
    """Entrada inválida: attendance_rate > 100.0.
    Ver nota sobre comparação exata de mensagem em test_gpa_below_zero_raises_value_error."""
    with pytest.raises(ValueError) as exc_info:
        evaluate_scholarship(**make(attendance_rate=100.1))
    assert str(exc_info.value) == MSG_ATTENDANCE_RANGE_ERROR


def test_gpa_zero_and_ten_are_valid_boundaries():
    """BV: 0.0 e 10.0 são os extremos VÁLIDOS de gpa (não devem lançar exceção).
    DEC: branches `gpa < 0.0` e `gpa > 10.0` ambos False nesses extremos."""
    # gpa=0.0 é válido para _validate_inputs, mas ainda é < 6.0 -> REJECTED
    assert_result(
        evaluate_scholarship(**make(gpa=0.0)), Status.REJECTED, [MSG_GPA_REJECT]
    )
    # gpa=10.0 é válido e >= 7.0 -> não gera motivo de gpa
    assert_result(
        evaluate_scholarship(**make(gpa=10.0)), Status.APPROVED, [MSG_APPROVED]
    )


def test_attendance_zero_and_hundred_are_valid_boundaries():
    """BV: 0.0 e 100.0 são os extremos VÁLIDOS de attendance_rate (não lançam exceção)."""
    assert_result(
        evaluate_scholarship(**make(attendance_rate=0.0)),
        Status.REJECTED,
        [MSG_ATTENDANCE_REJECT],
    )
    assert_result(
        evaluate_scholarship(**make(attendance_rate=100.0)),
        Status.APPROVED,
        [MSG_APPROVED],
    )


# ---------------------------------------------------------------------------
# 8. Robustez do tipo de retorno
# ---------------------------------------------------------------------------
#
# NOTA (ver relatório, análise de mutantes): esta suíte verifica deliberadamente
# apenas o contrato observável descrito no enunciado -- status e reasons.
# Não testamos aqui se EvaluationResult é ou não mutável (não é um requisito
# funcional especificado). Essa decisão de escopo é o que torna a mutação
# manual `frozen=True -> frozen=False` um mutante EQUIVALENTE do ponto de
# vista desta suíte: nenhuma chamada a evaluate_scholarship(...) consegue
# distinguir as duas versões, porque nenhuma delas inspeciona mutabilidade.

def test_evaluation_result_fields_and_types():
    """Confirma o formato do objeto de retorno: `status` é um `Status` e
    `reasons` é uma lista de strings -- reforça o contrato observável da API."""
    result = evaluate_scholarship(**make())
    assert isinstance(result, EvaluationResult)
    assert isinstance(result.status, Status)
    assert isinstance(result.reasons, list)
    assert all(isinstance(reason, str) for reason in result.reasons)
