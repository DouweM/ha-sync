"""Tests for Pydantic models."""

from ha_sync.models import (
    Automation,
    HELPER_MODELS,
    InputBoolean,
    InputNumber,
    Scene,
    Script,
    View,
)


class TestScript:
    """Tests for Script model."""

    def test_basic_validation(self) -> None:
        """Test basic script validation."""
        data = {
            "id": "test_script",
            "alias": "Test Script",
            "sequence": [{"service": "light.turn_on"}],
        }
        script = Script.model_validate(data)
        assert script.id == "test_script"
        assert script.alias == "Test Script"
        assert script.sequence == [{"service": "light.turn_on"}]

    def test_field_order_preserved(self) -> None:
        """Test that model_dump preserves field order from model definition."""
        data = {
            "sequence": [{"service": "light.turn_on"}],
            "alias": "Test Script",
            "id": "test_script",
            "mode": "single",
        }
        script = Script.model_validate(data)
        dumped = script.model_dump(exclude_none=True)

        keys = list(dumped.keys())
        # Order should match model definition: id, alias, description, icon, mode, sequence
        assert keys.index("id") < keys.index("alias")
        assert keys.index("alias") < keys.index("mode")
        assert keys.index("mode") < keys.index("sequence")

    def test_extra_fields_preserved(self) -> None:
        """Test that extra fields not in model are preserved."""
        data = {
            "id": "test_script",
            "alias": "Test Script",
            "sequence": [],
            "custom_field": "custom_value",
            "use_blueprint": {"path": "test.yaml"},
        }
        script = Script.model_validate(data)
        dumped = script.model_dump(exclude_none=True)

        assert dumped["custom_field"] == "custom_value"
        assert dumped["use_blueprint"] == {"path": "test.yaml"}

    def test_exclude_none(self) -> None:
        """Test that None fields are excluded."""
        data = {"id": "test_script", "sequence": []}
        script = Script.model_validate(data)
        dumped = script.model_dump(exclude_none=True)

        assert "alias" not in dumped
        assert "description" not in dumped
        assert "icon" not in dumped

    def test_normalize_idempotent(self) -> None:
        """Test that normalizing twice gives same result."""
        data = {
            "sequence": [{"service": "light.turn_on"}],
            "id": "test_script",
            "alias": "Test",
        }
        first = Script.model_validate(data).model_dump(exclude_none=True)
        second = Script.model_validate(first).model_dump(exclude_none=True)
        assert first == second


class TestAutomation:
    """Tests for Automation model."""

    def test_basic_validation(self) -> None:
        """Test basic automation validation with plural fields."""
        data = {
            "id": "test_auto",
            "alias": "Test Automation",
            "triggers": [{"platform": "state"}],
            "actions": [{"service": "light.turn_on"}],
        }
        auto = Automation.model_validate(data)
        assert auto.id == "test_auto"
        assert auto.alias == "Test Automation"

    def test_field_order_preserved(self) -> None:
        """Test that field order matches model definition."""
        data = {
            "actions": [{"service": "light.turn_on"}],
            "triggers": [{"platform": "state"}],
            "alias": "Test",
            "id": "test_auto",
        }
        auto = Automation.model_validate(data)
        dumped = auto.model_dump(exclude_none=True)

        keys = list(dumped.keys())
        assert keys.index("id") < keys.index("alias")
        assert keys.index("triggers") < keys.index("actions")

    def test_normalize_singular_to_plural(self) -> None:
        """Test that singular field names are normalized to plural."""
        data = {
            "id": "test_auto",
            "alias": "Test",
            "trigger": [{"platform": "state"}],
            "condition": [{"condition": "state"}],
            "action": [{"service": "light.turn_on"}],
        }
        normalized = Automation.normalize(data)
        assert "triggers" in normalized
        assert "conditions" in normalized
        assert "actions" in normalized
        assert "trigger" not in normalized
        assert "condition" not in normalized
        assert "action" not in normalized

    def test_normalize_mixed_fields(self) -> None:
        """Test that when both singular and plural exist, plural takes precedence."""
        data = {
            "id": "test_auto",
            "alias": "Test",
            "trigger": [],  # Empty singular
            "triggers": [{"platform": "state"}],  # Non-empty plural
            "action": [],
            "actions": [{"service": "light.turn_on"}],
        }
        normalized = Automation.normalize(data)
        assert normalized["triggers"] == [{"platform": "state"}]
        assert normalized["actions"] == [{"service": "light.turn_on"}]
        assert "trigger" not in normalized
        assert "action" not in normalized


