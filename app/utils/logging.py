import json
import time
from flask import session, request

RPA_MONITOR_ENABLED = False
rpa_log = None


def init_rpa_monitor(rpa_id, host, port, region, transport):
    global RPA_MONITOR_ENABLED, rpa_log
    try:
        from rpa_monitor_client import setup_rpa_monitor, rpa_log as _rpa_log
        setup_rpa_monitor(
            rpa_id=rpa_id,
            host=host,
            port=port,
            region=region,
            transport=transport,
        )
        rpa_log = _rpa_log
        RPA_MONITOR_ENABLED = True
        print(f"RPA Monitor connected: {rpa_id} -> {host}")
        return True
    except ImportError:
        print("WARNING: rpa_monitor_client not installed, monitoring disabled")
        return False
    except Exception as e:
        print(f"RPA Monitor initialization failed: {e}")
        return False


def rpa_info(message, regiao="sistema"):
    if RPA_MONITOR_ENABLED and rpa_log:
        try:
            rpa_log.info(message)
        except Exception as e:
            print(f"RPA log error: {e}")


def rpa_warn(message, regiao="sistema"):
    if RPA_MONITOR_ENABLED and rpa_log:
        try:
            rpa_log.warn(message)
        except Exception as e:
            print(f"RPA log error: {e}")


def rpa_error(message, exc=None, regiao="sistema", take_screenshot=True):
    if RPA_MONITOR_ENABLED and rpa_log:
        try:
            rpa_log.error(message, exc=exc, regiao=regiao)
            if take_screenshot:
                agora = time.time()
                rpa_log.screenshot(
                    filename=f"error_{int(agora)}.png",
                    regiao=regiao,
                )
        except Exception as e:
            print(f"RPA log error: {e}")


def log_activity(action, target_type=None, target_id=None, target_name=None, metadata=None, user_id=None, username=None):
    from app.extensions import db
    from app.models import User, ActivityLog
    
    try:
        if user_id is None and 'user_id' in session:
            user_id = session.get('user_id')
            user = User.query.get(user_id)
            username = user.username if user else None
        
        ip_address = request.remote_addr if request else None
        user_agent = request.headers.get('User-Agent', '')[:500] if request else None
        
        activity = ActivityLog(
            user_id=user_id,
            username=username,
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_json=json.dumps(metadata) if metadata else None
        )
        db.session.add(activity)
        db.session.commit()
    except Exception as e:
        print(f"Error logging activity: {e}")
        db.session.rollback()
