import json


def normalize_wsid(x) -> str:
    """Normalize a Fluxogama WSID to a clean string.
    - None / '' → ''
    - "None" (str) → ''
    - "14.0" (Excel float) → "14"
    - strips whitespace
    """
    s = str(x or '').strip()
    if not s or s == 'None':
        return ''
    try:
        if '.' in s:
            s = str(int(float(s)))
    except (ValueError, TypeError):
        pass
    return s


def convert_value_to_string(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def get_or_create_supplier(supplier_name, user_id, db_session=None):
    from app.extensions import db
    from app.models import Supplier
    
    if not supplier_name or supplier_name.strip() == "":
        return None

    if db_session is None:
        db_session = db.session

    supplier_name = supplier_name.strip()

    try:
        existing_supplier = db_session.query(Supplier).filter(
            db.func.lower(Supplier.name) == supplier_name.lower(),
            Supplier.user_id == user_id).first()

        if existing_supplier:
            print(f"✓ Fornecedor encontrado: {existing_supplier.name} (ID: {existing_supplier.id})")
            return existing_supplier

        import random
        colors = [
            '#667eea', '#f093fb', '#4facfe', '#43e97b', '#fa709a', '#fee140',
            '#30cfd0', '#a8edea'
        ]
        new_supplier = Supplier(
            user_id=user_id,
            name=supplier_name,
            avatar_color=random.choice(colors)
        )
        db_session.add(new_supplier)
        db_session.commit()

        print(f"✨ Novo fornecedor criado: {new_supplier.name} (ID: {new_supplier.id})")
        return new_supplier

    except Exception as e:
        print(f"⚠️ Erro ao buscar/criar fornecedor: {e}")
        db_session.rollback()
        return None