class TestScene:
    """Tests for Scene model."""

    def test_basic_validation(self) -> None:
        """Test basic scene validation."""
        data = {
            "id": "test_scene",
            "name": "Test Scene",
            "entities": {"light.living_room": {"state": "on"}},
        }
        scene = Scene.model_validate(data)
        assert scene.id == "test_scene"
        assert scene.name == "Test Scene"

    def test_field_order_preserved(self) -> None:
        """Test that field order matches model definition."""
        data = {
            "entities": {"light.test": {"state": "on"}},
            "name": "Test",
            "id": "test_scene",
        }
        scene = Scene.model_validate(data)
        dumped = scene.model_dump(exclude_none=True)

        keys = list(dumped.keys())
        assert keys.index("id") < keys.index("name")
        assert keys.index("name") < keys.index("entities")


class TestView:
    """Tests for View model."""

    def test_basic_validation(self) -> None:
        """Test basic view validation."""
        data = {
            "title": "Home",
            "path": "home",
            "cards": [{"type": "entities"}],
        }
        view = View.model_validate(data)
        assert view.title == "Home"
        assert view.path == "home"

    def test_position_field(self) -> None:
        """Test position field for ordering."""
        data = {
            "position": 1,
            "title": "Home",
            "cards": [],
        }
        view = View.model_validate(data)
        dumped = view.model_dump(exclude_none=True)

        keys = list(dumped.keys())
        # Position should be first
        assert keys[0] == "position"


class TestHelpers:
    """Tests for helper models."""

    def test_input_boolean(self) -> None:
        """Test InputBoolean model."""
        data = {"id": "test_bool", "name": "Test Boolean", "initial": True}
        helper = InputBoolean.model_validate(data)
        assert helper.id == "test_bool"
        assert helper.initial is True

    def test_input_number(self) -> None:
        """Test InputNumber model."""
        data = {
            "id": "test_num",
            "name": "Test Number",
            "min": 0,
            "max": 100,
            "step": 5,
        }
        helper = InputNumber.model_validate(data)
        assert helper.min == 0
        assert helper.max == 100
        assert helper.step == 5

    def test_helper_models_dict(self) -> None:
        """Test HELPER_MODELS contains all helper types."""
        assert "input_boolean" in HELPER_MODELS
        assert "input_number" in HELPER_MODELS
        assert "input_select" in HELPER_MODELS
        assert "input_text" in HELPER_MODELS
        assert "input_datetime" in HELPER_MODELS
        assert "input_button" in HELPER_MODELS


class TestNormalize:
    """Tests for the normalize() classmethod."""

    def test_normalize_basic(self) -> None:
        """Test basic normalize functionality."""
        data = {
            "id": "test",
            "alias": "Test",
            "sequence": [{"service": "light.turn_on"}],
        }
        normalized = Script.normalize(data)

        assert normalized["id"] == "test"
        assert normalized["alias"] == "Test"
        assert normalized["sequence"] == [{"service": "light.turn_on"}]

    def test_normalize_orders_keys(self) -> None:
        """Test that normalize orders keys according to model."""
        data = {
            "sequence": [{"service": "light.turn_on"}],
            "alias": "Test",
            "id": "test",
        }
        normalized = Script.normalize(data)

        keys = list(normalized.keys())
        assert keys.index("id") < keys.index("alias")
        assert keys.index("alias") < keys.index("sequence")

    def test_normalize_excludes_none(self) -> None:
        """Test that normalize excludes None values."""
        data = {"id": "test", "alias": None, "sequence": []}
        normalized = Script.normalize(data)

        assert "alias" not in normalized

    def test_normalize_preserves_extra_fields(self) -> None:
        """Test that normalize preserves extra fields."""
        data = {
            "id": "test",
            "sequence": [],
            "use_blueprint": {"path": "test.yaml"},
        }
        normalized = Script.normalize(data)

        assert normalized["use_blueprint"] == {"path": "test.yaml"}

    def test_normalize_is_idempotent(self) -> None:
        """Test that normalizing twice gives same result."""
        data = {"id": "test", "alias": "Test", "sequence": []}
        first = Script.normalize(data)
        second = Script.normalize(first)

        assert first == second

    def test_normalize_same_data_different_order_equal(self) -> None:
        """Test that same data in different order compares equal after normalize."""
        data1 = {
            "id": "test",
            "alias": "Test",
            "sequence": [{"service": "light.turn_on"}],
        }
        data2 = {
            "sequence": [{"service": "light.turn_on"}],
            "alias": "Test",
            "id": "test",
        }

        assert Script.normalize(data1) == Script.normalize(data2)

    def test_normalize_different_data_not_equal(self) -> None:
        """Test that different data compares not equal."""
        data1 = {"id": "test", "alias": "Test 1", "sequence": []}
        data2 = {"id": "test", "alias": "Test 2", "sequence": []}

        assert Script.normalize(data1) != Script.normalize(data2)

    def test_normalize_missing_optional_vs_none_equal(self) -> None:
        """Test that missing optional field vs None compares equal."""
        data1 = {"id": "test", "sequence": []}
        data2 = {"id": "test", "alias": None, "sequence": []}

        assert Script.normalize(data1) == Script.normalize(data2)
