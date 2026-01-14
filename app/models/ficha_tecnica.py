from datetime import datetime
from app.extensions import db


class FichaTecnica(db.Model):
    __tablename__ = 'ficha_tecnica'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    source_filename = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Header fields
    proforma_invoice = db.Column(db.String(255))
    number_pi_order = db.Column(db.String(255))
    supplier_no = db.Column(db.String(255))
    buyer_importer = db.Column(db.String(255))
    manufacturer_exporter = db.Column(db.String(255))
    order_information = db.Column(db.String(255))
    name_company = db.Column(db.String(255))
    adress = db.Column(db.String(500))
    city = db.Column(db.String(255))
    state_province = db.Column(db.String(255))
    country = db.Column(db.String(255))
    tel_fax = db.Column(db.String(255))
    contact_name = db.Column(db.String(255))
    e_mail = db.Column(db.String(255))
    order_date = db.Column(db.String(255))
    production_time = db.Column(db.String(255))
    shipment_date = db.Column(db.String(255))
    terms_of_payment = db.Column(db.String(255))
    incoterm = db.Column(db.String(255))
    shipment_port = db.Column(db.String(255))
    destination_port = db.Column(db.String(255))
    bank_information = db.Column(db.String(255))
    beneficiary = db.Column(db.String(255))
    beneficiary_adress = db.Column(db.String(500))
    advising_bank = db.Column(db.String(255))
    swift_code = db.Column(db.String(255))
    bank_adress = db.Column(db.String(500))
    account = db.Column(db.String(255))
    packing_information = db.Column(db.String(255))
    total_of_package_s = db.Column(db.String(255))
    type_of_package = db.Column(db.String(255))
    dimensions_of_pack = db.Column(db.String(255))
    total_gross_weight = db.Column(db.String(255))
    total_net_weight = db.Column(db.String(255))
    total_cbm = db.Column(db.String(255))
    information_oaz_comercial_ltda = db.Column(db.String(255))

    header_raw = db.Column(db.Text)
    columns_meta = db.Column(db.Text)

    items = db.relationship(
        'FichaTecnicaItem',
        backref='ficha',
        lazy=True,
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        db.UniqueConstraint('number_pi_order', name='uq_ficha_tecnica_pi_order'),
    )


class FichaTecnicaItem(db.Model):
    __tablename__ = 'ficha_tecnica_item'

    id = db.Column(db.Integer, primary_key=True)
    ficha_id = db.Column(db.Integer, db.ForeignKey('ficha_tecnica.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    img_ref = db.Column(db.String(255))
    item_no_ref_supplier = db.Column(db.String(255))
    material_composition_percentage = db.Column(db.String(255))
    color = db.Column(db.String(255))
    description_item = db.Column(db.String(500))
    ncm = db.Column(db.String(255))
    changes_by_oaz = db.Column(db.String(255))
    oaz_reference = db.Column(db.String(255))
    care_instructions = db.Column(db.String(500))
    label = db.Column(db.String(255))
    length_cm = db.Column(db.Float)
    width_cm = db.Column(db.Float)
    height_cm = db.Column(db.Float)
    diameter_cm = db.Column(db.Float)
    unit_net_weight_kg = db.Column(db.Float)
    moq = db.Column(db.Float)
    oaz_qty = db.Column(db.Float)
    inner_packing_pcs = db.Column(db.Float)
    outer_packing_pcs = db.Column(db.Float)
    cbm = db.Column(db.Float)
    packing = db.Column(db.String(255))
    unit_price = db.Column(db.Float)
    total_amount = db.Column(db.Float)
    preco_r = db.Column(db.Float)
    atacado = db.Column(db.Float)
    familia = db.Column(db.String(255))
    entrada = db.Column(db.String(255))
    linha = db.Column(db.String(255))
    grupo = db.Column(db.String(255))
    sub_grupo = db.Column(db.String(255))
    nome_desc_produto = db.Column(db.String(500))
    cor_sistema = db.Column(db.String(255))
    material_obs_ns = db.Column(db.String(500))
    obs = db.Column(db.String(500))
    pp_samples_qty = db.Column(db.Float)
    repeat_recompra = db.Column(db.String(255))

    raw_row = db.Column(db.Text)

    __table_args__ = (
        db.UniqueConstraint(
            'ficha_id',
            'item_no_ref_supplier',
            'oaz_reference',
            name='uq_ficha_item_key',
        ),
        db.Index('ix_ficha_item_item_no', 'item_no_ref_supplier'),
        db.Index('ix_ficha_item_grupo', 'grupo'),
        db.Index('ix_ficha_item_linha', 'linha'),
        db.Index('ix_ficha_item_cor', 'cor_sistema'),
    )
