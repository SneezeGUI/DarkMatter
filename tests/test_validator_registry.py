import pytest
import threading
from core.validators import ValidatorRegistry, DEFAULT_VALIDATORS, HttpBinValidator, IpApiValidator, Validator, ValidatorType

class TestValidatorRegistry:
    
    def setup_method(self):
        # Save state to restore after test
        self.original_validators = ValidatorRegistry._validators.copy()
        self.original_enabled = ValidatorRegistry._enabled.copy()
        
    def teardown_method(self):
        # Restore state
        ValidatorRegistry._validators = self.original_validators
        ValidatorRegistry._enabled = self.original_enabled

    def test_singleton(self):
        """Ensure only one instance exists."""
        r1 = ValidatorRegistry()
        r2 = ValidatorRegistry()
        assert r1 is r2

    def test_registration_flow(self):
        """Test registering and unregistering validators."""
        class MockValidator(Validator):
            def __init__(self):
                super().__init__("mock", "http://mock", ValidatorType.HEADERS)
                
        ValidatorRegistry.register("mock", MockValidator)
        assert ValidatorRegistry.get("mock") == MockValidator
        
        validators_list = ValidatorRegistry.list_validators()
        names = [v["name"] for v in validators_list]
        assert "mock" in names
        
        ValidatorRegistry.unregister("mock")
        assert ValidatorRegistry.get("mock") is None

    def test_enable_disable(self):
        """Test enabling and disabling validators."""
        name = "httpbin.org" # Use an existing one
        
        # Ensure it starts enabled (as per auto-register)
        ValidatorRegistry.enable(name)
        assert ValidatorRegistry.is_enabled(name)
        
        ValidatorRegistry.disable(name)
        assert not ValidatorRegistry.is_enabled(name)
        assert HttpBinValidator not in ValidatorRegistry.get_enabled()
        
        ValidatorRegistry.enable(name)
        assert ValidatorRegistry.is_enabled(name)
        assert HttpBinValidator in ValidatorRegistry.get_enabled()

    def test_get_all_vs_get_enabled(self):
        """Test filtering of enabled validators."""
        # Ensure at least two are present
        ValidatorRegistry.register("v1", HttpBinValidator, enabled=True)
        ValidatorRegistry.register("v2", IpApiValidator, enabled=False)
        
        all_vals = ValidatorRegistry.get_all()
        enabled_vals = ValidatorRegistry.get_enabled()
        
        assert HttpBinValidator in all_vals
        assert IpApiValidator in all_vals
        
        # Since we just registered v2 as disabled, checking if it is in enabled_vals
        # Note: IpApiValidator might be registered under its original name "ip-api.com" as enabled.
        # "v2" maps to IpApiValidator class.
        # get_enabled returns list of CLASSES.
        # If IpApiValidator is registered twice (once enabled, once disabled), it will appear in get_enabled() 
        # if the enabled one is processed.
        
        # Let's be more specific with a unique class to avoid ambiguity
        class DisabledMock(Validator): pass
        ValidatorRegistry.register("disabled_mock", DisabledMock, enabled=False)
        
        assert DisabledMock in ValidatorRegistry.get_all()
        assert DisabledMock not in ValidatorRegistry.get_enabled()

    def test_thread_safety(self):
        """Test concurrent registration."""
        errors = []
        def register_loop():
            try:
                for i in range(100):
                    name = f"thread_val_{threading.get_ident()}_{i}"
                    ValidatorRegistry.register(name, HttpBinValidator)
            except Exception as e:
                errors.append(e)
                
        threads = [threading.Thread(target=register_loop) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
            
        assert len(errors) == 0
        # Verify a random one exists
        # We can't easily predict exact names without capturing thread IDs, 
        # but we can check count increased significantly
        assert len(ValidatorRegistry.get_all()) >= 100

    def test_backward_compatibility(self):
        """Test that DEFAULT_VALIDATORS works as expected."""
        # DEFAULT_VALIDATORS is computed at import time, so it reflects the initial state
        assert len(DEFAULT_VALIDATORS) > 0
        assert isinstance(DEFAULT_VALIDATORS[0], Validator)
        
        # Check specific known validator
        httpbin = next((v for v in DEFAULT_VALIDATORS if v.name == "httpbin.org"), None)
        assert httpbin is not None
        assert isinstance(httpbin, HttpBinValidator)
