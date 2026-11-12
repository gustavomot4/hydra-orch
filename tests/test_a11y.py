"""T21: hermetic WCAG AA accessibility contract and UI authority guard tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hydra_orch.core.preferences import (
    AccessibilitySettings,
    ColorTokenPair,
    ControlA11yDescriptor,
    UiCommandEnvelope,
    assert_ui_command_authorized,
    contrast_ratio,
    relative_luminance,
    validate_a11y_contract,
)
from hydra_orch.model import ContractViolation


def _valid_controls() -> tuple[ControlA11yDescriptor, ...]:
    return (
        ControlA11yDescriptor(
            control_id="btn-submit",
            role="button",
            label="Submit run",
            keyboard_accessible=True,
            tab_index=0,
            focus_visible=True,
        ),
        ControlA11yDescriptor(
            control_id="run-status",
            role="status",
            label="Run execution status",
            keyboard_accessible=True,
            tab_index=0,
            focus_visible=True,
            has_status_indicator=True,
            status_text="Accepted after checks",
        ),
        ControlA11yDescriptor(
            control_id="timeline-drawer",
            role="region",
            label="Event timeline",
            keyboard_accessible=True,
            tab_index=0,
            focus_visible=True,
            animated=True,
            respects_reduce_motion=True,
        ),
    )


@pytest.mark.a11y
def test_keyboard_navigation():
    checklist = validate_a11y_contract(AccessibilitySettings(controls=_valid_controls()))
    assert checklist.passed is True

    with pytest.raises(ContractViolation) as disabled_exc:
        validate_a11y_contract(AccessibilitySettings(keyboard_navigation=False))
    assert disabled_exc.value.code == "a11y_contract_violation"

    unreachable = ControlA11yDescriptor(
        control_id="mouse-only",
        role="button",
        label="Mouse only action",
        keyboard_accessible=False,
        focus_visible=True,
    )
    report = validate_a11y_contract(
        AccessibilitySettings(controls=(unreachable,)),
        raise_on_failure=False,
    )
    assert report.passed is False
    assert any(item.criterion == "keyboard_navigation" and not item.passed for item in report.items)


@pytest.mark.a11y
def test_focus_visible():
    checklist = validate_a11y_contract(
        AccessibilitySettings(focus_visible=True, focus_outline_px=2, controls=_valid_controls())
    )
    assert checklist.passed is True

    for bad_settings in (
        AccessibilitySettings(focus_visible=False),
        AccessibilitySettings(focus_visible=True, focus_outline_px=0),
        AccessibilitySettings(
            controls=(
                ControlA11yDescriptor(
                    control_id="no-focus-ring",
                    role="button",
                    label="No focus ring",
                    focus_visible=False,
                ),
            )
        ),
    ):
        with pytest.raises(ContractViolation) as exc_info:
            validate_a11y_contract(bad_settings)
        assert exc_info.value.code == "a11y_contract_violation"


@pytest.mark.a11y
def test_semantic_roles():
    checklist = validate_a11y_contract(AccessibilitySettings(semantic_roles=True, controls=_valid_controls()))
    assert checklist.passed is True

    with pytest.raises(ContractViolation):
        validate_a11y_contract(AccessibilitySettings(semantic_roles=False))

    invalid_role_ctrl = ControlA11yDescriptor(
        control_id="raw-div",
        role="clickable-div",
        label="Raw container",
    )
    report = validate_a11y_contract(
        AccessibilitySettings(controls=(invalid_role_ctrl,)),
        raise_on_failure=False,
    )
    assert report.passed is False
    assert any(item.criterion == "semantic_roles" and not item.passed for item in report.items)

    with pytest.raises(ValidationError):
        ControlA11yDescriptor(control_id="blank-label", role="button", label="   ")

    # Color-only status without textual label also fails
    color_only = ControlA11yDescriptor(
        control_id="dot-status",
        role="status",
        label="Task status",
        has_status_indicator=True,
        status_text="",
    )
    status_report = validate_a11y_contract(
        AccessibilitySettings(controls=(color_only,)),
        raise_on_failure=False,
    )
    assert status_report.passed is False
    assert any(item.criterion == "textual_status_labels" and not item.passed for item in status_report.items)


@pytest.mark.a11y
def test_contrast_wcag_aa():
    assert relative_luminance("#000000") == pytest.approx(0.0)
    assert relative_luminance("#ffffff") == pytest.approx(1.0)
    assert contrast_ratio("#ffffff", "#000000") == pytest.approx(21.0)
    assert contrast_ratio("#000000", "#000000") == pytest.approx(1.0)
    assert contrast_ratio("#fff", "#000") == pytest.approx(21.0)

    # Default proposed Hydra dark tokens pass WCAG AA
    default_report = validate_a11y_contract(AccessibilitySettings())
    assert default_report.passed is True
    assert default_report.contrast_results["primary_text"] >= 4.5
    assert default_report.contrast_results["secondary_text"] >= 4.5
    assert default_report.contrast_results["large_heading"] >= 3.0
    assert default_report.contrast_results["focus_ring"] >= 3.0

    # ~3.57:1 fails normal_text (>= 4.5:1) but passes large_text (>= 3.0:1)
    mid_gray_normal = ColorTokenPair(name="mid_normal", foreground="#777777", background="#202020", kind="normal_text")
    mid_gray_large = ColorTokenPair(name="mid_large", foreground="#777777", background="#202020", kind="large_text")
    assert 3.0 <= mid_gray_normal.ratio < 4.5
    assert mid_gray_normal.passes_wcag_aa is False
    assert mid_gray_large.passes_wcag_aa is True

    with pytest.raises(ContractViolation) as low_contrast_exc:
        validate_a11y_contract(AccessibilitySettings(color_pairs=(mid_gray_normal,)))
    assert low_contrast_exc.value.code == "a11y_contract_violation"

    assert validate_a11y_contract(AccessibilitySettings(color_pairs=(mid_gray_large,))).passed is True

    # Below 3.0:1 fails even for UI components
    low_ui = ColorTokenPair(name="low_border", foreground="#3b3b3b", background="#141414", kind="ui_component")
    assert low_ui.ratio < 3.0
    with pytest.raises(ContractViolation):
        validate_a11y_contract(AccessibilitySettings(color_pairs=(low_ui,)))

    with pytest.raises(ValueError):
        contrast_ratio("not-a-hex", "#000000")


@pytest.mark.a11y
def test_reduce_motion():
    reduced = validate_a11y_contract(
        AccessibilitySettings(reduce_motion=True, respects_prefers_reduced_motion=True, controls=_valid_controls())
    )
    assert reduced.passed is True
    assert reduced.reduce_motion_active is True
    assert reduced.effective_animation_ms == 0

    normal = validate_a11y_contract(AccessibilitySettings(reduce_motion=False, controls=_valid_controls()))
    assert normal.effective_animation_ms > 0

    stubborn_control = ControlA11yDescriptor(
        control_id="spinner",
        role="progressbar",
        label="Loading",
        animated=True,
        respects_reduce_motion=False,
    )
    with pytest.raises(ContractViolation) as exc_info:
        validate_a11y_contract(AccessibilitySettings(reduce_motion=True, controls=(stubborn_control,)))
    assert exc_info.value.code == "a11y_contract_violation"

    with pytest.raises(ContractViolation):
        validate_a11y_contract(AccessibilitySettings(reduce_motion=True, respects_prefers_reduced_motion=False))


@pytest.mark.a11y
@pytest.mark.negative
def test_ui_cannot_accept_task_without_versioned_command():
    with pytest.raises(ContractViolation) as missing_exc:
        assert_ui_command_authorized(None, action="accept_task")
    assert missing_exc.value.code == "ui_command_required"

    # Raw UI state flag without versioned command envelope is blocked
    with pytest.raises(ContractViolation) as raw_exc:
        assert_ui_command_authorized({"task_status": "accepted"}, action="accept_task")
    assert raw_exc.value.code == "ui_command_invalid"

    # Missing expected_revision or review evidence is blocked
    with pytest.raises(ContractViolation) as no_rev_exc:
        assert_ui_command_authorized(
            UiCommandEnvelope(
                command_id="cmd-ui-001",
                command_version="1.0",
                action="accept_task",
                actor="operator",
                idempotency_key="ui-accept-key-0001",
                payload={"result_id": "res-1", "reason": "Looks good"},
            ),
            action="accept_task",
        )
    assert no_rev_exc.value.code == "ui_command_invalid"

    # Actor mismatch blocked
    valid = UiCommandEnvelope(
        command_id="cmd-ui-002",
        command_version="1.0",
        action="accept_task",
        actor="operator",
        idempotency_key="ui-accept-key-0002",
        expected_revision=1,
        payload={"result_id": "res-1", "reason": "All checks passed"},
    )
    with pytest.raises(ContractViolation) as auth_exc:
        assert_ui_command_authorized(valid, action="accept_task", authenticated_actor="other-user")
    assert auth_exc.value.code == "authorization_denied"

    # Properly versioned and authenticated UI command succeeds
    authorized = assert_ui_command_authorized(valid, action="accept_task", authenticated_actor="operator")
    assert authorized == valid
