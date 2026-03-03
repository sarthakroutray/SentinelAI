from app.services import rule_engine


def test_rule_engine_high_for_error_level():
    result = rule_engine.evaluate(
        log_level="ERROR",
        message="normal message",
        ip_address="1.1.1.1",
    )

    assert result is not None
    assert result.severity == "HIGH"
    assert result.reason == "Log level is ERROR"


def test_rule_engine_high_for_failed_login_keyword():
    result = rule_engine.evaluate(
        log_level="INFO",
        message="User had a failed login from portal",
        ip_address="1.1.1.2",
    )

    assert result is not None
    assert result.severity == "HIGH"
    assert "failed login" in result.reason.lower()


def test_rule_engine_high_for_unauthorized_keyword():
    result = rule_engine.evaluate(
        log_level="INFO",
        message="Unauthorized endpoint hit",
        ip_address="1.1.1.3",
    )

    assert result is not None
    assert result.severity == "HIGH"
    assert "unauthorized" in result.reason.lower()


def test_rule_engine_medium_for_ip_burst():
    ip = "2.2.2.2"
    result = None

    for i in range(6):
        result = rule_engine.evaluate(
            log_level="INFO",
            message=f"event {i}",
            ip_address=ip,
        )

    assert result is not None
    assert result.severity == "MEDIUM"
    assert ip in result.reason


def test_rule_engine_no_alert_case():
    result = rule_engine.evaluate(
        log_level="INFO",
        message="Routine system status update",
        ip_address="3.3.3.3",
    )

    assert result is None
